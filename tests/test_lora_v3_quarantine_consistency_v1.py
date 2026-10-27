"""Fail-closed V3 quarantine consistency checks. Does not sign or approve QA."""
import pytest
from src.lora.release_guard import require_curated_v3_dispositions

HELD = 'fact-review-2024-026'


def samples():
    decisions = [{'candidate_id': f'fact-review-2024-{i:03d}',
                  'decision': 'approve'} for i in range(1, 25)]
    decisions.append({'candidate_id': HELD, 'decision': 'quarantine'})
    rows = [{'id': entry['candidate_id']} for entry in decisions[:-1]]
    return decisions, rows


def test_24_approved_and_one_quarantined_passes():
    decisions, rows = samples()
    binding = require_curated_v3_dispositions(decisions, rows)
    assert set(binding) == {item['candidate_id'] for item in decisions}
    assert binding[HELD]['decision'] == 'quarantine'


def test_quarantined_qa_must_not_be_labeled_approved():
    decisions, rows = samples()
    decisions[-1]['decision'] = 'approve'
    with pytest.raises(RuntimeError, match='must be quarantined'):
        require_curated_v3_dispositions(decisions, rows)


def test_missing_quarantine_decision_blocks():
    decisions, rows = samples()
    decisions[-1]['decision'] = 'reject'
    with pytest.raises(RuntimeError, match='must be quarantined'):
        require_curated_v3_dispositions(decisions, rows)


def test_another_candidate_unapproved_blocks():
    decisions, rows = samples()
    decisions[3]['decision'] = 'pending'
    with pytest.raises(RuntimeError, match='24 approvals'):
        require_curated_v3_dispositions(decisions, rows)


def test_quarantined_qa_in_training_blocks():
    decisions, rows = samples()
    rows[-1]['id'] = HELD
    with pytest.raises(RuntimeError, match='curated IDs'):
        require_curated_v3_dispositions(decisions, rows)


def test_legacy_ids_block_even_with_disposition():
    decisions, rows = samples()
    decisions[0]['candidate_id'] = 'train-2022-001'
    rows[0]['id'] = 'train-2022-001'
    with pytest.raises(RuntimeError, match='curated IDs'):
        require_curated_v3_dispositions(decisions, rows)


def test_duplicate_and_missing_decision_ids_block():
    decisions, rows = samples()
    decisions[1]['candidate_id'] = decisions[0]['candidate_id']
    with pytest.raises(RuntimeError, match='coverage'):
        require_curated_v3_dispositions(decisions, rows)
    decisions, rows = samples()
    decisions.pop()
    with pytest.raises(RuntimeError, match='coverage'):
        require_curated_v3_dispositions(decisions, rows)


def test_unexpected_training_id_blocks():
    decisions, rows = samples()
    rows[-1]['id'] = 'forged-2024-999'
    with pytest.raises(RuntimeError, match='curated IDs'):
        require_curated_v3_dispositions(decisions, rows)


def test_no_training_authorization_in_helper_source():
    from pathlib import Path
    import src.lora.release_guard as guard
    text = Path(guard.__file__).read_text(encoding='utf-8')
    assert "by_id[held].get('decision') != 'quarantine'" in text
    assert "require_full_benchmark_review(repo, release, bench)" in text
    assert "require_overlap_inventory_binding(repo, release, leak_rows, bench, decisions_rows)" in text
