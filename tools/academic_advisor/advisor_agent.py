"""Product orchestration: scoped, bounded workflows over existing read-only tools.
No unverified model text as policy, no raw excerpts as answers, no personal values
in signed context. Existing research and compatibility paths remain unchanged.
"""
import re
from quality import norm
from quality_routes import response, source_response, pinned, cohort, find_student
from quality_workflows import snapshot
from workflow import screening, scope_error, debt_rows, valid
from intelligence import course_counts
from semantic_product import fee_year, tuition_scopes, source_table

FOREIGN=re.compile(r'\b(?:hutech|ulis|uit|bach khoa|thac si|tien si|5115|3079|thong tu|nghi dinh|tam khoa|lop khac|lop moi|sinh vien khac)\b')
FEES=re.compile(r'\b(?:hoc phi|dinh muc|muc thu|bao nhieu tien|het bao nhieu tien|bao nhieu dong|phai dong|chi phi|du tru|uoc tinh (?:khoan )?tien|tinh (?:khoan )?tien|khoan tien)\b')
RETAKE=re.compile(r'\b(?:hoc lai|hoc cai thien|cai thien diem)\b')
CLASS=re.compile(r'\b(?:ca lop|toan lop|lop hien tai|tinh hinh lop|tinh hinh hoc tap cua lop|lop minh|buoi tu van lop|lop (?:demo )?k\d{2} [a-z0-9]+|buoi sinh hoat (?:voi )?lop|sinh hoat (?:voi )?lop)\b')
SELECT=re.compile(r'\b(?:chon|lay|liet ke|uu tien|top)\s+(\d{1,2}|mot|hai|ba|bon|nam)\s+(?:sinh vien|em|ban)\b')
ACTIONS=re.compile(r'\b(?:nen lam gi|ho tro|tu van|hanh dong|phuong an)\b')
DRAFT=re.compile(r'\b(?:soan|viet|chuan bi|tao)\b.*\b(?:thong bao|thu moi|loi moi)\b')
MINUTES=re.compile(r'\b(\d{1,3}) phut\b')
LOAD=re.compile(r'\b(?:gpa|cpa|diem trung binh)\b')
REGISTER=re.compile(r'\b(?:dang ky|khoi luong|gioi han|han che)\b')

def clarify(text):return response(text,'advisor_clarification')

def ctx(kind,**kw):return {'kind':'advisor_agent','topic':kind,**kw}

