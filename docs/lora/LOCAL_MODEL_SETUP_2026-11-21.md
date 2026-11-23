# Cài checkpoint LoRA V3 sau khi merge — ChronoReg

Phần mã nguồn được merge vào `main` **không đồng nghĩa** adapter V3 và base model Qwen 3B đã có trong Git. Không gọi inference là thật nếu thiếu trọng số. Đường chạy thật là `src.lora.verified_v3`, không phải prediction bank trong API legacy.

## Một lần cài model (Windows PowerShell)

```powershell
cd "$HOME\ChronoReg-main"
python scripts/setup_lora_v3.py --archive "$HOME\Downloads\ChronoReg_LoRA_3B_Trained_V3.zip" --download-base
```

`--download-base` tải Qwen2.5-3B-Instruct từ Hugging Face khi có Internet, chỉ sau khi được người chạy yêu cầu. Nếu đã có Qwen cục bộ, chép nó vào `.local_models/Qwen2.5-3B-Instruct` (phải có `config.json`, tokenizer và trọng số). Không cần tải model từ Kaggle Input. Mô hình có thể cần vài GB dung lượng và máy GPU để inference 4-bit hiệu quả.

Nếu đã cài model, chỉ kiểm tra lại:

```powershell
python scripts/setup_lora_v3.py
python -m pytest -q tests/test_lora_runtime_setup.py tests/test_verified_v3_handoff.py tests/test_evidence_selector.py tests/test_academic_api_v2.py
```

Kết quả mong đợi: `INSTALLED_AND_SHA_VERIFIED` hoặc `ALREADY_INSTALLED`, `ARTIFACT_INTEGRITY_PASS`. Chỉ báo `ready_for_gpu_inference` nghĩa là có cả file adapter và base; chương trình **không** tự nhận đã chạy GPU hoặc có độ chính xác đạt chuẩn.

## Chạy API

```powershell
$env:CUDA_VISIBLE_DEVICES = "0"
python -m uvicorn src.api.studenthub_server:app --host 127.0.0.1 --port 8000
```

`POST /api/answer-v2` dùng đường PEFT khi câu hỏi phù hợp và bộ chọn có bằng chứng năng lực, hoặc trong chế độ so sánh nghiên cứu. **Không** tự động dùng LoRA để trả lời các quy định chính thức khi chưa chứng minh độ chính xác. Giao diện cũ `/api/chat` chưa chuyển sang API mới.

## Giới hạn cần công bố

- V3 là 396 QA từ 53 tài liệu, không phải LoRA toàn bộ kho quy chế.
- SHA của 5 adapter được kiểm tra; `run_config.json` của V3 có pin base revision `aa8e72537993ba99e69dfaafa59ed015b17504d1`. Bộ cài dùng đúng revision này. Nếu tự chép model vào cache không có dấu revision thì chương trình ghi rõ `revision_verified=false`; không được gọi đó là kiểm chứng đầy đủ mô hình nền.
- Benchmark 90 câu của V3 chỉ là chẩn đoán, chưa qua khóa V8. Không tuyên bố RAG hoặc LoRA là nhánh thắng nếu chưa có đối chứng đáng tin cậy.
- `.local_models/` bị loại khỏi Git để tránh đưa nhiều GB trọng số vào commit; cần một kho artifact có quản lý (GitHub Releases / Hugging Face / LFS) nếu muốn người khác clone repo có thể tự tải model mà không cần nhận ZIP.
