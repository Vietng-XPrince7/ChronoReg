"""Commands are lazy: prepare/test need no Torch, GPU, or model download."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import gc

from .candidates import propose
from .evaluate import evaluate_stages
from .modeling import LoRAAnswerer, train_stage
from .prepare import prepare


def config(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError('Install PyYAML for configs/lora.yaml') from exc
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    cfg = data['lora']
    for k in ('base_model', 'years', 'seed', 'max_seq_length', 'lora_r',
              'lora_alpha', 'lora_dropout', 'target_modules'):
        if k not in cfg:
            raise ValueError(f'Missing LoRA configuration key: {k}')
    if cfg.get('strategy') != 'sequential':
        raise ValueError('Only sequential adapter training is implemented')
    return cfg


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='ChronoReg continual LoRA tools')
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--config', type=Path, default=Path('configs/lora.yaml'))
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('propose', help='Create source-grounded DRAFT QA from verified registry')
    p.add_argument('--registry', type=Path, default=Path('data/versioning/documents.jsonl'))
    p.add_argument('--output', type=Path, default=Path('src/lora/runs/candidates.jsonl'))
    p = commands.add_parser('prepare', help='Validate MANUALLY APPROVED QA and benchmark separation')
    p.add_argument('--train', type=Path)
    p.add_argument('--benchmark', type=Path)
    p.add_argument('--output', type=Path, default=Path('src/lora/runs/prepared'))
    p = commands.add_parser('train', help='Train one stage from previously prepared QA')
    p.add_argument('--year', type=int, required=True)
    p.add_argument('--prepared', type=Path, default=Path('src/lora/runs/prepared'))
    p.add_argument('--previous', type=Path)
    p.add_argument('--checkpoints', type=Path, default=Path('src/lora/runs/checkpoints'))
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--allow-cpu', action='store_true')
    p = commands.add_parser('answer', help='Call shared answer(question, as_of_year) interface')
    p.add_argument('--question', required=True)
    p.add_argument('--as-of-year', type=int)
    p.add_argument('--adapter', type=Path)
    p = commands.add_parser('evaluate', help='Held-out forgetting across all checkpoints')
    p.add_argument('--benchmark', type=Path)
    p.add_argument('--checkpoints', type=Path, default=Path('src/lora/runs/checkpoints'))
    p.add_argument('--output', type=Path, default=Path('src/lora/runs/evaluation'))
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    conf_path = args.config if args.config.is_absolute() else root / args.config
    cfg = config(conf_path)
    def resolve(path: Path | str) -> Path:
        path = Path(path)
        return path if path.is_absolute() else root / path
    if args.command == 'propose':
        output = propose(root, resolve(args.registry), resolve(args.output))
    elif args.command == 'prepare':
        output = prepare(root, resolve(args.train or cfg['train_qa']),
                         resolve(args.benchmark or cfg['benchmark']),
                         resolve(args.output), cfg['years'])
    elif args.command == 'train':
        output = train_stage(cfg, resolve(args.prepared), args.year,
                             resolve(args.checkpoints), resolve(args.previous) if args.previous else None,
                             allow_cpu=args.allow_cpu, dry_run=args.dry_run)
    elif args.command == 'answer':
        output = LoRAAnswerer(cfg, resolve(args.adapter) if args.adapter else None).answer(
            args.question, args.as_of_year)
    else:
        bench = resolve(args.benchmark or cfg['benchmark'])
        checkpoints = resolve(args.checkpoints)
        state = {'stage': None, 'model': None}
        def predict(stage, question, as_of_year):
            if stage != state['stage']:
                state['model'] = None
                gc.collect()
                # A single model is live at once to bound GPU/CPU memory usage.
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                adapter = checkpoints / f'year-{stage}'
                if not (adapter / 'stage.json').is_file():
                    raise FileNotFoundError(f'Missing checkpoint: {adapter}')
                state['model'] = LoRAAnswerer(cfg, adapter)
                state['stage'] = stage
            return state['model'].answer(question, as_of_year)['answer']
        output = evaluate_stages(bench, cfg['years'], predict, resolve(args.output))
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
