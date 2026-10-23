"""GPU integration smoke: synthetic two-stage continual LoRA, no UET data.

Run from the repository root in Ubuntu WSL2 after installing the LoRA dependencies.
All generated files are contained in a temporary Linux directory and removed afterwards.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import torch
import yaml

from .contracts import write_jsonl
from .modeling import LoRAAnswerer, train_stage
from .prepare import prepare


def main() -> None:
    if not torch.cuda.is_available():
        raise SystemExit('CUDA is required for this integration smoke')
    root = Path.cwd()
    cfg_file = root / 'configs/lora.yaml'
    if not cfg_file.is_file():
        raise SystemExit('Run from the ChronoReg repository root')
    cfg = yaml.safe_load(cfg_file.read_text(encoding='utf-8'))['lora']
    if cfg['base_model'] != 'Qwen/Qwen2.5-0.5B-Instruct':
        raise SystemExit('Smoke is scoped to the tested Qwen 0.5B baseline')
    cfg = dict(cfg, epochs=1, gradient_accumulation_steps=1,
               max_seq_length=192, train_batch_size=1)
    with tempfile.TemporaryDirectory(prefix='chronoreg-lora-synthetic-') as d:
        workspace = Path(d)
        docs = workspace / 'data/raw/synthetic'
        docs.mkdir(parents=True)
        rows = []
        for year in (2025, 2026):
            evidence = f'Đây là dữ liệu tổng hợp kỹ thuật cho năm {year}-{year+1}; không phải quy định UET.'
            source = docs / f'synthetic-{year}.md'
            source.write_text(evidence + '\n', encoding='utf-8')
            rows.append({
                'id': f'synthetic-{year}',
                'question': f'Kiểm tra kỹ thuật năm {year}-{year+1} có phải quy định UET không?',
                'answer': 'Không. Đây là một phép thử kỹ thuật tổng hợp.',
                'doc_id': f'synthetic-doc-{year}',
                'as_of_year': year,
                'academic_year': f'{year}-{year+1}',
                'evidence_quote': evidence,
                'source_file': str(source.relative_to(workspace)).replace('\\', '/'),
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'review_status': 'approved',  # in isolated synthetic workspace only
            })
        train = workspace / 'train.jsonl'
        benchmark = workspace / 'heldout.jsonl'
        write_jsonl(train, rows)
        write_jsonl(benchmark, [{
            'id': 'synthetic-held-out',
            'question': 'Đây có phải kết quả đánh giá UET thật không?',
            'gold_answer': 'Không.',
            'gold_doc_id': 'synthetic-heldout-doc',
            'as_of_year': 2025,
            'type': 'historical',
        }])
        prepared = workspace / 'prepared'
        manifest = prepare(workspace, train, benchmark, prepared, [2025, 2026])
        assert manifest['total'] == 2
        checkpoints = workspace / 'checkpoints'
        print('SYNTHETIC QA ONLY; no UET content, no performance claims', flush=True)
        for year in (2025, 2026):
            previous = checkpoints / 'year-2025' if year == 2026 else None
            result = train_stage(cfg, prepared, year, checkpoints, previous=previous)
            assert (checkpoints / f'year-{year}' / 'adapter_model.safetensors').stat().st_size > 0
            print(json.dumps({'stage': year, 'saved': True, 'training_rows': result['training_rows']}, ensure_ascii=False), flush=True)
            torch.cuda.empty_cache()
        answerer = LoRAAnswerer(cfg, checkpoints / 'year-2026', allow_cpu=False)
        outcome = answerer.answer('Đây có phải câu hỏi kỹ thuật tổng hợp?', 2025)
        assert isinstance(outcome['answer'], str)
        assert outcome['sources'] == []
        print(json.dumps({'adapter_reload': 'PASS', 'answer_contract': 'PASS',
                          'synthetic': True, 'no_benchmark_metric': True,
                          'gpu_peak_allocated_mib': round(torch.cuda.max_memory_allocated() / 1048576)}, ensure_ascii=False), flush=True)
    print('PASS: two sequential synthetic stages saved and final adapter reloaded; temporary files removed.', flush=True)


if __name__ == '__main__':
    main()
