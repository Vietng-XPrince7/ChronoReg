"""Human QA CSV interchange must never confer approval without valid review."""
import csv
import json

import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.review_packet import generate_packet
from src.lora.review_sheet import export_sheet, import_sheet
from tests.test_lora_review_packet import example


def setup(tmp_path):
    source, registry, holds, prose, tables, packet, manifest = example(tmp_path)
    generate_packet(tmp_path, prose, tables, registry, holds, packet, manifest)
    sheet = tmp_path / 'human_sheet.csv'
    combo = tmp_path / 'combined.jsonl'
    decisions = tmp_path / 'decisions.jsonl'
    args = (tmp_path, prose, tables, registry, holds, packet)
    return source, args, sheet, combo, decisions


def modify(sheet, fn):
    with sheet.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0])
    fn(rows)
    with sheet.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def approve_table(rows):
    table = next(r for r in rows if r['source_kind'] == 'table')
    table.update({
        'decision': 'approve',
        'reviewed_question': 'Theo văn bản năm học 2025–2026, học phí của khóa QH-2025 là bao nhiêu?',
        'verified_answer': '2.350.000đ',
        'reviewer_name': 'QA Reviewer', 'review_date': '2026-10-23',
        'review_note': 'Đã đối chiếu nội dung và bảng với văn bản gốc cho năm học.',
    })


def test_export_is_pending_and_source_untouched(tmp_path):
    source, args, sheet, combo, decisions = setup(tmp_path)
    before = source.read_bytes()
    result = export_sheet(*args, sheet)
    assert result['rows'] == 2 and result['approved'] == 0
    with sheet.open(encoding='utf-8-sig', newline='') as f:
        data = list(csv.DictReader(f))
    assert all(x['decision'] == 'pending' for x in data)
    assert source.read_bytes() == before
    assert not combo.exists() and not decisions.exists()


def test_pending_import_contains_no_approved_QA(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    result = import_sheet(*args, sheet, combo, decisions)
    assert result['approved'] == 0 and result['decisions']['pending'] == 2
    assert len(read_jsonl(combo)) == 2
    assert all(r['decision'] == 'pending' for r in read_jsonl(decisions))
    assert not result['benchmark_isolation_certified']


def test_valid_human_review_is_bound_to_exact_candidate(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, approve_table)
    report = import_sheet(*args, sheet, combo, decisions)
    assert report['approved'] == 1 and report['decisions']['pending'] == 1
    row = next(x for x in read_jsonl(decisions) if x['decision'] == 'approve')
    assert row['candidate_sha256'] and row['reviewer'] == 'QA Reviewer'


def test_source_mutation_blocks_import(tmp_path):
    source, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    source.write_text(source.read_text(encoding='utf-8') + '\nmodified', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA'):
        import_sheet(*args, sheet, combo, decisions)
    assert not combo.exists() and not decisions.exists()


def test_packet_mutation_detected_at_export(tmp_path):
    _, args, sheet, _, _ = setup(tmp_path)
    packet = args[-1]
    modify(packet, lambda rows: rows[0].update({'answer_draft': 'wrong'}))
    with pytest.raises(ValueError, match='packet field answer_draft'):
        export_sheet(*args, sheet)
    assert not sheet.exists()


def test_immutable_sheet_columns_cannot_be_modified(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, lambda rows: rows[0].update({'doc_id': 'fake-source'}))
    with pytest.raises(ValueError, match='immutable review column'):
        import_sheet(*args, sheet, combo, decisions)
    assert not combo.exists() and not decisions.exists()


def test_duplicate_and_missing_rows_fail_closed(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, lambda rows: rows.__setitem__(1, dict(rows[0])))
    with pytest.raises(ValueError, match='Unknown or duplicated'):
        import_sheet(*args, sheet, combo, decisions)
    assert not combo.exists()


def test_pending_cannot_hold_unresolved_manual_changes(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, lambda rows: rows[0].update({'review_note': 'I checked it'}))
    with pytest.raises(ValueError, match='pending decision contains edits'):
        import_sheet(*args, sheet, combo, decisions)


def test_no_approval_from_untouched_question(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    def unchanged(rows):
        approve_table(rows)
        t = next(x for x in rows if x['source_kind'] == 'table')
        t['reviewed_question'] = t['question_draft']
    modify(sheet, unchanged)
    with pytest.raises(ValueError, match='rewriting draft question'):
        import_sheet(*args, sheet, combo, decisions)


def test_rejected_row_requires_named_reviewer_and_note(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, lambda rows: rows[0].update({'decision': 'reject'}))
    with pytest.raises(ValueError, match='reviewer is required'):
        import_sheet(*args, sheet, combo, decisions)


def test_reject_with_proper_review(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    def reject(rows):
        rows[0].update({'decision': 'reject', 'reviewer_name': 'QA Reviewer',
                        'review_date': '2026-10-23',
                        'review_note': 'Rejected because this excerpt lacks the correct decision context.'})
    modify(sheet, reject)
    result = import_sheet(*args, sheet, combo, decisions)
    assert result['approved'] == 0 and result['decisions']['reject'] == 1


def test_benchmark_exact_overlap_prevents_approval(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, approve_table)
    t = read_jsonl(args[2])[0]
    with sheet.open(encoding='utf-8-sig', newline='') as f:
        question = next(r['reviewed_question'] for r in csv.DictReader(f) if r['source_kind']=='table')
    benchmark = tmp_path / 'benchmark.jsonl'
    write_jsonl(benchmark,[{'id':'b1','question':question,'gold_answer':'2.350.000đ',
                            'gold_doc_id':t['doc_id'],'type':'historical','as_of_year':2025}])
    with pytest.raises(ValueError, match='held-out benchmark'):
        import_sheet(*args, sheet, combo, decisions, benchmark)
    assert not combo.exists() and not decisions.exists()


def test_existing_outputs_cannot_be_overwritten(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    with pytest.raises(FileExistsError):
        export_sheet(*args, sheet)
    combo.write_text('KEEP',encoding='utf-8')
    with pytest.raises(FileExistsError):
        import_sheet(*args, sheet, combo, decisions)
    assert combo.read_text(encoding='utf-8') == 'KEEP' and not decisions.exists()


def test_benchmark_free_approval_not_marked_isolation_certified(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    modify(sheet, approve_table)
    result = import_sheet(*args, sheet, combo, decisions)
    assert result['approved'] == 1
    assert result['benchmark_provided'] is False
    assert result['benchmark_isolation_certified'] is False
    assert result['approved_training_exported'] is False


def test_sheet_with_formula_edit_rejected(tmp_path):
    _, args, sheet, combo, decisions = setup(tmp_path)
    export_sheet(*args, sheet)
    def bad(rows):
        approve_table(rows)
        t = next(r for r in rows if r['source_kind'] == 'table')
        t['verified_answer'] = '=HYPERLINK("https://invalid.test")'
    modify(sheet, bad)
    with pytest.raises(ValueError, match='spreadsheet formula'):
        import_sheet(*args, sheet, combo, decisions)
