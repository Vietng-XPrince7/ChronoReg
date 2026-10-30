"""Review batch 3: source-backed tuition metadata and normalized tables."""
from pathlib import Path
from src.versioning.core import read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def test_batch3_year_scoping_and_safe_unknown_dates():
    rows = read_jsonl(ROOT / 'data/versioning/reviewed_documents.jsonl')
    matches = [r for r in rows if r['doc_id'] in (
        'uet-2024-dinh-muc-hoc-phi-dai-hoc-2024-82e336a2fd',
        'uet-2024-dinh-muc-hoc-phi-sau-dai-hoc-2024-58724ca756')]
    assert len(matches) == 2
    for r in matches:
        assert r['academic_year'] == '2024-2025'
        assert r['issued_date'] is None
        assert r['effective_from'] is None
        assert r['effective_until_exclusive'] is None
        assert not r['open_ended_verified']
        assert 'uet.vnu.edu.vn' in r['evidence_reference']


def test_batch3_postgraduate_tables_and_undergraduate_cohort():
    d = ROOT / 'data/raw/uet/markdown/2024'
    grad = (d / 'Dinh_muc_hoc_phi_sau_dai_hoc_2024.md').read_text(encoding='utf-8')
    undergrad = (d / 'Dinh_muc_hoc_phi_dai_hoc_2024.md').read_text(encoding='utf-8')
    assert '|1|Khóa tuyển sinh từ năm 2021 trở về trước|24.600.000|767.000|' in grad
    assert '|2|Khóa tuyển sinh trong năm 2022, năm 2023 và năm 2024|33.000.000|1.076.000|' in grad
    assert '40.000.000|1.218.000' in grad
    assert 'Khóa QH-2019 đến 2021-I/CQ|35.000.000|800.000|' in undergrad
    assert 'Khóa QH-2022-I/CQ|35.000.000|800.000|' in undergrad
    assert '32.000.000|869.000' in undergrad
    assert '40.000.000|1.076.000' in undergrad
