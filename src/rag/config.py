"""Đọc configs/rag.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else ROOT / "configs" / "rag.yaml"
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(rel: str) -> Path:
    """Đường dẫn tương đối trong config -> đường dẫn tuyệt đối từ gốc repo."""
    return ROOT / rel
