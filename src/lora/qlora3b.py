"""Isolated, release-gated 3B NF4 QLoRA runner for the ChronoReg experiment.

Only imports CUDA/ML packages after evidence and device checks. Only the current QLoRA 3B pipeline is supported.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
import sys
from pathlib import Path

from .contracts import (read_jsonl, sha256, validate_benchmark,
                        validate_training, write_jsonl)
from .qlora3b_release import authorize, YEARS

MODEL = 'Qwen/Qwen2.5-3B-Instruct'
PIN = 'aa8e72537993ba99e69dfaafa59ed015b17504d1'
QUANT = 'nf4_double_quant'


def load_cfg(path: Path) -> dict:
    import yaml
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))['lora']
    if (cfg.get('base_model') != MODEL or cfg.get('model_revision') != PIN
            or cfg.get('strategy') != 'sequential' or cfg.get('years') != YEARS
            or cfg.get('model_dtype') != 'float16' or cfg.get('quantization') != QUANT
            or cfg.get('max_seq_length') != 512 or cfg.get('minimum_gpu_gib', 0) < 12):
        raise RuntimeError('3B_CONFIG_INVALID: expected pinned 3B NF4 / FP16 five-stage profile')
    if (cfg.get('minimum_total_qa', 0) < 200 or cfg.get('minimum_qa_per_year', 0) < 30
            or cfg.get('epochs', 0) <= 0 or cfg.get('train_batch_size', 0) != 1
            or cfg.get('gradient_accumulation_steps', 0) < 1):
        raise RuntimeError('3B_CONFIG_INVALID: training limits invalid')
    for key in ('learning_rate', 'lora_r', 'lora_alpha', 'lora_dropout', 'seed',
                'target_modules', 'max_new_tokens'):
        if key not in cfg:
            raise RuntimeError('3B_CONFIG_INVALID: missing ' + key)
    return cfg


def cfg_hash(cfg: dict) -> str:
    b = json.dumps(cfg, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(b).hexdigest()


def relative_file(repo: Path, p: str) -> Path:
    raw = Path(p)
    if raw.is_absolute() or not p.strip():
        raise RuntimeError('INPUT_BLOCKED: expected repository-relative file')
    full = (repo / raw).resolve()
    if not full.is_relative_to(repo.resolve()):
        raise RuntimeError('INPUT_BLOCKED: file outside repository')
    return full


def stage_dataset(repo: Path, cfg: dict, train_rel: str, bench_rel: str,
                  output_dir: Path) -> dict:
    """Draft/pin data for independent approval; NEVER authorizes training."""
    train_path = relative_file(repo, train_rel)
    benchmark_path = relative_file(repo, bench_rel)
    if output_dir.exists():
        raise FileExistsError('STAGE_EXISTS: refusing to overwrite staging data')
    benchmark = validate_benchmark(read_jsonl(benchmark_path))
    if len(benchmark) != 90:
        raise RuntimeError('STAGE_BLOCKED: the independent benchmark must contain 90 cases')
    raw = read_jsonl(train_path)
    if any(str(q.get('id', '')).startswith('train-20') for q in raw):
        raise RuntimeError('STAGE_BLOCKED: 200 legacy template QA not eligible')
    train = validate_training(raw, repo, benchmark)
    counts = {str(y): sum(q['as_of_year'] == y for q in train) for y in YEARS}
    if (len(train) < cfg['minimum_total_qa']
            or any(v < cfg['minimum_qa_per_year'] for v in counts.values())):
        raise RuntimeError('STAGE_BLOCKED: not enough source-verified QA per year')
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {'train_sha256': sha256(train_path),
                'benchmark_sha256': sha256(benchmark_path),
                'years': YEARS, 'year_convention': 'academic_year_start',
                'counts': counts, 'total': len(train), 'year_sha256': {},
                'status': 'STAGED_NOT_RELEASED'}
    for year in YEARS:
        file = output_dir / f'train_{year}.jsonl'
        write_jsonl(file, [q for q in train if q['as_of_year'] == year])
        manifest['year_sha256'][str(year)] = sha256(file)
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)
                                               + '\n', encoding='utf-8')
    return {'status': 'STAGED_NOT_RELEASED', 'rows': len(train), 'counts': counts,
            'manifest_sha256': sha256(output_dir / 'manifest.json')}


def integrity(checkpoints: Path, year: int, cfg: dict, auth: dict, manifest: dict) -> dict:
    folder = checkpoints / f'year-{year}'
    required = ['adapter_model.safetensors', 'adapter_config.json', 'stage.json']
    if not folder.is_dir() or folder.is_symlink():
        raise RuntimeError(f'CHECKPOINT_MISSING: {folder}')
    sidecar = folder / 'adapter_integrity.json'
    if not sidecar.is_file():
        raise RuntimeError(f'CHECKPOINT_NOT_VERIFIED: {sidecar}')
    data = json.loads(sidecar.read_text(encoding='utf-8'))
    meta = json.loads((folder / 'stage.json').read_text(encoding='utf-8'))
    if (data.get('schema') != 'chronoreg-qlora3b-integrity/v1' or data.get('year') != year
            or data.get('run_config_sha256') != cfg_hash(cfg)
            or data.get('release_file_sha256') != auth['release_sha256']
            or meta.get('year') != year or meta.get('model') != MODEL
            or meta.get('model_revision') != PIN or meta.get('quantization') != QUANT
            or meta.get('strategy') != 'sequential' or meta.get('model_dtype') != 'float16'
            or meta.get('training_sha256') != manifest['year_sha256'][str(year)]
            or meta.get('release_sha256') != auth['release_sha256']
            or meta.get('previous_year') != (year - 1 if year > YEARS[0] else None)):
        raise RuntimeError(f'CHECKPOINT_INTEGRITY_MISMATCH: {folder}')
    for name in required:
        p = folder / name
        if (not p.is_file() or p.stat().st_size == 0
                or data.get('file_sha256', {}).get(name) != sha256(p)):
            raise RuntimeError(f'CHECKPOINT_INTEGRITY_MISMATCH: {p}')
    return meta


def checkpoint_chain(checkpoints: Path, cfg: dict, auth: dict, manifest: dict) -> list[int]:
    seen, encountered_missing = [], False
    for year in YEARS:
        folder = checkpoints / f'year-{year}'
        if folder.exists():
            if encountered_missing:
                raise RuntimeError('CHECKPOINT_CHAIN_GAP: cannot skip chronological stages')
            integrity(checkpoints, year, cfg, auth, manifest)
            seen.append(year)
        else:
            encountered_missing = True
    return seen


def preflight(repo: Path, cfg: dict, prepared: Path,
              release: Path | None, checkpoints: Path) -> tuple[dict, dict]:
    evidence = authorize(repo, cfg, prepared, release)
    manifest = json.loads((prepared / 'manifest.json').read_text(encoding='utf-8'))
    seen = checkpoint_chain(checkpoints, cfg, evidence, manifest)
    return evidence, {'status': 'READY_FOR_GPU_PREFLIGHT', 'model': MODEL,
                      'training_rows': evidence['training_rows'],
                      'counts': evidence['counts'], 'completed_stages': seen,
                      'remaining_stages': [y for y in YEARS if y not in seen],
                      'release_sha256': evidence['release_sha256']}


def gpu_preflight(cfg: dict):
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError('GPU_BLOCKED: install PyTorch with CUDA') from exc
    if not torch.cuda.is_available():
        raise RuntimeError('GPU_BLOCKED: CUDA GPU is required for 3B QLoRA')
    props = torch.cuda.get_device_properties(0)
    total_gib = props.total_memory / (1024 ** 3)
    if total_gib < cfg['minimum_gpu_gib']:
        raise RuntimeError(f'GPU_BLOCKED: {total_gib:.2f} GiB < minimum '
                           f'{cfg["minimum_gpu_gib"]} GiB; do not use the local 4GB T1000')
    return torch, {'gpu_name': props.name, 'gpu_gib': round(total_gib, 2)}


def qlora_model(cfg: dict, torch, *, previous: Path | None, inference: bool):
    try:
        from transformers import (AutoModelForCausalLM, AutoTokenizer,
                                  BitsAndBytesConfig)
        from peft import (LoraConfig, PeftModel, get_peft_model,
                          prepare_model_for_kbit_training)
    except ImportError as exc:
        raise RuntimeError('Missing QLoRA packages: transformers/peft/bitsandbytes') from exc
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                               bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=torch.float16)
    tok = AutoTokenizer.from_pretrained(MODEL, revision=PIN, trust_remote_code=False)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        MODEL, revision=PIN, quantization_config=quant, dtype=torch.float16,
        device_map={'': 0}, trust_remote_code=False, use_safetensors=True,
        attn_implementation='eager')
    if inference:
        if previous is None:
            raise RuntimeError('Inference requires an explicit verified adapter')
        model = PeftModel.from_pretrained(base, str(previous), is_trainable=False)
    else:
        base.config.use_cache = False
        base = prepare_model_for_kbit_training(
            base, use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={'use_reentrant': False})
        if previous:
            model = PeftModel.from_pretrained(base, str(previous), is_trainable=True)
        else:
            lc = LoraConfig(task_type='CAUSAL_LM', r=cfg['lora_r'],
                            lora_alpha=cfg['lora_alpha'], lora_dropout=cfg['lora_dropout'],
                            target_modules=cfg['target_modules'], bias='none')
            model = get_peft_model(base, lc)
        if not any('lora_' in k and p.requires_grad for k, p in model.named_parameters()):
            raise RuntimeError('TRAINING_BLOCKED: no trainable LoRA parameters')
    return model, tok


def train_one(repo: Path, cfg: dict, prepared: Path, checkpoints: Path,
              auth: dict, year: int) -> dict:
    from .qa_runtime import (tokenize_qa, QADataset, pad_batch,
                           _training_adapter_snapshot, _verify_training_numerics)
    from transformers import Trainer, TrainingArguments
    import torch
    manifest = json.loads((prepared / 'manifest.json').read_text(encoding='utf-8'))
    index = YEARS.index(year)
    prior = checkpoints / f'year-{YEARS[index - 1]}' if index else None
    if prior is not None:
        integrity(checkpoints, year - 1, cfg, auth, manifest)
    final = checkpoints / f'year-{year}'
    partial = checkpoints / f'.year-{year}.partial'
    if final.exists() or partial.exists():
        raise FileExistsError('Refusing to overwrite checkpoint or interrupted partial')
    rows = read_jsonl(prepared / f'train_{year}.jsonl')
    torch.manual_seed(cfg['seed'])
    model, tok = qlora_model(cfg, torch, previous=prior, inference=False)
    before = _training_adapter_snapshot(model, torch)
    encoded = [tokenize_qa(tok, q, cfg['max_seq_length']) for q in rows]
    scratch = checkpoints / f'.trainer-{year}'
    if scratch.exists():
        raise FileExistsError('Refusing to reuse old trainer scratch path')
    args = TrainingArguments(
        output_dir=str(scratch), per_device_train_batch_size=1,
        gradient_accumulation_steps=cfg['gradient_accumulation_steps'],
        num_train_epochs=cfg['epochs'], learning_rate=float(cfg['learning_rate']),
        seed=cfg['seed'], report_to='none', save_strategy='no', logging_steps=1,
        remove_unused_columns=False, dataloader_num_workers=0,
        fp16=True, bf16=False, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant': False},
        optim='paged_adamw_8bit', max_grad_norm=0.3)
    trainer = Trainer(model=model, args=args, train_dataset=QADataset(encoded),
                      data_collator=lambda batch: pad_batch(batch, tok.pad_token_id),
                      processing_class=tok)
    result = trainer.train()
    numeric = _verify_training_numerics(model, torch, before,
                                        trainer.state.log_history, result.training_loss,
                                        trainer.state.global_step)
    checkpoints.mkdir(parents=True, exist_ok=True)
    partial.mkdir(parents=False, exist_ok=False)
    model.save_pretrained(str(partial), safe_serialization=True)
    tok.save_pretrained(str(partial))
    meta = {'year': year, 'model': MODEL, 'model_revision': PIN,
            'model_dtype': 'float16', 'quantization': QUANT, 'strategy': 'sequential',
            'training_rows': len(rows), 'training_sha256': sha256(prepared / f'train_{year}.jsonl'),
            'release_sha256': auth['release_sha256'],
            'previous_year': YEARS[index - 1] if index else None,
            'numeric_evidence': numeric}
    (partial / 'stage.json').write_text(json.dumps(meta, sort_keys=True, indent=2)
                                         + '\n', encoding='utf-8')
    names = ['adapter_model.safetensors', 'adapter_config.json', 'stage.json']
    if not all((partial / n).is_file() and (partial / n).stat().st_size > 0 for n in names):
        raise RuntimeError('Checkpoint incomplete, partial retained; no stage published')
    sidecar = {'schema': 'chronoreg-qlora3b-integrity/v1', 'year': year,
               'run_config_sha256': cfg_hash(cfg),
               'release_file_sha256': auth['release_sha256'],
               'file_sha256': {n: sha256(partial / n) for n in names}}
    (partial / 'adapter_integrity.json').write_text(json.dumps(sidecar, sort_keys=True, indent=2)
                                                        + '\n', encoding='utf-8')
    partial.rename(final)
    del trainer, model, tok
    gc.collect()
    torch.cuda.empty_cache()
    return {'year': year, 'status': 'TRAINED_VERIFIED', 'training_rows': len(rows),
            'checkpoint': str(final), 'numeric_evidence': numeric}


def run_train(repo: Path, cfg: dict, prepared: Path, release: Path,
              checkpoints: Path, *, resume: bool) -> dict:
    auth, plan = preflight(repo, cfg, prepared, release, checkpoints)
    if plan['completed_stages'] and not resume:
        raise RuntimeError('EXISTING_CHAIN: --resume required to reuse verified stages')
    _, gpu = gpu_preflight(cfg)
    done = []
    for year in plan['remaining_stages']:
        done.append(train_one(repo, cfg, prepared, checkpoints, auth, year))
    return {'status': 'TRAINED_ALL_FIVE_STAGES', 'gpu': gpu,
            'already_verified': plan['completed_stages'], 'newly_trained': done,
            'training_rows': auth['training_rows'],
            'release_sha256': auth['release_sha256']}


def run_eval(repo: Path, cfg: dict, prepared: Path, release: Path,
             checkpoints: Path, out: Path) -> dict:
    if out.exists():
        raise FileExistsError('Evaluation output exists; refusing overwrite')
    auth, plan = preflight(repo, cfg, prepared, release, checkpoints)
    if plan['remaining_stages']:
        raise RuntimeError('EVAL_BLOCKED: 5 verified stages required')
    gpu_preflight(cfg)
    import torch
    from .evaluate import evaluate_stages
    benchmark = repo / cfg['benchmark']
    if sha256(benchmark) != auth['benchmark_sha256']:
        raise RuntimeError('EVAL_BLOCKED: benchmark changed')
    state = {'year': None, 'model': None, 'tok': None}
    def predict(stage: int, question: str, as_of_year: int) -> str:
        if state['year'] != stage:
            state['model'] = None
            state['tok'] = None
            gc.collect()
            torch.cuda.empty_cache()
            model, tok = qlora_model(cfg, torch,
                                    previous=checkpoints / f'year-{stage}', inference=True)
            model.eval()
            state.update(year=stage, model=model, tok=tok)
        from .qa_runtime import messages
        prompt = state['tok'].apply_chat_template(messages(question, as_of_year),
                                                  tokenize=False, add_generation_prompt=True)
        encoded = state['tok'](prompt, add_special_tokens=False, return_tensors='pt')
        encoded = {k: v.to('cuda:0') for k, v in encoded.items()}
        with torch.inference_mode():
            ids = state['model'].generate(**encoded, do_sample=False,
                                          max_new_tokens=cfg['max_new_tokens'],
                                          pad_token_id=state['tok'].pad_token_id)
        return state['tok'].decode(ids[0][encoded['input_ids'].shape[1]:],
                                   skip_special_tokens=True).strip()
    scores = evaluate_stages(benchmark, YEARS, predict, out)
    provenance = {'status': 'EVALUATED_NOT_SEMANTICALLY_CERTIFIED', 'model': MODEL,
                  'revision': PIN, 'release_sha256': auth['release_sha256'],
                  'benchmark_sha256': auth['benchmark_sha256'],
                  'run_config_sha256': cfg_hash(cfg),
                  'checkpoint_sha256': {str(y): sha256(checkpoints / f'year-{y}' / 'adapter_model.safetensors')
                                        for y in YEARS},
                  'count': scores['count'], 'unique_benchmark_cases': scores['unique_benchmark_cases']}
    (out / 'qlora3b_provenance.json').write_text(json.dumps(provenance, indent=2)
                                                 + '\n', encoding='utf-8')
    return provenance



def run_answer(repo: Path, cfg: dict, prepared: Path, release: Path,
               checkpoints: Path, *, year: int, as_of_year: int,
               question: str) -> dict:
    """Source-free parametric answer; requires a verified, released 3B adapter."""
    if year not in YEARS or as_of_year not in YEARS or year < as_of_year:
        raise ValueError('year / as-of-year invalid; checkpoint cannot precede question year')
    if not isinstance(question, str) or not question.strip():
        raise ValueError('A nonempty question is required')
    auth, plan = preflight(repo, cfg, prepared, release, checkpoints)
    if year not in plan['completed_stages']:
        raise RuntimeError(f'ANSWER_BLOCKED: year-{year} checkpoint not verified')
    torch, gpu = gpu_preflight(cfg)
    model, tok = qlora_model(cfg, torch, previous=checkpoints / f'year-{year}', inference=True)
    model.eval()
    from .qa_runtime import messages
    prompt = tok.apply_chat_template(messages(question, as_of_year),
                                     tokenize=False, add_generation_prompt=True)
    encoded = tok(prompt, add_special_tokens=False, return_tensors='pt')
    encoded = {k: v.to('cuda:0') for k, v in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(**encoded, do_sample=False,
                                   max_new_tokens=cfg['max_new_tokens'],
                                   pad_token_id=tok.pad_token_id)
    response = tok.decode(generated[0][encoded['input_ids'].shape[1]:],
                          skip_special_tokens=True).strip()
    return {'status': 'MODEL_ONLY_NOT_SOURCE_VERIFIED', 'answer': response,
            'model': MODEL, 'checkpoint_year': year, 'as_of_year': as_of_year,
            'checkpoint': str(checkpoints / f'year-{year}'),
            'adapter_sha256': sha256(checkpoints / f'year-{year}' / 'adapter_model.safetensors'),
            'sources': [], 'gpu': gpu, 'release_sha256': auth['release_sha256']}


def main(argv=None):
    p = argparse.ArgumentParser(description='Release-bound ChronoReg Qwen2.5-3B QLoRA')
    p.add_argument('--repo', type=Path, default=Path('.'))
    p.add_argument('--config', default='configs/lora.yaml')
    p.add_argument('--prepared', default='src/lora/runs/qlora3b/prepared')
    p.add_argument('--checkpoints', default='src/lora/runs/qlora3b/checkpoints')
    p.add_argument('--release', default=None)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('stage')
    s.add_argument('--train', required=True, help='repo-relative independently reviewed QA JSONL')
    s.add_argument('--benchmark', default='data/qa_benchmark/benchmark.jsonl')
    sub.add_parser('preflight')
    t = sub.add_parser('train')
    t.add_argument('--resume', action='store_true')
    e = sub.add_parser('evaluate')
    e.add_argument('--output', default='src/lora/runs/qlora3b/evaluation')
    a = sub.add_parser('answer')
    a.add_argument('--year', type=int, required=True)
    a.add_argument('--as-of-year', type=int, required=True)
    a.add_argument('--question', required=True)
    args = p.parse_args(argv)
    try:
        repo = args.repo.resolve()
        def local(path: str):
            rel = Path(path)
            if rel.is_absolute():
                raise RuntimeError('Paths must remain under repository root')
            dest = (repo / rel).resolve()
            if not dest.is_relative_to(repo):
                raise RuntimeError('Path escapes repository')
            return dest
        cfg = load_cfg(local(args.config))
        prepared, ckpt = local(args.prepared), local(args.checkpoints)
        release = local(args.release) if args.release else None
        if args.command == 'stage':
            result = stage_dataset(repo, cfg, args.train, args.benchmark, prepared)
        elif args.command == 'preflight':
            _, result = preflight(repo, cfg, prepared, release, ckpt)
        elif args.command == 'train':
            result = run_train(repo, cfg, prepared, release, ckpt, resume=args.resume)
        elif args.command == 'answer':
            result = run_answer(repo, cfg, prepared, release, ckpt,
                                year=args.year, as_of_year=args.as_of_year,
                                question=args.question)
        else:
            result = run_eval(repo, cfg, prepared, release, ckpt, local(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, KeyError, ValueError, RuntimeError, ImportError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
