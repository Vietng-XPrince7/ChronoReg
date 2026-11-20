# CHRONOREG — CHỐT THÍ NGHIỆM CONTINUAL QLORA 3B

**Ngày chốt hồ sơ:** 20/11/2026  
**Phạm vi:** Phần LoRA phục vụ đồ án KHDV, KHÔNG phải DATA 7 ngành, RAG, web, hay phát hành trợ lý quy chế chính thức.  
**Trạng thái:** **ĐÃ CHỐT THỰC NGHIỆM COURSE-MODE V1; CHƯA ĐẠT NGHIỆM THU NỘI DUNG QUY CHẾ / TRI THỨC PHÁP LÝ.**

## 1. Nguồn đầu vào và nguyên tắc khóa

1. ZIP repository thời điểm huấn luyện: `ChronoReg-main (6)(1).zip`; SHA-256 `fde3fabf8dc1894975f628676b439ee400a72ad46011949d3c38727a07dd3d46`; commit tham chiếu lúc tạo `f32d4e2`.
2. ZIP Kaggle suy luận retention thật: `ChronoReg_LoRA_RETENTION_45_REAL_RESULTS.zip`; SHA-256 `89c386afa124888469f715098a663b2206ea3fdeab9cc5421ba0389931469938`.
3. Train 200 QA: SHA-256 `1e7f8dffa8425e6a441f651bb320935bd4e1e32a69933ac5073e85a55d71851e`.
4. Benchmark regression 90: SHA-256 `47497e6bea518c95fa9c3b674fc63ccf022cc625e73da056c3e87bc63a70596f`.
5. 450 predictions: SHA-256 `50eeff18b66e733dd377d17feec17cc7ca9eaf`.
6. Điểm kết thúc huấn luyện course 2026: SHA-256 adapter `95c82416cd768f75145f220a670d563dc4f77c3c01ea39abf2ed4b54cf38dba3`.

**Lưu ý về `main` hiện nay:** Repo đã cập nhật DATA 7 ngành tại commit `eff1989` sau snapshot thí nghiệm; ít nhất ba Markdown Hàng không vũ trụ đã được làm sạch. Không cập nhật SHA nguồn trong tập train cũ để giả vờ thí nghiệm được huấn luyện bằng văn bản mới. Nếu tái lập, dùng đúng snapshot lịch sử hoặc bảo toàn bản gốc dưới archive.

## 2. Kết quả kiểm tra các thành phần

| Hạng mục | Phán quyết kỹ thuật | Bằng chứng |
| --- | --- | --- |
| Khả năng **đọc QA khi huấn luyện** | PASS | `course_train_runner.py` lấy `question`, `answer`, `as_of_year`, token hóa và tạo `labels` trên câu trả lời cho `Trainer`. Không đưa toàn văn Markdown vào mô hình. |
| Cấu hình continual QLoRA | PASS về triển khai | Qwen2.5-3B-Instruct; NF4 4-bit; LoRA r8 alpha16; 5 giai đoạn 2022→2026, nạp adapter trước để tiếp tục cập nhật. |
| 5 checkpoint có trọng số thật | PASS | 5/5 SHA và `previous_adapter_sha256` hợp lệ, provenance chuỗi không đứt. |
| Manifest thí nghiệm course | PASS có ngoại lệ lịch sử | Đối chiếu 60 file: 59 khớp; **một file test** `reproduction/test_course_runner.py` có SHA ghi trong manifest cũ, thực tế trên repository không khớp. Không sửa manifest/đánh dấu 60/60 tuyệt đối. |
| 200 QA train | PASS tính toàn vẹn | 200/200 nguồn SHA chính xác và có nguyên văn `evidence_quote` trong Markdown snapshot. |
| Kiểm tra mã học phần + cột tín chỉ | PASS kiểm tra cấu trúc | **64/64** QA `curriculum_course_credits`: mã môn hỏi/đáp trùng, trùng mã học phần trong dòng bảng, số tín chỉ nằm đúng cột. |
| QA nội dung/tính hiệu lực được người độc lập duyệt | **BLOCKED** | 0/200 `independent_review_verified=true`, 0/200 `effective_year_verified=true`. Kiểm tra kỹ thuật không thay thế duyệt nội dung. |
| Benchmark regression 90 câu | PASS về khóa dữ liệu, **NOT BLIND / REVIEW PENDING** | 90/90 câu có SHA và ID nhất quán; 0 trùng nguyên văn câu train nhưng **49/90 chung nguồn Markdown** với train course (6 tài liệu); vẫn cần rà semantic overlap. |
| Đánh giá 450 dự đoán | PASS về tính tái lập | 450 cặp checkpoint×question, chấm Token F1 kiểm tra lại ra đúng dữ liệu đã lưu. |
| Retention in-sample | PASS về dữ liệu và suy luận | 25/25 câu lấy từ train gốc, 45/45 dự đoán Kaggle, check adapter đúng mỗi năm; chấm lại từ đầu cho ra cùng file và checksum. |
| Full-main v5, **thí nghiệm khác** | CHƯA RELEASE | 2.732 train, 574 validation; 2023 không có validation; 10 trường `evidence_quote` ghép hàng nên chưa khớp nguyên văn. KHÔNG lấy kết quả course gán cho v5. |

