"""Generate *draft-only* QA candidates from verified Markdown tables.

This is a conservative evidence-extraction aid, not a table reasoning engine.
Question/answer pairs must be checked against original documents and never
enter training without explicit human review and benchmark separation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .contracts import read_jsonl, write_jsonl
from .review import _documents, _source_path, SOURCE_ROOT

YEAR = re.compile(r'^(20\d{2})-(20\d{2})$')
SEPARATOR = re.compile(r'^:?-{3,}:?$')
HEADING = re.compile(r'^\s{0,3}#{1,6}\s+(.+?)\s*$')
SUBHEADING = re.compile(r'^\s*\*\*(?:\d+\.|Điều\s+\d+\.)\s*(.+?)\*\*', re.I)
PREFERRED_LABELS = ('chương trình', 'khóa', 'khoá', 'đối tượng', 'hình thức', 'ngành')
TOPICS = frozenset(('tuition', 'scholarship'))
IDENTIFIER_COLUMNS = frozenset(('tt', 'stt', 'số thứ tự', 'mã', 'ký hiệu', 'no.', 'no'))
NUMERIC_AMOUNT = re.compile(r'\d+(?:[.,]\d+)*(?:\s*(?:đ|đồng|vnđ|vnd|%))?', re.I)


def _cells(line: str) -> list[str] | None:
    """Parse plain Markdown pipe rows; reject escaped pipes and HTML tables."""
    line = line.strip()
    if not line.startswith('|') or not line.endswith('|') or '\\|' in line:
        return None
    cells = [s.strip() for s in line[1:-1].split('|')]
    if len(cells) < 2 or not all(cells):
        return None
    return cells


def _clean(value: str) -> str:
    value = re.sub(r'<br\s*/?>', ' ', value, flags=re.I)
    value = re.sub(r'<[^>]*>', '', value)
    value = re.sub(r'\*\*|__|<mark>|</mark>', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def _separator(cells: list[str] | None, width: int) -> bool:
    return bool(cells and len(cells) == width and all(SEPARATOR.fullmatch(x.replace(' ', '')) for x in cells))


def _label_column(headers: list[str]) -> int | None:
    for i, label in enumerate(headers):
        if any(s in label.casefold() for s in PREFERRED_LABELS):
            return i
    for i, label in enumerate(headers):
        if label.casefold() not in ('stt', 'số thứ tự', 'no.', 'no'):
            return i
    return None


def _amount(value: str) -> bool:
    # Broad enough for monetary and numeric amounts, but exclude empty cells and
    # purely decorative symbols. Exact meaning/units require human review.
    return bool(2 <= len(value) <= 100 and NUMERIC_AMOUNT.fullmatch(value.strip()))


def _find_tables(text: str):
    lines = text.splitlines()
    section = ''
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = HEADING.match(line)
        submatch = SUBHEADING.match(line)
        if match:
            section = _clean(match.group(1))[:160]
        elif submatch:
            section = _clean(submatch.group(0))[:160]
        header = _cells(line)
        if header and idx + 2 < len(lines) and _separator(_cells(lines[idx + 1]), len(header)):
            raw_rows = []
            j = idx + 2
            while j < len(lines):
                row = _cells(lines[j])
                if row is None:
                    break
                raw_rows.append((lines[j].strip(), row))
                j += 1
            yield section, header, raw_rows
            idx = j
        else:
            idx += 1


def propose_tables(repo: Path, registry: Path, holds: Path, output: Path,
                   max_per_doc: int = 45) -> dict:
    """Propose bounded, SHA-bound table-cell QAs; all return as DRAFT.

    Fail closed if a verified document has a changed source, malformed table,
    hold, unverified academic year or unsupported document topic.
    """
    if max_per_doc < 1 or max_per_doc > 250:
        raise ValueError('max_per_doc must be 1..250')
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite candidate work: {output}')
    docs = _documents(repo, registry, holds)
    result = []
    stats = Counter()
    for doc in sorted(docs.values(), key=lambda d: (str(d.get('relative_path')), str(d.get('doc_id')))):
        if doc.get('topic_hint') not in TOPICS:
            continue
        if (not doc.get('policy_qa_ready') or doc.get('review_status') != 'verified_against_source'
                or doc.get('_qa_hold')):
            stats['blocked_or_unverified_docs'] += 1
            continue
        match = YEAR.fullmatch(str(doc.get('academic_year_verified') or ''))
        if not match or int(match.group(2)) != int(match.group(1)) + 1:
            stats['unverified_year_docs'] += 1
            continue
        year = int(match.group(1))
        if year not in range(2022, 2027):
            continue
        rel = doc.get('relative_path')
        if not isinstance(rel, str):
            raise ValueError(f'{doc.get("doc_id")}: missing source path')
        source_rel = (SOURCE_ROOT / rel).as_posix()
        file = _source_path(repo, source_rel)
        contents = file.read_bytes()
        sha = hashlib.sha256(contents).hexdigest()
        if sha != doc.get('content_sha256'):
            raise ValueError(f'{doc.get("doc_id")}: source SHA mismatch')
        text = contents.decode('utf-8-sig').replace('\r\n', '\n')
        produced = 0
        for section, raw_headers, raw_rows in _find_tables(text):
            headers = [_clean(x) for x in raw_headers]
            label_idx = _label_column(headers)
            if label_idx is None or len(set(h.casefold() for h in headers)) != len(headers):
                stats['ambiguous_table_headers'] += 1
                continue
            if not section:
                # Without section context, table values may be ambiguous.
                stats['no_section_context_tables'] += 1
                continue
            for quote, row in raw_rows:
                if len(row) != len(headers):
                    stats['malformed_rows'] += 1
                    continue
                label = _clean(row[label_idx])
                if not label or len(label) > 160 or label.isdigit():
                    continue
                for col, raw in enumerate(row):
                    if col == label_idx or headers[col].casefold().strip() in IDENTIFIER_COLUMNS:
                        continue
                    val = _clean(raw)
                    if not _amount(val):
                        continue
                    # The question includes specific row/column/section, not
                    # the old generic "mục này quy định gì" formulation.
                    question = (f'Trong năm học {year}-{year+1}, tại mục "{section}", '
                                f'đối với "{label}", giá trị "{headers[col]}" là bao nhiêu?')
                    if len(question) > 650:
                        continue
                    cid = hashlib.sha256((doc['doc_id'] + '\0' + section + '\0' + quote
                                          + '\0' + str(col)).encode('utf-8')).hexdigest()[:16]
                    result.append({
                        'id': f'lora-table-{year}-{cid}',
                        'question': question,
                        'answer': val,
                        'doc_id': doc['doc_id'],
                        'as_of_year': year,
                        'academic_year': f'{year}-{year+1}',
                        'source_file': source_rel,
                        'source_sha256': sha,
                        'evidence_quote': quote,
                        'review_status': 'draft',
                        'review_note': ('TABLE DRAFT ONLY: verify the original PDF, merged cells, '
                                        'units and cohort scope; rewrite if required before approval.'),
                        'table_section': section,
                        'table_row_label': label,
                        'table_column': headers[col],
                    })
                    produced += 1
                    if produced >= max_per_doc:
                        break
                if produced >= max_per_doc:
                    break
            if produced >= max_per_doc:
                break
        if produced:
            stats['source_documents'] += 1
    if len({r['id'] for r in result}) != len(result):
        raise ValueError('Duplicate table candidate IDs')
    write_jsonl(output, result)
    tally = Counter(r['as_of_year'] for r in result)
    return {
        'candidates': len(result), 'source_documents': stats['source_documents'],
        'years': {str(y): tally[y] for y in range(2022, 2027)},
        'output': str(output), 'auto_approved': 0, 'all_require_manual_review': True,
        'skipped': {key: val for key, val in stats.items() if key != 'source_documents'},
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Propose DRAFT-only QA from verified Markdown tables')
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--registry', type=Path, default=Path('data/versioning/documents.jsonl'))
    parser.add_argument('--holds', type=Path, default=Path('data/versioning/publication_holds.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('src/lora/runs/table_candidates.jsonl'))
    parser.add_argument('--max-per-doc', type=int, default=45)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    def from_repo(path: Path) -> Path:
        return path if path.is_absolute() else repo / path
    print(json.dumps(propose_tables(repo, from_repo(args.registry), from_repo(args.holds),
                                    from_repo(args.output), args.max_per_doc),
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
