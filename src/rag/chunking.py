"""Chunk các file Markdown đã xử lý (data/processed/*.md) theo Điều.

Mỗi chunk = một Điều, kế thừa metadata cấp tài liệu (frontmatter) và
metadata cấp Điều (HTML comment <!-- meta ... -->) theo docs/schema.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Heading một Điều: "## Điều 15 — Tên" hoặc "### Điều 15. Tên" (schema có cả ## và ###)
ARTICLE = re.compile(r"^#{1,4}\s*(Điều\s+\d+\w*)\s*[—–\-:.]?\s*(.*)$", re.MULTILINE)
# Heading kết thúc một Điều (Điều tiếp theo, Chương, Mục, Phần, Phụ lục)
BOUNDARY = re.compile(r"^#{1,4}\s*(Điều|Chương|Mục|Phần|Phụ lục)\b", re.MULTILINE)
META = re.compile(r"<!--\s*meta\s*\n(.*?)-->", re.DOTALL)

OPEN_END = 99991231  # expired_date = null -> chưa hết hiệu lực


@dataclass
class Chunk:
    id: str
    text: str       # dùng để tạo embedding (có tiêu đề + tóm tắt)
    document: str   # nội dung gốc của Điều, đưa cho LLM
    metadata: dict  # chỉ chứa str/int (vector DB không nhận None hoặc list)


def date_to_int(value) -> int:
    """'2023-09-01' (hoặc kiểu date của YAML) -> 20230901."""
    return int(str(value)[:10].replace("-", ""))


def chunk_text(raw: str, source: str = "") -> list[Chunk]:
    m = FRONTMATTER.match(raw)
    if not m:
        raise ValueError(f"Thiếu frontmatter YAML: {source}")
    fm = yaml.safe_load(m.group(1))
    body = raw[m.end():]

    heads = list(ARTICLE.finditer(body))
    bounds = [b.start() for b in BOUNDARY.finditer(body)]
    chunks, seen = [], {}
    for h in heads:
        end = next((b for b in bounds if b > h.start()), len(body))
        block = body[h.start():end].strip()

        meta_m = META.search(block)
        meta = (yaml.safe_load(meta_m.group(1)) if meta_m else None) or {}
        content = META.sub("", block, count=1)
        content = content.split("\n", 1)[1].strip() if "\n" in content else ""

        dieu = meta.get("dieu_so") or h.group(1)
        khoan = meta.get("khoan_so")
        cid = f"{fm['doc_id']}::{dieu}" + (f"::{khoan}" if khoan else "")
        seen[cid] = seen.get(cid, 0) + 1
        if seen[cid] > 1:
            cid += f"#{seen[cid]}"

        summary = meta.get("noi_dung_tom_tat") or ""
        text = f"{fm['title']} | {dieu} — {h.group(2).strip()}\n{summary}\n{content}"

        chunks.append(Chunk(
            id=cid,
            text=text.strip(),
            document=content,
            metadata={
                "doc_id": fm["doc_id"],
                "title": fm["title"],
                "issuing_body": fm.get("issuing_body", ""),
                "source_type": fm.get("source_type", ""),
                "dieu_so": dieu,
                "khoan_so": khoan or "",
                "tags": ",".join(meta.get("tags") or []),
                "effective_ts": date_to_int(fm["effective_date"]),
                "expired_ts": date_to_int(fm["expired_date"]) if fm.get("expired_date") else OPEN_END,
                "superseded_by": fm.get("superseded_by") or "",
                "source_file": fm.get("source_file", ""),
            },
        ))
    return chunks


def load_processed(folder: str | Path = "data/processed") -> list[Chunk]:
    out: list[Chunk] = []
    for p in sorted(Path(folder).rglob("*.md")):
        out.extend(chunk_text(p.read_text(encoding="utf-8"), str(p)))
    return out
