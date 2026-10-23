"""Auditable temporal document registry for the ChronoReg Markdown corpus.

This is a document registry, not a legal effective-date inference engine.
Unreviewed hints are deliberately never promoted into binding legal facts.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_CORPUS = Path('data/raw/uet/markdown')
OUT = Path('data/versioning')
YEAR_RE = re.compile(r'năm\s+học\s*(20\d{2})\s*[-–—/]\s*(20\d{2})', re.IGNORECASE)
URL_RE = re.compile(r'(?im)^\s*(?:Nguồn|Source)\s*:\s*(https?://[^\s<>]+)')
DECISION_RE = re.compile(r'\b\d{1,5}\s*/\s*(?:QĐ|KH|TB|NQ|CV)[-–][\wĐđ]+', re.IGNORECASE)
RELATION_RE = re.compile(r'(thay\s+thế|sửa\s+đổi|bổ\s+sung|điều\s+chỉnh|căn\s+cứ\s+quyết\s+định\s+số)', re.IGNORECASE)
YEAR_DIR_RE = re.compile(r'20\d{2}')
TOPICS = ('tuition', 'scholarship', 'academic_calendar', 'research', 'admissions', 'training_rules', 'other')
RELATION_TYPES = ('supersedes', 'partially_supersedes', 'amends', 'references', 'same_series')


def hash_text(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{label} must be a YYYY-MM-DD string or null')
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError(f'Invalid {label}: {value}')
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('Expected object')
                rows.append(row)
            except (ValueError, TypeError) as exc:
                raise ValueError(f'{path}:{n}: {exc}') from exc
    return rows


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in records)
    path.write_text(text, encoding='utf-8')


def make_id(relative: Path) -> str:
    root = relative.with_suffix('').as_posix()
    ascii_name = ''.join(c for c in unicodedata.normalize('NFKD', root) if not unicodedata.combining(c)).lower()
    ascii_name = ascii_name.replace('đ', 'd')
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_name).strip('-')[:64]
    return f'uet-{slug}-{hashlib.sha256(root.encode("utf-8")).hexdigest()[:10]}'


def topic_of(path: Path) -> str:
    name = path.name.lower()
    if any(s in name for s in ('hoc_phi', 'học_phi', 'hoc_bong', 'học_bổng', 'chinh_sach_hoc_bong')):
        if 'hoc_phi' in name or 'học_phi' in name:
            return 'tuition' if not ('hoc_bong' in name or 'học_bổng' in name) else 'other'
        return 'scholarship'
    if any(s in name for s in ('ke_hoach_hoc_tap', 'thoi_khoa_bieu')):
        return 'academic_calendar'
    if any(s in name for s in ('nckh', 'de_tai')):
        return 'research'
    if 'quy_che_dao_tao' in name or 'quy_dinh_nop' in name:
        return 'training_rules'
    if any(s in name for s in ('tuyen_sinh','xet_tuyen','diem_trung_tuyen','ts_', 'nhap_hoc', 'dau_vao', 'nguyen_vong', 'hsa_')):
        return 'admissions'
    return 'other'


def kind_of(path: Path, raw: str = "") -> str:
    name = path.name.lower()
    if (any(s in name for s in ('danh_sach_', 'danh_muc_', 'gioi_thieu_', 'danh_sach_phong'))
            or ('danh sách sinh viên' in raw[:850].lower() and 'học bổng' in raw[:850].lower())):
        return 'directory_or_list'
    if 'ke_hoach_hoc_tap' in name or 'thoi_khoa_bieu' in name:
        return 'schedule'
    if any(s in name for s in ('du_kien', 'ke_hoach_thu_', 'tam_thu')):
        return 'provisional_notice'
    if any(s in name for s in ('quy_dinh_', 'quy_che_', 'dinh_muc_')):
        return 'potential_normative'
    if 'dieu_chinh_hoc_phi' in name:
        return 'individual_adjustment_check_scope'
    return 'notice_or_other'


def issuing_body_hint(raw: str, path: Path) -> str | None:
    if 'bo_gd' in path.name.lower() or 'bộ_gd' in path.name.lower():
        return 'BGDDT'
    beginning = raw[:1600].upper()
    if 'BỘ GIÁO DỤC VÀ ĐÀO TẠO' in beginning:
        return 'BGDDT'
    if 'TRƯỜNG ĐẠI HỌC CÔNG NGHỆ' in beginning or 'TRƯỜNG ĐH CÔNG NGHỆ' in beginning:
        return 'UET'
    if 'ĐẠI HỌC QUỐC GIA HÀ NỘI' in beginning:
        return 'VNU'
    return None


def _title(raw: str, path: Path) -> str:
    # PDF-to-Markdown often begins with the issuer/letterhead or "QUYẾT ĐỊNH".
    # Prefer a substantive title, never presenting a letterhead as the document title.
    terms = ('HỌC PHÍ', 'HỌC BỔNG', 'HỌC TẬP', 'NGHIÊN CỨU',
             'QUY CHẾ', 'ĐỊNH MỨC', 'TUYỂN SINH', 'KẾ HOẠCH', 'KHOA HỌC')
    boilerplate = ('ĐẠI HỌC QUỐC GIA', 'TRƯỜNG ĐẠI HỌC',
                   'CỘNG HOÀ', 'CỘNG HÒA', 'SỐ:', 'SAO Y', 'BỘ GIÁO DỤC')
    for line in raw[:8000].splitlines():
        clean = re.sub(r'<[^>]+>', '', line.strip()).strip(' #*_')
        upper = clean.upper()
        if (12 <= len(clean) <= 200 and not upper.startswith(boilerplate)
                and any(term in upper for term in terms)):
            return clean
    return path.stem.replace('_', ' ')


def infer_hints(raw: str, path: Path) -> dict[str, Any]:
    # A document may cite several academic years: do not collapse these silently.
    years = sorted({f'{a}-{b}' for a, b in YEAR_RE.findall(raw[:8000]) if int(b) == int(a) + 1})
    url_match = URL_RE.search(raw[:3000])
    url = url_match.group(1).rstrip('.,;)') if url_match else None
    rel_clues = []
    for match in RELATION_RE.finditer(raw):
        start, end = max(0, match.start() - 90), min(len(raw), match.end() + 170)
        context = ' '.join(raw[start:end].split())
        # Repeated OCR mentions or generic citations are evidence candidates only.
        if context not in rel_clues:
            rel_clues.append(context[:300])
        if len(rel_clues) >= 5:
            break
    return {'academic_year_candidates': years, 'source_url_in_text': url, 'relation_clues': rel_clues}


def inventory(corpus: Path) -> list[dict[str, Any]]:
    if not corpus.is_dir():
        raise FileNotFoundError(f'Markdown corpus not found: {corpus}')
    docs = []
    for path in sorted(corpus.rglob('*.md')):
        if path.is_symlink():
            raise ValueError(f'Symlink not permitted in source corpus: {path}')
        relative = path.relative_to(corpus)
        raw_bytes = path.read_bytes()
        raw = raw_bytes.decode('utf-8-sig')
        hint = infer_hints(raw, relative)
        folder = relative.parts[0] if len(relative.parts) > 1 else None
        folder_year = folder if folder and YEAR_DIR_RE.fullmatch(folder) else None
        category, kind = topic_of(relative), kind_of(relative, raw)
        docs.append({
            'doc_id': make_id(relative), 'relative_path': relative.as_posix(),
            'source_path': (DEFAULT_CORPUS / relative).as_posix(),
            'content_sha256': hash_text(raw_bytes), 'title_hint': _title(raw, relative),
            'topic_hint': category, 'document_kind_hint': kind,
            'issuing_body_hint': issuing_body_hint(raw, relative),
            'document_number_candidates': sorted(set(DECISION_RE.findall(raw[:2500]))),
            'eligible_for_policy_qa': (category in
                ('tuition','scholarship','academic_calendar','research','training_rules')
                and kind not in ('directory_or_list', 'individual_adjustment_check_scope',
                                 'provisional_notice')),
            'folder_year_hint': folder_year,
            'academic_year_candidates': hint['academic_year_candidates'],
            'source_url_in_text': hint['source_url_in_text'],
            'issued_date': None, 'effective_from': None, 'effective_until_exclusive': None,
            'scope': None, 'open_ended_verified': False, 'review_status': 'unreviewed',
            'relation_clues': hint['relation_clues'],
        })
    ids = [row['doc_id'] for row in docs]
    if len(set(ids)) != len(ids):
        raise ValueError('Document ID collision')
    return docs


def apply_reviews(docs: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> None:
    lookup = {d['doc_id']: d for d in docs}
    seen = set()
    for rev in reviews:
        id_ = rev.get('doc_id')
        if id_ in seen or id_ not in lookup:
            raise ValueError(f'Unknown or duplicate reviewed document ID: {id_}')
        seen.add(id_)
        d = lookup[id_]
        if rev.get('content_sha256') != d['content_sha256']:
            raise ValueError(f'Stale document review (SHA mismatch): {id_}')
        if rev.get('review_status') != 'verified_against_source':
            raise ValueError(f'Manual document review needs verified_against_source: {id_}')
        evidence = rev.get('evidence_reference', '')
        if not isinstance(evidence, str) or not evidence.strip() or 'REPLACE' in evidence.upper():
            raise ValueError(f'Missing or placeholder evidence_reference for {id_}')
        # Anything not explicitly confirmed stays unknown.
        allowed = {'doc_id','content_sha256','review_status','evidence_reference','issued_date',
                   'effective_from','effective_until_exclusive','open_ended_verified','scope','academic_year'}
        if extra := (rev.keys() - allowed):
            raise ValueError(f'Unrecognized manual metadata fields for {id_}: {extra}')
        for key in ('issued_date', 'effective_from', 'effective_until_exclusive'):
            _iso(rev.get(key), key)
        start, end = rev.get('effective_from'), rev.get('effective_until_exclusive')
        if start and end and end <= start:
            raise ValueError(f'Invalid effective interval: {id_}')
        if end and not start:
            raise ValueError(f'Cannot set an end without start: {id_}')
        if rev.get('open_ended_verified') and end:
            raise ValueError(f'Open end conflicts with explicit end: {id_}')
        academic_year = rev.get('academic_year')
        if (academic_year is not None and (not re.fullmatch(r'20\d{2}-20\d{2}', academic_year)
             or int(academic_year[5:]) != int(academic_year[:4]) + 1)):
            raise ValueError(f'Invalid academic_year: {id_}')
        for key in ('issued_date','effective_from','effective_until_exclusive','scope','open_ended_verified'):
            if key in rev:
                d[key] = rev[key]
        d['academic_year_verified'] = academic_year
        d['review_status'] = 'verified_against_source'
        d['evidence_reference'] = rev['evidence_reference']


def policy_qa_readiness(doc: dict[str, Any]) -> str:
    """Readiness of a document for reviewed, year-scoped retrieval.

    This is not a legal ruling that a regulation is currently in force. For an
    as-of query, the verified effective interval and population scope must
    still be evaluated independently.
    """
    if not doc['eligible_for_policy_qa']:
        return 'excluded_from_policy_qa'
    if doc['review_status'] != 'verified_against_source':
        return 'unreviewed'
    if not isinstance(doc.get('scope'), str) or not doc['scope'].strip():
        return 'missing_verified_scope'
    if not (doc.get('academic_year_verified') or doc.get('effective_from')):
        return 'missing_verified_time'
    return 'reviewed_scope_and_time'


def validate_relations(docs: list[dict[str, Any]], relations: list[dict[str, Any]],
                       corpus: Path | None = None) -> list[dict[str, Any]]:
    lookup = {d['doc_id']: d for d in docs}
    graph: dict[str, list[str]] = {}
    seen = set()
    for relation in relations:
        src, target = relation.get('from_doc_id'), relation.get('to_doc_id')
        typ = relation.get('relation_type')
        if src not in lookup or target not in lookup or src == target:
            raise ValueError(f'Invalid relation endpoints: {src} -> {target}')
        if typ not in RELATION_TYPES:
            raise ValueError(f'Invalid relation type: {typ}')
        key = (src, target, typ)
        if key in seen:
            raise ValueError(f'Duplicate relation: {key}')
        seen.add(key)
        quote = relation.get('evidence_quote', '')
        if (relation.get('review_status') != 'verified_against_source'
                or not isinstance(quote, str) or not quote.strip() or 'REPLACE' in quote.upper()):
            raise ValueError(f'Relation missing verified evidence: {key}')
        if corpus is not None:
            from_path = corpus / lookup[src]['relative_path']
            source_text = ' '.join(from_path.read_text(encoding='utf-8-sig').split())
            if ' '.join(quote.split()) not in source_text:
                raise ValueError(f'Evidence quote not present in source Markdown: {key}')
        if (relation.get('from_sha256') != lookup[src]['content_sha256'] or
                relation.get('to_sha256') != lookup[target]['content_sha256']):
            raise ValueError(f'Stale relation approval, source contents changed: {key}')
        if typ in ('supersedes', 'partially_supersedes', 'amends'):
            graph.setdefault(src, []).append(target)
        if not relation.get('applicability_scope') and typ in ('partially_supersedes', 'amends'):
            raise ValueError(f'Amendment missing applicability_scope: {key}')
    visited, visiting = set(), set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f'Temporal relation cycle detected at {node}')
        if node in visited:
            return
        visiting.add(node)
        for neighbor in graph.get(node, []):
            visit(neighbor)
        visiting.remove(node)
        visited.add(node)
    for n in graph:
        visit(n)
    return relations


def build(root: Path, *, corpus: Path | None = None, out: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    corpus = corpus if corpus is not None else root / DEFAULT_CORPUS
    out = out if out is not None else root / OUT
    docs = inventory(corpus)
    # Only human-approved edits belong in these files. Do not write over them.
    reviews = read_jsonl(out / 'reviewed_documents.jsonl')
    relations = read_jsonl(out / 'approved_relations.jsonl')
    apply_reviews(docs, reviews)
    for d in docs:
        d['policy_qa_readiness'] = policy_qa_readiness(d)
        d['policy_qa_ready'] = d['policy_qa_readiness'] == 'reviewed_scope_and_time'
    validate_relations(docs, relations, corpus)
    # Generate in memory; write only after entire review/graph validation passes.
    candidates = []
    for d in docs:
        for clue in d.pop('relation_clues'):
            candidates.append({'doc_id': d['doc_id'], 'content_sha256': d['content_sha256'],
                               'evidence_excerpt': clue, 'status': 'needs_review_not_a_relation'})
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / 'documents.jsonl', docs)
    write_jsonl(out / 'relation_review_queue.jsonl', candidates)
    write_jsonl(out / 'relations.jsonl', relations)
    import csv
    with (out / 'review_worklist.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['doc_id','relative_path','topic_hint','document_kind_hint','folder_year_hint',
                         'academic_year_candidates','document_number_candidates','source_url_in_text',
                         'review_status','policy_qa_readiness','sha256','action'])
        for d in docs:
            writer.writerow([d['doc_id'], d['relative_path'], d['topic_hint'], d['document_kind_hint'],
                             d['folder_year_hint'] or '', '; '.join(d['academic_year_candidates']),
                             '; '.join(d['document_number_candidates']), d['source_url_in_text'] or '',
                             d['review_status'], d['policy_qa_readiness'], d['content_sha256'],
                             ('OUT_OF_SCOPE_POLICY_QA' if not d['eligible_for_policy_qa']
                              else 'CHECK_ORIGINAL_PDF_AND_SCOPE' if d['review_status'] == 'unreviewed'
                              else 'CHECK_MISSING_METADATA' if not d['policy_qa_ready']
                              else 'REVIEWED_READY_FOR_YEAR_SCOPED_RETRIEVAL')])
    with (out / 'coverage_by_folder.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['folder_year_hint', 'topic_hint', 'document_count'])
        for (year, topic), n in sorted(Counter((d['folder_year_hint'] or 'unassigned', d['topic_hint'])
                                                for d in docs).items()):
            writer.writerow([year, topic, n])
    counts = {'total': len(docs), 'verified': sum(d['review_status'] == 'verified_against_source' for d in docs),
              'approved_relations': len(relations), 'relation_clues_to_review': len(candidates),
              'policy_qa_ready': sum(d['policy_qa_ready'] for d in docs),
              'by_topic': dict(sorted(Counter(d['topic_hint'] for d in docs).items())),
              'by_folder_year': dict(sorted(Counter(d['folder_year_hint'] or 'unassigned' for d in docs).items())),
              'docs_without_academic_year': sum(not d['academic_year_candidates'] for d in docs),
              'docs_with_ambiguous_academic_year': sum(len(d['academic_year_candidates']) > 1 for d in docs)}
    (out / 'build_report.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return counts


def query(docs: list[dict[str, Any]], *, topic: str | None = None,
          academic_year: str | None = None, folder_year: str | None = None,
          as_of: str | None = None) -> list[dict[str, Any]]:
    if topic and topic not in TOPICS:
        raise ValueError(f'Unknown topic: {topic}')
    _iso(as_of, 'as_of')
    rows = []
    for doc in docs:
        if topic and doc['topic_hint'] != topic:
            continue
        if folder_year and doc['folder_year_hint'] != folder_year:
            continue
        year = doc.get('academic_year_verified') or None
        if academic_year and not (year == academic_year if year else academic_year in doc['academic_year_candidates']):
            continue
        d = dict(doc)
        if as_of:
            if d['review_status'] != 'verified_against_source' or not d.get('effective_from'):
                d['temporal_match'] = 'unknown_unverified'
            elif as_of < d['effective_from']:
                d['temporal_match'] = 'outside_verified_interval'
            elif d.get('effective_until_exclusive') and as_of >= d['effective_until_exclusive']:
                d['temporal_match'] = 'outside_verified_interval'
            elif d.get('effective_until_exclusive') or d.get('open_ended_verified'):
                d['temporal_match'] = 'inside_verified_interval'
            else:
                d['temporal_match'] = 'unknown_end_date'
        rows.append(d)
    return rows


def export_chunks(docs: list[dict[str, Any]], root: Path, destination: Path,
                  max_chars: int = 3500, include_non_policy: bool = False,
                  include_unreviewed: bool = False) -> int:
    if max_chars < 300:
        raise ValueError('max_chars must be >= 300')
    chunks = []
    for doc in docs:
        if not include_non_policy and not doc['eligible_for_policy_qa']:
            continue
        # The published output is intentionally empty until enough metadata
        # has been verified. A separate draft export is opt-in for development.
        if not include_unreviewed and not doc.get('policy_qa_ready', False):
            continue
        p = root / DEFAULT_CORPUS / doc['relative_path']
        content = p.read_bytes()
        if hash_text(content) != doc['content_sha256']:
            raise ValueError(f'Corpus changed after inventory: {p}')
        text = content.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        # Character offsets link back to the original Markdown, even for long lines.
        for start in range(0, len(text), max_chars):
            part = text[start:start+max_chars]
            if not part.strip():
                continue
            chunks.append({
                'chunk_id': f"{doc['doc_id']}:{start}", 'doc_id': doc['doc_id'],
                'start_char': start, 'end_char': start + len(part), 'text': part,
                'content_sha256': doc['content_sha256'], 'topic_hint': doc['topic_hint'],
                'academic_year_candidates': doc['academic_year_candidates'],
                'academic_year_verified': doc.get('academic_year_verified'),
                'review_status': doc['review_status'], 'effective_from': doc['effective_from'],
                'eligible_for_policy_qa': doc['eligible_for_policy_qa'],
                'policy_qa_ready': bool(doc.get('policy_qa_ready', False)),
                'policy_qa_readiness': doc.get('policy_qa_readiness', 'unreviewed'),
                'scope': doc.get('scope'),
                'effective_until_exclusive': doc['effective_until_exclusive'],
                'source_url_in_text': doc['source_url_in_text'],
            })
    write_jsonl(destination, chunks)
    return len(chunks)
