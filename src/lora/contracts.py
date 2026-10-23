"""Dataset contracts owned by the LoRA branch, without modifying shared schema.

All QAs used for training must be manually approved with grounded evidence.
`as_of_year` is the START year of the applicable academic year; the team must
confirm this convention with evaluation owners before reporting comparisons.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

YEARS = tuple(range(2022, 2027))
FIELDS = ('id', 'question', 'answer', 'doc_id', 'as_of_year',
          'evidence_quote', 'review_status')


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f'Missing input: {path}')
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('Expected a JSON object')
        except ValueError as exc:
            raise ValueError(f'{path}:{number}: {exc}') from exc
        rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(x, ensure_ascii=False, sort_keys=True)
                            + '\n' for x in rows), encoding='utf-8')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def question_key(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'\s+', ' ', value).strip(' .?!\t\n')


def _text(row: dict, key: str) -> str:
    val = row.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f'{row.get("id", "<unknown>")}: missing/invalid {key}')
    return val.strip()


def _year(val: Any, label: str) -> int:
    if type(val) is not int or val not in YEARS:
        raise ValueError(f'{label}: as_of_year must be an integer from 2022 to 2026')
    return val


def _path_within(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError('source_file must be repository-relative')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Source path escapes repository: {relative}')
    return path


def validate_training(rows: list[dict], repo: Path,
                      benchmark: list[dict] | None = None) -> list[dict]:
    """Fail closed on missing approvals, missing evidence, and benchmark leakage."""
    ids, questions = set(), set()
    reserved_ids, reserved_questions = set(), set()
    for b in benchmark or []:
        bid = _text(b, 'id')
        bq = question_key(_text(b, 'question'))
        if bid in reserved_ids or bq in reserved_questions:
            raise ValueError('Duplicate benchmark ID/question')
        reserved_ids.add(bid)
        reserved_questions.add(bq)
    approved = []
    for raw in rows:
        rid = _text(raw, 'id')
        question = _text(raw, 'question')
        answer = _text(raw, 'answer')
        doc_id = _text(raw, 'doc_id')
        evidence = _text(raw, 'evidence_quote')
        year = _year(raw.get('as_of_year'), rid)
        if raw.get('review_status') != 'approved':
            raise ValueError(f'{rid}: only manually approved QA can enter training')
        if rid in ids or question_key(question) in questions:
            raise ValueError(f'{rid}: duplicate ID or question in training')
        if rid in reserved_ids or question_key(question) in reserved_questions:
            raise ValueError(f'{rid}: overlaps held-out benchmark')
        if raw.get('academic_year') is not None:
            if raw['academic_year'] != f'{year}-{year + 1}':
                raise ValueError(f'{rid}: academic_year and as_of_year disagree')
        if len(question) > 1500 or len(answer) > 5000:
            raise ValueError(f'{rid}: excessive question/answer length')
        source = raw.get('source_file')
        if source is None:
            raise ValueError(f'{rid}: approved QA requires source_file and source_sha256')
        if source is not None:
            file = _path_within(repo, _text(raw, 'source_file'))
            if not file.is_file():
                raise ValueError(f'{rid}: source_file missing: {file}')
            src_bytes = file.read_bytes()
            if raw.get('source_sha256') != hashlib.sha256(src_bytes).hexdigest():
                raise ValueError(f'{rid}: source SHA-256 mismatch / absent')
            src_text = src_bytes.decode('utf-8-sig').replace('\r\n', '\n')
            if evidence.replace('\r\n', '\n') not in src_text:
                raise ValueError(f'{rid}: evidence not found verbatim in source')
        ids.add(rid)
        questions.add(question_key(question))
        approved.append({'id': rid, 'question': question, 'answer': answer,
                         'doc_id': doc_id, 'as_of_year': year})
    if not approved:
        raise ValueError('No approved training questions available')
    return sorted(approved, key=lambda x: (x['as_of_year'], x['id']))


def validate_benchmark(rows: list[dict]) -> list[dict]:
    ids = set()
    out = []
    for raw in rows:
        rid = _text(raw, 'id')
        _text(raw, 'question')
        _text(raw, 'gold_answer')
        _text(raw, 'gold_doc_id')
        _text(raw, 'type')
        year = _year(raw.get('as_of_year'), rid)
        if rid in ids:
            raise ValueError(f'Duplicate benchmark ID: {rid}')
        ids.add(rid)
        row = dict(raw)
        row['as_of_year'] = year
        out.append(row)
    return out
