"""Product-only, scoped advisory planning. Facts are local roster records, not certification.
No student names/grades sent to LLM here. Never treats demo CPA alias as independent CPA.
"""
import math,re,time,statistics
from quality import norm
from regulation import lookup_regulation


def number(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None


def plan(question, bundle, root):
    start=time.monotonic();ab=bundle or {};category=ab.get('category');roster=ab.get('roster_obj') or {}
    if category not in ('STUDENT_STATUS','CLASS_STATS','ELIGIBILITY_CHECK'):return None
    students=roster.get('students') or [];target=ab.get('student_id')
    q=norm(question);cohort=roster.get('cohort','chưa rõ');class_name=roster.get('class_short') or roster.get('class_id') or 'lớp đang chọn'
    steps=[];lines=[];clauses=[]
    # A named administrative class must match the actual loaded roster.
    # Never use K69 records to answer a request about K68, etc.
    explicit_classes=set(re.findall(r'\b(?:lop\s+)?(k6[5-9]|k7[01])(?:\s+cntt\s*1)?\b',q))
    actual_classes=set(re.findall(r'\bk(?:6[5-9]|7[01])\b',norm(str(class_name)+' '+str(cohort))))
    if explicit_classes and actual_classes and not explicit_classes.issubset(actual_classes):
        return {'predicted_answer':f'Hồ sơ demo đang mở là {class_name} ({cohort}), không phải lớp được hỏi. Cần nạp đúng hồ sơ lớp trước khi phân tích; tôi không dùng dữ liệu lớp khác để suy ra kết quả.', 'mode':'chrono_rag','is_advisor_composite':True,'cited_doc_ids':[],'model_name':None,'inference_source':'deterministic_advisor_plan','engine_mode':'ADVISOR_PLAN','advisor_category':category,'advisor_entities':ab.get('entities'),'roadmap':[],'advisor_sources':[],'latency_ms':(time.monotonic()-start)*1000}
    if category=='STUDENT_STATUS':
        matches=[s for s in students if target and str(s.get('student_id') or s.get('mssv'))==str(target)]
        if len(matches)!=1:
            lines=['Không xác định được duy nhất sinh viên trong hồ sơ đang chọn. Vui lòng chọn sinh viên hoặc nhập đúng MSSV.']
        else:
            s=matches[0];g=number(s.get('gpa_semester'));dr=number(s.get('drl'));owed=number(s.get('owed_credits'));earned=number(s.get('accumulated_credits'))
            lines=[f"Hồ sơ demo: {s.get('full_name') or 'Sinh viên'} — {target} ({class_name}, {cohort})."]
            for label,val in [('GPA học kỳ',g),('Điểm rèn luyện',dr),('Tín chỉ tích lũy',earned),('Tín chỉ nợ theo hồ sơ',owed)]:
                if val is not None:lines.append(f'• {label}: {val:g}.')
            lines.append('GPA tích lũy (CPA độc lập với GPA học kỳ), lịch sử cảnh báo, kế hoạch học chuẩn và số tín chỉ còn thiếu chưa được xác nhận; không suy ra kết luận học vụ chính thức từ GPA.')
            if owed is not None and owed>0:
                codes={str(x.get('ma_mon')) for x in s.get('bang_diem',[]) if x.get('dat') is False and x.get('ma_mon')}
                if codes:lines.append('• Học phần từng không đạt (cần đối chiếu lần học lại): '+', '.join(sorted(codes))+'.')
                steps.append(('Ưu tiên xử lý học phần nợ','Đối chiếu học phần chưa đạt, điều kiện tiên quyết và lịch mở lớp với Phòng Đào tạo.'))
            if g is not None and g<2:
                steps.append(('Củng cố kết quả học tập','Trao đổi với cố vấn về nguyên nhân điểm thấp; lập kế hoạch ôn tập, hỗ trợ môn khó và rà giới hạn đăng ký.'))
            if dr is not None and dr<70:steps.append(('Rà soát điểm rèn luyện','Kiểm tra minh chứng và thời hạn phản hồi điểm; không mặc định được hay mất học bổng.'))
            if not steps:steps.append(('Duy trì tiến độ','Đối chiếu tín chỉ đã tích lũy với CTĐT đúng khóa, kiểm tra các học phần tiên quyết và chuẩn đầu ra.'))
            steps.append(('Chuẩn bị kỳ tiếp theo','Chọn học phần theo kế hoạch chuẩn và khả năng học tập; xác nhận lịch mở lớp trước khi đăng ký.'))
            steps.append(('Theo dõi cùng cố vấn','Rà kết quả sau mỗi đợt đánh giá, cập nhật kế hoạch theo điểm thực tế và thông báo của trường.'))
    else:
        lines=[f'Hồ sơ demo hiện có: {class_name}, {cohort}, {len(students)} sinh viên.']
        if not students:lines.append('Chưa có dữ liệu sinh viên để phân tích.')
        else:
            # Real descriptive statistics, no model-generated arithmetic. Missing
            # records are not treated as zero; ties are preserved.
            if re.search(r'\b(?:gpa|diem trung binh|trung binh lop|cao nhat|thap nhat|thong ke|tong quan|phan tich lop)\b',q):
                valid=[(number(s.get('gpa_semester')),s) for s in students]
                valid=[(v,s) for v,s in valid if v is not None and 0<=v<=4]
                if valid:
                    vals=[v for v,_ in valid];lo=min(vals);hi=max(vals)
                    lines.append(f'• GPA học kỳ: trung bình {statistics.mean(vals):.2f}; trung vị {statistics.median(vals):.2f}; thấp nhất {lo:.2f}; cao nhất {hi:.2f} (từ {len(vals)} hồ sơ có GPA hợp lệ).')
                    if re.search(r'\b(?:cao nhat|thap nhat|ai|em nao|sinh vien nao)\b',q):
                        for label,v in [('Cao nhất',hi),('Thấp nhất',lo)]:
                            matches=[str(st.get('full_name') or 'SV')+' ('+str(st.get('student_id') or st.get('mssv') or 'chưa rõ')+')' for g,st in valid if g==v]
                            lines.append('  '+label+': '+ '; '.join(matches)+'.')
                else:lines.append('Chưa có GPA học kỳ hợp lệ để tính thống kê.')
            # Only use actual roster values; do not reuse unverified eligibility flags.
            groups=[('GPA học kỳ dưới 2,0 — cần rà giới hạn đăng ký',lambda s: number(s.get('gpa_semester')) is not None and number(s.get('gpa_semester'))<2),('Còn tín chỉ nợ theo hồ sơ — cần đối chiếu',lambda s:(number(s.get('owed_credits')) or 0)>0),('Điểm rèn luyện dưới 70 — nhóm cần hỗ trợ',lambda s:number(s.get('drl')) is not None and number(s.get('drl'))<70)]
            if 'hoc bong' in q or 'kkht' in q:groups=[groups[2],('GPA học kỳ từ 3,20 — nhóm xem xét sơ bộ, không phải đủ điều kiện học bổng',lambda s:(number(s.get('gpa_semester')) or 0)>=3.2),groups[1]]
            for label,cond in groups:
                matched=[s for s in students if cond(s)];lines.append(f'• {label}: {len(matched)} sinh viên.')
                if matched and re.search(r'\b(?:liet ke|nhung em|em nao|sinh vien nao|danh sach|chi ro)\b',q):
                    lines.append('  '+ '; '.join(str(s.get('full_name') or 'SV')+' ('+str(s.get('student_id') or s.get('mssv') or 'chưa rõ')+')' for s in matched))
            lines.append('Các nhóm có thể giao nhau; ngưỡng hỗ trợ sơ bộ không phải quyết định cảnh báo, học bổng hay học vượt. GPA tích lũy (CPA) trong demo không độc lập với GPA học kỳ.')
        steps=[('Sàng lọc hồ sơ','Đối chiếu điểm, tín chỉ nợ và dữ liệu còn thiếu trước khi tư vấn từng em.'),('Tra quy chế đúng kỳ','Xác định khóa, năm học, chương trình và thông báo áp dụng.'),('Tư vấn theo nhóm','Ưu tiên gặp sinh viên có học phần nợ hoặc điểm thấp; thống nhất mục tiêu khả thi.'),('Theo dõi và cập nhật','Ghi nhận tiến độ theo từng đợt đánh giá; không coi gợi ý là quyết định chính thức.')]
    # Attach exact clauses for the topic only. An explicit historical request is handled by the existing reader.
    try:
        # Strip class scope only for a present/unspecified-period policy topic,
        # retaining the cohort check. Do not convert a historical comparison into QD3626.
        source_question=question
        if not re.search(r'\b(?:20\d{2}|so sanh|so voi|quy che cu|truoc day|thay doi)\b',q) and re.search(r'20(?:2[2-6])',str(cohort)):
            for cue,source in [('canh bao','Tiêu chí cảnh báo học vụ UET?'),('hoc vuot','Điều kiện học vượt?'),('24 tin chi','Điều kiện học vượt?'),('tot nghiep','Điều kiện tốt nghiệp?'),('bao luu','Xin bảo lưu kết quả học tập?'),('rut hoc phan','Quy trình rút học phần?')]:
                if cue in q:source_question=source;break
        c=lookup_regulation(root,source_question)
        if c:clauses.append(c)
    except (OSError,ValueError):pass
    if 'hoc bong' in q or 'kkht' in q:lines.append('Học bổng: cần quy định áp dụng đúng kỳ, điểm rèn luyện, kết quả học tập, số tín chỉ và các điều kiện khác; không khẳng định đủ điều kiện hoặc suất học bổng chỉ bằng hồ sơ demo.')
    if 'hoc vuot' in q or '24 tin chi' in q:lines.append('Học vượt: cần kế hoạch học tập chuẩn, giới hạn khối lượng đăng ký và các hạn chế áp dụng. Không xác nhận được phép đăng ký 24 tín chỉ chỉ từ GPA.')
    lines.extend(['','Lộ trình đề xuất (không phải lịch học chính thức):']+[f'{i+1}. {title}: {detail}' for i,(title,detail) in enumerate(steps)])
    if clauses:lines+=['','Căn cứ tham khảo:']+[c['answer'] for c in clauses]
    return {'predicted_answer':'\n'.join(lines),'mode':'chrono_rag','is_advisor_composite':True,'cited_doc_ids':[],'model_name':None,'inference_source':'deterministic_advisor_plan','engine_mode':'ADVISOR_PLAN','advisor_category':category,'advisor_entities':ab.get('entities'),'roadmap':[{'title':a,'detail':b} for a,b in steps],'advisor_sources':[{'source_path':c['path'],'sha256':c['sha256'],'source_url':c['source_url']} for c in clauses], 'latency_ms':(time.monotonic()-start)*1000}