def fee(q,n,old,roster,root):
    previous=old.get('topic') in ('fee','fee_pending'); base=old.get('fee',{}) if previous else {}; pending=old.get('topic')=='fee_pending'
    # Only simple fee rate and arithmetic requests, never infer special fees.
    if re.search(r'\b(?:mien|giam|hoc bong|bang kep|nuoc ngoai|quoc tich|ngoai chuong trinh|tieng anh|gia han|han nop|so sanh|du kien|ban dau|truoc dieu chinh|khoan no|toan ky|ca ky|nhieu mon|khong phai|thay vi|khong hoc lai)\b',n):return None
    quantity=re.findall(r'\b(\d{1,2})\s*(?:tin chi|tc)\b',n)
    cost=bool(quantity and re.search(r'\b(?:bao nhieu tien|het bao nhieu|tong tien|chi phi|tinh tien|mat bao nhieu|thanh tien|du tru bao nhieu|can du tru|uoc tinh (?:khoan )?tien|tinh (?:khoan )?tien)\b',n))
    follow_year=previous and bool(re.fullmatch(r'(?:the |vay )?(?:sang|con|doi sang|chuyen sang) nam hoc 20\d{2} 20\d{2}(?: thi sao)?(?: (?:van )?giu nguyen khoa va (?:ctdt|chuong trinh))?',n))
    scope_reply=pending and bool(cohort(n) or fee_year(q) or tuition_scopes(n)) and not re.search(r'\b(?:phan tich|tu van|diem chuan|lich hoc|gpa|cpa|sinh vien khac|hoc bong|quy che)\b',n)
    if not ((FEES.search(n) and RETAKE.search(n)) or (previous and cost) or follow_year or scope_reply):return None
    if FOREIGN.search(n) or re.search(r'\b(?:tt 23|clc|chat luong cao|dmktkt|dinh muc kinh te ky thuat)\b',n):return None
    # No personal lookup is needed for a public rate; no inherited roster IDs.
    if re.search(r'\b\d{8}\b',q):return None
    cy=cohort(n); year=fee_year(q); scopes=tuition_scopes(n)
    explicit_cohorts={1955+int(x) for x in re.findall(r'\bk(6[5-9]|7[0-9])\b',n)}|{int(x) for x in re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?)\s*(20\d{2})\b',n)}
    if len(scopes)>1 or len(explicit_cohorts)>1 or ('nam hoc' in n and re.search(r'\b20\d{2} 20\d{2}\b',n) and year is None):return clarify('Cô xác nhận một khóa và một loại chương trình giúp em.'),{}
    if previous and (cost or follow_year or scope_reply):
        cy=cy or base.get('cohort');year=year or base.get('year');scopes=scopes or ([base['scope']] if base.get('scope') else [])
    if (scope_reply or follow_year) and base.get('quantity') and not quantity:
        quantity=[str(base['quantity'])];cost=True
    if cost and (len(quantity)!=1 or not 1<=int(quantity[0])<=30 or re.search(r'\d[.,]\d+\s*(?:tin chi|tc)',q,re.I)):
        return clarify('Cô cho em số tín chỉ nguyên của học phần cần tính.'),old
    if not (cy and year and scopes):
        missing=[label for ok,label in [(cy,'khóa tuyển sinh'),(year,'năm học'),(scopes,'chương trình đào tạo')] if not ok]
        return clarify('Dạ cô, để tra đúng đơn giá học lại, em cần '+', '.join(missing)+'. Không cần mã sinh viên.'),ctx('fee_pending',fee={'cohort':cy,'year':year,'scope':scopes[0] if len(scopes)==1 else None,'quantity':int(quantity[0]) if cost else None})
    if not (scopes==['standard'] and 2023<=cy<=int(year[:4]) and int(year[:4]) in (2024,2025,2026)):return None
    if re.search(r'\b(?:hoc lan dau|hoc phi lan dau)\b',n) and not RETAKE.search(n):return None
    try:
        from tuition import lookup_tuition
        v=lookup_tuition(root,f'Học phí chương trình chuẩn QH-{cy} năm học {year}')
        r=source_table(root,v)
        if not r:return clarify('Em chưa tìm được dòng học phí đúng khóa, chương trình và năm học.'),{}
        # Extract the verified retake column only; not a guessed number or a model summary.
        rows=[x for x in v['answer'].splitlines() if x.startswith('•') and 'hoc lai' in norm(x) and 'tin chi' in norm(x)]
        m=re.search(r':\s*(\d{1,3}(?:\.\d{3})+) đồng\.?$',rows[0]) if len(rows)==1 else None
        if not m:return clarify('Em chưa xác định được đơn giá học lại từ dòng nguồn.'),{}
        rate=int(m[1].replace('.','')); fmt=lambda x:f'{x:,}'.replace(',','.')
        lead=f'Dạ cô, năm học {year}, sinh viên khóa QH-{cy} thuộc CTĐT chuẩn có định mức học lại **{fmt(rate)} đồng/tín chỉ**.'
        if cost:
            if len(quantity)!=1 or not 1<=int(quantity[0])<=30 or re.search(r'\d[.,]\d+\s*(?:tin chi|tc)',q,re.I):return clarify('Cô cho em số tín chỉ nguyên của học phần cần tính.'),old
            k=int(quantity[0]);lead=f'Dạ cô, với định mức {fmt(rate)} đồng/tín chỉ của CTĐT chuẩn QH-{cy}, năm học {year}:\n\n{k} × {fmt(rate)} = **{fmt(k*rate)} đồng**.'
        r['answer']=lead+'\n\nĐây là định mức học phần, chưa tính khoản nợ, đối trừ hoặc khoản thu khác nếu có.'
        r['metadata']['workflow_tools']=['policy_reference']+(['fee_calculator'] if cost else [])
        return r,ctx('fee',fee={'cohort':cy,'year':year,'scope':'standard','quantity':int(quantity[0]) if cost else None})
    except (OSError,ValueError,KeyError,TypeError):return clarify('Em chưa xác minh được bảng học phí đúng phạm vi. Không nên dùng mức của khóa hoặc năm khác thay thế.'),{}

