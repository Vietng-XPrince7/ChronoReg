"""Common, model-independent QA formatting and numeric checks."""
from __future__ import annotations

import math
from typing import Any

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


def _training_adapter_snapshot(model, torch) -> dict:
    """CPU-side baseline for trainable LoRA weights; never used before release."""
    original = {name: param.detach().float().cpu().clone()
                for name, param in model.named_parameters()
                if param.requires_grad and 'lora_' in name}
    if not original:
        raise RuntimeError('TRAINING_NUMERIC_BLOCKED: no trainable LoRA parameters')
    if any(not bool(torch.isfinite(w).all()) for w in original.values()):
        raise RuntimeError('TRAINING_NUMERIC_BLOCKED: nonfinite adapter before training')
    return original


def _verify_training_numerics(model, torch, before: dict,
                              history: list[dict], train_loss: float,
                              optimizer_steps: int) -> dict:
    """Reject NaN/Inf gradients, skipped optimizer steps and no-op LoRA updates."""
    if optimizer_steps < 1 or not math.isfinite(float(train_loss)):
        raise RuntimeError('TRAINING_NUMERIC_BLOCKED: missing step or nonfinite train loss')
    logged = [entry for entry in history if 'grad_norm' in entry]
    if not logged:
        raise RuntimeError('TRAINING_NUMERIC_BLOCKED: no optimizer-step diagnostics')
    for entry in logged:
        loss = entry.get('loss')
        grad = entry.get('grad_norm')
        if (not isinstance(loss, (int, float)) or not math.isfinite(float(loss))
                or not isinstance(grad, (int, float)) or not math.isfinite(float(grad))
                or float(grad) <= 0):
            raise RuntimeError('TRAINING_NUMERIC_BLOCKED: nonfinite or zero gradient/loss')
    after = {name: param for name, param in model.named_parameters()
             if param.requires_grad and 'lora_' in name}
    if set(after) != set(before):
        raise RuntimeError('TRAINING_NUMERIC_BLOCKED: adapter parameter set changed')
    updates, max_delta = 0, 0.0
    for name, original in before.items():
        current = after[name].detach().float().cpu()
        if not bool(torch.isfinite(current).all()):
            raise RuntimeError(f'TRAINING_NUMERIC_BLOCKED: nonfinite adapter {name}')
        delta = float((current - original).abs().max().item())
        if not math.isfinite(delta):
            raise RuntimeError(f'TRAINING_NUMERIC_BLOCKED: nonfinite update {name}')
        if delta > 0:
            updates += 1
        max_delta = max(max_delta, delta)
    if not updates:
        raise RuntimeError('TRAINING_NUMERIC_BLOCKED: no adapter update')
    return {'optimizer_steps': optimizer_steps,
            'training_loss': float(train_loss),
            'last_grad_norm': float(logged[-1]['grad_norm']),
            'updated_adapter_tensors': updates,
            'max_abs_adapter_update': max_delta}
