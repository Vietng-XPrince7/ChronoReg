"""Lazy-loading Hugging Face backend for sequential continual LoRA.

No network/model imports occur for data preparation, audits, or unit tests.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .contracts import read_jsonl, sha256

SYSTEM = (
    'Bạn là trợ lý hỏi đáp quy định UET. Trả lời theo năm học được hỏi. '
    'Nếu thiếu bằng chứng, nói rõ không đủ thông tin. Không bịa nguồn hoặc số liệu.'
)


def messages(question: str, year: int) -> list[dict]:
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': f'Năm học: {year}-{year+1}\nCâu hỏi: {question}'}]


def tokenize_qa(tokenizer: Any, qa: dict, max_seq_length: int) -> dict:
    """Loss is computed on assistant tokens ONLY; ignore system/user prompts."""
    prompt = tokenizer.apply_chat_template(messages(qa['question'], qa['as_of_year']),
                                           tokenize=False, add_generation_prompt=True)
    prompt_ids = tokenizer(prompt, add_special_tokens=False)['input_ids']
    answer_ids = tokenizer(qa['answer'], add_special_tokens=False)['input_ids']
    if tokenizer.eos_token_id is None:
        raise ValueError('Tokenizer requires eos_token_id')
    if len(prompt_ids) + len(answer_ids) + 1 > max_seq_length:
        raise ValueError(f'{qa["id"]}: tokenized QA exceeds max_seq_length={max_seq_length}; review or raise limit')
    ids = prompt_ids + answer_ids + [tokenizer.eos_token_id]
    return {'input_ids': ids, 'attention_mask': [1] * len(ids),
            'labels': [-100] * len(prompt_ids) + answer_ids + [tokenizer.eos_token_id]}


class QADataset:
    def __init__(self, encoded: list[dict]):
        self.records = encoded

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict:
        return self.records[index]


def pad_batch(records: list[dict], pad_token_id: int):
    import torch
    width = max(len(x['input_ids']) for x in records)
    result = {}
    for field, pad in (('input_ids', pad_token_id),
                       ('attention_mask', 0), ('labels', -100)):
        result[field] = torch.tensor([x[field] + [pad] * (width - len(x[field]))
                                      for x in records], dtype=torch.long)
    return result


def _libraries():
    try:
        import torch
        from peft import LoraConfig, PeftConfig, PeftModel, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    except ImportError as exc:
        raise RuntimeError('Missing LoRA dependencies; install src/lora/requirements.txt and a compatible torch build') from exc
    return torch, LoraConfig, PeftConfig, PeftModel, get_peft_model, AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments


def model_loading_kwargs(cfg: dict, torch: Any, *, on_cuda: bool) -> dict:
    """Explicit dtype/backend tested on the Turing T1000; fail on unsupported BF16."""
    requested = cfg.get('model_dtype', 'float16')
    choices = {'float16': torch.float16, 'float32': torch.float32,
               'bfloat16': torch.bfloat16}
    if requested not in choices:
        raise ValueError(f'Unsupported model_dtype={requested!r}; expected float16, bfloat16 or float32')
    if on_cuda and requested == 'bfloat16' and not torch.cuda.is_bf16_supported():
        raise ValueError('Configured bfloat16 on a CUDA GPU without BF16 support; use float16 on Quadro T1000')
    # CPU smoke testing is permitted only with FP32, regardless of the CUDA preference.
    dtype = choices[requested] if on_cuda else torch.float32
    return {'dtype': dtype, 'trust_remote_code': False,
            'low_cpu_mem_usage': True, 'use_safetensors': True,
            'attn_implementation': 'eager'}


def check_previous(previous: Path, year: int, cfg: dict) -> dict:
    meta_path = previous / 'stage.json'
    weight = previous / 'adapter_model.safetensors'
    if not meta_path.is_file() or not (previous / 'adapter_config.json').is_file() or not weight.is_file() or weight.stat().st_size == 0:
        raise ValueError(f'Missing complete previous adapter checkpoint: {previous}')
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    if meta['year'] != year - 1:
        raise ValueError(f'Sequential chain requires previous year {year-1}, got {meta["year"]}')
    if meta['model'] != cfg['base_model']:
        raise ValueError('Base model changed between stages')
    if meta.get('model_revision') != (cfg.get('model_revision') or 'main'):
        raise ValueError('Model revision changed between stages')
    if meta.get('strategy') != 'sequential':
        raise ValueError('Previous adapter was not trained sequentially')
    if meta.get('model_dtype', 'float16') != cfg.get('model_dtype', 'float16'):
        raise ValueError('Model dtype changed between stages')
    return meta


def train_stage(cfg: dict, prepared_dir: Path, year: int,
                checkpoint_root: Path, previous: Path | None = None,
                allow_cpu: bool = False, dry_run: bool = False,
                release_path: Path | None = None, repo: Path | None = None) -> dict:
    """Train exactly one chronological stage and persist its adapter separately."""
    train_path = prepared_dir / f'train_{year}.jsonl'
    rows = read_jsonl(train_path)
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    if year not in manifest['years']:
        raise ValueError('Year not listed in prepared dataset manifest')
    if len(rows) != manifest['counts'][str(year)]:
        raise ValueError('Training row count disagrees with manifest')
    if sha256(train_path) != manifest['year_sha256'][str(year)]:
        raise ValueError('Stage QA has changed since preparation; refuse to train')
    if previous is None and year != manifest['years'][0]:
        raise ValueError('Sequential stage requires the previous-year adapter')
    if previous is not None:
        check_previous(previous, year, cfg)
    checkpoint = checkpoint_root / f'year-{year}'
    if checkpoint.exists():
        raise FileExistsError(f'Refusing to overwrite adapter checkpoint: {checkpoint}')
    plan = {'year': year, 'model': cfg['base_model'],
            'model_revision': cfg.get('model_revision') or 'main',
            'strategy': 'sequential',
            'model_dtype': cfg.get('model_dtype', 'float16'),
            'gradient_checkpointing': bool(cfg.get('gradient_checkpointing', True)),
            'training_rows': len(rows), 'training_sha256': sha256(train_path),
            'previous_checkpoint': str(previous) if previous else None,
            'checkpoint': str(checkpoint)}
    if dry_run:
        return dict(plan, dry_run=True, model_loaded=False)
    # Never load model weights or allocate GPU without a pinned, reviewed release.
    from .release_guard import require_training_release
    release_evidence = require_training_release(repo, prepared_dir, year, release_path)
    plan['release_evidence'] = release_evidence
    (torch, LoraConfig, PeftConfig, PeftModel, get_peft_model,
     AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments) = _libraries()
    if not torch.cuda.is_available() and not allow_cpu:
        raise RuntimeError('CUDA GPU not available. Training blocked (CPU training is impractical); use --allow-cpu only for a small smoke test.')
    torch.manual_seed(cfg['seed'])
    random.seed(cfg['seed'])
    revision = cfg.get('model_revision') or 'main'
    tokenizer = AutoTokenizer.from_pretrained(cfg['base_model'], revision=revision, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    on_cuda = torch.cuda.is_available()
    dtype = model_loading_kwargs(cfg, torch, on_cuda=on_cuda)['dtype']
    base = AutoModelForCausalLM.from_pretrained(
        cfg['base_model'], revision=revision,
        **model_loading_kwargs(cfg, torch, on_cuda=on_cuda))
    if on_cuda:
        base = base.to('cuda')
    if previous:
        adapter_cfg = PeftConfig.from_pretrained(str(previous))
        if adapter_cfg.base_model_name_or_path != cfg['base_model']:
            raise ValueError('Adapter base model does not match current config')
        model = PeftModel.from_pretrained(base, str(previous), is_trainable=True)
    else:
        lora = LoraConfig(task_type='CAUSAL_LM', r=cfg['lora_r'],
                          lora_alpha=cfg['lora_alpha'], lora_dropout=cfg['lora_dropout'],
                          target_modules=cfg['target_modules'], bias='none')
        model = get_peft_model(base, lora)
    model.config.use_cache = False
    encoded = [tokenize_qa(tokenizer, row, cfg['max_seq_length']) for row in rows]
    dataset = QADataset(encoded)
    # Keep trainer scratch files isolated from final checkpoint; no hub pushes.
    scratch = checkpoint_root / f'.trainer-{year}'
    args = TrainingArguments(
        output_dir=str(scratch), overwrite_output_dir=False,
        per_device_train_batch_size=cfg['train_batch_size'],
        gradient_accumulation_steps=cfg['gradient_accumulation_steps'],
        num_train_epochs=cfg['epochs'], learning_rate=float(cfg['learning_rate']),
        seed=cfg['seed'], report_to='none', save_strategy='no',
        logging_steps=10, remove_unused_columns=False,
        bf16=bool(on_cuda and dtype == torch.bfloat16),
        fp16=bool(on_cuda and dtype == torch.float16),
        gradient_checkpointing=bool(cfg.get('gradient_checkpointing', True)),
        gradient_checkpointing_kwargs={'use_reentrant': False},
        dataloader_num_workers=0,
    )
    trainer = Trainer(model=model, args=args, train_dataset=dataset,
                      data_collator=lambda features: pad_batch(features, tokenizer.pad_token_id),
                      processing_class=tokenizer)
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    trainer.train()
    # Write into a temporary folder and publish it atomically only after save succeeds.
    temp_checkpoint = checkpoint_root / f'.year-{year}.partial'
    if temp_checkpoint.exists():
        raise FileExistsError(f'Interrupted checkpoint exists: {temp_checkpoint}')
    temp_checkpoint.mkdir(parents=True)
    try:
        model.save_pretrained(str(temp_checkpoint), safe_serialization=True)
        tokenizer.save_pretrained(str(temp_checkpoint))
        if not (temp_checkpoint / 'adapter_config.json').is_file():
            raise RuntimeError('Adapter config was not saved')
        saved_weights = temp_checkpoint / 'adapter_model.safetensors'
        if not saved_weights.is_file() or saved_weights.stat().st_size == 0:
            raise RuntimeError('Serialized adapter weights missing/empty')
        (temp_checkpoint / 'stage.json').write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
            encoding='utf-8')
        temp_checkpoint.rename(checkpoint)
    except Exception:
        # Preserve partial contents for debugging rather than claiming a checkpoint.
        raise
    return dict(plan, dry_run=False, model_loaded=True)


class LoRAAnswerer:
    """Adapter-backed callable; parametric answers have no verified citations."""
    def __init__(self, cfg: dict, adapter: Path | None, allow_cpu: bool = True):
        (torch, _LC, _PC, PeftModel, _gp, AutoModelForCausalLM,
         AutoTokenizer, _Trainer, _Args) = _libraries()
        if not torch.cuda.is_available() and not allow_cpu:
            raise RuntimeError('CUDA required for inference by this configuration')
        self.torch = torch
        self.cfg = cfg
        self.adapter = adapter
        self.tokenizer = AutoTokenizer.from_pretrained(cfg['base_model'],
                                                       revision=cfg.get('model_revision') or 'main',
                                                       trust_remote_code=False)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        on_cuda = torch.cuda.is_available()
        base = AutoModelForCausalLM.from_pretrained(
            cfg['base_model'], revision=cfg.get('model_revision') or 'main',
            **model_loading_kwargs(cfg, torch, on_cuda=on_cuda))
        if on_cuda:
            base = base.to('cuda')
        self.model = PeftModel.from_pretrained(base, str(adapter)) if adapter else base
        self.model.eval()

    def answer(self, question: str, as_of_year: int | None = None) -> dict:
        if as_of_year is None:
            return {'answer': 'Vui lòng cho biết năm học cần hỏi (năm bắt đầu, ví dụ 2025 cho 2025–2026).',
                    'sources': [], 'as_of_year': None}
        if type(as_of_year) is not int or as_of_year not in range(2022, 2027):
            raise ValueError('as_of_year must be the start year of an academic year 2022–2026')
        prompt = self.tokenizer.apply_chat_template(messages(question, as_of_year),
                                                    tokenize=False, add_generation_prompt=True)
        encoded = self.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
        device = next(self.model.parameters()).device
        encoded = {k: v.to(device) for k, v in encoded.items()}
        with self.torch.inference_mode():
            generation = self.model.generate(**encoded, do_sample=False,
                                             max_new_tokens=self.cfg.get('max_new_tokens', 160),
                                             pad_token_id=self.tokenizer.pad_token_id)
        answer_ids = generation[0][encoded['input_ids'].shape[1]:]
        return {'answer': self.tokenizer.decode(answer_ids, skip_special_tokens=True).strip(),
                'sources': [], 'as_of_year': as_of_year,
                'checkpoint': str(self.adapter) if self.adapter else 'base_model',
                'source_note': 'No retrieval; cannot claim document-backed citations'}
