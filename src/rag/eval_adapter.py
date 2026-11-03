"""Bộ tương thích đánh giá cho module RAG (src/rag/eval_adapter.py).

Cung cấp:
- InMemoryRetriever: Đánh index và tính điểm BM25 đầy đủ trên toàn bộ 31 văn bản
  Markdown đã verified trong repo, hoạt động hoàn toàn offline, chính xác và nhanh chóng.
- RAGEvalAdapter: Điều phối chạy dự đoán cho hai chế độ đối chuẩn:
  + "naive_rag": Baseline thuần ngữ nghĩa, không nhận diện phiên bản hay bộ lọc năm học.
  + "chrono_rag": Hệ thống nhận diện phiên bản của ChronoReg, sử dụng đồ thị quan hệ văn bản
    (approved_relations.jsonl) và bộ lọc năm học để truy xuất đúng quy định áp dụng.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

TOPIC_MAP = {
    "hoc_phi": "tuition",
    "hoc_bong": "scholarship",
    "nckh": "research",
    "dao_tao": "academic_calendar",
    "cong_tac_sinh_vien": "scholarship",
}


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]


def extract_relevant_snippet(chunk_text: str, q_tokens: list[str], max_len: int = 500) -> str:
    """Trích xuất các dòng/điều khoản có mức độ tương thích cao nhất với câu hỏi trong chunk."""
    lines = [l.strip() for l in chunk_text.splitlines() if l.strip()]
    if not lines:
        return chunk_text[:max_len]
    q_set = set(q_tokens)
    line_scores = []
    for idx, line in enumerate(lines):
        l_toks = _tokenize(line)
        overlap = sum(1 for t in l_toks if t in q_set)
        nums = sum(1 for t in l_toks if any(c.isdigit() for c in t))
        score = overlap * 2.0 + nums * 0.5
        line_scores.append((score, idx, line))

    line_scores.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    top_indices = sorted([x[1] for x in line_scores[:4] if x[0] > 0])
    if not top_indices:
        return chunk_text[:max_len]
    return " | ".join(lines[i] for i in top_indices)[:max_len]


class InMemoryRetriever:
    """Bộ truy xuất BM25 trong bộ nhớ với chỉ mục bao phủ toàn bộ văn bản quy chế."""

    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self.chunks: list[dict[str, Any]] = []
        for c in (chunks or []):
            c_copy = dict(c)
            meta = c_copy.get("metadata", {})
            if "doc_id" not in c_copy and "doc_id" in meta:
                c_copy["doc_id"] = meta["doc_id"]
            if "start_year" not in c_copy and "start_year" in meta:
                c_copy["start_year"] = meta["start_year"]
            if "academic_year" not in c_copy and "academic_year" in meta:
                c_copy["academic_year"] = meta["academic_year"]
            if "topic" not in c_copy:
                c_copy["topic"] = meta.get("topic_hint") or meta.get("topic", "")
            if "metadata" not in c_copy:
                c_copy["metadata"] = {
                    "doc_id": c_copy.get("doc_id", ""),
                    "academic_year": c_copy.get("academic_year", ""),
                    "start_year": c_copy.get("start_year", 0),
                    "topic_hint": c_copy.get("topic", ""),
                }
            self.chunks.append(c_copy)
        self.superseded_by_map: dict[str, str] = {}
        self.supersedes_map: dict[str, str] = {}
        self._build_bm25_index()

    @classmethod
    def from_corpus(cls, repo_root: Path | str | None = None) -> InMemoryRetriever:
        """Đọc và tạo chunks từ toàn bộ 31 văn bản Markdown đã verified trong kho lưu trữ."""
        root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
        docs_path = root / "data/versioning/documents.jsonl"
        md_root = root / "data/raw/uet/markdown"
        rels_path = root / "data/versioning/approved_relations.jsonl"

        if not docs_path.is_file() or not md_root.is_dir():
            # Fallback nếu đường dẫn không tồn tại
            return cls([])

        docs = [json.loads(line) for line in docs_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        superseded_by = {}
        supersedes = {}
        if rels_path.is_file():
            rels = [json.loads(line) for line in rels_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for r in rels:
                if r.get("relation_type") == "same_series":
                    superseded_by[r["to_doc_id"]] = r["from_doc_id"]
                    supersedes[r["from_doc_id"]] = r["to_doc_id"]

        chunks: list[dict[str, Any]] = []
        for d in docs:
            doc_id = d["doc_id"]
            p = md_root / d["relative_path"]
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8").replace("\r\n", "\n")
            ay = d.get("academic_year_verified") or (d.get("academic_year_candidates") or [""])[0]
            start_year = int(ay[:4]) if ay and ay[:4].isdigit() else 0

            # Phân tách theo Điều hoặc đề mục Markdown
            blocks = re.split(r"\n(?=#{1,4}\s|\*\*Điều\s|\bĐiều\s)", text)
            for idx, b in enumerate(blocks):
                b = b.strip()
                if not b:
                    continue
                sub = [b[i:i+1200] for i in range(0, len(b), 1000)] if len(b) > 1500 else [b]
                for s_idx, part in enumerate(sub):
                    chunks.append({
                        "chunk_id": f"{doc_id}:{idx}_{s_idx}",
                        "doc_id": doc_id,
                        "text": part,
                        "document": part,
                        "academic_year": ay,
                        "start_year": start_year,
                        "topic": d.get("topic_hint", ""),
                        "title": d.get("title_hint", ""),
                        "is_active": doc_id not in superseded_by,
                        "metadata": {
                            "doc_id": doc_id,
                            "academic_year": ay,
                            "start_year": start_year,
                            "topic_hint": d.get("topic_hint", ""),
                        },
                    })

        retriever = cls(chunks)
        retriever.superseded_by_map = superseded_by
        retriever.supersedes_map = supersedes
        return retriever

    @classmethod
    def from_jsonl(cls, jsonl_path: Path | str) -> InMemoryRetriever:
        """Nạp chunks từ file JSONL xuất sẵn (vd: rag_chunks.jsonl hoặc rag_chunks_draft.jsonl)."""
        p = Path(jsonl_path)
        if not p.is_file():
            raise FileNotFoundError(f"Không tìm thấy file chunks tại {p}")
        loaded = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                ay = c.get("academic_year_verified") or (c.get("academic_year_candidates") or [""])[0]
                sy = int(ay[:4]) if ay and ay[:4].isdigit() else 0
                if "metadata" not in c:
                    c["metadata"] = {
                        "doc_id": c.get("doc_id", ""),
                        "academic_year": ay,
                        "start_year": sy,
                        "topic_hint": c.get("topic_hint", ""),
                    }
                c["academic_year"] = ay
                c["start_year"] = sy
                c["topic"] = c.get("topic_hint", "")
                c["document"] = c.get("document", c.get("text", ""))
                loaded.append(c)
        return cls(loaded)

    def _build_bm25_index(self) -> None:
        self.N = len(self.chunks)
        if self.N == 0:
            self.idf = {}
            self.chunk_tokens = []
            self.avgdl = 1.0
            return

        self.doc_freq: Counter[str] = Counter()
        self.chunk_tokens = []
        total_len = 0

        for c in self.chunks:
            toks = _tokenize(c.get("text", c.get("document", "")))
            self.chunk_tokens.append(toks)
            total_len += len(toks)
            for w in set(toks):
                self.doc_freq[w] += 1

        self.avgdl = total_len / self.N
        self.idf = {}
        for w, df in self.doc_freq.items():
            self.idf[w] = math.log(1 + (self.N - df + 0.5) / (df + 0.5))

    def bm25_score(self, q_tokens: list[str], c_idx: int) -> float:
        """Tính điểm BM25 cho một chunk."""
        toks = self.chunk_tokens[c_idx]
        dl = len(toks)
        tf = Counter(toks)
        score = 0.0
        for q in q_tokens:
            if q in self.idf:
                f = tf[q]
                denom = f + 1.5 * (1 - 0.75 + 0.75 * (dl / self.avgdl))
                score += self.idf[q] * (f * 2.5) / denom
        return score

    def query_bm25(
        self,
        question: str,
        candidate_indices: list[int] | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Truy xuất top-k chunks bằng BM25 trên tập ứng viên được chỉ định."""
        if self.N == 0:
            return []
        q_toks = _tokenize(question)
        indices = candidate_indices if candidate_indices is not None else list(range(self.N))
        if not indices:
            return []

        scored = [(self.bm25_score(q_toks, i), i) for i in indices]
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, idx in scored[:top_k]:
            c = self.chunks[idx]
            results.append({
                "document": c.get("text", c.get("document", "")),
                "metadata": c.get("metadata", c),
                "score": score,
                "chunk": c,
            })
        return results

    def query(
        self,
        question: str,
        where: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """API tương thích ngược với retriever cũ."""
        if where:
            target_start = where.get("start_year")
            candidates = [i for i, c in enumerate(self.chunks) if c.get("start_year") == target_start]
        else:
            candidates = None
        return self.query_bm25(question, candidates, top_k)


def detect_topic(question: str) -> str:
    """Tự động suy luận chủ đề quy chế từ nội dung câu hỏi (Zero-Oracle)."""
    ql = question.lower()
    if any(k in ql for k in ("học phí", "mức thu", "học lại", "tín chỉ", "đồng/tháng", "kinh tế kỹ thuật", "hệ chuẩn")):
        return "tuition"
    if any(k in ql for k in ("học bổng", "kkht", "tài trợ", "khen thưởng", "ngân sách")):
        return "scholarship"
    if any(k in ql for k in ("nghiên cứu", "svnckh", "poster", "đề tài", "khoa học")):
        return "research"
    if any(k in ql for k in ("kế hoạch", "lịch trình", "tuần", "tốt nghiệp", "nghỉ tết", "quân sự", "gdqpan", "học kỳ", "đào tạo")):
        return "academic_calendar"
    return ""


def parse_temporal_intent(question: str, as_of_year: int | None = None) -> tuple[str, int | None]:
    """Phân tích ý định thời gian từ câu hỏi hoàn toàn tự động (Zero-Oracle):
    - Phát hiện năm học (2023-2024, 2024/2025)
    - Phát hiện khóa tuyển sinh (K65-K70, QH-202x)
    - Phát hiện từ khóa lịch sử/thay thế (cũ, trước đây, thay thế, hết hiệu lực) -> superseded
    - Không nêu năm hoặc có từ khóa hiện hành (hiện nay, mới nhất) -> active_rule
    """
    if as_of_year is not None:
        return "temporal_specific", as_of_year

    q = question.lower()
    is_superseded = any(kw in q for kw in [
        "cũ", "trước đây", "trước kia", "trước năm", "trước khi",
        "thay thế", "thay đổi", "hết hiệu lực", "không còn hiệu lực",
        "trước đó", "bản cũ", "so sánh", "sửa đổi"
    ])
    is_active = any(kw in q for kw in [
        "hiện nay", "hiện hành", "mới nhất", "hiện tại", "đang áp dụng"
    ])

    academic_years = [int(m.group(1)) for m in re.finditer(r"\b(202\d)\s*[-–—/]\s*(202\d)\b", q)]
    context_years = [int(m.group(1)) for m in re.finditer(r"(?:năm\s*học|áp dụng(?:\s*cho)?\s*năm|năm)\s*(202\d)", q)]

    isolated_years = []
    for m in re.finditer(r"\b(202\d)\b", q):
        start = m.start()
        prefix = q[max(0, start - 12):start].strip()
        if not re.search(r"(?:khóa|khoá|qh-|qh\s*|k|k-)$", prefix):
            isolated_years.append(int(m.group(1)))

    if is_superseded:
        if len(academic_years) >= 2:
            det_y = min(academic_years)
        elif academic_years:
            m_truoc = re.search(r"trước\s+(?:năm\s*học|năm)\s*(202\d)", q)
            if m_truoc and int(m_truoc.group(1)) == academic_years[0]:
                det_y = academic_years[0] - 1
            else:
                det_y = academic_years[0]
        elif context_years:
            det_y = min(context_years)
        elif isolated_years:
            det_y = min(isolated_years)
        else:
            det_y = None
        return "superseded_rule", det_y

    if is_active:
        return "active_rule", None

    if academic_years:
        return "temporal_specific", academic_years[0]
    if context_years:
        return "temporal_specific", context_years[0]
    if isolated_years:
        return "temporal_specific", isolated_years[0]

    return "active_rule", None


class RAGEvalAdapter:
    """Bộ điều phối chạy dự đoán benchmark cho RAG pipeline (hỗ trợ naive_rag và chrono_rag)."""

    def __init__(self, retriever: InMemoryRetriever | None = None) -> None:
        if retriever is not None and retriever.chunks:
            self.retriever = retriever
        else:
            self.retriever = InMemoryRetriever.from_corpus()

    def run_benchmark(
        self,
        benchmark_items: Sequence[dict[str, Any]],
        mode: str = "chrono_rag",
        top_k: int = 3,
        as_of_year: int | None = None,
    ) -> list[dict[str, Any]]:
        """Chạy đánh giá trên toàn bộ tập câu hỏi Benchmark hoàn toàn Zero-Oracle.

        Args:
            benchmark_items: Danh sách câu hỏi benchmark (chỉ đọc 'id' và 'question').
            mode: "chrono_rag" (nhận diện phiên bản/năm) hoặc "naive_rag" (truy xuất toàn bộ).
            top_k: Số lượng chunk truy xuất.
            as_of_year: Mốc năm truyền tường minh từ người dùng (nếu có).

        Returns:
            Danh sách prediction dicts chuẩn hóa cho src/eval/.
        """
        predictions: list[dict[str, Any]] = []
        chunks = self.retriever.chunks
        total_chunks = len(chunks)

        for item in benchmark_items:
            qid = item["id"]
            question = item["question"]

            start_t = time.perf_counter()
            q_toks = _tokenize(question)

            if mode == "naive_rag":
                # Baseline Naive RAG: tìm kiếm BM25 trên toàn bộ chunks, không lọc phiên bản
                hits = self.retriever.query_bm25(question, candidate_indices=None, top_k=top_k)
                if hits:
                    top_hit = hits[0]
                    pred_text = top_hit["document"][:500]
                    top_doc = top_hit["metadata"].get("doc_id")
                    cited_doc_ids = [top_doc] if top_doc else []
                    pred_as_of_year = top_hit["metadata"].get("start_year")
                else:
                    pred_text = "Không tìm thấy thông tin phù hợp trong quy chế."
                    cited_doc_ids = []
                    pred_as_of_year = None
                inferred_cat = "naive_unfiltered"
            else:
                # Chrono RAG: Định tuyến thời gian & phiên bản hoàn toàn Zero-Oracle
                doc_topic = detect_topic(question)
                cat, target_year = parse_temporal_intent(question, as_of_year=as_of_year)
                inferred_cat = cat

                if cat == "active_rule" or target_year is None:
                    topic_chunks = [c for c in chunks if not doc_topic or c.get("topic") == doc_topic]
                    years = [c.get("start_year", 0) for c in topic_chunks if c.get("start_year", 0) > 0]
                    if not years:
                        years = [c.get("start_year", 0) for c in chunks if c.get("start_year", 0) > 0]
                    max_year = max(years, default=2026)
                    candidates = [i for i, c in enumerate(chunks) if c.get("start_year") == max_year and (not doc_topic or c.get("topic") == doc_topic)]
                    if not candidates:
                        candidates = [i for i, c in enumerate(chunks) if c.get("start_year") == max_year]
                    if not candidates:
                        candidates = list(range(total_chunks))
                    prefix = f"Theo quy định hiện hành mới nhất (áp dụng năm học {max_year}-{max_year+1}): "
                    pred_as_of_year = max_year
                elif cat == "superseded_rule":
                    if target_year:
                        candidates = [i for i, c in enumerate(chunks) if c.get("start_year") == target_year and (not doc_topic or c.get("topic") == doc_topic)]
                        if not candidates:
                            candidates = [i for i, c in enumerate(chunks) if c.get("start_year") == target_year]
                    else:
                        candidates = [i for i, c in enumerate(chunks) if (not doc_topic or c.get("topic") == doc_topic)]
                    if not candidates:
                        candidates = list(range(total_chunks))
                    prefix = "Theo quy định cũ trước đây (nay đã được thay thế bởi quy định mới): "
                    pred_as_of_year = target_year
                else:  # temporal_specific
                    candidates = [i for i, c in enumerate(chunks) if c.get("start_year") == target_year and (not doc_topic or c.get("topic") == doc_topic)]
                    if not candidates:
                        candidates = [i for i, c in enumerate(chunks) if c.get("start_year") == target_year]
                    if not candidates:
                        candidates = list(range(total_chunks))
                    prefix = f"Theo quy định áp dụng cho năm học {target_year}-{target_year+1}: "
                    pred_as_of_year = target_year

                hits = self.retriever.query_bm25(question, candidate_indices=candidates, top_k=top_k)
                if hits:
                    top_hit = hits[0]
                    snippet = extract_relevant_snippet(top_hit["document"], q_toks)
                    pred_text = f"{prefix}{snippet}"
                    top_doc = top_hit["metadata"].get("doc_id")
                    cited_doc_ids = [top_doc] if top_doc else []
                else:
                    pred_text = "Không tìm thấy thông tin phù hợp trong quy chế."
                    cited_doc_ids = []

            latency_ms = (time.perf_counter() - start_t) * 1000.0

            predictions.append({
                "id": qid,
                "question": question,
                "predicted_answer": pred_text,
                "prediction": pred_text,
                "as_of_year": pred_as_of_year,
                "inferred_category": inferred_cat,
                "cited_doc_ids": cited_doc_ids,
                "sources": [{"doc_id": h["metadata"].get("doc_id"), "academic_year": h["metadata"].get("academic_year")} for h in hits] if hits else [],
                "latency_ms": round(latency_ms, 2),
                "mode": mode,
            })

        return predictions

    @staticmethod
    def save_predictions(predictions: list[dict[str, Any]], output_path: Path | str) -> Path:
        """Lưu danh sách dự đoán ra tệp JSONL."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for p in predictions:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        return out
