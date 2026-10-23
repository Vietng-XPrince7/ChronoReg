"""Propose source-grounded QA candidates; NEVER mark these as approved.

The rule-extraction heuristics deliberately yield narrow, often awkward QA.
Reviewers must verify evidence and reword questions before approving training.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .contracts import read_jsonl, write_jsonl

HEADING = re.compile(r'^#{1,4}\s+(.+?)\s*$', re.MULTILINE)
YEAR = re.compile(r'^(20\d{2})-(20\d{2})$')


def propose(repo: Path, registry: Path, output: Path, max_per_doc: int = 4) -> dict:
    rows = read_jsonl(registry)
    candidates, skips = [], []
    for doc in rows:
        if not doc.get('policy_qa_ready') or doc.get('review_status') != 'verified_against_source':
            continue
        academic_year = doc.get('academic_year_verified')
        match = YEAR.fullmatch(academic_year or '')
        if not match or int(match.group(2)) != int(match.group(1)) + 1:
            skips.append({'doc_id': doc.get('doc_id'), 'reason': 'no verified academic year'})
            continue
        year = int(match.group(1))
        if not 2022 <= year <= 2026:
            continue
        relative = doc.get('relative_path')
        if not isinstance(relative, str):
            skips.append({'doc_id': doc.get('doc_id'), 'reason': 'missing relative_path'})
            continue
        root = (repo / 'data/raw/uet/markdown').resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Invalid source path for {doc.get("doc_id")}')
        src_bytes = path.read_bytes()
        digest = hashlib.sha256(src_bytes).hexdigest()
        if digest != doc.get('content_sha256'):
            raise ValueError(f'Registry SHA mismatch for {doc.get("doc_id")}')
        text = src_bytes.decode('utf-8-sig').replace('\r\n', '\n')
        found = list(HEADING.finditer(text))
        count = 0
        for index, heading in enumerate(found):
            start = heading.end()
            end = found[index + 1].start() if index + 1 < len(found) else len(text)
            section = text[start:end].strip()
            # Avoid training on tables, indices, private names, and tiny fragments.
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', section)
                          if 90 <= len(p.strip()) <= 650 and '\n|' not in p
                          and not re.search(r'^\s*\|', p, re.MULTILINE)]
            if not paragraphs:
                continue
            excerpt = paragraphs[0]
            title = (doc.get('title_hint') or Path(relative).stem).strip()
            heading_text = heading.group(1).strip('* _')
            fingerprint = hashlib.sha256((doc['doc_id'] + heading_text + excerpt).encode('utf-8')).hexdigest()[:12]
            candidates.append({
                'id': f'lora-{year}-{fingerprint}',
                'question': f'Theo văn bản "{title}", mục "{heading_text}" quy định gì trong năm học {year}-{year+1}?',
                'answer': excerpt,
                'doc_id': doc['doc_id'], 'as_of_year': year,
                'academic_year': f'{year}-{year+1}',
                'evidence_quote': excerpt,
                'source_file': (Path('data/raw/uet/markdown') / relative).as_posix(),
                'source_sha256': digest,
                'review_status': 'draft',
                'review_note': 'Verify scope, question quality, and answer against official source before approving.'
            })
            count += 1
            if count >= max_per_doc:
                break
    write_jsonl(output, candidates)
    return {'candidates': len(candidates), 'skipped_without_year': len(skips),
            'output': str(output), 'all_require_manual_review': True}
