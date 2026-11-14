"""Offline checkpoint contract + explicit demo inference for ChronoReg.

The module NEVER trains, promotes QA approvals or uses the benchmark as training.
It does not make demo answers authoritative. No model import in check-only mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

YEARS = (2022, 2023, 2024, 2025, 2026)
FILES = ('adapter_model.safetensors', 'adapter_config.json', 'stage.json')


class AdapterCheckError(ValueError):
    """A checkpoint was rejected before any model was loaded."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise AdapterCheckError(f'Invalid or missing JSON: {path}') from exc
    if not isinstance(result, dict):
        raise AdapterCheckError(f'Expected JSON object: {path}')
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check_checkpoint(folder: Path, year: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate a *demo* adapter's local structure and base-model compatibility.

    The check is structural/provenance only; it does not validate learned facts.
    A present owner-release field does not grant an approval in this command.
    """
    folder = Path(folder).resolve()
    if not folder.is_dir() or folder.is_symlink():
        raise AdapterCheckError(f'Adapter directory missing/unsafe: {folder}')
    if type(year) is not int or year not in YEARS or year not in cfg.get('years', []):
        raise AdapterCheckError(f'Invalid adapter year: {year}')
    for name in FILES:
        path = folder / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise AdapterCheckError(f'Missing/empty/unsafe checkpoint file: {path}')
    meta = _read_json(folder / 'stage.json')
    adapter_cfg = _read_json(folder / 'adapter_config.json')
    expected_model = cfg.get('base_model')
    expected_revision = cfg.get('model_revision')
    if (meta.get('year') != year or meta.get('strategy') != 'sequential'
            or meta.get('model') != expected_model
            or meta.get('model_revision') != expected_revision):
        raise AdapterCheckError(f'Stage metadata mismatch for {year}: model/revision/year/strategy')
    if (meta.get('model_dtype') is not None
            and meta['model_dtype'] != cfg.get('model_dtype', 'float16')):
        raise AdapterCheckError(f'Dtype mismatch in stage {year}')
    if (adapter_cfg.get('base_model_name_or_path') != expected_model
            or adapter_cfg.get('peft_type') != 'LORA'
            or adapter_cfg.get('task_type') != 'CAUSAL_LM'):
        raise AdapterCheckError(f'PEFT metadata incompatible with base model: {year}')
    for key, expected in (('r', cfg.get('lora_r')), ('lora_alpha', cfg.get('lora_alpha'))):
        if expected is not None and adapter_cfg.get(key) != expected:
            raise AdapterCheckError(f'PEFT {key} incompatible with configuration: {year}')
    rows = meta.get('training_rows')
    if type(rows) is not int or rows < 1:
        raise AdapterCheckError(f'Missing/invalid stage training_rows: {year}')
    hashes = {name: _sha256(folder / name) for name in FILES}
    sidecar_path = folder / 'adapter_integrity.json'
    sidecar_status = 'not_present_demo'
    if sidecar_path.exists():
        if sidecar_path.is_symlink() or not sidecar_path.is_file():
            raise AdapterCheckError(f'Invalid sidecar: {sidecar_path}')
        sidecar = _read_json(sidecar_path)
        if (sidecar.get('schema') != 'chronoreg-adapter-integrity/v2'
                or sidecar.get('year') != year
                or any(sidecar.get('file_sha256', {}).get(key) != value
                       for key, value in hashes.items())):
            raise AdapterCheckError(f'Adapter integrity sidecar hash mismatch: {year}')
        sidecar_status = 'hashes_match'
    return {
        'year': year, 'model': expected_model, 'revision': expected_revision,
        'adapter_directory': str(folder), 'training_rows_from_stage': rows,
        'files_sha256': hashes, 'integrity_sidecar': sidecar_status,
        'status': 'DEMO_UNRELEASED', 'factual_quality_validated': False,
        'released_for_training_or_student_qa': False,
    }


def check_chain(root: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    results = [check_checkpoint(root / f'year-{year}', year, cfg) for year in YEARS]
    return {
        'status': 'DEMO_UNRELEASED', 'check': 'PASS_STRUCTURAL_ONLY',
        'base_model': cfg['base_model'], 'revision': cfg['model_revision'],
        'adapter_count': len(results),
        'training_rows_from_stage_metadata': sum(x['training_rows_from_stage'] for x in results),
        'checkpoints': results,
        'warning': 'The 5 checkpoints are demo artifacts, not approved policy-QA models.',
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='ChronoReg LoRA demo checkpoint verification')
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--adapter-root', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true', help='No torch, GPU or model load')
    parser.add_argument('--year', type=int, default=2026, choices=YEARS)
    parser.add_argument('--as-of-year', type=int, default=2025, choices=YEARS)
    parser.add_argument('--question', help='Only for real inference')
    parser.add_argument('--allow-demo', action='store_true', help='Acknowledge output is not approved')
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    from .cli import config
    cfg = config(repo / 'configs/lora.yaml')
    try:
        if args.check_only:
            result = check_chain(args.adapter_root, cfg)
        else:
            if not args.allow_demo:
                raise AdapterCheckError('Explicit --allow-demo is required for unreleased demo inference')
            if not args.question or not args.question.strip():
                raise AdapterCheckError('--question is required for inference')
            adapter = args.adapter_root.resolve() / f'year-{args.year}'
            evidence = check_checkpoint(adapter, args.year, cfg)
            from .modeling import LoRAAnswerer
            answer = LoRAAnswerer(cfg, adapter, allow_cpu=False).answer(args.question, args.as_of_year)
            if answer.get('checkpoint') != str(adapter):
                raise AdapterCheckError('Inference used unexpected checkpoint')
            result = {
                'status': 'DEMO_UNRELEASED', 'inference': 'COMPLETED',
                'base_model': evidence['model'], 'adapter_sha256': evidence['files_sha256']['adapter_model.safetensors'],
                'adapter_year': args.year, 'as_of_year': args.as_of_year,
                'question': args.question, 'answer': answer['answer'],
                'checkpoint': answer['checkpoint'], 'sources': answer.get('sources', []),
                'factual_quality_validated': False,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except AdapterCheckError as exc:
        parser.exit(2, f'ADAPTER_CHECK_BLOCKED: {exc}\n')


if __name__ == '__main__':
    main()
