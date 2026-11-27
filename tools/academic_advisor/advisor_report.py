"""Local draft reports from scoped facts, never an official decision or automatic outreach."""
from collections import Counter


def build_report(roster, *, groups=None, duplicate_records=0, student=None, flags=(), missing=(), history_rows=(), ambiguous=(), unknown=()):
    individual = student is not None
    title = 'Phiếu tư vấn cá nhân — BẢN NHÁP RIÊNG TƯ' if individual else 'Báo cáo hỗ trợ học tập của lớp — BẢN NHÁP TỔNG HỢP'
    scope = str(roster.get('class_short') or roster.get('class_id') or 'chưa xác định')
    lines = [title, f'Lớp: {scope} | Khóa: {roster.get("cohort") or "chưa xác định"}',
             f'Kỳ trong hồ sơ demo: {roster.get("semester") or "chưa xác định"}',
             'Căn cứ: hồ sơ demo đang mở, không thay thế bảng điểm hoặc quyết định chính thức.', '']
    actions = []
    def add(owner, action, check, checkpoint):
        actions.append({'owner':owner,'action':action,'completion_check':check,'checkpoint':checkpoint})
    if individual:
        lines += [f'Hồ sơ: {student.get("full_name") or "Sinh viên"} ({student.get("student_id") or student.get("mssv")})',
                  'Tín hiệu cần trao đổi: '+('; '.join(flags) if flags else 'Chưa phát hiện theo tiêu chí sàng lọc.'),
                  'Thông tin còn thiếu: '+(', '.join(missing) if missing else 'Chưa thấy thiếu ba trường sàng lọc; vẫn phải xác nhận GPA tích lũy, lịch sử cảnh báo và CTĐT.'),
                  'Học phần có lần không đạt, chưa thấy lần đạt: '+(', '.join(r[0] for r in history_rows) or 'Chưa xác định được từ hồ sơ.')]
        if ambiguous:lines.append('Mã có cả lần đạt và không đạt: '+', '.join(ambiguous)+'.')
        if unknown:lines.append('Mã chưa xác minh tín chỉ: '+', '.join(unknown)+'.')
        add('Cô và sinh viên','Trao đổi riêng về khó khăn, kiểm tra bảng điểm mới nhất.','Ghi nhận vấn đề do sinh viên xác nhận, GPA tích lũy và lịch sử cảnh báo.','Trước khi chốt phương án')
        if history_rows or ambiguous or unknown or any('tín chỉ nợ' in x for x in flags):
            add('Cô và sinh viên','Đối chiếu môn nợ, mã tương đương, tiên quyết và lịch mở lớp.','Danh sách môn cần học lại được đối chiếu với CTĐT và cổng đào tạo.','Trước khi đăng ký')
        add('Cô và sinh viên','Thống nhất mục tiêu khả thi và cách theo dõi.','Ghi mục tiêu, khối lượng dự kiến và mốc trao đổi tiếp theo do hai bên thống nhất.','Sau buổi tư vấn')
    else:
        groups = groups or {};counts={k:len(groups.get(k,[])) for k in range(1,5)}
        lines += ['Sàng lọc nội bộ, không phải phân loại cảnh báo học vụ:',
                  f'• Ưu tiên gặp riêng: {counts[1]} sinh viên.',f'• Cần trao đổi thêm: {counts[2]} sinh viên.',
                  f'• Cần bổ sung dữ liệu: {counts[3]} sinh viên.',f'• Chưa thấy tín hiệu: {counts[4]} sinh viên.',
                  f'• Bản ghi trùng/thiếu mã chưa phân nhóm: {duplicate_records}.',
                  'Ngưỡng hỗ trợ nội bộ: GPA học kỳ dưới 2,00; tín chỉ nợ lớn hơn 0; điểm rèn luyện dưới 70. Nhóm ưu tiên có đồng thời GPA thấp và tín chỉ nợ.']
        if counts[1]:add('Cô','Mời riêng nhóm ưu tiên để rà kết quả, khó khăn và lịch sử môn nợ.','Mỗi trường hợp có ghi nhận trao đổi và một bước hỗ trợ cụ thể.','Đợt gặp đầu tiên do cô sắp xếp')
        if counts[2]:add('Cô và sinh viên','Trao đổi với nhóm có tín hiệu cần hỗ trợ.','Xác định nhu cầu thực tế, tránh mặc định mọi tín hiệu là vi phạm quy chế.','Đợt gặp tiếp theo')
        if counts[3] or duplicate_records:add('Cô','Rà hồ sơ thiếu hoặc trùng mã.','Xác minh bản ghi trước khi phân nhóm lại.','Trước khi dùng kết quả để tư vấn')
        add('Cô','Gửi hướng dẫn tự rà soát chung, không công bố danh sách cá nhân.','Thông báo chỉ chứa hướng dẫn chung; kênh trao đổi riêng được nêu rõ.','Sau khi cô duyệt nội dung')
    add('Cô','Rà tiến độ và cập nhật phương án sau lần đánh giá tiếp theo.','Ghi lại kết quả thực tế và vấn đề còn mở.','Mốc do cô thống nhất')
    lines += ['', 'Kế hoạch hành động đề xuất (không phải hạn chính thức):']
    for i,a in enumerate(actions,1):lines += [f'{i}. {a["owner"]}: {a["action"]}', f'   Kiểm tra hoàn thành: {a["completion_check"]}', f'   Mốc: {a["checkpoint"]}']
    lines += ['', 'Trạng thái: chưa thực hiện, chưa gửi, chưa xác nhận. Cô duyệt và cập nhật theo hồ sơ thật trước khi sử dụng.']
    return {'title':title,'scope': 'individual_private' if individual else 'class_aggregate','text':'\n'.join(lines),'actions':actions,'draft':True}
