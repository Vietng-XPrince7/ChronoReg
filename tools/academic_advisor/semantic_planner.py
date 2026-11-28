"""Local semantic planner contract. No benchmark cases or answer bank."""
import json, re, urllib.request
KINDS = ['rank_check','credit_cap','student_lookup','student_compare','retake_plan','counseling','draft','admissions','tuition','calendar','class_scope','clarify']
# Unified nullable typed contract. Fields not needed for the current task must be null.
TYPES = {'cohort':'integer','year':'integer','academic_year':'string','program':'string','tuition_scope':'string','method':'string','semester':'string','rank':'string','total_credits':'integer','repeat_credits':'integer','discipline':'boolean','gpa':'number','gpa_kind':'string','standard_credits':'integer','not_dismissed':'boolean','all_counted':'boolean','student':'string','other_student':'string','metric':'string','budget':'integer','first_course':'string','minutes':'integer','days':'integer','preference':'string','audience':'string','format':'string','max_words':'integer','subject':'string','exclude_private':'boolean','intent_detail':'string','counsel_action':'string','opening_count':'integer','draft_purpose':'string','include_summary':'boolean','prepare_issue':'boolean'}
ENUM = {'tuition_scope':['standard','dm','tt23'],'counsel_action':['opening','study_plan','privacy'],'draft_purpose':['invite'],'rank':['excellent','good','fair','average'], 'gpa_kind':['semester','cumulative'], 'semester':['main','main_1','main_2','summer'], 'metric':['debt','semester_gpa','cumulative_gpa','earned_credits'], 'audience':['private','class'], 'format':['email','message','notice'], 'method':['THPT','HSA','SAT'], 'preference':['individual','group'], 'intent_detail':['check','revise','compare','explain','plan','lookup','refuse_reuse','availability']}
SCHEMA = {'type':'object','properties':{'intent':{'type':'string','enum':KINDS},'slots':{'type':'object','properties':{k:({'anyOf':[{'type':v,**({'enum':ENUM[k]} if k in ENUM else {})},{'type':'null'}]}) for k,v in TYPES.items()},'additionalProperties':False}},'required':['intent','slots'],'additionalProperties':False}

def plan(intent,**slots):return {'intent':intent,'slots':slots}


def validate(obj):
    if not isinstance(obj,dict) or set(obj)!={'intent','slots'} or obj['intent'] not in KINDS or not isinstance(obj['slots'],dict):raise ValueError('invalid plan shape')
    slots=obj['slots']
    if set(slots)-set(TYPES):raise ValueError('unknown slot')
    for k,v in slots.items():
        if v is None:continue
        t=TYPES[k]
        good=(type(v) is int if t=='integer' else type(v) in (int,float) if t=='number' else type(v) is bool if t=='boolean' else type(v) is str and 0<len(v)<=120)
        if not good:raise ValueError('invalid slot type: '+k)
        if k in ENUM and v not in ENUM[k]:raise ValueError('invalid enum: '+k)
        if k in ('cohort','year') and not 2000<=v<=2100:raise ValueError('invalid year')
        if k=='gpa' and not 0<=v<=4:raise ValueError('invalid GPA')
        if k in ('total_credits','standard_credits','budget','minutes','days','max_words') and v<=0:raise ValueError('invalid positive field')
        if k=='repeat_credits' and v<0:raise ValueError('invalid repeat credits')
    return {'intent':obj['intent'],'slots':{k:v for k,v in slots.items() if v is not None}}


