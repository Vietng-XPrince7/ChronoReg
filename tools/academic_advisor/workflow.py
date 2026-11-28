"""Scoped, product-only advisor workflows. Local read-only tools; no official decisions.
All numeric results and drafts are computed/rendered, not generated facts.
"""
from collections import defaultdict, Counter
import re,time
from quality import norm
from advisor import number
from course_planning import load_candidate,dependency_lines,REL,SHA
from advisor_report import build_report

CLASS_TASK = re.compile(r'\b(?:gap rieng|uu tien ho tro|phan nhom|sang loc|ke hoach tu van|can quan tam|can ho tro|can thiep|bao cao tu van)\b')
STUDENT_TASK = re.compile(r'\b(?:tien quyet|phuong an|kich ban|phan bo|ke hoach hoc lai|lo trinh.*(?:tung ky|qua cac ky|theo ky|hoc ky)|mon no.*(?:xu ly|uu tien)|so sanh.*(?:hoc lai|giam tai))\b')
REPORT_TASK = re.compile(r'\b(?:bao cao tu van|bien ban tu van|phieu tu van|ke hoach hanh dong|danh sach viec can lam|bao cao ho tro hoc tap)\b')
DRAFT_TASK = re.compile(r'\b(?:soan|viet|tao|chuan bi)\b.{0,60}\b(?:tin nhan|email|thu moi|thong bao|bien ban|noi dung trao doi)\b')

def scope_error(q,roster):
    requested=set(re.findall(r'\bk(?:6[5-9]|7[01])\b',q))
    actual=set(re.findall(r'\bk(?:6[5-9]|7[01])\b',norm(str(roster.get('class_short',''))+' '+str(roster.get('cohort','')))))
    if requested and (not actual or not requested.issubset(actual)):return 'lớp/khóa được hỏi không khớp hồ sơ đang mở'
    named=re.findall(r'\bk(?:6[5-9]|7[01])\s+[a-z]{2,6}\s*\d{1,2}\b',q)
    actual_named=norm(str(roster.get('class_short',''))).replace(' ','')
    if named and any(x.replace(' ','')!=actual_named for x in named):return 'lớp được hỏi không khớp hồ sơ đang mở'
    rq=set(re.findall(r'\bqh (20\d{2})\b',q)); ac=set(re.findall(r'20\d{2}',str(roster.get('cohort',''))))
    if rq and not rq.issubset(ac):return 'khóa tuyển sinh được hỏi không khớp hồ sơ đang mở'
    # No time travel from a single demo snapshot.
    yrs=re.findall(r'\bnam hoc (20\d{2})\s+(20\d{2})\b',q)
    if yrs and any(not all(y in str(roster.get('semester','')) for y in pair) for pair in yrs):return 'không có hồ sơ lịch sử đúng năm học được hỏi'
    return None

def valid(v,lo,hi):
    n=number(v);return n if n is not None and lo<=n<=hi else None

def signals(st):
    g=valid(st.get('gpa_semester'),0,4); d=valid(st.get('drl'),0,100); o=valid(st.get('owed_credits'),0,1000)
    flags=[];missing=[]
    for value,label in [(g,'GPA học kỳ'),(d,'điểm rèn luyện'),(o,'tín chỉ nợ')]:
        if value is None:missing.append(label)
    if g is not None and g<2:flags.append(f'GPA học kỳ {g:.2f}')
    if o is not None and o>0:flags.append(f'{o:g} tín chỉ nợ')
    if d is not None and d<70:flags.append(f'điểm rèn luyện {d:g}')
    # Internal support priority, not a school rule or eligibility classifier.
    tier=1 if g is not None and g<2 and o is not None and o>0 else 2 if flags else 3 if missing else 4
    return tier,flags,missing

