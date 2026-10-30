"""Kiểm thử chunk theo Điều (kết hợp với chunk theo ký tự của Việt)."""
import json
import tempfile
from pathlib import Path

from src.rag.chunker import (load_chunks, match_chuong, match_dieu, match_phuluc,
                             split_articles, summarize)

QUY_DINH = """ĐẠI HỌC QUỐC GIA HÀ NỘI

# **QUY ĐỊNH VỀ NỘP HỌC PHÍ**

# **CHƯƠNG I – QUY ĐỊNH CHUNG**

# **Điều 1. Phạm vi áp dụng**

Quy định này áp dụng cho sinh viên.

# **Điều 2. Mức thu**

Mức thu theo quy định của ĐHQGHN, xem thêm theo Điều 5 của Quy chế.
Điều 5 của Quy chế quy định rõ hơn về việc này.

# **CHƯƠNG II – THỰC HIỆN**

# **Điều 3. Thời hạn nộp**

Nộp trước ngày 15 hằng tháng.

**Điều 4.** Thi hành kể từ ngày ký.

# **PHỤ LỤC 01**

| Bậc | Mức |
|---|---|
| Đại học | 1.000 |
"""

BANG = "# Kế hoạch học tập\n\n| Tuần | Nội dung |\n|---|---|\n| 1 | Nhập học |\n"


def _rec(doc, idx, text, verified=True, ay="2025-2026"):
    return {
        "chunk_id": f"{doc}:{idx}", "doc_id": doc, "text": text, "topic_hint": "tuition",
        "academic_year_verified": ay if verified else None,
        "academic_year_candidates": [ay], "review_status": "verified_against_source" if verified else "unreviewed",
        "scope": "Phạm vi thử", "effective_from": None, "effective_until_exclusive": None,
        "start_char": idx * 100, "end_char": idx * 100 + 99, "policy_qa_ready": verified,
    }


class Env:
    """Thư mục tạm giả lập repo: file .md gốc, documents.jsonl và file chunk của Việt."""

    def __init__(self, docs: dict, records: list):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "md").mkdir()
        rows = []
        for doc_id, text in docs.items():
            if text is not None:
                (self.root / "md" / f"{doc_id}.md").write_text(text, encoding="utf-8")
            rows.append({"doc_id": doc_id, "source_path": f"md/{doc_id}.md"})
        self.documents = self.root / "documents.jsonl"
        self.documents.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        self.chunks = self.root / "chunks.jsonl"
        self.chunks.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")

    def load(self, **kw):
        return load_chunks(self.chunks, documents_file=self.documents, source_root=self.root, **kw)


def test_heading_detection():
    assert match_dieu("# **Điều 7. Các quy định khác**") == ("7", "Các quy định khác")
    assert match_dieu("## Điều 15 — Điều kiện xét tốt nghiệp") == ("15", "Điều kiện xét tốt nghiệp")
    assert match_dieu("**Điều 1.** Phê duyệt định mức")[0] == "1"
    assert match_dieu("Điều 2: Hiệu lực")[0] == "2"
    assert match_dieu("ĐIỀU 3. THI HÀNH")[0] == "3"
    # không phải tiêu đề: nhắc tới Điều giữa câu, hoặc đầu dòng nhưng không có dấu hiệu tiêu đề
    assert match_dieu("Mức thu theo Điều 5 của Quy chế") is None
    assert match_dieu("Điều 5 của Quy chế quy định rõ hơn") is None
    assert match_dieu("| Điều 3 | nội dung |") is None
    assert match_chuong("# **CHƯƠNG III – ĐIỀU KHOẢN THI HÀNH**") == "Chương III - ĐIỀU KHOẢN THI HÀNH"
    assert match_chuong("Chương trình đào tạo chuẩn") is None
    assert match_phuluc("# **PHỤ LỤC 01**") == "Phụ lục 01"
    assert match_phuluc("Phụ lục kèm theo quyết định") is None