FIELDS = {
 'rank_check': 'cohort rank total_credits repeat_credits discipline',
 'credit_cap': 'cohort semester gpa gpa_kind standard_credits not_dismissed all_counted',
 'student_lookup': 'student metric', 'student_compare': 'student other_student metric',
 'retake_plan': 'student budget first_course', 'counseling': 'student minutes days preference counsel_action opening_count',
 'draft': 'student audience format subject max_words exclude_private draft_purpose include_summary prepare_issue',
 'admissions': 'program method year', 'tuition': 'cohort program academic_year tuition_scope',
 'calendar': 'semester academic_year', 'class_scope': 'intent_detail', 'clarify': '',
}
FIELDS={k: v.split() for k,v in FIELDS.items()}
DESC = {
 'rank_check':'Xếp loại bằng, ảnh hưởng học lại hoặc kỷ luật đến hạng tốt nghiệp.',
 'credit_cap':'Giới hạn số tín chỉ đăng ký trong kỳ, theo GPA hoặc kế hoạch chuẩn.',
 'student_lookup':'Lấy một chỉ số học tập của một sinh viên cụ thể.',
 'student_compare':'So sánh một chỉ số học tập giữa hai sinh viên.',
 'retake_plan':'Xếp các môn cần học lại thành đợt, giới hạn tải, môn tiên quyết.',
 'counseling':'Tư vấn, cách trao đổi, hỗ trợ và tự học của sinh viên.',
 'draft':'Viết hoặc sửa email, tin nhắn, thông báo; gồm cả đổi giọng văn, rút gọn.',
 'admissions':'Điểm chuẩn, điểm trúng tuyển hoặc ngưỡng xét tuyển theo ngành/năm/phương thức.',
 'tuition':'Học phí, mức thu, đơn vị tính học phí theo khóa và năm học.',
 'calendar':'Lịch học, thời điểm bắt đầu/kết thúc học kỳ theo năm học.',
 'class_scope':'Hỏi có được sử dụng dữ liệu lớp khác hoặc lớp chưa có hồ sơ không.',
 'clarify':'Thiếu đối tượng tham chiếu cần thiết hoặc không xác định được mục tiêu.',
}
HINT = {
 'counsel_action':'opening=mở đầu buổi trao đổi; study_plan=kế hoạch tự học/hỗ trợ; privacy=bảo mật',
 'opening_count':'số cách mở đầu', 'draft_purpose':'invite=lời mời trao đổi học tập', 'include_summary':'true nếu yêu cầu cả tóm tắt sàng lọc nội bộ và thông báo chung', 'prepare_issue':'true nếu yêu cầu chuẩn bị vấn đề hoặc câu hỏi',
 'cohort':'năm tuyển sinh của khóa, K67=2022, K68=2023, K69=2024, K70=2025, K71=2026; không phải năm học',
 'year':'năm tuyển sinh/điểm chuẩn được yêu cầu, nếu nói thay vì X thì lấy năm mới',
 'academic_year':'năm học gồm hai năm liên tiếp YYYY-YYYY, không phải khóa tuyển sinh',
 'program':'tên ngành nguyên văn', 'tuition_scope':'standard=CTĐT chuẩn; dm=ĐMKTKT; tt23=CLC theo TT23; chỉ ghi khi nêu rõ', 'method':'THPT/HSA/SAT nếu được nêu',
 'semester':'main=kỳ chính không rõ số; main_1=kỳ chính 1; main_2=kỳ chính 2; summer=kỳ phụ/hè',
 'rank':'excellent=Xuất sắc; good=Giỏi; fair=Khá; average=Trung bình',
 'total_credits':'tổng số tín chỉ chương trình', 'repeat_credits':'tổng số tín chỉ phải học lại',
 'discipline':'true=có kỷ luật; false=không kỷ luật', 'gpa':'giá trị GPA, dấu phẩy thập phân đổi thành dấu chấm',
 'gpa_kind':'semester=GPA học kỳ; cumulative=GPA tích lũy; tôn trọng đính chính',
 'standard_credits':'số tín chỉ trung bình kỳ theo kế hoạch chuẩn',
 'not_dismissed':'true=chưa/không thuộc diện buộc thôi học; false=thuộc diện buộc thôi học',
 'all_counted':'true=mọi học phần đều tính tải; false=có học phần loại trừ',
 'student':'MSSV gồm đúng 8 chữ số; khi so sánh giữ đối tượng gốc',
 'other_student':'MSSV thứ hai gồm đúng 8 chữ số; không thay MSSV gốc',
 'metric':'debt=tín chỉ nợ; semester_gpa=GPA kỳ; cumulative_gpa=GPA tích lũy; earned_credits=TC tích lũy',
 'budget':'giới hạn tín chỉ học lại mỗi đợt', 'first_course':'mã học phần yêu cầu ở đợt đầu',
 'minutes':'số phút mỗi ngày', 'days':'số ngày; một tuần=7 ngày',
 'preference':'individual=tự học một mình; group=học nhóm',
 'audience':'class=cả lớp/công khai; private=riêng một sinh viên',
 'format':'email=email; message=tin nhắn; notice=thông báo',
 'subject':'tiêu đề email được nêu nguyên văn, không tự đặt',
 'max_words':'giới hạn từ phần nội dung, không phải tín chỉ',
 'exclude_private':'true=không đưa tên, mã, điểm cá nhân; mặc định không tự đặt false',
 'intent_detail':'refuse_reuse nếu hỏi về việc dùng số liệu lớp khác thay thế',
}

def project_prior(intent, prior, reuse):
    if not reuse or not prior:return {}
    old=prior['intent']
    if old=='counseling' and intent=='draft':return {k:v for k,v in prior['slots'].items() if k=='student'}
    if old != intent and (old,intent) not in {('student_lookup','student_compare'),('student_compare','student_lookup')}:return {}
    return {k:v for k,v in prior['slots'].items() if k in FIELDS[intent]}

def slot_schema(intent):
    return {'type':'object','properties':{k:SCHEMA['properties']['slots']['properties'][k] for k in FIELDS[intent]},'additionalProperties':False}

def validate_route(obj, prior):
    if not isinstance(obj,dict) or set(obj)!={'intent','reuse'} or obj['intent'] not in KINDS or type(obj['reuse']) is not bool:raise ValueError('invalid route')
    if obj['reuse'] and not prior:raise ValueError('reuse with no prior')
    return obj

