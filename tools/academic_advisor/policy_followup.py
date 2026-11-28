"""Scoped public-policy continuation; recheck exact source and holds every turn."""
import re
from quality import norm
from quality_routes import pinned,source_response,response

def return_to_study(q,prior,root):
    n=norm(q)
    if not re.search(r'\b(?:hoc tiep|hoc tro lai|quay lai hoc)\b',n) or not re.search(r'\b(?:tam nghi|tam thoi|bao luu|nghi hoc|thoi han nghi)\b',n) or not re.search(r'\b(?:han|thoi diem|moc|khi nao|bao lau|cham nhat)\b',n):return None
    expected={'kind':'policy_clause','article':36,'clause':3,'instrument':'3626'}
    same=all(prior.get(k)==v for k,v in expected.items())
    explicit=bool(re.search(r'\b3626\b',n))
    if not (same or explicit):
        if re.search(r'\b(?:cung quyet dinh|cung quy che|quyet dinh do|quy che do|van ban do|thoi han nghi|nghi hoc tam thoi)\b',n):
            return response('Dạ cô, chưa xác định được văn bản ở lượt trước. Cô cho em số hiệu quyết định để tra đúng hạn.','policy_scope'),{}
        return None
    instruments=re.findall(r'\b(?:qd|quyet dinh) (\d{2,8})\b',n)
    if any(x!='3626' for x in instruments) or re.search(r'\b(?:5115|3079|k71|khoa 2026|qh 2026|2020|2021|k65|k66|thong tu|nghi dinh|so sanh|hoc phi|hoc bong|mssv|hutech|ulis|uit|bach khoa|thac si|tien si)\b',n) or re.search(r'\b\d{8}\b',n):
        return response('Dạ cô, cần đối chiếu đúng văn bản và phạm vi mới, không tự áp dụng mốc từ QĐ 3626.','policy_scope'),{}
    c=pinned(root,'Điều 36 khoản 3 QĐ 3626')
    if not c:return response('Dạ cô, chưa có điều khoản đủ căn cứ để xác định hạn nộp đơn.','policy_unavailable'),{}
    # Pull sentence from actual clause, never substitute a date from other evidence.
    m=re.search(r'Sinh viên nghỉ học tạm thời nếu muốn học tiếp phải có đơn[^.]+\.',c['answer'],re.I)
    if not m:return response('Dạ cô, chưa trích được câu quy định về học tiếp.','policy_unavailable'),{}
    return source_response('Theo khoản 3 Điều 36 QĐ 3626: '+m[0]+' Cần đối chiếu phạm vi áp dụng và thủ tục của UET.','return_to_study',c),{'kind':'policy_clause','article':36,'clause':3,'instrument':'3626'}
