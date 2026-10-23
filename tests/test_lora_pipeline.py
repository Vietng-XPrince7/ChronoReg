"""LoRA data and temporal contracts, fully offline (no torch/model download)."""
import hashlib
import json
from pathlib import Path

import pytest

from src.lora.candidates import propose
from src.lora.contracts import read_jsonl, validate_training, write_jsonl
from src.lora.evaluate import evaluate_stages
from src.lora.metrics import forgetting, token_f1
from src.lora.modeling import check_previous, tokenize_qa, train_stage
from src.lora.prepare import prepare


def fixture(repo: Path):
    src = repo / 'data/raw/uet/markdown/2025/tuition.md'
    src.parent.mkdir(parents=True)
    evidence = 'Mức thu được áp dụng cho năm học 2025-2026 theo chương trình đào tạo đã phê duyệt.'
    src.write_text('## Điều 1. Học phí\n\n' + evidence + ' ' + 'Tài liệu minh họa. '*6, encoding='utf-8')
    txt = src.read_text(encoding='utf-8')
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    item = dict(id='qa-1', question='Văn bản học phí áp dụng thế nào năm học 2025-2026?',
                answer='Áp dụng theo chương trình đào tạo đã phê duyệt.',
                doc_id='uet-hp-2025', as_of_year=2025, academic_year='2025-2026',
                evidence_quote=evidence, source_file='data/raw/uet/markdown/2025/tuition.md',
                source_sha256=digest, review_status='approved')
    bench = dict(id='bench-1', question='Câu hỏi kiểm tra độc lập?', gold_answer='Câu trả lời kiểm tra',
                 gold_doc_id='uet-hp-2025', as_of_year=2025, type='historical',
                 outdated_answer='Lỗi thời')
    return item, bench, txt, digest


def test_candidate_stays_draft(tmp_path):
    item, bench, text, digest = fixture(tmp_path)
    registry = tmp_path / 'data/versioning/documents.jsonl'
    write_jsonl(registry, [{'doc_id': 'uet-hp-2025', 'relative_path': '2025/tuition.md',
                            'content_sha256': digest, 'policy_qa_ready': True,
                            'academic_year_verified': '2025-2026',
                            'review_status': 'verified_against_source',
                            'title_hint': 'Học phí 2025'}])
    output = tmp_path / 'out/candidates.jsonl'
    result = propose(tmp_path, registry, output)
    assert result['candidates'] == 1
    candidate = read_jsonl(output)[0]
    assert candidate['review_status'] == 'draft'
    assert candidate['evidence_quote'] in text
    with pytest.raises(ValueError, match='manually approved'):
        validate_training([candidate], tmp_path)


def test_unreviewed_registry_not_proposed(tmp_path):
    item, bench, text, digest = fixture(tmp_path)
    registry = tmp_path / 'docs.jsonl'
    write_jsonl(registry, [{'doc_id':'x','relative_path':'2025/tuition.md',
                            'content_sha256':digest,'policy_qa_ready':False,
                            'review_status':'unreviewed','academic_year_verified':'2025-2026'}])
    assert propose(tmp_path, registry, tmp_path/'out.jsonl')['candidates'] == 0


def test_validate_requires_evidence_sha(tmp_path):
    item, _, _, _ = fixture(tmp_path)
    assert len(validate_training([item], tmp_path)) == 1
    item['source_sha256'] = 'incorrect'
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        validate_training([item], tmp_path)


def test_year_mismatch_rejected(tmp_path):
    item, _, _, _ = fixture(tmp_path)
    item['academic_year'] = '2024-2025'
    with pytest.raises(ValueError, match='disagree'):
        validate_training([item], tmp_path)


def test_benchmark_leakage(tmp_path):
    item, bench, _, _ = fixture(tmp_path)
    bench['question'] = item['question']
    with pytest.raises(ValueError, match='overlaps'):
        validate_training([item], tmp_path, [bench])


