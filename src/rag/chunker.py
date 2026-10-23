"""Đọc chunk đã xuất bởi `python -m src.versioning.cli export-chunks` (JSONL).

Chunk của Việt cắt theo số ký tự (start_char/end_char), kèm metadata phiên bản.
Metadata gửi vào vector DB chỉ chứa str/int/bool (DB không nhận None hoặc list).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    id: str
    text: str       # dùng để tạo embedding (có thêm chủ đề, năm học, phạm vi)
    document: str   # nội dung gốc, đưa cho LLM
    metadata: dict


def year_info(rec: dict) -> tuple[str, int, str]:
    """-> (năm học 'YYYY-YYYY' hoặc '', năm bắt đầu hoặc 0, trạng thái).

    verified  : Việt đã duyệt (academic_year_verified)
    candidate : chưa duyệt nhưng chỉ có đúng 1 ứng viên
    unknown   : không có hoặc còn mơ hồ -> KHÔNG dùng để lọc theo năm
    """
    verified = rec.get("academic_year_verified")
    cands = rec.get("academic_year_candidates") or []
    if verified:
        ay, status = verified, "verified"
    elif len(cands) == 1:
        ay, status = cands[0], "candidate"
    else:
        return "", 0, "unknown"
    return ay, int(ay[:4]), status


def _issued_dates(path: str | Path | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["doc_id"]] = r.get("issued_date") or ""
    return out


def load_chunks(chunks_file: str | Path, reviewed_file: str | Path | None = None,
                only_ready: bool = False) -> list[Chunk]:
    issued = _issued_dates(reviewed_file)
    chunks: list[Chunk] = []
    with open(chunks_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if only_ready and not r.get("policy_qa_ready"):
                continue
            ay, start, status = year_info(r)
            topic = r.get("topic_hint") or ""
            scope = r.get("scope") or ""
            head = f"[{topic}] Năm học {ay or 'chưa rõ'}. {scope}".strip()
            chunks.append(Chunk(
                id=r["chunk_id"],
                text=f"{head}\n{r['text']}",
                document=r["text"],
                metadata={
                    "doc_id": r["doc_id"],
                    "academic_year": ay,
                    "start_year": start,
                    "year_status": status,
                    "review_status": r.get("review_status") or "",
                    "topic_hint": topic,
                    "scope": scope,
                    "issued_date": issued.get(r["doc_id"], ""),
                    "effective_from": r.get("effective_from") or "",
                    "effective_until_exclusive": r.get("effective_until_exclusive") or "",
                    "start_char": r.get("start_char") or 0,
                    "end_char": r.get("end_char") or 0,
                },
            ))
    return chunks