def load(q,n,old,root):
    prev=old.get('topic')=='load'
    if not ((LOAD.search(n) and REGISTER.search(n)) or (prev and LOAD.search(n))):return None
    if re.search(r'\b(?:hai ctdt|hai chuong trinh|chuong trinh thu hai|nganh thu hai|hoc cung luc|hoc dong thoi|gpa chung cac hoc phan)\b',n):return None
    if any(x!='3626' for x in re.findall(r'\b(?:qd|quyet dinh)\s*(\d{3,6})\b',n)):return None
    if FOREIGN.search(n) or re.search(r'\b(?:danh sach|ca lop|toan lop|hoc phi|hoc bong|ha hang|so sanh quy che|ky phu|ky he|hoc he|\d{8})\b',n):return None
    if re.search(r'\b(?:tai chuan|khoi luong trung binh|toi da bao nhieu)\b',n) and re.search(r'\b\d+\s*tin chi\b',n):return None # existing exact calculator
    cy=cohort(n,old.get('cohort') if prev else None)
    if cy is not None and not 2022<=cy<=2025:return clarify('Cần xác minh quy chế đúng khóa; em không áp dụng mặc định QĐ 3626 cho khóa này.'),{}
    if re.search(r'\b(?:nam hoc|quy che) (?:2020|2021|2026|202[7-9])\b',n):return None
    c=pinned(root,'Giới hạn tín chỉ đăng ký học kỳ chính?')
    if not c or not all(x in norm(c['answer']) for x in ('duoi 2 00','khong qua 18 tin chi','3 2 khoi luong trung binh')):return clarify('Em chưa xác minh được điều khoản về giới hạn đăng ký học. Cần đối chiếu quy chế đúng khóa.'),{}
    # Only an explicitly semester-labelled GPA can trigger the cap. CPA never substitutes.
    g=None
    # Accent-normalized, punctuation-preserving match for numeric GPA.
    import unicodedata
    a=''.join(x for x in unicodedata.normalize('NFKD',q.lower().replace('đ','d')) if not unicodedata.combining(x))
    m=re.search(r'\b(?:gpa|diem trung binh)\s*(?:hoc )?ky(?:\s+(?:truoc|gan nhat|nay))?\s*(?:chi|la|bang)?\s*([0-4](?:[.,]\d{1,2})?)\b',a)
    if m:g=float(m[1].replace(',','.'))
    if g is not None and not 0<=g<=4:g=None
    text='Dạ cô, theo Điều 21 và 23 QĐ 3626, nếu GPA học kỳ trước dưới 2,00 và sinh viên chưa thuộc diện buộc thôi học, khối lượng đăng ký học kỳ chính không quá **18 tín chỉ**. Còn phải đối chiếu giới hạn 1,5 lần tải chuẩn bình quân và các học phần được loại trừ.'
    if g is not None and g<2:text=f'Dạ cô, GPA học kỳ trước {g:g} thấp hơn 2,00. Nếu sinh viên chưa thuộc diện buộc thôi học và quy chế này áp dụng, trần đăng ký học kỳ chính là **18 tín chỉ**, đồng thời không vượt giới hạn theo tải chuẩn.'
    elif g is not None:text=f'Dạ cô, GPA học kỳ trước {g:g} không thấp hơn 2,00, nên riêng điều kiện giới hạn 18 tín chỉ này không phát sinh. Vẫn phải kiểm tra tải chuẩn và các điều kiện khác.'
    if 'cpa' in n or 'tich luy' in n:text+=' CPA tích lũy và GPA học kỳ là hai chỉ số khác nhau; CPA trên 2 không tự loại bỏ giới hạn dựa trên GPA học kỳ.'
    text+='\n\nĐây là giới hạn quy chế có điều kiện, không phải mức nên đăng ký. Cần xác nhận khóa, kỳ và tình trạng học vụ trước khi áp dụng.'
    return source_response(text,'load',c),ctx('load',cohort=cy)

