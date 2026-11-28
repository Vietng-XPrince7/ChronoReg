"""Bounded parameter grounding, no test fixtures, no model or data access."""
import re
S={'type':'string'}; I={'type':'integer'}
def enum(*v):return {'type':'string','enum':list(v)}
def nullable(s):return {'anyOf':[s,{'type':'null'}]}
def obj(p):return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
FEE={'cohort':{'type':'integer','minimum':2000,'maximum':2100},'program_type':enum('standard','dm','tt23'),'academic_year':S,'credits':{'type':'array','items':{'type':'integer','minimum':1,'maximum':200},'minItems':1,'maxItems':12}}
STUDY={'student':S,'minutes':{'type':'integer','minimum':1,'maximum':1440},'days':{'type':'integer','minimum':1,'maximum':365}}
ITEM=obj({'program':enum('cntt','khmt','httt','ktmt'),'cohort':I})
CONTRACTS={
 'fee_total':FEE,
 'fee_compare':{**FEE,'previous_year':S},
 'study_plan':STUDY,'study_review':STUDY,
 'curriculum_compare':{'items':{'type':'array','items':ITEM,'minItems':2,'maxItems':12},'metric':enum('total_credits','thesis_credits')},
 'policy_lookup':{'instrument':S,'article':I,'clause':I,'question_type':enum('leave_conditions','return_deadline','research_bonus','exam_eligibility')},
 'clarify_student':{'reason':enum('no_student','cross_session')},
 'unsupported_scope':{'reason':enum('unverified_cohort')},
 'clarify_request':{'reason':enum('missing_parameters','unsupported_intent')},
}
def plan(action,**args):return {'action':action,'args':args}
def item(p,c):return dict(program=p,cohort=c)
def canonical(p):
    if not isinstance(p,dict) or set(p)!={'action','args'} or p['action'] not in CONTRACTS or not isinstance(p['args'],dict):raise ValueError('invalid plan shape')
    spec=CONTRACTS[p['action']];a=p['args']
    if set(a)!=set(spec):raise ValueError('missing or extraneous action fields')
    def check(v,s):
        t=s['type']
        if t=='integer' and (type(v) is not int or v<s.get('minimum',1) or v>s.get('maximum',2100)):raise ValueError('invalid integer')
        if t=='string' and (type(v) is not str or not v or len(v)>120):raise ValueError('invalid string')
        if 'enum' in s and v not in s['enum']:raise ValueError('invalid enum')
        if t=='array':
            if not isinstance(v,list) or not s.get('minItems',1)<=len(v)<=s.get('maxItems',12):raise ValueError('invalid array')
            for x in v:check(x,s['items'])
        if t=='object':
            if not isinstance(v,dict) or set(v)!=set(s['properties']):raise ValueError('invalid object')
            for k,x in v.items():check(x,s['properties'][k])
    for k,v in a.items():
        if v is None:raise ValueError('unresolved parameter: '+k)
        check(v,spec[k])
    for k in ('academic_year','previous_year'):
        if k in a:
            m=re.fullmatch(r'(20[0-9]{2})-(20[0-9]{2})',a[k]);
            if not m or int(m[2])!=int(m[1])+1:raise ValueError('invalid academic year')
    if 'student' in a and not re.fullmatch(r'[0-9]{8}',a['student']):raise ValueError('invalid student ID')
    if p['action']=='fee_compare' and a['academic_year']==a['previous_year']:raise ValueError('identical comparison years')
    return p

import unicodedata

def fold(text):
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFD',text.lower().replace('đ','d')) if unicodedata.category(c)!='Mn')).strip()

def one(values, label):
    v=list(dict.fromkeys(values))
    if len(v)>1:raise ValueError('ambiguous '+label)
    return v[0] if v else None

def choose(new,old,label):
    if new is not None:return new
    if old is not None:return old
    raise ValueError('unresolved '+label)

COHORT=r'\b(?:k\s*(\d{2})|qh\s*[- ]?\s*(20\d{2}))\b'
YEAR=r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b'
MAJOR=r'\b(cong nghe thong tin|khoa hoc may tinh|he thong thong tin|ky thuat may tinh|cntt|khmt|httt|ktmt)\b'
MAJORS={'cong nghe thong tin':'cntt','khoa hoc may tinh':'khmt','he thong thong tin':'httt','ky thuat may tinh':'ktmt','cntt':'cntt','khmt':'khmt','httt':'httt','ktmt':'ktmt'}

def cohort_match(m):
    return 1955+int(m[1]) if m[1] else int(m[2])

def cohorts(n):return [cohort_match(m) for m in re.finditer(COHORT,n)]
def years(n):
    ys=[]
    for m in re.finditer(YEAR,n):
        if int(m[2])!=int(m[1])+1:raise ValueError('nonconsecutive academic year')
        ys.append(f'{m[1]}-{m[2]}')
    return ys

def prior_args(p,allowed):
    if p.get('action') not in allowed:return {}
    return canonical(p)['args']

def positive_ints(n,pattern,label):return one([int(x) for x in re.findall(pattern,n)],label)

