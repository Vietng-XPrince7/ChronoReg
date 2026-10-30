"""Đọc chunk của Việt (export-chunks) và chunk lại THEO ĐIỀU khi văn bản có cấu trúc Điều.

Chiến lược kết hợp:
- Văn bản có >= min_articles "Điều"  -> tách theo Điều (kèm phần mở đầu và Phụ lục),
  đọc toàn văn từ file .md gốc (đường dẫn lấy từ documents.jsonl).
- Còn lại (bảng học phí, kế hoạch học tập, ...) -> giữ nguyên chunk cắt theo ký tự của Việt.

Chỉ xử lý các văn bản có trong file chunk của Việt, và năm học / trạng thái duyệt luôn lấy
từ chunk của Việt, nên việc duyệt vẫn do Việt quyết định.
Metadata gửi vào vector DB chỉ chứa str/int/bool (DB không nhận None hoặc list).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Markdown thật có dạng "# **Điều 7. Tên**", "**Điều 1.** Nội dung...", "Điều 2: ...".
# "Điều 5 của Quy chế..." đứng đầu dòng KHÔNG được coi là tiêu đề (không có #, ** hay dấu . :).
_DIEU = re.compile(
    r"^[ \t]*(?P<hash>#{1,6}[ \t]*)?(?P<bold>\*\*|__)?[ \t]*Điều[ \t]+(?P<num>\d+)"
    r"(?P<punct>[ \t]*[.:\-–—])?[ \t]*(?P<rest>.*)$",
    re.IGNORECASE,
)
_CHUONG = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*(?:Chương|CHƯƠNG)[ \t]+(?P<num>[IVXLCDM\d]+)\b(?P<rest>.*)$"
)
_PHULUC = re.compile(
    r"^[ \t]*(?P<hash>#{1,6}[ \t]*)?(?P<bold>\*\*|__)?[ \t]*(?P<kw>PHỤ LỤC|Phụ lục)[ \t]*"
    r"(?P<num>[0-9IVXLC]*)\b(?P<rest>.*)$"
)


@dataclass
class Chunk:
    id: str
    text: str       # dùng để tạo embedding (có thêm chủ đề, năm học, phạm vi, Điều)
    document: str   # nội dung gốc, đưa cho LLM
    metadata: dict


# ── Năm học ────────────────────────────────────────────────────────────────

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


# ── Nhận diện Điều / Chương / Phụ lục ──────────────────────────────────────

def _clean(s: str) -> str:
    return s.strip(" \t*_#–—-.:")


def match_dieu(line: str) -> tuple[str, str] | None:
    m = _DIEU.match(line)
    if not m or not (m.group("hash") or m.group("bold") or m.group("punct")):
        return None
    return m.group("num"), _clean(m.group("rest"))[:120]


def match_chuong(line: str) -> str | None:
    m = _CHUONG.match(line)
    if not m:
        return None
    title = _clean(m.group("rest"))
    return f"Chương {m.group('num')}" + (f" - {title}" if title else "")


def match_phuluc(line: str) -> str | None:
    m = _PHULUC.match(line)
    if not m or not (m.group("hash") or m.group("bold") or m.group("kw") == "PHỤ LỤC"):
        return None
    return f"Phụ lục {m.group('num')}".strip()


def split_articles(text: str) -> list[dict]:
    """Tách văn bản thành các phần: mở đầu, từng Điều, Phụ lục.

    Mỗi phần: {kind, dieu_so, title, chuong, content}. Dòng "Chương ..." không nằm trong
    nội dung mà được ghi vào trường chuong của các Điều phía sau nó.
    """
    sections: list[dict] = []
    chuong = ""

    def new(kind, dieu_so="", title="", ch=""):
        return {"kind": kind, "dieu_so": dieu_so, "title": title, "chuong": ch, "lines": []}

    def flush(sec):
        body = "\n".join(sec["lines"]).strip()
        if body:
            sections.append({k: v for k, v in sec.items() if k != "lines"} | {"content": body})

    cur = new("preamble")
    for line in text.splitlines():
        d = match_dieu(line)
        if d:
            flush(cur)
            cur = new("dieu", f"Điều {d[0]}", d[1], chuong)
            cur["lines"].append(line)
            continue
        c = match_chuong(line)
        if c:
            flush(cur)
            chuong = c
            cur = new("other", "", "", chuong)
            continue
        p = match_phuluc(line)
        if p:
            flush(cur)
            chuong = ""
            cur = new("phuluc", p, "", "")
            cur["lines"].append(line)
            continue
        cur["lines"].append(line)
    flush(cur)
    return sections


def _pack_lines(para: str, limit: int) -> list[str]:
    out, cur = [], ""
    for ln in para.split("\n"):
        if cur and len(cur) + 1 + len(ln) > limit:
            out.append(cur)
            cur = ln
        else:
            cur = f"{cur}\n{ln}" if cur else ln
    if cur:
        out.append(cur)
    return out


def _split_long(text: str, limit: int) -> list[str]:
    """Cắt phần quá dài theo đoạn (giữ nguyên bảng); đoạn dài quá thì cắt theo dòng."""
    if limit <= 0 or len(text) <= limit:
        return [text]
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        units.extend([para] if len(para) <= limit else _pack_lines(para, limit))
    parts, cur = [], ""
    for u in units:
        if cur and len(cur) + 2 + len(u) > limit:
            parts.append(cur)
            cur = u
        else:
            cur = f"{cur}\n\n{u}" if cur else u
    if cur:
        parts.append(cur)
    return parts


# ── Đọc dữ liệu của Việt ───────────────────────────────────────────────────

def _read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _issued_dates(path: str | Path | None) -> dict[str, str]:
    if path and Path(path).exists():
        return {r["doc_id"]: r.get("issued_date") or "" for r in _read_jsonl(path)}
    return {}


def _source_paths(path: str | Path | None) -> dict[str, str]:
    if path and Path(path).exists():
        return {r["doc_id"]: r.get("source_path") or "" for r in _read_jsonl(path)}
    return {}


def _head(base: dict, ay: str) -> str:
    topic = base.get("topic_hint") or ""
    scope = base.get("scope") or ""
    return f"[{topic}] Năm học {ay or 'chưa rõ'}. {scope}".strip()


def _metadata(base: dict, issued: str, **extra) -> dict:
    ay, start, status = year_info(base)
    meta = {
        "doc_id": base["doc_id"],
        "academic_year": ay,
        "start_year": start,
        "year_status": status,
        "review_status": base.get("review_status") or "",
        "topic_hint": base.get("topic_hint") or "",
        "scope": base.get("scope") or "",
        "issued_date": issued,
        "effective_from": base.get("effective_from") or "",
        "effective_until_exclusive": base.get("effective_until_exclusive") or "",
        "start_char": 0,
        "end_char": 0,
        "dieu_so": "",
        "dieu_title": "",
        "chuong": "",
        "chunking": "span",
        "part": 0,
    }
    meta.update(extra)
    return meta


def _article_chunks(base: dict, sections: list[dict], issued: str, max_chars: int) -> list[Chunk]:
    ay = year_info(base)[0]
    head = _head(base, ay)
    chunks: list[Chunk] = []
    for idx, sec in enumerate(sections, 1):
        parts = _split_long(sec["content"], max_chars)
        label = " | ".join(x for x in (
            sec["chuong"], f"{sec['dieu_so']}. {sec['title']}".strip(" .") if sec["dieu_so"] else "") if x)
        for k, part in enumerate(parts, 1):
            cid = f"{base['doc_id']}:a{idx}" + (f".p{k}" if len(parts) > 1 else "")
            chunks.append(Chunk(
                id=cid,
                text=f"{head}\n{label}\n{part}".strip() if label else f"{head}\n{part}",
                document=part,
                metadata=_metadata(
                    base, issued, dieu_so=sec["dieu_so"], dieu_title=sec["title"],
                    chuong=sec["chuong"], chunking="article", part=k if len(parts) > 1 else 0),
            ))
    return chunks


def _span_chunks(recs: list[dict], issued: str) -> list[Chunk]:
    out = []
    for r in recs:
        ay = year_info(r)[0]
        out.append(Chunk(
            id=r["chunk_id"],
            text=f"{_head(r, ay)}\n{r['text']}",
            document=r["text"],
            metadata=_metadata(r, issued, start_char=r.get("start_char") or 0,
                               end_char=r.get("end_char") or 0),
        ))
    return out


def load_chunks(chunks_file: str | Path, reviewed_file: str | Path | None = None,
                documents_file: str | Path | None = None, only_ready: bool = False,
                min_articles: int = 3, max_article_chars: int = 2000,
                source_root: str | Path | None = None) -> list[Chunk]:
    root = Path(source_root) if source_root else ROOT
    issued = _issued_dates(reviewed_file)
    sources = _source_paths(documents_file)

    by_doc: dict[str, list[dict]] = {}
    for r in _read_jsonl(chunks_file):
        if only_ready and not r.get("policy_qa_ready"):
            continue
        by_doc.setdefault(r["doc_id"], []).append(r)

    chunks: list[Chunk] = []
    for doc_id, recs in by_doc.items():
        base, iss = recs[0], issued.get(doc_id, "")
        sections = None
        src = sources.get(doc_id)
        if src and (root / src).exists():
            secs = split_articles((root / src).read_text(encoding="utf-8"))
            if sum(1 for s in secs if s["kind"] == "dieu") >= min_articles:
                sections = secs
        if sections is not None:
            chunks.extend(_article_chunks(base, sections, iss, max_article_chars))
        else:
            chunks.extend(_span_chunks(recs, iss))
    return chunks


def summarize(chunks: list[Chunk]) -> dict:
    """Thống kê để kiểm tra: bao nhiêu văn bản/chunk theo Điều, bao nhiêu theo ký tự."""
    out = {}
    for mode in ("article", "span"):
        sel = [c for c in chunks if c.metadata["chunking"] == mode]
        out[mode] = {"documents": len({c.metadata["doc_id"] for c in sel}), "chunks": len(sel)}
    out["by_year_status"] = dict(Counter(c.metadata["year_status"] for c in chunks))
    return out