def merge_delta(intent, base, delta):
    if not isinstance(delta,dict) or set(delta)-set(FIELDS[intent]):raise ValueError('invalid task-specific fields')
    # Validate every non-null value. Null explicitly clears; omitted means unchanged.
    validate(plan(intent,**delta))
    for k in ('student','other_student'):
        if k in delta and delta[k] is not None and not re.fullmatch(r'[0-9]{8}',delta[k]):raise ValueError('invalid student ID shape')
    if 'academic_year' in delta and delta['academic_year'] is not None:
        y=delta['academic_year'];m=re.fullmatch(r'(20[0-9]{2})-(20[0-9]{2})',y)
        if not m or int(m[2])!=int(m[1])+1:raise ValueError('invalid academic year')
    s=dict(base)
    for k,v in delta.items():
        if v is None:s.pop(k,None)
        else:s[k]=v
    # Public drafts never carry an individual identifier, regardless of model output.
    if intent=='draft' and s.get('audience')=='class':s.pop('student',None)
    return validate(plan(intent,**s))


ONE_SCHEMA={'anyOf':[{'type':'object','properties':{'intent':{'type':'string','enum':[i]},'reuse':{'type':'boolean'},'slots':slot_schema(i)},'required':['intent','reuse','slots'],'additionalProperties':False} for i in KINDS]}
ONE_SYSTEM='''Phân tích yêu cầu tiếng Việt, không trả lời câu hỏi. Trả JSON intent, reuse, slots. Chọn đúng mục tiêu. reuse=true chỉ khi tiếp nối nhiệm vụ cũ; không có trạng thái thì false. slots chỉ chứa dữ kiện mới/đính chính, không cần sao chép dữ kiện giữ nguyên. Bỏ trường nếu không thay đổi; null chỉ khi yêu cầu xóa. Không tự suy ra số, mã, ngày, khóa, kỳ, hay kết quả. Không nhầm từ cần loại bỏ với nhiệm vụ mới. Phân biệt GPA kỳ và tích lũy; khóa tuyển sinh và năm học; thi lại và học lại; giới hạn từ và tín chỉ. Nếu thiếu sinh viên trong câu hỏi tra hồ sơ, chọn clarify. Nếu chuyển đối tượng, không giữ dữ kiện của đối tượng cũ; so sánh thì giữ đối tượng gốc. Thông báo cả lớp không chứa định danh. Chọn loại và trường theo danh mục:\n'''+ '\n'.join(i+': '+DESC[i]+' | '+', '.join(FIELDS[i]) for i in KINDS)+'\nÝ nghĩa trường:\n'+'\n'.join(k+': '+v for k,v in HINT.items())

# These checks use only the actual question and prior, never a benchmark answer.
def checked_plan(raw,question,prior):
    if not isinstance(raw,dict) or set(raw)!={'intent','reuse','slots'}:raise ValueError('invalid one-pass shape')
    route={k:raw[k] for k in ('intent','reuse')}
    if not prior and route.get('reuse') is True:route['reuse']=False
    route=validate_route(route,prior); i=route['intent']; d=raw['slots']
    if prior and route['reuse'] and prior.get('intent')=='counseling' and i=='draft':
        from quality import norm
        if not re.search(r'\b(?:ban nay|ban ay|ban do|em nay|em ay|em do|sinh vien nay|sinh vien do)\b',norm(question)) and str(prior['slots'].get('student','')) not in re.findall(r'\b\d{8}\b',question):
            route['reuse']=False
    base=project_prior(i,prior,route['reuse']);p=merge_delta(i,base,d)
    s=p['slots']; ids=set(re.findall(r'(?<!\d)\d{8}(?!\d)',question)); previous={str(v) for k,v in base.items() if k in ('student','other_student')}
    if prior and route['reuse'] and prior.get('intent')=='student_compare' and i=='student_lookup':
        from quality import norm
        if re.search(r'\b(?:ban|sinh vien) thu hai\b',norm(question)) and prior['slots'].get('other_student'):
            previous.add(prior['slots']['other_student'])
    for k in ('student','other_student'):
        if k in s and s[k] not in ids|previous:raise ValueError('student identifier without grounding')
    if i in ('student_lookup','student_compare','retake_plan','counseling') and ids:
        represented={s[k] for k in ('student','other_student') if k in s}
        if not ids<=represented:raise ValueError('explicit student identifier omitted')
    if i in ('student_lookup','student_compare','retake_plan') and not s.get('student'):
        return plan('clarify'),route,base
    if i=='student_compare' and (not s.get('other_student') or s['student']==s['other_student']):return plan('clarify'),route,base
    if i=='draft' and s.get('audience')=='class':s.pop('student',None);s['exclude_private']=True
    # Never let a rejected plan reach the synthetic tool.
    return p,route,base


MODEL='qwen3.5:4b-q4_K_M'

def infer(question, prior):
    # Fixed local endpoint, no proxy, no redirects, no downloads, no cloud.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    payload={'model':MODEL,'messages':[{'role':'system','content':ONE_SYSTEM},{'role':'user','content':'Trạng thái trước: '+json.dumps(prior,ensure_ascii=False)+'\nCâu hỏi: '+question}], 'stream':False,'format':ONE_SCHEMA,'think':False,'options':{'temperature':0,'num_ctx':4096,'num_predict':256,'num_gpu':0}}
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=100) as r:
        body=json.load(r)
    if body.get('done_reason')=='length':raise ValueError('incomplete planner output')
    return json.loads(body['message']['content'])