def credit_values(n,old):
    # Do not interpret ranges, fractions or load ceilings as prices.
    if re.search(r'\d+[.,]\d+\s*(?:tin chi|tc)\b|\b\d+\s*[-–]\s*\d+\s*(?:tin chi|tc)\b|\b(?:toi da|it nhat|khoang)\s*\d+\s*(?:tin chi|tc)\b',n):raise ValueError('ambiguous credit quantity')
    if re.search(r'\b(?:bo|loai|khong tinh|tru)\s+(?:mon|hoc phan)\b',n):
        m=re.search(r'\b(?:bo|loai|khong tinh|tru)\s+(?:mon|hoc phan)\s+(\d+)\s*(?:tin chi|tc)\b',n)
        if not m or not old or old.count(int(m[1]))!=1:raise ValueError('ambiguous course removal')
        if len(re.findall(r'\b\d+\s*(?:tin chi|tc)\b',n))!=1:raise ValueError('mixed credit changes')
        return [x for x in old if x!=int(m[1])]
    groups=re.findall(r'\b(\d+(?:(?:\s*,\s*|\s+va\s+)\d+)*)\s*(?:tin chi|tc)\b',n)
    if groups:
        if re.search(r'\b(?:moi mon|moi hoc phan|moi dot|moi ky)\b',n):raise ValueError('unsupported credit multiplier or load')
        return [int(x) for g in groups for x in re.findall(r'\d+',g)]
    return choose(None,old,'credits')

