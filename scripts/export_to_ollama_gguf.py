"""Export and merge ChronoReg QLoRA 3B adapter for offline CPU inference via Ollama + GGUF (Q4_K_M).

Chạy trên máy có GPU (máy train LoRA):
1. Nạp Base Model (Qwen/Qwen2.5-3B-Instruct hoặc đường dẫn local qua --base-model / BASE_MODEL_PATH)
   và checkpoint LoRA (--lora-adapter).
2. Gộp trọng số: model = PeftModel.from_pretrained(base_model, lora_adapter).merge_and_unload()
   và lưu ra thư mục artifacts/merged_lora_3b/.
3. Sinh tự động Modelfile.base và Modelfile.lora trong artifacts/ollama/.
4. In hướng dẫn chi tiết từng bước convert HF -> GGUF -> Q4_K_M -> ollama create.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_MODEL = (
    os.environ.get("CHRONOREG_BASE_MODEL")
    or os.environ.get("BASE_MODEL_PATH")
    or "Qwen/Qwen2.5-3B-Instruct"
)
DEFAULT_LORA_ADAPTER = str(
    REPO_ROOT
    / "experiments"
    / "qlora3b_full_main_v5_20261116"
    / "checkpoints"
    / "checkpoints"
    / "year-2026"
)
DEFAULT_OUTPUT_DIR = str(REPO_ROOT / "artifacts" / "merged_lora_3b")
DEFAULT_OLLAMA_DIR = str(REPO_ROOT / "artifacts" / "ollama")

BASE_SYSTEM_PROMPT = (
    "Bạn là trợ lý học vụ UET. Chỉ trả lời chính xác dựa trên các đoạn văn bản pháp quy "
    "được cung cấp, giữ nguyên mọi con số định mức và số hiệu Quyết định, không tự suy diễn."
)

LORA_SYSTEM_PROMPT = (
    "Bạn là trợ lý học vụ UET. Trả lời ngắn, đúng phạm vi câu hỏi; "
    "không bịa quy định hay năm hiệu lực."
)

MODELFILE_BASE_TEMPLATE = """FROM ./qwen2.5-3b-instruct-q4_k_m.gguf

PARAMETER temperature 0.1
PARAMETER num_ctx 4096

SYSTEM \"\"\"{system_prompt}\"\"\"
"""

MODELFILE_LORA_TEMPLATE = """FROM ./chronoreg-lora-3b-q4_k_m.gguf

PARAMETER temperature 0.2
PARAMETER num_ctx 2048

