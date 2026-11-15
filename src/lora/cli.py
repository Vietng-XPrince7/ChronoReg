"""Only active LoRA entrypoint: Qwen2.5-3B NF4 continual QLoRA."""
from __future__ import annotations

from .qlora3b import main

if __name__ == '__main__':
    raise SystemExit(main())