def class_flow(q,n,old,roster,explicit,classified,root):
    prior=old.get('topic')=='class'; select=SELECT.search(n); mins=MINUTES.search(n)
    analyze=bool(CLASS.search(n) and re.search(r'\b(?:phan tich|uu tien|quan tam|sang loc|tu van|ke hoach)\b',n))
    individual=bool(prior and ACTIONS.search(n) and re.search(r'\b(?:tung sinh vien|tung em|tung ban|nhom do|cac ban do)\b',n))
    agenda=bool(mins and (CLASS.search(n) or prior and old.get('minutes') and re.search(r'\b(?:con|giam|rut|doi|thoi gian|bo bot)\b',n)))
    if not (analyze or select and prior or individual or agenda):return None
    if re.search(r'\b(?:diem chuan|tuyen sinh|hoc phi|hoc bong|quy che|nghi hoc|chuyen nganh|tot nghiep)\b',n):return None
    if DRAFT.search(n) and not agenda:return None
    if explicit or classified or re.search(r'\b\d{8}\b',q):return None
    if FOREIGN.search(n) or scope_error(n,roster) or not roster.get('students'):return clarify('Cô xác nhận đúng lớp và hồ sơ đang mở trước khi em phân tích.'),{}
    if re.search(r'\b(?:cong khai danh sach|dang danh sach|gui danh sach|cong khai diem|cong khai mssv)\b',n) or (not agenda and re.search(r'\b(?:cong khai|nhom lop|chia se|dang len|gui cho ca lop)\b',n)):return clarify('Em có thể lập danh sách nội bộ cho cô, nhưng không đưa thông tin cá nhân lên thông báo chung.'),{}
    if prior and old.get('scope')!=snapshot(roster) and not analyze:return clarify('Hồ sơ lớp đã thay đổi; cô yêu cầu phân tích lại để em không dùng kết quả cũ.'),{}
    groups,dup=screening(roster['students']); tools=['scope_check','screening']; count=old.get('count') if prior else None
    if select:
        raw=select[1];count=int(raw) if raw.isdigit() else {'mot':1,'hai':2,'ba':3,'bon':4,'nam':5}[raw]
        if not 1<=count<=10:return clarify('Cô chọn từ 1 đến 10 hồ sơ để ưu tiên trao đổi riêng.'),old
    state=ctx('class',scope=snapshot(roster),count=count)
    lead=f'Dạ cô, em đã rà {sum(map(len,groups.values()))} hồ sơ: **{len(groups[1])} cần ưu tiên gặp riêng**, {len(groups[2])} cần trao đổi thêm, {len(groups[3])} thiếu dữ liệu, {len(groups[4])} chưa thấy tín hiệu theo tiêu chí sàng lọc.'
    if dup:lead+=f' Có {dup} bản ghi trùng hoặc thiếu mã được loại khỏi thống kê.'
    revision=bool(agenda and prior and old.get('minutes') and not analyze and not DRAFT.search(n))
    lines=[] if revision else ([f'Dạ cô, em chọn {min(count or len(groups[1]),len(groups[1])+len(groups[2]))} hồ sơ theo thứ tự ưu tiên đã nêu.'] if prior and (select or individual) and not analyze else [lead]); candidates=groups[1]+groups[2]
    if analyze or (agenda and not revision):
        counts=course_counts(roster['students']);tools.append('class_course_statistics')
        if counts:
            top=[v for v in counts if v[1]==counts[0][1]][:5]
            lines.append('**Học phần cần rà thêm:** '+', '.join(f'{c} ({f}/{t} hồ sơ có điểm chưa thấy lần đạt)' for c,f,t,_ in top)+'. Nên trao đổi với giảng viên bộ môn để xác minh khó khăn, không suy ra nguyên nhân chỉ từ điểm.')
    chosen=candidates[:count] if count else groups[1]
    if agenda:
        total=int(mins[1]);
        if not 10<=total<=180:return clarify('Cô cho em thời lượng từ 10 đến 180 phút để chia chương trình buổi tư vấn.'),old
        # One workflow: screening -> priorities -> time allocation -> public draft.
        state.update(minutes=total);tools+=['action_strategy','agenda_planning']; a=total//6;b=total//3;c=total//3;d=total-a-b-c
        lines+=['\n**Chương trình tư vấn chung**',f'1. {a} phút — Tổng kết tình hình học tập ở mức tổng hợp, không nêu cá nhân.',f'2. {b} phút — Hướng dẫn rà học phần nợ và xác minh các môn cần học lại.',f'3. {c} phút — Hướng dẫn lập kế hoạch đăng ký phù hợp tải học, tiên quyết và lịch mở lớp.',f'4. {d} phút — Giải đáp, thống nhất việc tiếp theo và kênh trao đổi riêng.', 'Không công khai danh sách nhóm ưu tiên; hẹn gặp riêng sau buổi chung. Đây là sàng lọc hỗ trợ sơ bộ, không phải cảnh báo học vụ chính thức.']
        if re.search(r'\b(?:theo doi|sau buoi|danh gia lai)\b',n):lines.append('Sau buổi chung, thống nhất với từng em cần hỗ trợ một mục tiêu nhỏ và mốc kiểm tra lại trong tuần tới; ghi nhận đã liên hệ, việc còn vướng và bước hỗ trợ tiếp theo qua kênh riêng.')
        if prior and old.get('minutes') and total<old['minutes']:lines.append('Với thời lượng rút ngắn, em ưu tiên rà môn nợ và kế hoạch đăng ký; chuyển phần trao đổi cá nhân sang buổi riêng.')
        if prior and old.get('draft'):state['draft']=True
        if DRAFT.search(n) or (prior and old.get('draft') and not revision):
            state['draft']=True;tools.append('communication_draft');lines+=['\n**Thông báo mời tham gia (bản nháp)**','Các em thân mến, cô dự kiến tổ chức một buổi trao đổi về kết quả học tập, rà soát học phần còn nợ và kế hoạch đăng ký học. Các em hãy kiểm tra hồ sơ của mình và chuẩn bị câu hỏi trước buổi gặp. Nếu có khó khăn cá nhân, các em có thể trao đổi riêng với cô. Thời gian và địa điểm sẽ được thông báo sau.']
    else:
        state['ranked_list']=True
        lines+=['\n**Ưu tiên trao đổi riêng**']
        if individual:
            from course_planning import load_candidate,candidate_label,candidate_source
            table,_=load_candidate(root,roster)
        else:table=None
        for sid,name,flags,missing in chosen:
            lines.append(f'- **{sid}** — '+('; '.join(flags) if flags else 'cần rà dữ liệu')+'.')
            if individual:
                st=find_student(roster,sid);rows,amb,unknown=debt_rows(st,roster.get('courses') or []) if st else ([],[],[])
                if rows:lines.append('  Đối chiếu các môn chưa thấy lần đạt: '+', '.join(x[0] for x in rows[:5])+('.' if len(rows)<=5 else ' và các môn còn lại.'))
                pending={x[0] for x in rows if table and x[0] in table and table[x[0]][0]==x[2]}
                blockers=sorted(((c,sum(c in table[x][1] for x in pending)) for c in pending),key=lambda x:(-x[1],x[0]))
                if blockers and blockers[0][1]:
                    lines.append(f'  Rà trước {blockers[0][0]} vì có thể mở đường cho {blockers[0][1]} môn nợ theo bảng {candidate_label(table)}; xác minh trước khi đăng ký.')
                    if 'prerequisite_planning' not in tools:tools.append('prerequisite_planning')
                debt=valid(st.get('owed_credits'),0,1000) if st else None
                if debt is not None and debt>=30:lines.append('  Nên chia xử lý nợ thành nhiều đợt và rà thời gian đào tạo còn lại; không khuyến nghị học dồn chỉ để trả nợ nhanh.')
                conduct=valid(st.get('drl'),0,100) if st else None
                if conduct is not None and conduct<70:lines.append('  Rà điểm rèn luyện và hỏi em có cần hỗ trợ tham gia hoạt động phù hợp không; chưa coi đây là kết luận học vụ.')
                if amb or unknown:lines.append('  Rà mã hoặc kết quả học phần chưa khớp trước khi lập lộ trình.')
                lines.append('  Hỏi về khó khăn thực tế, thống nhất một mục tiêu vừa sức và mốc kiểm tra lại; chưa suy ra nguyên nhân từ điểm.')
        if individual:tools+=['student_signals','course_history','action_strategy']
        if count and len(chosen)<count:lines.append('Chỉ có '+str(len(chosen))+' hồ sơ có tín hiệu hỗ trợ; em không thêm người chưa có căn cứ chỉ để đủ số lượng.')
        if not chosen:lines.append('Chưa thấy hồ sơ thuộc nhóm ưu tiên theo dữ liệu hiện có.')
        lines.append('Thứ tự theo tín chỉ nợ giảm dần, GPA học kỳ thấp hơn, rồi điểm rèn luyện; không phải xếp hạng học vụ.')
    if not revision:lines.append('\nHồ sơ đang mở: '+str(roster.get('class_short',''))+', '+str(roster.get('semester','kỳ chưa rõ'))+'. Đây là đề xuất hỗ trợ, cần đối chiếu dữ liệu kỳ hiện tại.')
    return response('\n'.join(lines),'class_advisor_workflow',tools,[candidate_source(table)] if 'prerequisite_planning' in tools else [],category='CLASS_STATS'),state

