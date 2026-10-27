"""Isolated, synthetic two-stage LoRA GPU smoke. Never uses UET data.

This tests the Hugging Face/PEFT backend independently of the owner-released
training entry point. It MUST NOT invoke train_stage or bypass its release guard.
Temporary synthetic adapters are removed on exit. No benchmark scoring.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import json
import tempfile
from pathlib import Path

MODEL = 'Qwen/Qwen2.5-0.5B-Instruct'
STAGES = (2025, 2026)
SYNTHETIC_ANSWER = 'Không. Đây chỉ là phép thử kỹ thuật tổng hợp, không phải quy định UET.'


def synthetic_qa(year: int) -> dict:
    if year not in STAGES:
        raise ValueError('Only synthetic 2025/2026 stages are permitted')
    return {
        'id': f'synthetic-gpu-smoke-{year}',
        'question': 'Đây có phải quy định thực tế của UET không?',
        'answer': SYNTHETIC_ANSWER,
        'as_of_year': year,
    }


def _read_config(repo: Path) -> dict:
    file = repo / 'configs/lora.yaml'
    if not file.is_file():
        raise FileNotFoundError('Expected configs/lora.yaml; run from the ChronoReg repository root')
    import yaml
    cfg = yaml.safe_load(file.read_text(encoding='utf-8'))['lora']
    if cfg['base_model'] != MODEL or cfg['strategy'] != 'sequential':
        raise ValueError('Synthetic GPU smoke is scoped to the sequential Qwen 0.5B backend')
    if cfg.get('model_dtype') != 'float16':
        raise ValueError('This GPU smoke expects float16. Do not change the experiment config for the smoke.')
    return cfg


def preflight(repo: Path) -> dict:
    cfg = _read_config(repo)
    modules = ('torch', 'transformers', 'peft', 'accelerate', 'yaml', 'safetensors')
    found = {name: importlib.util.find_spec(name) is not None for name in modules}
    gpu = {'available': False, 'name': None}
    if found['torch']:
        import torch
        gpu = {'available': bool(torch.cuda.is_available()),
               'name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    return {'mode': 'SYNTHETIC_GPU_PREFLIGHT', 'model': cfg['base_model'],
            'dependencies': found, 'gpu': gpu,
            'ready': all(found.values()) and gpu['available'],
            'production_training_authorized': False,
            'uet_data_accessed': False}




def _finite_training_logs(log_history: list[dict]) -> dict:
    """Fail if a logged optimizer step skipped/overflowed, even with finite loss."""
    steps = [item for item in log_history if 'grad_norm' in item]
    if not steps:
        raise RuntimeError('NO_EFFECTIVE_OPTIMIZER_STEP: Trainer did not log a gradient norm')
    for item in steps:
        norm = item.get('grad_norm')
        loss = item.get('loss')
        if not isinstance(norm, (int, float)) or not math.isfinite(norm) or norm <= 0:
            raise RuntimeError(f'NONFINITE_GRADIENT: grad_norm={norm!r}')
        if not isinstance(loss, (int, float)) or not math.isfinite(loss):
            raise RuntimeError(f'NONFINITE_TRAINING_LOSS: loss={loss!r}')
    return {'grad_norm': float(steps[-1]['grad_norm']), 'loss': float(steps[-1]['loss'])}


def _trainable_adapter_snapshot(model, torch) -> dict:
    weights = {name: p.detach().float().cpu().clone()
               for name, p in model.named_parameters()
               if p.requires_grad and 'lora_' in name}
    if not weights:
        raise RuntimeError('NO_TRAINABLE_LORA_PARAMETERS')
    if any(not bool(torch.isfinite(v).all()) for v in weights.values()):
        raise RuntimeError('NONFINITE_ADAPTER_BEFORE_TRAINING')
    return weights


def _verified_parameter_update(before: dict, model, torch) -> dict:
    after = {name: p for name, p in model.named_parameters()
             if p.requires_grad and 'lora_' in name}
    if set(before) != set(after):
        raise RuntimeError('CHANGED_ADAPTER_PARAMETER_SET')
    changed, max_delta = 0, 0.0
    for name, original in before.items():
        current = after[name].detach().float().cpu()
        if not bool(torch.isfinite(current).all()):
            raise RuntimeError(f'NONFINITE_ADAPTER_AFTER_TRAINING: {name}')
        delta = (original - current).abs().max().item()
        if not math.isfinite(delta):
            raise RuntimeError(f'NONFINITE_ADAPTER_DELTA: {name}')
        if delta > 0:
            changed += 1
        max_delta = max(max_delta, delta)
    if changed == 0 or max_delta <= 0:
        raise RuntimeError('ZERO_ADAPTER_UPDATE: training saved weights without learning')
    return {'updated_tensors': changed, 'max_abs_delta': max_delta}


def run_gpu_smoke(repo: Path) -> dict:
    """Exercise real model loads/training/adapter reload using hardcoded toy text."""
    # Synthetic diagnostic only: FP32 avoids first-step FP16 AMP overflow on Turing.
    # Production configs/lora.yaml stays unchanged and still requires release.
    cfg = dict(_read_config(repo), model_dtype='float32')
    from .modeling import (LoRAAnswerer, QADataset, _libraries,
                           check_previous, model_loading_kwargs,
                           pad_batch, tokenize_qa)

    (torch, LoraConfig, PeftConfig, PeftModel, get_peft_model,
     AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments) = _libraries()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU is required for the two-stage smoke; no CPU fallback')
    torch.manual_seed(cfg['seed'])
    import random
    random.seed(cfg['seed'])
    revision = cfg.get('model_revision') or 'main'
    # Use a temporary OS directory, NOT src/lora/runs, production datasets,
    # trainer checkpoints, benchmark JSONL or any repository-relative paths.
    with tempfile.TemporaryDirectory(prefix='chronoreg-synthetic-gpu-only-') as temp:
        root = Path(temp)
        for year in STAGES:
            checkpoint = root / f'year-{year}'
            previous = root / f'year-{year-1}' if year != STAGES[0] else None
            if previous is not None:
                check_previous(previous, year, cfg)
            tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=revision, trust_remote_code=False)
            if tokenizer.eos_token_id is None:
                raise RuntimeError('Model tokenizer has no EOS token')
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token
            base = AutoModelForCausalLM.from_pretrained(
                MODEL, revision=revision,
                **model_loading_kwargs(cfg, torch, on_cuda=True))
            base = base.to('cuda')
            if previous:
                adapter_cfg = PeftConfig.from_pretrained(str(previous))
                if adapter_cfg.base_model_name_or_path != MODEL:
                    raise RuntimeError('Previous synthetic adapter base model mismatch')
                model = PeftModel.from_pretrained(base, str(previous), is_trainable=True)
            else:
                lora = LoraConfig(
                    task_type='CAUSAL_LM', r=cfg['lora_r'],
                    lora_alpha=cfg['lora_alpha'], lora_dropout=cfg['lora_dropout'],
                    target_modules=cfg['target_modules'], bias='none')
                model = get_peft_model(base, lora)
            model.config.use_cache = False
            encoded = tokenize_qa(tokenizer, synthetic_qa(year), 256)
            args = TrainingArguments(
                output_dir=str(root / f'.scratch-{year}'),
                overwrite_output_dir=False,
                per_device_train_batch_size=1,
                gradient_accumulation_steps=1,
                num_train_epochs=1,
                learning_rate=float(cfg['learning_rate']),
                seed=cfg['seed'], report_to='none', save_strategy='no',
                logging_steps=1, remove_unused_columns=False,
                bf16=False, fp16=False,
                gradient_checkpointing=bool(cfg.get('gradient_checkpointing', True)),
                gradient_checkpointing_kwargs={'use_reentrant': False},
                dataloader_num_workers=0)
            trainer = Trainer(
                model=model, args=args,
                train_dataset=QADataset([encoded]),
                data_collator=lambda examples: pad_batch(examples, tokenizer.pad_token_id),
                processing_class=tokenizer)
            initial_adapters = _trainable_adapter_snapshot(model, torch)
            trainer.train()
            gradient_stats = _finite_training_logs(trainer.state.log_history)
            update_stats = _verified_parameter_update(initial_adapters, model, torch)
            checkpoint.mkdir()
            model.save_pretrained(str(checkpoint), safe_serialization=True)
            (checkpoint / 'stage.json').write_text(json.dumps({
                'year': year, 'model': MODEL, 'model_revision': revision,
                'strategy': 'sequential', 'model_dtype': cfg['model_dtype'],
                'synthetic_only': True}, sort_keys=True) + '\n', encoding='utf-8')
            weights = checkpoint / 'adapter_model.safetensors'
            if not weights.is_file() or weights.stat().st_size == 0:
                raise RuntimeError('Synthetic LoRA adapter was not saved')
            if not (checkpoint / 'adapter_config.json').is_file():
                raise RuntimeError('Synthetic adapter config was not saved')
            from safetensors import safe_open
            with safe_open(str(weights), framework='pt', device='cpu') as reader:
                for tensor_name in reader.keys():
                    if not torch.isfinite(reader.get_tensor(tensor_name)).all():
                        raise RuntimeError(f'Nonfinite synthetic adapter weights: {tensor_name}')
            print(json.dumps({'synthetic_stage': year, 'adapter_saved': True,
                              'fp32_diagnostic_only': True,
                              'grad_norm': gradient_stats['grad_norm'],
                              'training_loss': gradient_stats['loss'],
                              'adapter_update_max_abs': update_stats['max_abs_delta'],
                              'trainable_tensors_updated': update_stats['updated_tensors'],
                              'gpu_peak_mib': round(torch.cuda.max_memory_allocated() / (1024 * 1024))}), flush=True)
            # Release resources before loading the next stage on a small GPU.
            del trainer, model, base, tokenizer
            import gc
            gc.collect()
            torch.cuda.empty_cache()
        answerer = LoRAAnswerer(cfg, root / 'year-2026', allow_cpu=False)
        result = answerer.answer('Đây có phải văn bản UET thật không?', as_of_year=2026)
        if not isinstance(result['answer'], str) or result['sources'] != []:
            raise RuntimeError('Synthetic adapter inference contract failed')
        summary = {'result': 'PASS', 'synthetic_stages': list(STAGES),
                   'training_update_verified': True, 'gradient_norms_finite': True,
                   'smoke_dtype': 'float32', 'production_dtype_unchanged': True,
                   'adapter_reload': 'PASS', 'answer_contract': 'PASS',
                   'temporary_artifacts_removed_on_exit': True,
                   'production_training_authorized': False,
                   'uet_data_accessed': False, 'heldout_scores_produced': False}
        del answerer
        import gc
        gc.collect()
        torch.cuda.empty_cache()
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Synthetic-only isolated LoRA GPU smoke')
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--preflight', action='store_true', help='Read-only dependency/GPU report; no model download')
    args = parser.parse_args(argv)
    if args.preflight:
        report = preflight(args.repo.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report['ready']:
            raise SystemExit(2)
        return
    result = run_gpu_smoke(args.repo.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
