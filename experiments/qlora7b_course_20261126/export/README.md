# GGUF export (reproduction instructions)
Use the pinned unquantized Hugging Face snapshot `Qwen/Qwen2.5-7B-Instruct` revision `a09a35458c702b33eeacc393d103063234e8bc28` and the verified 2026 adapter from the checkpoint archive. Do not merge the NF4 training base. Verify adapter SHA against `../manifests/gguf_manifest_reported.json` before merging. Keep temporary files on a large disk; 30 GiB available RAM was sufficient for the successful shardwise method. The earlier PEFT/Accelerate full-model merge failed with meta tensors.

On Linux with the same Python environment as training, set BASE, ADAPTER, TMP, DEST to absolute paths; run from this directory. Use llama.cpp tag b5400. The following commands reproduce the method (new paths, not previously existing output files):

```bash
set -e
mkdir -p "$TMP" "$DEST"
git clone --depth 1 --branch b5400 https://github.com/ggml-org/llama.cpp.git "$TMP/llama.cpp"
LLAMA="$TMP/llama.cpp"
cmake -S "$LLAMA" -B "$LLAMA/build" -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF
cmake --build "$LLAMA/build" --config Release --target llama-quantize --parallel 2
python "$LLAMA/convert_hf_to_gguf.py" "$BASE" --outfile "$TMP/base-f16.gguf" --outtype f16
"$LLAMA/build/bin/llama-quantize" "$TMP/base-f16.gguf" "$DEST/qwen2.5-7b-instruct-q4_k_m.gguf" Q4_K_M
python merge_shards.py "$BASE" "$ADAPTER" "$TMP/merged_7b"
python "$LLAMA/convert_hf_to_gguf.py" "$TMP/merged_7b" --outfile "$TMP/chronoreg-f16.gguf" --outtype f16
"$LLAMA/build/bin/llama-quantize" "$TMP/chronoreg-f16.gguf" "$DEST/chronoreg-lora-7b-q4_k_m.gguf" Q4_K_M
sha256sum "$DEST/"*.gguf
```

Compare hashes with reported manifest; differences across environments require investigation. Downloaded hashes matched the reported originals. GGUF generation/inference quality and Ollama integration have NOT been verified here. No external artifact URL has been provided; team must share binaries separately. Do not add the multi-GB GGUFs to Git.
