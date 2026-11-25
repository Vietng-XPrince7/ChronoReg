"""One real V3 model per web server process; never replay stored answers."""
from __future__ import annotations

import logging
from threading import RLock
from typing import Any

log = logging.getLogger(__name__)


class WebLoRARuntime:
    def __init__(self):
        self._lock = RLock()
        self._model = None
        self._state = "NOT_STARTED"
        self._reason = None
        self._device = None

    def preload(self) -> dict[str, Any]:
        """Attempt exactly once per server process. Missing files do not stop RAG."""
        with self._lock:
            if self._state != "NOT_STARTED":
                return self.status()
            self._state = "LOADING"
            try:
                from src.lora.verified_v3 import from_environment
                model = from_environment()
                model._load()  # verifies and loads actual PEFT weights, no generation/replay
                if model._model is None or model._tok is None:
                    raise RuntimeError("PEFT weights or tokenizer not loaded")
                self._model = model
                self._device = model._device
                self._state = "READY"
                log.info("CHRONOREG_LORA_READY: V3 year-2026 on %s", self._device)
                print(f"CHRONOREG_LORA_READY: V3 year-2026 on {self._device}", flush=True)
            except Exception as exc:
                self._model = None
                self._state = "UNAVAILABLE"
                self._reason = str(exc)
                log.warning("CHRONOREG_LORA_UNAVAILABLE: %s", exc)
                print(f"CHRONOREG_LORA_UNAVAILABLE: {exc}", flush=True)
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"status": self._state, "ready": self._state == "READY",
                    "model": "Qwen2.5-3B-Instruct + verified V3",
                    "checkpoint_year": 2026, "device": self._device,
                    "reason": self._reason, "quality_qualified": False,
                    "offline_answer_fallback": False}

    def generate(self, question: str, *, as_of_year: int | None = None) -> dict:
        # Serialize GPU requests: the same resident model is reused by all endpoints.
        with self._lock:
            if self._state != "READY" or self._model is None:
                raise RuntimeError(f"LoRA not ready: {self._reason or self._state}")
            result = self._model.generate(question, as_of_year=as_of_year)
            if result.get("engine_mode") != "LIVE_PEFT_GENERATION" or not result.get("answer", "").strip():
                raise RuntimeError("Live PEFT generation returned empty or non-live output")
            return result


web_lora = WebLoRARuntime()