def test_prepare_requires_every_year_and_benchmark(tmp_path):
    item, bench, _, _ = fixture(tmp_path)
    train = tmp_path/'approved.jsonl'
    eval_file = tmp_path/'benchmark.jsonl'
    write_jsonl(train, [item])
    write_jsonl(eval_file, [bench])
    with pytest.raises(ValueError, match='No approved training'):
        prepare(tmp_path, train, eval_file, tmp_path/'out', [2024,2025])
    manifest = prepare(tmp_path, train, eval_file, tmp_path/'out', [2025])
    assert manifest['counts']['2025'] == 1
    assert len(read_jsonl(tmp_path/'out/train_2025.jsonl')) == 1


def test_dry_run_requires_no_torch(tmp_path):
    item, bench, _, _ = fixture(tmp_path)
    train = tmp_path/'train.jsonl'
    eval_file = tmp_path/'eval.jsonl'
    write_jsonl(train, [item]); write_jsonl(eval_file,[bench])
    prepared = tmp_path/'prepared'
    prepare(tmp_path, train, eval_file, prepared, [2025])
    cfg = {'base_model':'Qwen/Qwen2.5-0.5B-Instruct'}
    result = train_stage(cfg, prepared, 2025, tmp_path/'checkpoints', dry_run=True)
    assert result['training_rows'] == 1 and result['model_loaded'] is False
    assert not (tmp_path/'checkpoints').exists()


def test_mutated_prepared_file_cannot_train(tmp_path):
    item, bench, _, _ = fixture(tmp_path)
    write_jsonl(tmp_path/'train.jsonl',[item]); write_jsonl(tmp_path/'eval.jsonl',[bench])
    prepare(tmp_path,tmp_path/'train.jsonl',tmp_path/'eval.jsonl',tmp_path/'out',[2025])
    f = tmp_path/'out/train_2025.jsonl'
    f.write_text(f.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        train_stage({'base_model':'x'},tmp_path/'out',2025,tmp_path/'checkpoints',dry_run=True)


def test_previous_adapter_contract(tmp_path):
    p = tmp_path/'year-2024'; p.mkdir()
    (p/'adapter_config.json').write_text('{}')
    (p/'stage.json').write_text(json.dumps({'year':2024,'model':'x','model_revision':'main','strategy':'sequential'}))
    check_previous(p,2025,{'base_model':'x'})
    with pytest.raises(ValueError,match='previous year'):
        check_previous(p,2026,{'base_model':'x'})


class ToyTokenizer:
    eos_token_id = 99
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        return 'system user assistant:'
    def __call__(self, text, add_special_tokens=False):
        return {'input_ids': list(range(1, len(text.split())+1))}


def test_assistant_only_loss_mask():
    row={'id':'x','question':'?','answer':'a b c','as_of_year':2025}
    encoded=tokenize_qa(ToyTokenizer(),row,40)
    assert encoded['labels'][:3] == [-100,-100,-100]
    assert encoded['labels'][-1] == 99
    assert len(encoded['labels']) == len(encoded['input_ids'])


def test_token_f1_and_forgetting():
    assert token_f1('Học phí 2025', 'Học phí 2025') == 1
    h={2022:{2022:0.8},2023:{2022:0.6,2023:0.7},2024:{2022:0.75,2023:0.5,2024:0.9}}
    assert forgetting(h)['2023']['2022'] == pytest.approx(0.2)
    assert forgetting(h)['2024']['2022'] == pytest.approx(0.05)


def test_evaluation_never_uses_future_benchmark(tmp_path):
    _, bench, _, _ = fixture(tmp_path)
    older = dict(bench, id='older', as_of_year=2024, question='old?')
    write_jsonl(tmp_path/'bench.jsonl',[older,bench])
    calls=[]
    def predict(stage, q, year):
        calls.append((stage,year))
        return 'Câu trả lời kiểm tra'
    result=evaluate_stages(tmp_path/'bench.jsonl',[2024,2025],predict,tmp_path/'eval')
    assert calls==[(2024,2024),(2025,2024),(2025,2025)]
    assert result['count']==3


def test_unsafe_source_path(tmp_path):
    item, _, _, _=fixture(tmp_path)
    item['source_file']='../escape.txt'
    with pytest.raises(ValueError,match='escapes'):
        validate_training([item],tmp_path)
