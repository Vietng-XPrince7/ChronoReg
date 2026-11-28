"""Product conversation repair: typed, bounded context and read-only tools.
No answer-bank lookup; only route explicit tasks to existing source/data tools.
"""
import re,hashlib,json,unicodedata
from quality import norm
from workflow import scope_error, debt_rows, valid
from regulation import lookup_regulation
from presentation import graduation_summary
from course_planning import load_candidate, make_plan, REL, SHA,candidate_source,candidate_label
from intelligence import course_counts

RANK=re.compile(r'\b(?:ha (?:hang|bang|loai)|bang (?:se )?(?:bi )?ha|giam (?:hang|loai|bac)|xep loai tot nghiep)\b')
LOAD=re.compile(r'\b(?:dang ky|gioi han|khoi luong)\b')
RETAKE=re.compile(r'\b(?:hoc lai|mon no|tin chi no)\b')
CAP=re.compile(r'\b(\d{1,2}) tin chi\b')
REF=re.compile(r'\b(?:ban ay|ban do|ban nay|em ay|em do|em nay|sinh vien nay|sinh vien do|sinh vien ay)\b')
FOLLOW=re.compile(r'^(?:neu|con|vay|the|a|doi|giu|chi|bay gio|gio|tuong tu|sua|thay|rut gon|tiep tuc)\b')
OTHER=re.compile(r'\b(?:hutech|uit|ulis|bach khoa|thac si|tien si|so sanh|quy che cu|thong tu|nghi dinh|5115|3079)\b')
HOLD=re.compile(r'\b(?:tam khoa|publication hold|chua duyet|chua phe duyet)\b')

def response(text,goal,tools=(),sources=(),category='REGULATION',sid=None):
    return {'answer':text,'routing':{'selected_engine':'chrono_rag','actual_engine_used':'chrono_rag','risk_tier':'GREEN','detected_signals':[],'routing_reason':'Định tuyến theo nhiệm vụ cố vấn'},'metadata':{'engine_mode':'ADVISOR_WORKFLOW' if tools else 'CONTEXT_CLARIFICATION','advisor_intent':goal,'advisor_category':category,'advisor_entities':{'mssv':sid} if sid else {},'workflow_tools':list(tools),'advisor_sources':list(sources),'source_label':'Công cụ cố vấn cục bộ' if tools else 'Làm rõ yêu cầu','inference_source':'deterministic_workflow_tools' if tools else 'deterministic_router','model_name':None,'latency_ms':0}}

def task(topic,**kw):return {'kind':'advisor_task','topic':topic,**kw}

def source_response(text,topic,c):
    r=response(text,'policy_question',['policy_reference'],[{'source_path':c['path'],'sha256':c['sha256'],'source_url':c['source_url']}]);r['metadata'].update(engine_mode='SOURCE_CLAUSE',inference_source='deterministic_source_clause',source_label='Điều khoản đối chiếu QĐ 3626',source_clause=c,advisor_evidence=c['answer'],source_type='source_clause',doc_title='Quyết định 3626/QĐ-ĐHQGHN',effective_year=2022,sha256_short=c['sha256'][:8],sha256=c['sha256'],pdf_sha256=c.get('pdf_sha256'),source_path=c['path'],source_url=c['source_url'],scope_url=c.get('scope_url'),notice_url=c.get('notice_url'),articles=c.get('articles',[]),quality_qualified=False)
    return r

def pinned(root,q):
    try:return lookup_regulation(root,q)
    except (OSError,ValueError,KeyError):return None

def cohort(n,old=None):
    m=re.search(r'\b(?:khoa(?: tuyen sinh)?|qh)\s*(20\d{2})\b',n)
    if m:return int(m[1])
    m=re.search(r'\bk(6[5-9]|7[0-9])\b',n)
    if m:return 1955+int(m[1])
    return old

def find_student(roster,sid):
    found=[s for s in roster.get('students',[]) if str(s.get('student_id') or s.get('mssv'))==str(sid)] if sid else []
    return found[0] if len(found)==1 else None

