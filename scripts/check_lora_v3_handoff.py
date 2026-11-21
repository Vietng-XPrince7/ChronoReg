"""Run: python scripts/check_lora_v3_handoff.py /path/to/extracted-v3 [--json out.json]"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.lora.verified_v3 import verify_v3


def main():
    parser = argparse.ArgumentParser(description="Verify V3 LoRA artifacts SHA and per-year chain")
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    evidence = verify_v3(args.root)
    result = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.json:
        args.json.write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