def screening(students):
    groups=defaultdict(list);counts=Counter(str(s.get('student_id') or s.get('mssv') or '') for s in students);duplicates=0
    for s in students:
        sid=str(s.get('student_id') or s.get('mssv') or '')
        if not sid or counts[sid]!=1:duplicates+=1;continue
        tier,flags,missing=signals(s);groups[tier].append((sid,str(s.get('full_name') or 'Sinh viên'),flags,missing))
    # Explicit, auditable triage within each tier: known debt first (descending),
    # then lower semester GPA, then lower conduct score; missing is not zero.
    by_id={str(s.get('student_id') or s.get('mssv') or ''):s for s in students}
    def priority(x):
        st=by_id[x[0]];o=valid(st.get('owed_credits'),0,1000);g=valid(st.get('gpa_semester'),0,4);d=valid(st.get('drl'),0,100)
        return (o is None,-o if o is not None else 0,g is None,g if g is not None else 0,d is None,d if d is not None else 0,x[0])
    for v in groups.values():v.sort(key=priority)
    return groups,duplicates

def debt_rows(st,courses):
    history=defaultdict(set)
    for g in st.get('bang_diem') or []:
        code=str(g.get('ma_mon') or '').upper(); passed=g.get('dat')
        if re.fullmatch(r'[A-Z]{3}\d{4}',code) and isinstance(passed,bool):history[code].add(passed)
    catalog=defaultdict(set)
    for c in courses:
        code=str(c.get('ma_mon') or '').upper();credit=valid(c.get('so_tin_chi'),1,30)
        if credit is not None and credit.is_integer():catalog[code].add((str(c.get('ten_mon') or code),int(credit)))
    eligible=[];ambiguous=[];missing=[]
    for code,results in sorted(history.items()):
        if False not in results:continue
        if True in results:ambiguous.append(code);continue
        if len(catalog[code])!=1:missing.append(code);continue
        name,credit=next(iter(catalog[code]));eligible.append((code,name,credit))
    return eligible,ambiguous,missing

def pack(rows,cap):
    """First-fit decreasing credit bundles, not guaranteed optimal or registrable."""
    bins=[];oversized=[]
    for row in sorted(rows,key=lambda r:(-r[2],r[0])):
        if row[2]>cap:oversized.append(row);continue
        for b in bins:
            if sum(x[2] for x in b)+row[2]<=cap:b.append(row);break
        else:bins.append([row])
    return bins,oversized

def caps(q):
    # Only explicit 'tối đa N tín chỉ môn nợ' changes the scenario budgets.
    raw=re.findall(r'\btoi da (\d{1,2}) tin chi (?:mon no|hoc lai)\b',q)
    if raw:
        v=int(raw[0]);return [v] if 1<=v<=30 and len(set(raw))==1 else []
    return [6,12]

def draft(student=False):
    if student:
        return ('Dự thảo tin nhắn riêng — cô duyệt trước khi gửi:\n'
                'Chào em, cô muốn trao đổi với em về tình hình học tập và kế hoạch kỳ tới. Em chuẩn bị bảng điểm cập nhật, các học phần cần học lại và những khó khăn đang gặp nhé. Em phản hồi thời gian thuận tiện để cô sắp xếp buổi trao đổi riêng. Cô và em sẽ cùng thống nhất phương án phù hợp.')
    return ('Dự thảo thông báo chung — cô duyệt trước khi gửi:\n'
            'Các em thân mến, để chuẩn bị kế hoạch học tập kỳ tới, các em vui lòng tự rà soát bảng điểm, học phần chưa hoàn thành và thông tin đăng ký trên cổng đào tạo. Nếu cần hỗ trợ, hãy liên hệ riêng với cô để được trao đổi. Không gửi bảng điểm hoặc thông tin cá nhân vào nhóm lớp. Cô sẽ cùng các em thống nhất kế hoạch phù hợp.')