def route(question,prior,explicit,classified,roster,root):
    """Return (response, typed context) or None. Only AUTO and non-RED caller."""
    n=norm(question); old=prior if prior.get('kind')=='advisor_task' else {}; topic=old.get('topic'); follow=bool(FOLLOW.search(n)); sid=explicit or classified
    if HOLD.search(n) and re.search(r'\b(?:trich|ap dung|tu van|dung|cong bo)\b',n):
        return response('Dạ cô, em không dùng văn bản đang tạm khóa hoặc chưa được duyệt làm căn cứ tư vấn chính thức. Cô cho em số hiệu văn bản để tìm nguồn đã được phép sử dụng, hoặc xác nhận với đơn vị ban hành.','publication_hold',['scope_check']),{}
    if OTHER.search(n):return None
    # An explicit unknown institution or comparison is left to the existing scoped router.
    # Explicit or contextual regulatory question, never attach personal data.
    rank=bool(RANK.search(n) and re.search(r'\b(?:thi lai|hoc lai|truot|rot|diem f|ky luat|co bi|co phai|phan tram)\b',n))
    rank_follow=topic=='rank' and follow and bool(re.search(r'\b(?:phan tram|5|khoa|qh|k7[0-9]|k6[5-9]|nguong|bang|vuot)\b',n))
    load=bool(LOAD.search(n) and 'tin chi' in n and re.search(r'\b(?:gpa|diem trung binh)\b',n) and not RETAKE.search(n))
    load_follow=topic=='load' and follow and bool(re.search(r'\b(?:gpa|tich luy|ky phu|ky he|hoc he|ky chinh|nguong|tin chi)\b',n))
    if not sid and not re.search(r'\b(?:sinh vien nao|em nao|nhung ai|danh sach|thong ke|toan lop|ca lop)\b',n) and (rank or rank_follow or load or load_follow):
        isrank=rank or rank_follow; name='rank' if isrank else 'load'; carry=old if topic==name else {}
        cy=cohort(n,carry.get('cohort')); new=task(name,cohort=cy)
        # No extrapolation to a different cohort or institution.
        if cy is None and re.search(r'\b(?:lop minh|lop co|lop toi)\b',n):
            cy=cohort(norm(str(roster.get('cohort',''))));new['cohort']=cy
        if re.search(r'\b(?:nam(?: hoc)?|quy che(?: nam)?) (?:20[01]\d|2020|2021|2026|202[7-9]|20[3-9]\d)\b',n) and not re.search(r'\b(?:khoa(?: tuyen sinh)?|qh)\s*20\d{2}\b',n):
            return response('Dạ cô, em chưa xác minh được hiệu lực của điều khoản ở thời điểm được hỏi. Cô cần đối chiếu văn bản đúng năm và khóa; em không suy diễn từ bản cũ.','policy_scope'),new
        if cy is not None and not 2022<=cy<=2025:
            return response(f'Dạ cô, em chưa có điều khoản đã xác minh cho khóa tuyển sinh {cy} về nội dung này. Không thể tự áp dụng quy định của khóa trước; cần đối chiếu quy chế đúng khóa.','policy_scope'),new
        if isrank:
            c=pinned(root,'Hạ hạng tốt nghiệp do học lại?')
            a=graduation_summary('Trượt môn có bị hạ bằng?',c['answer']) if c else None
            if not a:return response('Dạ cô, em chưa có điều khoản đủ căn cứ để kết luận về hạ hạng tốt nghiệp. Cần đối chiếu đúng khóa và văn bản được phép sử dụng.','policy_unavailable'),new
            if re.search(r'\bbang (?:dung )?5\b|\bdung bang 5\b',n):
                a='Dạ cô, đúng bằng 5% không thỏa điều kiện vượt quá 5% tại khoản 7 Điều 47. Vẫn phải xem hạng tốt nghiệp dự kiến và tình trạng kỷ luật; chỉ áp dụng nếu Quyết định 3626/QĐ-ĐHQGHN đúng với khóa đang xét.'
            elif 'thi lai' in n:a='Dạ cô, không phải cứ thi lại là hạ hạng. Cần phân biệt thi lại với học phần phải học lại; điều khoản tính tổng tín chỉ phải học lại, không chỉ số môn thi lại.\n\n'+a
            if not a.startswith('Dạ cô'):a='Dạ cô, '+a[0].lower()+a[1:]
            return source_response(a,'rank',c),new
        c=pinned(root,'Giới hạn tín chỉ đăng ký học kỳ chính?')
        if not c or not all(x in norm(c['answer']) for x in ('duoi 2 00','khong qua 18 tin chi','3 2 khoi luong trung binh')):
            return response('Dạ cô, em chưa có điều khoản đã xác minh để xác định tải đăng ký. Cần kiểm tra quy chế đúng khóa, học kỳ và tình trạng học vụ.','policy_unavailable'),new
        cumulative=bool(re.search(r'\b(?:gpa|cpa|diem trung binh)(?: do| nay)? (?:la )?tich luy\b',n))
        summer=bool(re.search(r'\b(?:ky phu|ky he|hoc he)\b',n)); new['gpa_kind']='cumulative' if cumulative else carry.get('gpa_kind','semester')
        from intelligence import explicit_gpa
        g=explicit_gpa(question)
        if g is not None and not cumulative:new.update(gpa_kind='semester',gpa=g)
        elif not cumulative and new['gpa_kind']=='semester' and 'gpa' in carry:new['gpa']=carry['gpa']
        if summer:a='Dạ cô, không thể tự áp dụng cho kỳ phụ ngưỡng 18 tín chỉ của học kỳ chính. Điều 21 giao đơn vị đào tạo quy định khối lượng kỳ phụ; cần tra thông báo đúng kỳ và khóa.'
        elif new['gpa_kind']=='cumulative':a='Dạ cô, GPA tích lũy không thay cho GPA học kỳ. Em rút lại việc dùng ngưỡng dựa trên GPA học kỳ; cô cho em GPA học kỳ gần nhất và tình trạng học vụ trước khi xét giới hạn.'
        elif new.get('gpa',4)<2:a='Dạ cô, chưa nên khuyên đăng ký đủ 18 tín chỉ chỉ dựa vào GPA. Nếu GPA học kỳ dưới 2,00 và chưa thuộc diện bị buộc thôi học, 18 tín chỉ là trần học kỳ chính, không phải mức nên đăng ký. Cần kiểm tra thêm kế hoạch chuẩn, học phần loại trừ và khả năng học.'
        elif 'gpa' in new:a='Dạ cô, GPA học kỳ này không thuộc điều kiện dưới 2,00; chưa thể xác định tải tối đa chỉ từ GPA. Cần kiểm tra kế hoạch chuẩn và tình trạng học vụ.'
        else:a='Dạ cô, chưa thể xác định tải tối đa chỉ từ GPA. Cần kiểm tra GPA học kỳ, tình trạng học vụ, giới hạn theo kế hoạch chuẩn và các học phần loại trừ.'
        return source_response(a+' Căn cứ đối chiếu: Điều 21, 23 Quyết định 3626/QĐ-ĐHQGHN, cần đúng khóa và kỳ.',name,c),new
    # Explicit retake planning; inherited identity only on narrow plan followups.
    ascii_q=''.join(c for c in unicodedata.normalize('NFKD',question.lower().replace('đ','d')) if not unicodedata.combining(c))
    budgets=re.findall(r'(?<![\d.,])([0-9]+(?:[.,][0-9]+)?)\s+tin chi\b',ascii_q)
    plan_request=bool(budgets and (RETAKE.search(n) or topic=='retake' and follow and re.search(r'\b(?:dot|ky|doi|giu)\b',n)))
    if plan_request:
        if not sid and not scope_error(n,roster):
            from quality_workflows import snapshot
            sid=old.get('mssv') if topic=='retake' or (topic=='student_priority' and old.get('scope')==snapshot(roster)) else prior.get('mssv') if prior.get('kind')=='student' else None
        if not sid or scope_error(n,roster) or not find_student(roster,sid):return response('Dạ cô, cô chọn đúng sinh viên hoặc nhập MSSV để em tính lộ trình học lại.','scope_clarification'),{}
        st=find_student(roster,sid)
        if len(set(budgets))!=1 or not budgets[0].isdigit():return response('Dạ cô, cô chọn một mức tín chỉ nguyên cho mỗi đợt để em mô phỏng.','invalid_budget'),task('retake',mssv=str(sid))
        cap=int(budgets[0]);scope=hashlib.sha256(json.dumps({'class':roster.get('class_short'),'semester':roster.get('semester'),'student':st,'courses':roster.get('courses')},sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        if topic=='retake' and not (explicit or classified) and old.get('scope') and old['scope']!=scope:return response('Dạ cô, hồ sơ đã thay đổi từ lần mô phỏng trước. Cô xác nhận lại sinh viên và mức tín chỉ trước khi so sánh.','scope_clarification'),{}
        new=task('retake',mssv=str(sid),budget=cap,scope=scope)
        if not 1<=cap<=30:return response('Dạ cô, mức mô phỏng cần là số tín chỉ nguyên từ 1 đến 30.','invalid_budget'),new
        rows,amb,unknown=debt_rows(st,roster.get('courses') or []);table,why=load_candidate(root,roster)
        if not table:return response('Dạ cô, em chưa thể xếp lịch có tiên quyết vì '+str(why)+'. Em không giả định các môn có thể học cùng lúc.','retake_plan',['scope_check','course_history'],category='STUDENT_STATUS',sid=sid),new
        stages,excluded=make_plan(rows,table,st.get('bang_diem') or [],cap);k=sum(map(len,stages));total=sum(row[2] for batch in stages for row in batch)
        lead=f'Dạ cô, mức {cap} tín chỉ mỗi đợt: {len(stages)} đợt cho {k} học phần ({total} tín chỉ) xếp được.' if stages else 'Dạ cô, chưa xếp được học phần nào theo các điều kiện đã xác minh.'
        if topic=='retake' and old.get('mssv')==str(sid) and old.get('scope')==scope and old.get('budget')!=cap and type(old.get('rounds')) is int:lead+=f" So với mức {old['budget']} tín chỉ: {old['rounds']} → {len(stages)} đợt (trên tập môn xếp được; cần đối chiếu môn bị loại)."
        lines=[lead]+[f'Đợt {i}: '+', '.join(r[0] for r in batch)+f' ({sum(r[2] for r in batch)} TC).' for i,batch in enumerate(stages,1)]
        if k and k<=12:lines.append('Tối thiểu trên tập môn xếp được: thuật toán tìm kiếm theo số đợt, duyệt mọi tổ hợp đủ tiên quyết và không vượt tải, nên không có lịch ít đợt hơn trong mô hình này.')
        elif k:lines.append('Phương án khả thi theo mô hình; chưa chứng minh tối ưu.')
        if excluded or amb or unknown:lines.append('Chưa xếp/đối chiếu: '+'; '.join([f'{c}: {v}' for c,v in sorted(excluded.items())]+amb+unknown)+'.')
        lines.append(f'Bảng {candidate_label(table)}. Đợt là giả định, không phải học kỳ; chưa xét lịch mở lớp, môn mới hay giới hạn đăng ký chính thức.')
        new['rounds']=len(stages)
        return response('\n'.join(lines),'retake_plan',['scope_check','course_history','prerequisite_planning','credit_scenarios'],[candidate_source(table)],'STUDENT_STATUS',sid),new
    # Course statistics and all tied leaders, computed not generated.
    metric=bool(re.search(r'\b(?:mon nao|hoc phan nao)\b',n) and re.search(r'\b(?:chua thay lan dat|chua dat|khong dat|truot|rot)\b',n) and re.search(r'\b(?:nhieu|dong hang)\b',n))
    if metric and not sid:
        if scope_error(n,roster):return response('Dạ cô, cần chọn đúng hồ sơ lớp trước khi thống kê.','scope_clarification'),{}
        counts=course_counts(roster.get('students') or []);top=[x for x in counts if x[1]==counts[0][1]] if counts else []
        a='Dạ cô, nhóm học phần có nhiều sinh viên từng không đạt và chưa thấy lần đạt nhất:\n'+'\n'.join(f'• {c}: {f}/{t} sinh viên có bản ghi điểm; {m} trường hợp có cả lần đạt và không đạt cần đối chiếu.' for c,f,t,m in top) if top else 'Dạ cô, chưa thấy học phần có tín hiệu này trong hồ sơ hợp lệ.'
        a+='\nĐây là số sinh viên chưa thấy lần đạt, không phải tỷ lệ trượt của cả trường. Hồ sơ '+str(roster.get('class_short',''))+', '+str(roster.get('semester','kỳ chưa rõ'))+'.'
        return response(a,'course_failure',['scope_check','course_history','class_course_statistics'],category='CLASS_STATS'),task('course_stats')
    if topic=='course_stats' and not sid and not scope_error(n,roster) and re.search(r'\b(?:giang vien|day kem|nguyen nhan)\b',n):
        return response('Dạ cô, không thể suy ra chất lượng giảng dạy chỉ từ số sinh viên chưa thấy lần đạt. Em đề xuất đối chiếu số lượt học, đề kiểm tra, kiến thức nền, mức tham gia học và phản hồi sinh viên; trao đổi với giảng viên bộ môn trước khi kết luận.','course_causality',['class_course_statistics'],category='CLASS_STATS'),old
    from quality_workflows import route_workflow
    repaired=route_workflow(question,prior,explicit,classified,roster,root)
    if repaired is not None:return repaired
    if not sid and REF.search(n) and not (prior.get('kind')=='student' or old.get('mssv')) and re.search(r'\b(?:tin chi|gpa|diem|no|ho so|tu van)\b',n):
        return response('Dạ cô, cô đang nhắc đến sinh viên nào? Cô chọn hồ sơ hoặc nhập MSSV giúp em.','scope_clarification'),{}
    if not sid and follow and re.search(r'\b(?:nguong do|muc do|phan thay doi|dung bang \d+|nhung viec con lai)\b',n):
        return response('Dạ cô, em chưa xác định được nội dung cô đang nhắc tới trong ngữ cảnh hiện có. Cô nêu lại chủ đề hoặc phương án cần đối chiếu giúp em.','context_clarification'),{}
    return None