def grounded(raw,question,prior):
    """No benchmark IDs, expected answer, network, roster or side effects.
    Prior must be authenticated by the caller in a real integration. This probe
    has teacher-forced synthetic priors. Reject rather than guess unsupported syntax.
    """
    if not isinstance(prior,dict) or not isinstance(raw,dict) or raw.get('action') not in CONTRACTS:raise ValueError('unknown proposal')
    n=fold(question);a=raw['action']
    # Cross-session request: no old identity may be carried into a new session.
    if re.search(r'\b(?:phien|cua so|cuoc tro chuyen|doan chat)\b',n) and re.search(r'\b(?:khac|hom qua|truoc do|cu)\b',n) and re.search(r'\b(?:ho so|sinh vien|mssv)\b',n):return plan('clarify_student',reason='cross_session')
    if a in ('fee_total','fee_compare'):
        old=prior_args(prior,('fee_total','fee_compare'))
        if not re.search(r'\b(?:hoc lai|hoc phi|khoan tien|khoan thu|tinh tien|kinh phi|chi phi|chenh lech|chenh ra)\b',n):raise ValueError('no fee evidence')
        if re.search(r'\b(?:hoc bong|mien hoc phi|tra gop|hoc lan dau|thi lai|khong hoc lai|ngoai le|thac si|tien si)\b',n):raise ValueError('mixed fee scope')
        # Explicit replacement is scoped to text after the change cue.
        selected=n
        if re.search(r'\bkhong\b',n):
            m=re.search(r'\bkhong tinh theo\b.+?\bchuyen sang\b(.+)',n)
            if not m:raise ValueError('unresolved negation')
            selected=m[1]
        c=choose(one(cohorts(selected),'cohort'),old.get('cohort'),'cohort')
        scopes=[]
        for name,pat in [('standard',r'\b(?:ctdt|chuong trinh|he)\s+chuan\b'),('dm',r'\b(?:dmktkt|dinh muc kinh te ky thuat)\b'),('tt23',r'\b(?:tt\s*23|thong tu 23)\b')]:
            if re.search(pat,selected):scopes.append(name)
        if re.search(r'\b(?:clc|chat luong cao)\b',selected) and 'tt23' not in scopes:raise ValueError('unknown fee program')
        scope=choose(one(scopes,'program_type'),old.get('program_type'),'program_type')
        credits=credit_values(selected,old.get('credits'))
        ys=years(selected)
        compare=bool(re.search(r'\b(?:so voi|doi chieu voi|chenh lech|chenh ra|tang them|giam di)\b',selected))
        if a=='fee_compare' or compare:
            if not compare:raise ValueError('comparison direction missing')
            m=re.search(r'\b(?:so voi|doi chieu voi)\b',selected)
            if m:
                target=one(years(selected[:m.start()]),'target year') or old.get('academic_year')
                base=one(years(selected[m.end():]),'comparison year')
            elif re.search(r'\b(?:sang|chuyen sang|doi sang)\b',selected) and len(ys)==1:
                target=ys[0];base=old.get('academic_year')
            else:raise ValueError('comparison direction ambiguous')
            return canonical(plan('fee_compare',cohort=c,program_type=scope,academic_year=target,previous_year=base,credits=credits))
        return canonical(plan('fee_total',cohort=c,program_type=scope,academic_year=choose(one(ys,'year'),old.get('academic_year'),'year'),credits=credits))
    if a in ('study_plan','study_review'):
        old=prior_args(prior,('study_plan','study_review'))
        if re.search(r'\b(?:khong lap|dung lap|khong tu hoc|khong can lap|hoc lai|hoc phi|hoc bong|soan|gui tin nhan|ca lop)\b',n):raise ValueError('mixed/negated study scope')
        ids=re.findall(r'(?<!\d)\d{8}(?!\d)',n);sid=one(ids,'student')
        previous=old.get('student') or (prior.get('student') if prior.get('kind')=='student_context' else None)
        review=bool(old and re.search(r'\b(?:can cu|dau hieu|ket qua|danh gia|theo doi|giam do kho|quyet dinh tiep|dua vao dau|hieu qua|tien bo|tieu chi|do luong)\b',n) and re.search(r'\b(?:ke hoach|phuong an|dot thu|cuoi tuan|tuan sau)\b',n))
        mins=positive_ints(n,r'\b(\d{1,4})\s*phut\b','minutes')
        days=positive_ints(n,r'\b(\d{1,3})\s*ngay\b','days')
        if re.search(r'\b(?:mot tuan|bay ngay|7 ngay)\b',n):
            if days not in (None,7):raise ValueError('conflicting duration')
            days=7
        if review:
            if mins is not None or days is not None or (sid and sid!=previous):raise ValueError('review changes plan')
            return canonical(plan('study_review',**old))
        if a=='study_review':raise ValueError('no review evidence')
        if not re.search(r'\b(?:tu hoc|tu on|on tap|lich on)\b',n):raise ValueError('no study evidence')
        if sid and sid!=previous:old={}
        sid=sid or previous
        if not sid:return plan('clarify_student',reason='no_student')
        return canonical(plan('study_plan',student=sid,minutes=choose(mins,old.get('minutes'),'minutes'),days=choose(days,old.get('days'),'days')))
    if a in ('curriculum_compare','unsupported_scope'):
        cy=cohorts(n)
        if any(y not in range(2022,2027) for y in cy):return plan('unsupported_scope',reason='unverified_cohort')
        if a=='unsupported_scope':raise ValueError('unsupported reason not grounded')
        if re.search(r'\b(?:clc|tt\s*23|dmktkt|tuong duong|hoc lai|tien quyet|hoc phi|khong tinh|thay the)\b',n):raise ValueError('unsupported curriculum scope')
        metric='thesis_credits' if re.search(r'\b(?:khoa luan|do an tot nghiep)\b',n) else 'total_credits' if re.search(r'\b(?:tong|toan khoa|tin chi tot nghiep)\b',n) else None
        if not metric:raise ValueError('unresolved curriculum metric')
        events=sorted([(m.start(),'major',MAJORS[m[1]]) for m in re.finditer(MAJOR,n)]+[(m.start(),'cohort',cohort_match(m)) for m in re.finditer(COHORT,n)])
        items=[];major=None;pending=False
        for _,kind,v in events:
            if kind=='major':
                if pending:raise ValueError('unpaired major')
                major=v;pending=True
            else:
                if not major:raise ValueError('unpaired cohort')
                items.append(item(major,v));pending=False
        if pending or len(items)<2 or len({(x['program'],x['cohort']) for x in items})!=len(items):raise ValueError('ambiguous curriculum pairs')
        return canonical(plan('curriculum_compare',items=items,metric=metric))
    if a=='policy_lookup':
        old=prior_args(prior,('policy_lookup',))
        if re.search(r'\b(?:ngoai le|dac cach|thong tu|nghi dinh|ap dung cho|hieu luc|k\d{2}|mssv|\d{8})\b',n):raise ValueError('unverified policy scope')
        inst=one(re.findall(r'\b(?:qd|quyet dinh)\s+(\d{3,8})\b',n),'instrument')
        art=positive_ints(n,r'\bdieu\s+(\d+)\b','article');cl=positive_ints(n,r'\bkhoan\s+(\d+)\b','clause')
        same=bool(re.search(r'\b(?:van ban do|quyet dinh ay|quyet dinh do|vua hoi|cung dieu khoan|dieu khoan ay|cung quyet dinh)\b',n))
        if not same and inst is None:raise ValueError('no document reference')
        inst=choose(inst,old.get('instrument') if same else None,'instrument')
        if inst!='3626':raise ValueError('unsupported instrument')
        oldref=old if same and old.get('instrument')==inst else {}
        art=choose(art,oldref.get('article'),'article')
        cl=choose(cl,oldref.get('clause') if art==oldref.get('article') else None,'clause')
        types=[]
        if re.search(r'\b(?:tro lai hoc|hoc tro lai|hoc tiep)\b',n) and re.search(r'\b(?:han|moc|truoc|khi nao)\b',n):types.append('return_deadline')
        if re.search(r'\b(?:tam nghi|nghi hoc)\b',n) and not types:types.append('leave_conditions')
        if re.search(r'\b(?:nckh|nghien cuu khoa hoc)\b',n):types.append('research_bonus')
        if re.search(r'\b(?:du thi|dieu kien thi)\b',n):types.append('exam_eligibility')
        t=one(types,'policy question type')
        if not t:raise ValueError('unresolved policy question type')
        return canonical(plan('policy_lookup',instrument=inst,article=art,clause=cl,question_type=t))
    if a=='clarify_student' and not prior and not re.search(r'\b\d{8}\b',n):return plan('clarify_student',reason='no_student')
    raise ValueError('unqualified action; no execution')