def test_split_articles_structure():
    secs = split_articles(QUY_DINH)
    assert [s["dieu_so"] for s in secs] == ["", "Điều 1", "Điều 2", "Điều 3", "Điều 4", "Phụ lục 01"]
    by = {s["dieu_so"]: s for s in secs}
    assert "ĐẠI HỌC QUỐC GIA" in by[""]["content"]
    assert by["Điều 1"]["chuong"] == "Chương I - QUY ĐỊNH CHUNG"
    assert by["Điều 3"]["chuong"] == "Chương II - THỰC HIỆN"
    assert all("CHƯƠNG" not in s["content"] for s in secs)         # dòng Chương không lọt vào nội dung
    assert "Điều 5 của Quy chế quy định" in by["Điều 2"]["content"]   # nhắc Điều giữa văn bản không cắt đôi
    assert "| Đại học | 1.000 |" in by["Phụ lục 01"]["content"]


def test_hybrid_article_and_span():
    env = Env({"qd": QUY_DINH, "bang": BANG},
              [_rec("qd", 0, "x"), _rec("qd", 1, "y"), _rec("bang", 0, BANG, verified=False)])
    chunks = env.load()
    art = [c for c in chunks if c.metadata["doc_id"] == "qd"]
    assert len(art) == 6 and all(c.metadata["chunking"] == "article" for c in art)
    assert {c.metadata["dieu_so"] for c in art} >= {"Điều 1", "Điều 4", "Phụ lục 01"}
    # năm học và trạng thái duyệt lấy từ chunk của Việt
    assert all(c.metadata["start_year"] == 2025 and c.metadata["year_status"] == "verified" for c in art)
    d3 = next(c for c in art if c.metadata["dieu_so"] == "Điều 3")
    assert "Điều 3" in d3.text and "Chương II" in d3.text and "Năm học 2025-2026" in d3.text
    # văn bản không có Điều: giữ nguyên chunk của Việt
    span = [c for c in chunks if c.metadata["doc_id"] == "bang"]
    assert len(span) == 1 and span[0].id == "bang:0" and span[0].metadata["chunking"] == "span"
    assert span[0].metadata["year_status"] == "candidate"
    s = summarize(chunks)
    assert s["article"] == {"documents": 1, "chunks": 6} and s["span"] == {"documents": 1, "chunks": 1}


def test_too_few_articles_or_missing_file_fall_back_to_span():
    two = "# **Điều 1. A**\n\nnội dung\n\n# **Điều 2. B**\n\nnội dung\n"
    env = Env({"ngan": two, "mat": None}, [_rec("ngan", 0, "a"), _rec("ngan", 1, "b"), _rec("mat", 0, "c")])
    chunks = env.load()                      # mặc định min_articles=3
    assert [c.id for c in chunks] == ["ngan:0", "ngan:1", "mat:0"]
    assert all(c.metadata["chunking"] == "span" for c in chunks)
    # hạ ngưỡng xuống 2: 'ngan' tách thành 2 Điều; 'mat' vẫn là 1 chunk theo ký tự (không có file gốc)
    assert len(env.load(min_articles=2)) == 2 + 1


def test_long_article_is_split_into_parts():
    long_art = "# **Điều 1. Dài**\n\n" + "\n\n".join(f"Đoạn {i} " + "chữ " * 30 for i in range(8))
    text = long_art + "\n\n# **Điều 2. B**\n\nngắn\n\n# **Điều 3. C**\n\nngắn\n"
    env = Env({"d": text}, [_rec("d", 0, "x")])
    chunks = env.load(max_article_chars=300)
    d1 = [c for c in chunks if c.metadata["dieu_so"] == "Điều 1"]
    assert len(d1) > 1
    assert [c.metadata["part"] for c in d1] == list(range(1, len(d1) + 1))
    assert all(len(c.document) <= 300 for c in d1)
    assert len({c.id for c in chunks}) == len(chunks)           # id không trùng
    assert "Đoạn 7" in "\n".join(c.document for c in d1)         # không mất nội dung


def test_only_ready_filters_unreviewed_documents():
    env = Env({"a": BANG, "b": BANG}, [_rec("a", 0, "x", verified=True), _rec("b", 0, "y", verified=False)])
    assert {c.metadata["doc_id"] for c in env.load(only_ready=True)} == {"a"}
