"""Source-QA review tooling, separated from the active 3B model runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .candidates import propose
from .review import review_template, finalize_review


def main(argv=None):
    p = argparse.ArgumentParser(description='ChronoReg independent QA review')
    p.add_argument('--repo', type=Path, default=Path('.'))
    sub = p.add_subparsers(dest='command', required=True)
    x = sub.add_parser('propose')
    x.add_argument('--registry', default='data/versioning/documents.jsonl')
    x.add_argument('--output', default='src/lora/runs/candidates.jsonl')
    x = sub.add_parser('review-template')
    x.add_argument('--candidates', default='src/lora/runs/candidates.jsonl')
    x.add_argument('--registry', default='data/versioning/documents.jsonl')
    x.add_argument('--holds', default='data/versioning/publication_holds.jsonl')
    x.add_argument('--output', default='src/lora/runs/review_decisions.jsonl')
    x.add_argument('--coverage', default='src/lora/runs/review_coverage.csv')
    x = sub.add_parser('review-finalize')
    x.add_argument('--candidates', default='src/lora/runs/candidates.jsonl')
    x.add_argument('--decisions', default='src/lora/runs/review_decisions.jsonl')
    x.add_argument('--registry', default='data/versioning/documents.jsonl')
    x.add_argument('--holds', default='data/versioning/publication_holds.jsonl')
    x.add_argument('--benchmark', default=None)
    x.add_argument('--output', default='src/lora/runs/approved_qa.jsonl')
    x.add_argument('--coverage', default='src/lora/runs/review_coverage.csv')
    a = p.parse_args(argv)
    repo = a.repo.resolve()
    def resolve(path):
        if path is None: return None
        pth = Path(path)
        return pth if pth.is_absolute() else repo / pth
    if a.command == 'propose':
        out = propose(repo, resolve(a.registry), resolve(a.output))
    elif a.command == 'review-template':
        out = review_template(repo, resolve(a.candidates), resolve(a.registry),
                              resolve(a.holds), resolve(a.output), resolve(a.coverage))
    else:
        out = finalize_review(repo, resolve(a.candidates), resolve(a.decisions),
                              resolve(a.registry), resolve(a.holds), resolve(a.output),
                              resolve(a.coverage), resolve(a.benchmark))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
