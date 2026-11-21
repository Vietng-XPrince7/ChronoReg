"""Offline SHA + temporal-source checks; no semantic entailment inference.

The checks prove the cited Markdown matches a reviewed registry record.
They DO NOT prove a generated answer logically follows from its source.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.lora.verified_v3 import sha256_file

_YEAR = re.compile(r"\b20(2[0-9])\b")


def explicit_year(question: str) -> int | None:
    # A year must be supplied explicitly by the user, not guessed from now.
    # A cohort like QH-2022 is NOT the effective year of a regulation.
    clean = re.sub(r"\bQH-20\d\d\b", "", question, flags=re.IGNORECASE)
    years = [int(m.group()) for m in _YEAR.finditer(clean)]
    numbers = set(years)
    if len(numbers) == 1:
        return next(iter(numbers))
    # The 2025-2026 academic-year span starts in 2025.
    span = re.search(r"năm\s+học\s+(20\d\d)\s*[-–/]\s*(20\d\d)", clean, re.I)
    if span and int(span.group(2)) == int(span.group(1)) + 1 and len(years) == 2:
        return int(span.group(1))
    return None


class SourceVerifier:
    def __init__(self, repo_root: Path | str):
        self.root = Path(repo_root).resolve()
        self.reviewed = {}
        self.holds = set()
        reviewed = self.root / "data/versioning/reviewed_documents.jsonl"
        holds = self.root / "data/versioning/publication_holds.jsonl"
        if reviewed.exists():
            for line in reviewed.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.reviewed[rec["doc_id"]] = rec
        if holds.exists():
            for line in holds.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.holds.add(rec["doc_id"])
        self.source_hashes = {sha256_file(p) for p in
                              (self.root / "data/raw/uet/markdown").rglob("*.md")}

    def check(self, doc_ids: list[str] | tuple[str, ...], question: str) -> dict:
        if not doc_ids:
            return {"sha_verified": False, "year_verified": False,
                    "has_hold": False, "reason": "No citations"}
        year = explicit_year(question)
        sha_ok = True
        year_ok = True
        has_hold = False
        for doc_id in doc_ids:
            rec = self.reviewed.get(doc_id)
            if doc_id in self.holds:
                has_hold = True
            if not rec or rec.get("review_status") != "verified_against_source":
                sha_ok = False
                year_ok = False
                continue
            digest = rec.get("content_sha256", "")
            if digest not in self.source_hashes:
                sha_ok = False
            recorded = rec.get("academic_year") or ""
            # Academic-year metadata supports explicitly scoped years only.
            # Open-ended rules require a verified effective date range, not an assumption.
            if year is not None and recorded:
                if not recorded.startswith(str(year)):
                    year_ok = False
            elif year is not None:
                effective = rec.get("effective_from")
                end = rec.get("effective_until_exclusive")
                if not effective or effective[:4] > str(year):
                    year_ok = False
                if not end and not rec.get("open_ended_verified", False):
                    year_ok = False
                if end and end[:4] <= str(year):
                    year_ok = False
            else:
                # Without an explicit year, 'current' validity is not proven.
                year_ok = False
        return {"sha_verified": sha_ok and not has_hold,
                "year_verified": year_ok and not has_hold,
                "has_hold": has_hold, "reason": "Hash of reviewed Markdown checked; no answer entailment verification"}