def route(question,prior,explicit,classified,roster,root):
    n=norm(question);old=prior if prior.get('kind')=='advisor_agent' else {}
    # Public rate / regulation queries must not be routed as individual coursework.
    if not explicit:
        if old.get('topic') in ('fee','load') and re.fullmatch(r'(?:can cu|nguon|dieu khoan)(?: vao)?(?: dieu khoan| van ban| dieu| nguon)? (?:nao|dau)(?: vay| a)?',n):
            if old['topic']=='load':
                return load('Giới hạn đăng ký học khi GPA thấp?', 'gioi han dang ky hoc khi gpa thap',old,root)
            f=old.get('fee',{});cy=f.get('cohort');year=f.get('year')
            if cy and year:return fee(f'Học phí học lại CTĐT chuẩn QH-{cy} năm học {year}',f'hoc phi hoc lai ctdt chuan qh {cy} nam hoc {year.replace(chr(45),chr(32))}',old,roster,root)
        r=fee(question,n,old,roster,root)
        if r is not None:return r
        r=load(question,n,old,root)
        if r is not None:return r
    from advisor_draft import route as draft_route
    r=draft_route(question,n,prior,explicit,classified,roster)
    if r is not None:return r
    from advisor_compare import route as compare_route
    r=compare_route(question,prior,explicit,classified,roster,root)
    if r is not None:return r
    from advisor_tasks import route as task_route
    r=task_route(question,n,prior,explicit,classified,roster,root)
    if r is not None:return r
    return class_flow(question,n,old,roster,explicit,classified,root)

def product_result(r):
    """Reject unsafe legacy fallback in advisor mode only; retain research endpoint."""
    m=r.get('metadata') or {};routing=r.get('routing') or {}
    if routing.get('risk_tier')=='RED':return r,True
    if m.get('engine_mode') in ('KNOWLEDGE_EXCERPTS','LORA_KNOWLEDGE_ACCESS','SLM_KNOWLEDGE_ACCESS','GEMINI_KNOWLEDGE_ACCESS') or m.get('inference_source') in ('knowledge_excerpts','local_slm_knowledge','gemini_public_knowledge'):
        clean=clarify('Dạ cô, em chưa tìm được bằng chứng đủ liên quan và đúng phạm vi để trả lời chắc chắn. Em không muốn đưa cô một đoạn tài liệu không đúng yêu cầu. Cô có thể cho em thêm tên quy định, khóa hoặc năm học nếu có.')
        clean['question']=r.get('question','');clean['routing']['risk_tier']=routing.get('risk_tier','GREEN');clean['metadata']['product_fallback_blocked']=True
        return clean,False
    return r,True