## 3. Diễn giải thí nghiệm LoRA chính xác

**Dataset course:** 200 cặp QA — 40/37/36/49/38 theo nhãn năm 2022–2026. Gồm 82 QA học phí, 39 QA học bổng, 64 QA tín chỉ học phần, 15 QA tổng tín chỉ. Dữ liệu 2022 có 40/40 QA tín chỉ học phần, không có QA học phí. Đây là phân bổ mang tính thăm dò, không đại diện toàn bộ văn bản học vụ mỗi năm. Mỗi giai đoạn huấn luyện 2 epoch, tích lũy gradient 8; số bước cập nhật nhỏ, có thể góp phần vào chất lượng kém nhưng chưa được kiểm chứng nguyên nhân bằng ablation.

**450 dự đoán:** Token F1 trung bình theo checkpoint: 2022 **0,4616**, 2023 **0,4430**, 2024 **0,4042**, 2025 **0,3613**, 2026 **0,3723**. **Không coi Token F1 là tỷ lệ trả lời đúng.** Ví dụ `BENCH_ACT_013` có F1 0,7000 dù đáp án là **3.500.000** so với gold **4.400.000 đồng/tháng**.

**Retention train-in-sample:** 45 lượt = 20 câu cũ × (checkpoint cùng năm và 2026) + 5 câu train 2026 (checkpoint 2026). **2/45** trả lời đúng giá trị số, **39/45** sai, **4/45** không đưa ra giá trị đích. Ở 20 cặp câu cũ, hai câu đúng tại checkpoint ban đầu chuyển thành sai ở 2026; **18/20** sai cả hai lần. Năm câu train mới 2026 đều sai. Đây là bằng chứng có hai trường hợp *suy giảm tái hiện dữ kiện*, nhưng **không chứng minh catastrophic forgetting**, cũng không đo generalization held-out.

Ví dụ dữ kiện có nguyên văn trong Markdown: `ELT2035` (AI QH-2022–2024 bản gốc) và `CTE2024` (Thiết kế công nghiệp và đồ họa QH-2024) đều **3 tín chỉ** ở nguồn, checkpoint cùng năm đúng 3, checkpoint 2026 trả lời 1. Không suy diễn nguyên nhân do cập nhật tham số khi chưa có đối chứng.

## 4. Cửa ải chất lượng nguồn và QA đang chặn release