def run_workflow(question,bundle,root):
    start=time.monotonic();ab=bundle or {};cat=ab.get('category');q=norm(question)
    personal=cat=='STUDENT_STATUS';class_scope=cat in ('CLASS_STATS','ELIGIBILITY_CHECK')
    if not (personal or class_scope):return None
    want_draft=bool(DRAFT_TASK.search(q));want_screen=class_scope and bool(CLASS_TASK.search(q));want_plan=personal and bool(STUDENT_TASK.search(q))
    want_report=bool(REPORT_TASK.search(q))
    if not (want_draft or want_screen or want_plan or want_report):return None
    # Avoid replacing questions with historical/legal eligibility conclusions or
    # unrelated data tasks. The underlying router handles RED before this path.
    if re.search(r'\b(?:du dieu kien|co duoc phep|buoc thoi hoc|co bi ha bang|muc hoc phi|muc hoc bong)\b',q) and not want_draft:return None
    roster=ab.get('roster_obj') or {};students=roster.get('students') or [];steps=[];tools=[];lines=[];sources=[];report=None
    error=scope_error(q,roster);sid=str(ab.get('student_id') or '')
    selected=[s for s in students if sid and str(s.get('student_id') or s.get('mssv'))==sid] if personal else []
    if error or (personal and len(selected)!=1) or not students:
        lines=['Dạ cô, em chưa thể thực hiện vì '+(error or 'chưa xác định được hồ sơ cần tư vấn')+'. Cô chọn đúng hồ sơ rồi hỏi lại giúp em.'];tools=['scope_check']
    else:
        tools=['scope_check']; lines=['Dạ cô, em đã rà hồ sơ demo '+str(roster.get('class_short') or roster.get('class_id') or 'đang mở')+' ('+str(roster.get('cohort') or 'khóa chưa xác định')+').']
        if want_screen:
            groups,dup=screening(students);tools.append('screening')
            lines+=['Em đề xuất thứ tự hỗ trợ sau (ngưỡng sàng lọc nội bộ, không phải quyết định học vụ):']
            labels={1:'Ưu tiên gặp riêng: GPA học kỳ thấp và còn tín chỉ nợ',2:'Cần trao đổi: có ít nhất một tín hiệu cần hỗ trợ',3:'Cần bổ sung dữ liệu',4:'Chưa thấy tín hiệu theo ba tiêu chí đang xét'}
            for tier in (1,2,3,4):
                group=groups[tier];lines.append(f'• {labels[tier]} — {len(group)} sinh viên.')
                if tier<4:
                    for sid2,name,flags,missing in group:
                        lines.append(f'  {name} ({sid2}): '+('; '.join(flags+(['thiếu '+', '.join(missing)] if missing else [])) or 'thiếu dữ liệu')+'.')
            if dup:lines.append(f'Có {dup} bản ghi trùng hoặc thiếu mã; chưa đưa vào nhóm.')
            steps += [('Gặp riêng nhóm ưu tiên','Trao đổi nguyên nhân, kiểm tra bảng điểm mới nhất và lịch sử học lại; không công bố danh sách này cho lớp.'),('Hỗ trợ nhóm còn lại','Thống nhất mục tiêu và cách theo dõi, rà dữ liệu còn thiếu.'),('Theo dõi sau tư vấn','Ghi nhận tiến độ từng em sau đợt đánh giá tiếp theo.')]
            lines.append('Không dùng GPA học kỳ làm GPA tích lũy; cần lịch sử cảnh báo, hồ sơ và quy chế đúng khóa trước khi kết luận chính thức.')
        if want_plan:
            st=selected[0];tier,flags,missing=signals(st);rows,ambiguous,unknown=debt_rows(st,roster.get('courses') or []);tools.extend(['student_signals','course_history','credit_scenarios'])
            lines.append('Hồ sơ: '+str(st.get('full_name') or 'Sinh viên')+' ('+sid+'). '+('; '.join(flags) if flags else 'Chưa thấy tín hiệu theo các tiêu chí sàng lọc')+'.')
            if missing:lines.append('Dữ liệu thiếu: '+', '.join(missing)+'.')
            if rows:lines.append('Các học phần có lần không đạt và chưa thấy lần đạt trong dữ liệu demo: '+ '; '.join(f'{code} – {name} ({c} tín chỉ)' for code,name,c in rows)+'. Tổng số tín chỉ của danh sách này: '+str(sum(r[2] for r in rows))+'.')
            if ambiguous:lines.append('Có cả lần đạt và không đạt, cần đối chiếu kết quả chính thức: '+', '.join(ambiguous)+'. Không tự đưa vào lịch học lại.')
            if unknown:lines.append('Chưa xác minh được số tín chỉ trong danh mục demo: '+', '.join(unknown)+'.')
            owed=valid(st.get('owed_credits'),0,1000)
            if owed is not None and owed!=sum(r[2] for r in rows):lines.append(f'Tín chỉ nợ theo hồ sơ là {owed:g}, khác tổng danh sách có thể phân bổ. Không coi hai con số là tương đương.')
            table,reason=load_candidate(root,roster)
            if table is not None:
                tools.append('prerequisite_planning')
                sources.append({'source_path':REL,'sha256':SHA,'source_url':'','review_status':'needs_human_review','scope':'filename_hint_only'})
                lines.append('Em tìm được bảng tham khảo CNTT 2022–2024 của nhóm. Phạm vi khóa chỉ là gợi ý từ tên file, bảng chưa duyệt; em dùng để mô phỏng thứ tự học lại, không xác nhận đủ điều kiện đăng ký.')
            else:
                lines.append('Chưa thể kiểm tra tiên quyết: '+reason+'. Em chỉ phân nhóm tín chỉ, không coi thứ tự dưới đây là lịch học.')
            limits=caps(q)
            if not limits:lines.append('Cô vui lòng nhập một giới hạn từ 1 đến 30 tín chỉ học lại cho mỗi nhóm giả định.')
            for cap in limits:
                lines.append(f'Phương án giả định: tối đa {cap} tín chỉ học lại mỗi đợt (không phải giới hạn đăng ký của trường).')
                if table is not None:
                    lines+=dependency_lines(rows,table,st.get('bang_diem') or [],cap)
                    continue
                bins,over=pack(rows,cap)
                if not bins:lines.append('  Chưa có học phần đủ dữ kiện để phân bổ.')
                for i,b in enumerate(bins,1):lines.append(f'  Đợt {i}: '+', '.join(r[0] for r in b)+f' — {sum(r[2] for r in b)} tín chỉ.')
                if over:lines.append('  Chưa xếp được vì vượt mức giả định: '+', '.join(r[0] for r in over)+'.')
            if table is not None:
                lines.append('Thứ tự có xét mã tiên quyết trong bảng tham khảo; mỗi đợt sau giả định các môn ở đợt trước đã đạt. Không tự coi môn chưa có điểm là đã đạt hoặc quy đổi mã tương đương. Chưa xét lịch mở lớp, độ khó, học phần mới và giới hạn đăng ký chính thức. Không suy ra số kỳ còn lại.')
            else:lines.append('Đây là phân nhóm theo tín chỉ của danh mục demo, chưa xét độ khó, môn tiên quyết, lịch mở lớp, học phần mới hay GPA tích lũy. Không phải kế hoạch đăng ký hoặc cam kết tốt nghiệp; không suy ra số kỳ còn lại.')
            steps += [('Xác nhận môn nợ','Đối chiếu lần học lại, mã học phần và bảng điểm chính thức.'),('So sánh phương án','Ít tín chỉ học lại mỗi đợt giảm tải hơn nhưng có thể kéo dài tiến độ; nhiều tín chỉ hơn cần đánh giá khả năng học và lịch học.'),('Chốt với sinh viên','Kiểm tra CTĐT đúng khóa, điều kiện tiên quyết, lịch mở lớp, giới hạn đăng ký và các học phần mới trước khi lập lịch.')]
        if want_report:
            if personal:
                st=selected[0];_,flags,missing=signals(st);rows,ambiguous,unknown=debt_rows(st,roster.get('courses') or [])
                report=build_report(roster,student=st,flags=flags,missing=missing,history_rows=rows,ambiguous=ambiguous,unknown=unknown)
            else:
                groups,dup=screening(students)
                report=build_report(roster,groups=groups,duplicate_records=dup)
            tools.append('advisor_report');lines+=['',report['text']]
        if want_draft:
            tools.append('communication_draft');lines+=['',draft(personal)];steps.append(('Duyệt nội dung','Cô xác nhận nội dung và thời gian trước khi gửi; hệ thống không tự gửi tin nhắn.'))
        if steps:lines+=['','Việc cô có thể làm tiếp:']+['• '+detail for _,detail in steps]
    return {'predicted_answer':'\n'.join(lines),'mode':'chrono_rag','is_advisor_composite':True,'cited_doc_ids':[],'model_name':None,'inference_source':'deterministic_workflow_tools','engine_mode':'ADVISOR_WORKFLOW','advisor_category':cat,'advisor_entities':ab.get('entities'),'roadmap':[{'title':a,'detail':b} for a,b in steps],'advisor_sources':sources,'workflow_tools':tools,'advisor_report':report,'latency_ms':(time.monotonic()-start)*1000}
