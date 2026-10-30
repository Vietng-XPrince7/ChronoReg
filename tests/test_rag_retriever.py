"""Kiểm thử logic chọn phiên bản và truy xuất của RAG (không cần ChromaDB/model thật)."""
import json
import re
import tempfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.rag import embedder, retriever, store
from src.rag.chunker import load_chunks
from src.rag.versioning import plan_version

CFG = {"top_k": 3, "embedding_model": "fake"}


def _rec(doc, ay, verified, topic, text, cands=None):
    return {
        "chunk_id": f"{doc}:0", "doc_id": doc, "text": text, "topic_hint": topic,
        "academic_year_verified": ay if verified else None,
        "academic_year_candidates": cands if cands is not None else ([ay] if ay else []),
        "review_status": "verified_against_source" if verified else "unreviewed",
        "scope": None, "effective_from": None, "effective_until_exclusive": None,
        "start_char": 0, "end_char": len(text), "policy_qa_ready": verified,
    }


RECORDS = [
    _rec("hp-2022", "2022-2023", False, "tuition", "Định mức học phí đào tạo đại học năm học 2022-2023"),
    _rec("hp-2023", "2023-2024", True, "tuition", "Định mức học phí đào tạo đại học năm học 2023-2024"),
    _rec("hp-2024", "2024-2025", True, "tuition", "Định mức học phí đào tạo đại học năm học 2024-2025"),
    _rec("hb-2023", "2023-2024", True, "scholarship", "Định mức học bổng khuyến khích học tập"),
    _rec("nc-2022", "2022-2023", False, "research", "Hoạt động nghiên cứu khoa học của sinh viên"),
    _rec("hp-mo-ho", None, False, "tuition", "Học phí chương trình đặc biệt chưa rõ năm học",
         cands=["2022-2023", "2023-2024"]),
]


def _vec(text):
    # crc32 (không dùng hash() của Python vì nó đổi giá trị giữa các lần chạy -> test chập chờn)
    v = [0.0] * 512
    for w in re.findall(r"\w+", text.lower()):
        v[zlib.crc32(w.encode("utf-8")) % 512] += 1.0
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n else v


def _match(meta, cond):
    if "$and" in cond:
        return all(_match(meta, c) for c in cond["$and"])
    return all(meta[k] == v for k, v in cond.items())


class FakeCollection:
    def __init__(self):
        self.rows = []

    def upsert(self, ids, documents, embeddings, metadatas):
        self.rows += list(zip(ids, documents, embeddings, metadatas))

    def query(self, query_embeddings, n_results, where=None):
        q = query_embeddings[0]
        rows = [r for r in self.rows if not where or _match(r[3], where)]
        dist = lambda r: 1 - sum(a * b for a, b in zip(q, r[2]))
        rows = sorted(rows, key=dist)[:n_results]
        return {"documents": [[r[1] for r in rows]], "metadatas": [[r[3] for r in rows]],
                "distances": [[dist(r) for r in rows]]}

    def get(self, include=None):
        return {"metadatas": [r[3] for r in self.rows]}


@contextmanager
def fake_index():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "chunks.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in RECORDS), encoding="utf-8")
        col = FakeCollection()
        for c in load_chunks(path):
            col.upsert([c.id], [c.document], [_vec(c.text)], [c.metadata])
        with patch.object(embedder, "embed", lambda cfg, texts: [_vec(t) for t in texts]), \
                patch.object(store, "get_collection", lambda cfg, reset=False: col):
            yield


def _search(question, as_of_year=None):
    plan = plan_version(question, as_of_year)
    hits, plan = retriever.retrieve(question, plan, CFG)
    return hits, plan


def test_plan_version_cases():
    assert plan_version("Học phí năm học 2023-2024?").start_year == 2023
    assert plan_version("Học phí năm 2023?").start_year == 2023        # mặc định: năm học bắt đầu
    assert plan_version("Học phí năm 2023?", None, "end").start_year == 2022
    assert plan_version("Học phí?", as_of_year=2024).start_year == 2024
    assert plan_version("Quy định cũ về học phí?").mode == "all"
    assert plan_version("Học phí hiện nay?").mode == "latest"
    # năm nêu trong câu hỏi ưu tiên hơn as_of_year
    assert plan_version("Học phí năm học 2022-2023?", as_of_year=2024).start_year == 2022
    # "khóa 2022" là khóa tuyển sinh, không phải năm của quy định
    assert plan_version("Học phí khóa 2022 là bao nhiêu?").mode == "latest"


def test_year_filter_returns_only_that_academic_year():
    with fake_index():
        hits, plan = _search("Định mức học phí năm học 2023-2024")
    assert plan.mode == "year" and hits
    assert {h["metadata"]["start_year"] for h in hits} == {2023}


def test_chunks_with_unknown_year_are_never_returned_by_year_filter():
    with fake_index():
        for y in (2022, 2023):
            hits, _ = _search(f"Học phí chương trình đặc biệt năm học {y}-{y + 1}")
            assert all(h["metadata"]["doc_id"] != "hp-mo-ho" for h in hits)


def test_latest_picks_newest_year_of_the_topic():
    with fake_index():
        hits, plan = _search("Định mức học phí đào tạo đại học hiện nay")
        assert plan.start_year == 2024
        assert {h["metadata"]["doc_id"] for h in hits} == {"hp-2024"}
        # chủ đề chỉ có một năm học: lấy năm đó, không bị ép sang năm mới nhất toàn cục
        hits, plan = _search("Hoạt động nghiên cứu khoa học của sinh viên")
        assert plan.start_year == 2022
        assert {h["metadata"]["doc_id"] for h in hits} == {"nc-2022"}


def test_old_rule_question_returns_several_academic_years():
    with fake_index():
        hits, plan = _search("Quy định cũ về định mức học phí đào tạo đại học")
    assert plan.mode == "all"
    assert len({h["metadata"]["start_year"] for h in hits}) >= 2