SYSTEM \"\"\"{system_prompt}\"\"\"
"""


def generate_ollama_modelfiles(ollama_dir: Path | str) -> tuple[Path, Path]:
    """Tạo Modelfile.base và Modelfile.lora trong thư mục artifacts/ollama/."""
    target_dir = Path(ollama_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    modelfile_base = target_dir / "Modelfile.base"
    modelfile_lora = target_dir / "Modelfile.lora"

    modelfile_base.write_text(
        MODELFILE_BASE_TEMPLATE.format(system_prompt=BASE_SYSTEM_PROMPT),
        encoding="utf-8",
    )
    modelfile_lora.write_text(
        MODELFILE_LORA_TEMPLATE.format(system_prompt=LORA_SYSTEM_PROMPT),
        encoding="utf-8",
    )
    return modelfile_base, modelfile_lora


def merge_lora_weights(
    base_model_path: str,
    lora_adapter_path: str,
    output_dir: Path | str,
    *,
    dtype: str = "float16",
    device_map: str = "auto",
) -> Path:
    """Nạp Base Model + LoRA adapter, gộp trọng số bằng merge_and_unload() và lưu ra đĩa."""
    adapter_dir = Path(lora_adapter_path)
    if not adapter_dir.exists():
        raise FileNotFoundError(
            f"Không tìm thấy thư mục LoRA adapter: {adapter_dir}. "
            "Hãy truyền đúng đường dẫn qua --lora-adapter."
        )

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Thiếu thư viện PyTorch / Transformers / PEFT để gộp trọng số. "
            f"Chi tiết: {exc}"
        ) from exc

    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    torch_dtype = dtype_map.get(dtype.lower(), torch.float16)
    if not torch.cuda.is_available() and torch_dtype == torch.float16:
        # Trên CPU thuần dùng float32 an toàn khi merge để tránh lỗi half-precision ops
        torch_dtype = torch.float32

    resolved_device_map = device_map if torch.cuda.is_available() else "cpu"

    print(f"[1/3] Đang nạp Base Model: {base_model_path} (dtype={torch_dtype}, device_map={resolved_device_map})...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=False)
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        torch_dtype=torch_dtype,
        device_map=resolved_device_map,
        trust_remote_code=False,
    )

    print(f"[2/3] Đang nạp LoRA adapter từ: {adapter_dir} và thực hiện merge_and_unload()...")
    peft_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    merged_model = peft_model.merge_and_unload()

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    print(f"[3/3] Đang lưu mô hình đã gộp trọng số ra: {out_path}...")
    merged_model.save_pretrained(str(out_path), safe_serialization=True)
    tokenizer.save_pretrained(str(out_path))
    return out_path


def format_deployment_instructions(
    base_model_path: str,
    merged_dir: Path | str,
    ollama_dir: Path | str,
    llama_cpp_dir: str = "./llama.cpp",
) -> str:
    """Tạo hướng dẫn chi tiết chuyển đổi GGUF Q4_K_M và đăng ký với Ollama."""
    merged_str = str(merged_dir)
    ollama_str = str(ollama_dir)
    quantize_bin = f"{llama_cpp_dir}/build/bin/llama-quantize"
    convert_script = f"{llama_cpp_dir}/convert_hf_to_gguf.py"

    lines = [
        "",
        "=" * 78,
        "HƯỚNG DẪN ĐÓNG GÓI GGUF (Q4_K_M) & ĐĂNG KÝ OLLAMA CHO LAPTOP DEMO (CPU)",
        "=" * 78,
        "",
        "# Bước 1: Chuẩn bị llama.cpp (nếu chưa build trên máy GPU):",
        f"git clone https://github.com/ggerganov/llama.cpp {llama_cpp_dir}",
        f"cmake -B {llama_cpp_dir}/build -S {llama_cpp_dir} && cmake --build {llama_cpp_dir}/build --config Release -j",
        f"pip install -r {llama_cpp_dir}/requirements.txt",
        "",
        "# Bước 2: Chuyển Base Model (Qwen2.5-3B-Instruct) sang GGUF F16 và lượng tử hóa Q4_K_M:",
        f"# (Nếu --base-model là repo HF, hãy tải về thư mục local trước, VD: ./models/Qwen2.5-3B-Instruct)",
        f"python {convert_script} {base_model_path} --outfile {ollama_str}/qwen2.5-3b-instruct-f16.gguf --outtype f16",
        f"{quantize_bin} {ollama_str}/qwen2.5-3b-instruct-f16.gguf {ollama_str}/qwen2.5-3b-instruct-q4_k_m.gguf Q4_K_M",
        "",
        "# Bước 3: Chuyển mô hình đã merge LoRA (artifacts/merged_lora_3b) sang GGUF F16 và lượng tử hóa Q4_K_M:",
        f"python {convert_script} {merged_str} --outfile {ollama_str}/chronoreg-lora-3b-f16.gguf --outtype f16",
        f"{quantize_bin} {ollama_str}/chronoreg-lora-3b-f16.gguf {ollama_str}/chronoreg-lora-3b-q4_k_m.gguf Q4_K_M",
        "",
        "# Bước 4: Copy thư mục sau sang laptop demo CPU:",
        f"#   - {ollama_str}/qwen2.5-3b-instruct-q4_k_m.gguf  (~1.9 GB)",
        f"#   - {ollama_str}/chronoreg-lora-3b-q4_k_m.gguf    (~1.9 GB)",
        f"#   - {ollama_str}/Modelfile.base",
        f"#   - {ollama_str}/Modelfile.lora",
        "",
        "# Bước 5: Trên laptop demo (đã cài Ollama), chạy 2 lệnh sau để tạo model:",
        f"cd {ollama_str}",
        "ollama create chronoreg-base:3b -f Modelfile.base",
        "ollama create chronoreg-lora:3b -f Modelfile.lora",
        "",
        "# Bước 6: Kiểm tra Ollama đã sẵn sàng chưa:",
        "ollama list",
        "# Sau đó khởi chạy web demo: python -m uvicorn src.api.studenthub_server:app --port 8000",
        "=" * 78,
    ]
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge QLoRA 3B adapter vào Qwen2.5-3B-Instruct và sinh cấu hình Ollama GGUF."
    )
    parser.add_argument(
        "--base-model",
        default=DEFAULT_BASE_MODEL,
        help="HF model ID hoặc đường dẫn local tới Qwen2.5-3B-Instruct (env: CHRONOREG_BASE_MODEL / BASE_MODEL_PATH).",
    )
    parser.add_argument(
        "--lora-adapter",
        default=DEFAULT_LORA_ADAPTER,
        help="Đường dẫn tới checkpoint LoRA adapter (mặc định: year-2026 checkpoint).",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Thư mục lưu mô hình sau khi merge_and_unload() (mặc định: artifacts/merged_lora_3b/).",
    )
    parser.add_argument(
        "--ollama-dir",
        default=DEFAULT_OLLAMA_DIR,
        help="Thư mục lưu Modelfile.base và Modelfile.lora (mặc định: artifacts/ollama/).",
    )
    parser.add_argument(
        "--llama-cpp-dir",
        default="./llama.cpp",
        help="Đường dẫn thư mục llama.cpp để in hướng dẫn chuyển đổi GGUF.",
    )
    parser.add_argument(
        "--dtype",
        choices=["float16", "bfloat16", "float32"],
        default="float16",
        help="Kiểu dữ liệu nạp Base Model khi merge trên GPU.",
    )
    parser.add_argument(
        "--modelfiles-only",
        action="store_true",
        help="Chỉ tạo Modelfile.base / Modelfile.lora và in hướng dẫn (không thực hiện nạp/merge trọng số).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    modelfile_base, modelfile_lora = generate_ollama_modelfiles(args.ollama_dir)
    print(f"Đã tạo: {modelfile_base}")
    print(f"Đã tạo: {modelfile_lora}")

    if not args.modelfiles_only:
        merge_lora_weights(
            base_model_path=args.base_model,
            lora_adapter_path=args.lora_adapter,
            output_dir=args.output_dir,
            dtype=args.dtype,
        )
        print(f"Đã lưu merged LoRA 3B tại: {args.output_dir}")
    else:
        print("[Chế độ --modelfiles-only] Bỏ qua bước nạp và merge trọng số HuggingFace.")

    print(
        format_deployment_instructions(
            base_model_path=args.base_model,
            merged_dir=args.output_dir,
            ollama_dir=args.ollama_dir,
            llama_cpp_dir=args.llama_cpp_dir,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

