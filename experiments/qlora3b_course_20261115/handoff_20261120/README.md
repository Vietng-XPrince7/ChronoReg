# ChronoReg QLoRA3B — Hồ sơ chốt thí nghiệm nghiên cứu 20/11/2026

**Kết luận:** Thí nghiệm course-mode đã hoàn thành; KHÔNG tuyên bố model trả lời đúng quy chế, benchmark blind hay có dữ liệu được duyệt độc lập.

Đọc `FINAL_REPORT_VI.md` trước. Các bảng nằm trong `results/`; `VERIFICATION.json` là kết quả kiểm tra trực tiếp dữ liệu gốc, không phải bản tường thuật.

## Kiểm tra lại bằng Python (không GPU)

Lưu đúng hai ZIP gốc như trong báo cáo, sau đó chạy:

```bash
python verify_final.py --repo-zip "ChronoReg-main (6)(1).zip" \
  --retention-zip "ChronoReg_LoRA_RETENTION_45_REAL_RESULTS.zip" \
  --out results
```

Cần Python 3.10+; chỉ dùng thư viện chuẩn. Khóa SHA snapshot gốc; thay đổi file sẽ báo lỗi. Tập retention dùng SHA của **danh sách JSON được canonical hóa** (`sort_keys=True`, separators=(',',':')), khác SHA các byte JSONL trực tiếp — tránh so nhầm.

Các đầu ra:
- `VERIFICATION.json`: 60 mục manifest, 5 checkpoint, 200 QA, 64 QA học phần được kiểm cột, 450 dự đoán, 45 retention, 49 benchmark chung nguồn.
- `results/RETENTION_25_PAIRED.csv`, `results/RETENTION_45_SCORED.csv`: bảng chấm retention thực.
- `results/BENCHMARK_90_REVIEW_AI_NOT_SIGNED.csv`: danh sách 90 câu với các nhãn rà soát AI, không phải chữ ký con người.
- `results/COURSE_QA_200_TECH_AUDIT.csv`: kiểm tra kỹ thuật 200 QA, không phê duyệt hiệu lực.
- `results/CURRICULA_17_TRAIN_COVERAGE.csv`: phạm vi dữ liệu 7 ngành đã dùng trong các thí nghiệm.
- `results/REGRESSION_450_WITH_DIAGNOSTICS.csv`: 450 lượt trả lời course-mode; Token F1 chỉ là chỉ số từ vựng.

`verify_final.py` **chỉ đọc hai ZIP**, không đổi checkpoint, train, benchmark hoặc GitHub. Có **một ngoại lệ manifest lịch sử** (`reproduction/test_course_runner.py`) được đối chiếu SHA chính xác, không bỏ qua các lỗi khác. Báo cáo thử nghiệm không phải một approval dossier.