- 200 QA có kiểm tra exact-source, nhưng **0/200 được duyệt độc lập**. Chưa thể xác nhận đầy đủ tính chính xác theo khóa, điều khoản, hiệu lực, thay thế/sửa đổi.
- Bộ 90 câu là **regression đã được sử dụng**, không blind. Theo hồ sơ rà soát V6: **53/90** có căn cứ được AI phân loại `APPROVE_CURRENT`/`APPROVE_HISTORICAL`, **8/90** `REVISE` và **29/90** `PENDING`. Đây không phải phê duyệt của người.
- `as_of_year` hiện là nhãn phục vụ bài toán huấn luyện; không nhất thiết chứng minh năm tài liệu có hiệu lực pháp lý. Trường hợp học phí 2022–2023 có văn bản điều chỉnh trong chính năm học nên không thể dựa vào tên file hoặc năm ban đầu.
- Các câu `superseded_rule` chỉ được gán khi có **bằng chứng thay thế thực sự**; cùng seri / tham chiếu tài liệu không đủ.
- Báo cáo V9 về full-main v5 ghi **106 hàng trên hold**, **2.890 hàng không có ledger nguồn tương ứng**, **310 hàng đã được xem xét nguồn nhưng chưa duyệt QA**; `release_authorized=false`. Không chuyển nhầm kết quả v5 thành release được phép.
- Bảy ngành UET: 17 Markdown trong repo là DATA (có toàn văn), không phải tự động làm 17 nguồn đã vào course train; course chỉ lấy 9/17, full-v5 lấy 8/17. `retrieval_eligible=false` cho cả 17 vì chưa có phê duyệt. LoRA **không sử dụng RAG** trong suy luận; nó dựa trên QA đã được dùng khi train.

## 5. Phán quyết bàn giao

**ĐẠT để bàn giao:** một **baseline nghiên cứu course-mode** có mã, dữ liệu, trọng số, suy luận thật, phương pháp chấm, kết quả âm tính và giới hạn; dừng vòng chạy GPU cho baseline này.

**CHƯA ĐẠT:** mô hình trả lời đúng quy chế/hiệu lực UET, chuẩn QA đã được người chứng nhận, benchmark blind hoặc mô hình có thể tích hợp sản phẩm xử lý học vụ. Những cổng này không được tự động chuyển PASS.

### Đề nghị chốt với nhóm

- Nhóm xác nhận nhận **thí nghiệm có kết quả âm tính** và sử dụng nó làm phương án so sánh với RAG. Chữ ký/đánh giá của nhóm không được giả mạo bằng script.
- Nếu nhóm yêu cầu dữ liệu/benchmark **đã được duyệt**, phải duyệt riêng với tài liệu UET: trước hết 8 câu V6 yêu cầu sửa, 29 câu pending, 200 QA chưa ký, và quyết định lại theo bằng chứng `replaces`/năm hiệu lực. Đây là một nhiệm vụ quản trị dữ liệu mới, **không thay đổi kết quả đã khóa**.
- **Không retrain** trên sửa đổi benchmark để làm đẹp điểm; nếu cần phiên bản chất lượng tốt hơn, mở thí nghiệm có ID, nguồn QA đã duyệt và benchmark blind hoàn toàn mới, không gọi kết quả đó là cùng baseline này.

## 6. Điều kiện chấm dứt công việc LoRA v1

- Đã đủ: 5 adapter, 200 QA, 450 predictions, 45 retention predictions; xác minh checksum và mã tái lập; báo cáo rõ sai số liệu và giới hạn.
- Không còn lý do kỹ thuật bắt buộc chạy Kaggle cho v1.
- **Phần còn lại về mặt tổ chức:** người phụ trách/giảng viên/người duyệt chấp nhận báo cáo hạn chế và nếu cần ký nhận; không phải công việc GPU/triển khai còn thiếu.

**Tiến độ diễn giải:** thực thi thí nghiệm **100%**; chuẩn bị hồ sơ bàn giao **~95%**; nghiệm thu tính đúng quy chế/độ an toàn sản phẩm **chưa đạt**. Phần trăm không phải accuracy.
