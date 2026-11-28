"""Opt-in local pilot for existing academic advisor tools. Read-only, fail closed.
No gold prompts or answers. A semantic plan is a proposal, not an authorization.
"""
import re, time, json, unicodedata
from decimal import Decimal
from pathlib import Path
from quality import norm, lookup, number_atoms, parse
from quality_routes import response, source_response, pinned, find_student, cohort
from quality_workflows import snapshot
from workflow import scope_error, valid
from semantic_planner import infer, checked_plan, MODEL

SUPPORTED={'rank_check','credit_cap','student_lookup','student_compare','retake_plan','admissions','tuition','class_scope','clarify','draft','counseling','calendar'}
PROFILE={'student_lookup','student_compare'}
STUDENT=PROFILE|{'retake_plan','counseling'}
FIELDS={'debt':('owed_credits','tín chỉ nợ',1000),'earned_credits':('accumulated_credits','tín chỉ tích lũy',1000),'semester_gpa':('gpa_semester','GPA học kỳ',4)}

def tuition_scopes(n):
    return [label for label,pat in [('standard',r'\b(?:chuong trinh(?: dao tao)?|ctdt|he) chuan\b'),('dm',r'\b(?:dmktkt|dinh muc kinh te ky thuat)\b'),('tt23',r'\b(?:tt 23|thong tu 23)\b')] if re.search(pat,n)]

def fee_anchor(n):
    return bool(re.search(r'\bhoc phi\b',n) or (re.search(r'\b(?:dinh muc|muc thu|muc tien)\b',n) and re.search(r'\b(?:hoc lan dau|hoc lai|hoc cai thien(?: diem)?|tu chon tu do)\b',n)))

def fee_year(q):
    periods=re.findall(r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b',q)
    return '-'.join(periods[0]) if len(periods)==1 and int(periods[0][1])==int(periods[0][0])+1 else None

def admission_methods(n):
    # Explicit method evidence is authoritative, including unsupported methods.
    patterns={'THPT':r'\bthpt\b','HSA':r'\b(?:hsa|dgnl|danh gia nang luc)\b','SAT':r'\bsat\b','OTHER':r'\b(?:ielts|toefl|act|a level|xet tuyen thang|uu tien xet tuyen|tuyen thang|v sat|vsat|tsa|danh gia tu duy|hoc ba|chung chi quoc te)\b'}
    return {m for m,pat in patterns.items() if re.search(pat,n)}


def historical_reference(n,old):
    s=(old or {}).get('slots',{})
    return ((old or {}).get('intent')=='tuition' and s.get('academic_year')=='2022-2023' and s.get('tuition_scope')=='standard' and s.get('cohort') in range(2018,2023) and bool(re.fullmatch(r'(?:day|do|muc nay|muc do|muc tren|muc vua neu|con so vua neu|muc da dieu chinh) (?:co phai|la|co phai la) muc (?:ban dau|truoc dieu chinh)(?: khong)?',n)))


def candidate(q,prior):
    n=norm(q)
    old=prior.get("plan",{}) if prior.get("kind")=="semantic_task" else {}
    if historical_reference(n,old):return True
    if old.get("intent")=="admissions" and admission_methods(n) and re.search(r"\b(?:phuong thuc|xet tuyen)\b",n):return True
    from semantic_communication import candidate as comm_candidate
    if comm_candidate(q):return True
    if (fee_anchor(n) and "hoc phi" not in n and tuition_scopes(n) and not re.search(r"\b(?:hoc bong|mien|giam|gia han|thu tuc|so sanh|tinh hoc phi|du doan|lop khac)\b",n)) or (prior.get("kind")=="semantic_task" and prior.get("plan",{}).get("intent")=="tuition" and re.search(r"\b(?:sang|con|doi sang|chuyen sang) nam hoc\b",n)):return True
    if re.search(r'\b(?:hoc ky|ky chinh|ky phu|ky he)\b',n) and re.search(r'\b(?:bat dau|ket thuc|ngay nao|khi nao)\b',n) and re.search(r'\b20\d{2} 20\d{2}\b',n):return True
    if prior.get('kind')=='semantic_task' and prior.get('plan',{}).get('intent') in ('draft','counseling') and re.search(r'\b(?:tu hoc|hoc nhom|phut|rieng tu|bao mat|chia se|rut|giu|them|chuyen|tieu de|loi nhan|loi moi|thong bao|email|tin nhan)\b',n) and not re.search(r'\b(?:hoc phi|hoc bong|diem chuan|quy che|lich hoc)\b',n):return True
    if prior.get('kind')=='semantic_task' and prior.get('plan',{}).get('intent')=='retake_plan' and re.search(r'\b(?:dot dau|dot thu nhat|luot dau|mo lop|moi dot)\b',n):return True
    if prior.get('kind')=='semantic_task' and (re.search(r'^(?:con|neu|the|vay|a|doi|giu|chi|bay gio|gio|tuong tu|sua|thay|rut|tiep tuc|cap nhat|dinh chinh|so voi|doi chieu|chuyen|hai muc|so phai|co sua)\b',n) or re.search(r'\b(?:giu nguyen|khong thay doi|nhu cu|cung nganh|cung phuong thuc|em do|ban do|ban ay|em ay)\b',n)):return True
    if re.search(r'\b(?:lop khac|lop moi|lop chua|lop k\d+)\b',n) and re.search(r'\b(?:chua|thay the|dung so lieu)\b',n):return True
    if re.search(r'\b(?:diem chuan|diem trung tuyen|hoc phi|nguong trung tuyen)\b',n) and not re.search(r'\b(?:hoc bong|mien giam|gia han|thu tuc|rut hoc phan|du doan)\b',n):return True
    if re.search(r'\b(?:bang|hang|loai tot nghiep|xep hang)\b',n) and re.search(r'\b(?:hoc lai|ky luat|thi lai)\b',n) and re.search(r'\d',n):return True
    if re.search(r'\b(?:gpa|cpa|diem trung binh)\b',n) and re.search(r'\b(?:ke hoach(?: chuan)?|tran|gioi han|muc toi da|toi da)\b',n) and re.search(r'\d',n):return True
    if re.search(r'\b(?:hoc lai|mon no)\b',n) and re.search(r'\b(?:dot|lo trinh|tien quyet)\b',n) and re.search(r'\b\d{8}\b',q):return True
    if re.search(r'\b(?:tin chi no|tin chi (?:da )?tich luy|tich luy (?:duoc )?bao nhieu tin chi|gpa|diem trung binh|tc no|tc con no)\b',n) and (re.search(r'\b\d{8}\b',q) or re.search(r'\b(?:so voi|doi chieu|chenh|ban do|ban ay|em ay|ban thu hai|sinh vien thu hai)\b',n)) and not re.search(r'\b(?:lo trinh|hoc lai|tu van|ke hoach|tin nhan|email|thong bao)\b',n):return True
    return False

def clarification(text):return response(text,'semantic_clarification')

def guard(p,q,prior):
    """Explicit linguistic evidence wins over model output; ambiguous facts stay absent."""
    n=norm(q);plain=''.join(c for c in unicodedata.normalize('NFKD',q.lower().replace('đ','d')) if not unicodedata.combining(c));s=p['slots'];i=p['intent']; old=(prior or {}).get('slots',{}) if (prior or {}).get('intent')==i else {}
    # Numeric literals must appear in the current question or be unchanged inherited values.
    atoms=number_atoms(q)
    for k,v in list(s.items()):
        if type(v) in (int,float) and k!='cohort' and old.get(k)!=v and str(Decimal(str(v)).normalize()) not in atoms:raise ValueError('ungrounded numeric parameter')
    if i in ('rank_check','credit_cap','tuition'):
        years={int(v) for v in re.findall(r'\b(?:khoa(?: tuyen sinh)?|qh)\s*(20\d{2})\b',n)}|{1955+int(v) for v in re.findall(r'\bk(6[5-9]|7[0-9])\b',n)}
        if len(years)>1:raise ValueError('ambiguous cohort')
        cy=cohort(n)
        if cy is not None:s['cohort']=cy
        elif 'cohort' in s and old.get('cohort')!=s['cohort']:raise ValueError('ungrounded cohort')
    if i=='rank_check':
        # Do not interpret unspecified disciplinary action as warning-level discipline.
        neg=bool(re.search(r'\b(?:khong|chua)(?: he)? (?:bi |co )?ky luat\b',n))
        pos=bool(re.search(r'\b(?:ky luat|quyet dinh ky luat)\b.*\bcanh cao\b',n)) and not neg and not re.search(r'\b(?:khong|chua)\b.*\bcanh cao\b',n)
        if neg:s['discipline']=False
        elif pos:s['discipline']=True
        elif 'ky luat' in n:s.pop('discipline',None)
        elif 'discipline' in old:s['discipline']=old['discipline']
        else:s.pop('discipline',None)
        ranks={x:y for x,y in [('xuat sac','excellent'),('gioi','good'),('kha','fair'),('trung binh','average')] if re.search(r'\b'+x+r'\b',n)}
        if len(ranks)==1:s['rank']=next(iter(ranks.values()))
        elif len(ranks)>1 or s.get('rank')!=old.get('rank'):s.pop('rank',None)
        # A numerical value is not enough to distinguish numerator from denominator.
        repeat=re.findall(r'\b(?:hoc lai|phai hoc lai)(?: thuc ra)?(?: la)?\s+(\d+)(?!\d|[.,]\d)\s*(?:tc|tin chi|tren)\b',plain)
        total=re.findall(r'\b(?:tong(?: chuong trinh| ctdt)?|chuong trinh|ctdt)\s+(\d+)(?!\d|[.,]\d)\s*(?:tc|tin chi)\b|\btren (?:tong )?(\d+)(?!\d|[.,]\d)\s*(?:tc|tin chi)\b',plain)
        if len(set(repeat))==1:s['repeat_credits']=int(repeat[0])
        elif len(set(repeat))>1 or s.get('repeat_credits')!=old.get('repeat_credits'):s.pop('repeat_credits',None)
        rel=re.fullmatch(r'(?:neu )?(?:phai )?hoc lai (them|bot|giam) (mot|hai|ba|\d{1,3}) (?:tin chi|tc)(?: nua)?(?: cac dieu kien con lai giu nguyen| cac dieu kien khac giu nguyen| thi sao| giu nguyen dieu kien)?',n)
        if rel and type(old.get('repeat_credits')) is int:
            k={'mot':1,'hai':2,'ba':3}.get(rel[2],int(rel[2]) if rel[2].isdigit() else 0);s['repeat_credits']=old['repeat_credits']+(k if rel[1]=='them' else -k)
        totals={int(a or b) for a,b in total}
        if len(totals)==1:s['total_credits']=totals.pop()
        elif len(totals)>1 or s.get('total_credits')!=old.get('total_credits'):s.pop('total_credits',None)
    if i=='credit_cap':
        if re.search(r'\b(?:gpa|diem trung binh)(?: do| nay)? (?:la )?tich luy|\bcpa\b\b',n):s['gpa_kind']='cumulative'
        elif re.search(r'\b(?:gpa|diem trung binh)(?: hoc)? ky\b',n):s['gpa_kind']='semester'
        elif s.get('gpa_kind')!=old.get('gpa_kind'):s.pop('gpa_kind',None)
        if re.search(r'\b(?:ky phu|ky he|hoc he)\b',n):s['semester']='summer'
        elif re.search(r'\bky chinh\b',n):s['semester']='main'
        elif s.get('semester')!=old.get('semester'):s.pop('semester',None)
        if re.search(r'\b(?:khong|chua) (?:thuoc dien |bi )?buoc thoi hoc\b',n):s['not_dismissed']=True
        elif 'buoc thoi hoc' in n:s.pop('not_dismissed',None)
        elif s.get('not_dismissed')!=old.get('not_dismissed'):s.pop('not_dismissed',None)
        if re.search(r'\b(?:moi|tat ca)(?: cac)? (?:mon|hoc phan) (?:deu |deu duoc |duoc )?tinh tai\b',n):s['all_counted']=True
        elif re.search(r'\b(?:loai tru|khong tinh tai)\b',n):s['all_counted']=False
        elif s.get('all_counted')!=old.get('all_counted'):s.pop('all_counted',None)
        m=re.findall(r'\b(?:trung binh|binh quan)(?: theo ke hoach)?(?: la)?\s+(\d+)(?!\d|[.,]\d)\s*(?:tc|tin chi)\b',plain)
        if len(set(m))==1:s['standard_credits']=int(m[0])
        elif len(set(m))>1 or s.get('standard_credits')!=old.get('standard_credits'):s.pop('standard_credits',None)
        gp=re.findall(r'\b(?:gpa|diem trung binh)(?: (?:hoc )?ky(?: truoc| nay| vua roi)?| tich luy)?(?: la)?\s+(\d+(?:[.,]\d+)?)(?!\d|[.,]\d)',plain)
        if len(set(gp))==1:
            val=float(gp[0].replace(',','.'))
            if not 0<=val<=4:raise ValueError('GPA outside scale')
            s['gpa']=val
        elif len(set(gp))>1 or s.get('gpa')!=old.get('gpa'):s.pop('gpa',None)
    if i in PROFILE:
        m=[]
        for name,pat in [('debt',r'\b(?:tin chi|tc)(?: con)? no\b|\bno (?:bao nhieu|may|nhieu)\b'),('earned_credits',r'\b(?:tin chi|tc)(?: da)? tich luy\b|\btich luy (?:duoc )?(?:bao nhieu|may) (?:tin chi|tc)\b'),('cumulative_gpa',r'\b(?:gpa|diem trung binh) tich luy\b|\bcpa\b'),('semester_gpa',r'\b(?:gpa|diem trung binh)(?: hoc)? ky\b')]:
            if re.search(pat,n):m.append(name)
        if len(m)==1:s['metric']=m[0]
        elif len(m)>1:raise ValueError('ambiguous metric')
        elif (prior or {}).get('intent') in PROFILE and (prior or {}).get('slots',{}).get('metric'):s['metric']=prior['slots']['metric']
        else:s.pop('metric',None)
    if i=='retake_plan':
        budget=re.findall(r'\b(?:moi dot(?: khong vuot(?: qua)?| khong qua| toi da| chi)?|muc|gioi han|doi thanh|doi sang)\s+(\d+)(?!\d|[.,]\d)\s*(?:tc|tin chi)\b|\b(\d+)(?!\d|[.,]\d)\s*(?:tc|tin chi)\s+moi dot\b',plain)
        amounts={int(a or b) for a,b in budget}
        if len(amounts)==1:s['budget']=amounts.pop()
        elif len(amounts)>1 or s.get('budget')!=old.get('budget'):s.pop('budget',None)
        codes=set(re.findall(r'\b[A-Z]{3}\d{4}\b',q.upper()))
        if 'first_course' in old and re.search(r'\b(?:bo|khong can|khong yeu cau)\b',n) and re.search(r'\b(?:uu tien|rang buoc|yeu cau)\b',n) and re.search(r'\b(?:mon do|mon nay|mon ay|dot dau|luot dau|dot thu nhat)\b',n):s.pop('first_course',None)
        elif re.search(r'\b(?:dot dau|luot dau|dot thu nhat)\b',n):
            if re.search(r'\b(?:khong can|bo|khong yeu cau)\b',n):s.pop('first_course',None)
            elif len(codes)==1:s['first_course']=codes.pop()
            else:raise ValueError('unclear first-course constraint')
        elif 'first_course' in old:s['first_course']=old['first_course']
        elif 'first_course' in s:raise ValueError('ungrounded first-course constraint')
    if i=='calendar':
        periods={(int(a),int(b)) for a,b in re.findall(r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b',q)}
        if len(periods)>1 or any(b!=a+1 for a,b in periods):raise ValueError('ambiguous academic period')
        if periods:
            a,b=periods.pop();s['academic_year']=f'{a}-{b}'
        elif old.get('academic_year'):s['academic_year']=old['academic_year']
        else:s.pop('academic_year',None)
        from calendar_source import SEM
        terms=[k for k,pat in SEM.items() if re.search(pat,n)]
        if len(terms)>1:raise ValueError('ambiguous semester')
        if terms:s['semester']=terms[0]
        elif old.get('semester'):s['semester']=old['semester']
        else:s.pop('semester',None)
    if i in ('admissions','tuition'):
        if i=='tuition':
            scopes=tuition_scopes(n)
            if len(scopes)==1 and not re.search(r'\b(?:khong phai|thay vi) (?:ctdt|chuong trinh|he)\b',n):s['tuition_scope']=scopes[0]
            elif scopes or s.get('tuition_scope')!=old.get('tuition_scope'):s.pop('tuition_scope',None)
            periods={(int(a),int(b)) for a,b in re.findall(r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b',q)}
            if len(periods)>1 or any(b!=a+1 for a,b in periods):raise ValueError('ambiguous academic period')
            if periods:
                a,b=periods.pop();s['academic_year']=f'{a}-{b}'
            elif old.get('academic_year') and not re.search(r'\bnam hoc\b',n):s['academic_year']=old['academic_year']
        if 'program' in s and old.get('program')!=s['program'] and f" {norm(s['program'])} " not in f' {n} ':raise ValueError('ungrounded program')
        if 'academic_year' in s and old.get('academic_year')!=s['academic_year'] and norm(s['academic_year']) not in n:raise ValueError('ungrounded academic period')
        if i=='admissions':
            methods=admission_methods(n)
            if len(methods)>1 or 'OTHER' in methods:raise ValueError('ambiguous or unsupported admission method')
            if methods:s['method']=next(iter(methods))
            elif old.get('method'):s['method']=old['method']
            else:s.pop('method',None)
            years=set(map(int,re.findall(r'\b20\d{2}\b',n)))
            if len(years)>1:raise ValueError('ambiguous admission year')
            if years:s['year']=next(iter(years))
            elif old.get('year'):s['year']=old['year']
            else:s.pop('year',None)
    return p

def fast_delta(question,old):
    """Only complete, unambiguous single-field edits. Other inputs go to the planner.
    Do not treat a quoted value, multi-field request or a new entity as an edit.
    """
    if not old:return None
    n=norm(question); i=old.get('intent'); slots=old.get('slots',{})
    if i=='rank_check':
        m=re.fullmatch(r'(?:neu |con |doi |sua |doi hang du kien thanh |hang du kien la )?(?:(?:em|ban|sinh vien) (?:do|ay) )?(?:chi )?(?:du kien )?(?:bang|hang|loai|tot nghiep loai) (xuat sac|gioi|kha|trung binh)(?: thi sao| the nao| con lai khong thay doi| giu nguyen cac dieu kien khac)?',n)
        if m and slots.get('cohort') and 'total_credits' in slots and 'repeat_credits' in slots:
            return {'intent':i,'reuse':True,'slots':{'rank':{'xuat sac':'excellent','gioi':'good','kha':'fair','trung binh':'average'}[m[1]]}}
        m=re.fullmatch(r'(?:neu |dinh chinh |sua lai |so phai )?(?:thuc te |thuc ra |chi |phai )*(?:hoc lai)(?: thuc ra| la| chi| thuc ra la)* (\d{1,3}) (?:tin chi|tc)(?: thoi| thi ket luan thay doi the nao| thi sao| giu nguyen dieu kien| cac dieu kien khac giu nguyen| nhung dieu kien kia giu nguyen)?',n)
        if m and slots.get('total_credits') and slots.get('rank') and slots.get('cohort'):
            return {'intent':i,'reuse':True,'slots':{'repeat_credits':int(m[1])}}
    if i=='credit_cap':
        m=re.fullmatch(r'(?:(?:co )?sua lai |dinh chinh |doi )?(?:tai chuan |ke hoach chuan )?trung binh(?: la)? (\d{1,2}) (?:tin chi|tc)(?: nhung dieu kien khac giu nguyen| cac dieu kien khac giu nguyen| giu nguyen dieu kien| thi sao)?',n)
        if m and all(k in slots for k in ('cohort','semester','gpa','gpa_kind','not_dismissed','all_counted')):
            return {'intent':i,'reuse':True,'slots':{'standard_credits':int(m[1])}}
    # A reference-only comparison may reuse the original metric, not a new metric.
    if i=='student_lookup' and slots.get('student') and slots.get('metric'):
        m=re.fullmatch(r'(?:so voi|doi chieu voi) (?:ma(?: gia)? )?(\d{8})(?: thi sao| the nao| thi ban nao no nhieu hon chenh bao nhieu| ai no nhieu hon)?',n)
        if m and m[1]!=slots['student'] and ('no nhieu hon' not in n or slots['metric']=='debt'):
            return {'intent':'student_compare','reuse':True,'slots':{'other_student':m[1]}}
    return None


def structured_input(q,old,root):
    """Narrow, source-backed typed parsing. Return None for ambiguous/multi-goal text."""
    n=norm(q); i=(old or {}).get('intent'); prev=(old or {}).get('slots',{})
    def raw(intent,reuse=False,**slots):return {'intent':intent,'reuse':reuse,'slots':slots}
    if re.search(r'\b(?:hutech|ulis|uit|bach khoa|thac si|tien si|5115|3079|thong tu|nghi dinh|tam khoa|chua duyet|ngoai le)\b',n):return None
    if i=='rank_check' and re.search(r'\b(?:sinh vien khac|em khac|ban khac)\b',n) and cohort(n):
        return raw('rank_check',cohort=cohort(n))
    if i=='rank_check' and re.fullmatch(r'(?:neu )?(?:phai )?hoc lai (?:them|bot|giam) (?:mot|hai|ba|\d{1,3}) (?:tin chi|tc)(?: nua)?(?: cac dieu kien con lai giu nguyen| cac dieu kien khac giu nguyen| thi sao| giu nguyen dieu kien)?',n):
        return raw(i,True)
    if i=='credit_cap' and re.search(r'\bcpa\b|\bgpa tich luy\b',n) and re.search(r'\b(?:chu khong phai|khong phai|dinh chinh)\b',n):return raw(i,True)
    if i in PROFILE and re.search(r'\b(?:ban|sinh vien) thu hai\b',n) and i=='student_compare' and prev.get('other_student') and re.search(r'\b(?:cpa|gpa tich luy)\b',n):
        return raw('student_lookup',True,student=prev['other_student'],metric='cumulative_gpa')
    if i=='counseling' and prev.get('student') and re.search(r'\b(?:soan|viet)\b',n) and re.search(r'\b(?:loi moi|moi trao doi)\b',n) and re.search(r'\b(?:ban nay|ban ay|em nay|em ay)\b',n) and 'email' in n and not re.search(r'\b(?:ca lop|cong khai|sinh vien khac)\b',n):
        return raw('draft',True,student=prev['student'],audience='private',format='email',draft_purpose='invite')
    if i=='draft' and re.fullmatch(r'(?:phan than|phan noi dung|noi dung) (?:toi da|chi|con) \d{1,3} tu giu (?:nguyen )?tieu de',n):return raw(i,True)
    if fee_anchor(n) and not re.search(r'\b(?:hoc bong|mien|giam|gia han|nop|so sanh|chenh lech|tang|du kien|du doan|bang kep|quoc tich|nuoc ngoai|thac si|tien si|khong phai|thay vi|thu tuc|rut hoc phan|tinh hoc phi|dong khi nao|lop khac|ho so)\b',n):
        y=fee_year(q); cy=cohort(n); scopes=tuition_scopes(n)
        if y and cy and 2018<=cy<=int(y[:4]) and len(scopes)==1 and not re.search(r'\b(?:clc|chat luong cao)\b',n):
            return raw('tuition',False,cohort=cy,academic_year=y,tuition_scope=scopes[0])
    if i=='tuition' and prev.get('cohort') and prev.get('tuition_scope') and re.fullmatch(r'(?:sang|con|doi sang|chuyen sang) nam hoc 20\d{2} 20\d{2}(?: thi sao)?(?: van (?:khoa va ctdt do|khoa va chuong trinh do|cung khoa)| (?:van )?giu nguyen khoa va (?:ctdt|chuong trinh))?',n) and fee_year(q):
        return raw(i,True,academic_year=fee_year(q))
    if i=='tuition' and prev.get('cohort') and re.search(r'\b(?:tan sinh vien|khoa moi)\b',n) and re.search(r'\b(?:co phai|co duoc|ap muc|dung muc)\b',n) and re.search(r'\b(?:chinh khoa|khoa cu|khoa nay)\b',n):
        periods=re.findall(r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b',q)
        if len(periods)==1 and int(periods[0][1])==int(periods[0][0])+1:return raw(i,True,academic_year='-'.join(periods[0]))
    ids=re.findall(r'\b\d{8}\b',q)
    if not old and len(ids)==1 and re.fullmatch(r'(?:lap|xay dung|de xuat) (?:phuong an|lo trinh|ke hoach) hoc lai(?: gia dinh)? cho (?:sinh vien|mssv)(?: demo)? \d{8} moi dot (?:khong qua|khong vuot(?: qua)?|toi da) \d{1,2} (?:tin chi|tc)(?: ton trong tien quyet| dam bao tien quyet)?(?: neu phan chua du can cu)?',n):
        p=guard({'intent':'retake_plan','slots':{'student':ids[0]}},q,None)
        if p['slots'].get('budget'):return raw('retake_plan',**p['slots'])
    if not old and len(ids)==1 and re.search(r'\b(?:bao nhieu|chi tra loi|lay rieng|tra dung|lay dung|cho biet)\b',n) and not re.search(r'\b(?:lo trinh|ke hoach|tu van|hoc lai|thong bao|email|so sanh|doi chieu|hoc bong|canh bao|va)\b',n):
        p=guard({'intent':'student_lookup','slots':{'student':ids[0]}},q,None)
        if p['slots'].get('metric'):return raw('student_lookup',**p['slots'])
    if i=='student_lookup' and prev.get('student') and prev.get('metric') and len(ids)==1 and ids[0]!=prev['student'] and re.fullmatch(r'(?:doi chieu|so sanh) (?:cung chi so|chi so do|chi so nay) voi (?:ma )?\d{8}',n):return raw('student_compare',True,other_student=ids[0])
    # A request for a source or scale is not a second academic task.
    # Resolve only a unique exact source-row name/code and an explicit year.
    if re.search(r'\b(?:diem chuan|diem trung tuyen)\b',n) and not re.search(r'\b(?:so sanh|du doan|cao nhat|thap nhat|chenh lech|hoc phi|hoc bong|viet email|nguong|diem san|khong phai|thay vi|ngoai le|tieu chi phu|cach tinh|xet tuyen thang|phuong thuc khac|ielts|toefl|act|a level|danh gia nang luc)\b',n):
        years=set(map(int,re.findall(r'\b20\d{2}\b',n)));methods=[m for m in ('THPT','HSA','SAT') if re.search(r'\b'+m.lower()+r'\b',n)]
        if len(years)==1 and len(methods)<=1:
            y=next(iter(years))
            try:rows,_,_=parse(root,y)
            except (OSError,ValueError,KeyError):return None
            explicit=set(re.findall(r'\bcn\d+\b',n)); names=[(code,name) for code,(name,_,_) in rows.items() if ' '+norm(name)+' ' in ' '+n+' ']
            # Remove contained names only; unrelated programs remain ambiguous.
            names=[(c,v) for c,v in names if not any(c!=d and ' '+norm(v)+' ' in ' '+norm(w)+' ' and len(norm(w))>len(norm(v)) for d,w in names)]
            chosen=None
            if len(explicit)==1:
                code=next(iter(explicit)).upper()
                if code in rows and (not names or {c for c,_ in names}=={code}):chosen=code
            elif not explicit and len(names)==1:chosen=names[0][1]
            if chosen:
                tail=' '+n+' '
                for _,name in names:tail=tail.replace(' '+norm(name)+' ',' ')
                # Conjunctions outside names may only introduce provenance/scale, not another target.
                if not re.search(r'\bva\b(?! (?:nguon|thang diem|can cu|duong dan|link)\b)',tail):
                    return raw('admissions',year=y,program=chosen,**({'method':methods[0]} if methods else {}))
    if i=='calendar' and prev.get('academic_year') and prev.get('semester'):
        from calendar_source import SEM
        # A bounded continuation only; do not treat deadline/teaching-date queries as intervals.
        m=re.fullmatch(r'(?:con|sang|doi sang|chuyen sang) (?:((?:hoc )?ky(?: chinh)? (?:1|2|i|ii|thu nhat|thu hai|phu|he))(?: (?:nam hoc )?(20\d{2} 20\d{2}))?|(?:nam hoc )?(20\d{2} 20\d{2}))(?: thi sao)?',n)
        if m:
            terms=[k for k,pat in SEM.items() if m[1] and re.search(pat,m[1])]
            period=fee_year(q)
            if (not m[1] or len(terms)==1) and (not (m[2] or m[3]) or period):
                return raw(i,True,**({'semester':terms[0]} if terms else {}),**({'academic_year':period} if period else {}))
    if i=='admissions' and prev.get('program') and prev.get('year'):
        m=re.fullmatch(r'(?:con|doi sang|chuyen sang|the) (?:phuong thuc )?(thpt|hsa|sat|dgnl|danh gia nang luc)(?: nam (20\d{2}))?(?: thi sao| van nganh va nam ay| giu nguyen nganh va nam)?',n)
        if m:
            return raw(i,True,method='HSA' if m[1] in ('dgnl','danh gia nang luc') else m[1].upper(),**({'year':int(m[2])} if m[2] else {}))
        if re.fullmatch(r'(?:doi|chuyen) sang (?:phuong thuc )?(thpt|hsa|sat)(?: van nganh va nam ay| giu nguyen nganh va nam| thi sao)?',n):
            return raw(i,True,method=re.search(r'\b(thpt|hsa|sat)\b',n)[1].upper())
        m=re.fullmatch(r'(?:con|doi sang|chuyen sang|nam) (?:nam )?(20\d{2})(?: (?:cung|van) nganh va phuong thuc| (?:cung|van) nganh| thi sao)?',n)
        if m:return raw(i,True,year=int(m[1]))
    if not old and re.search(r'\b(?:hang|bang|loai tot nghiep)\b',n) and 'hoc lai' in n and cohort(n) and not re.search(r'\b(?:dong thoi|sau do|hoc phi|hoc bong|viet email|lap lich|so sanh)\b',n):
        p=guard({'intent':'rank_check','slots':{}},q,None)
        if all(k in p['slots'] for k in ('cohort','rank','total_credits','repeat_credits','discipline')):return raw('rank_check',**p['slots'])
    if not old and re.search(r'\b(?:gpa|diem trung binh)\b',n) and re.search(r'\b(?:tran|muc toi da|toi da|gioi han)\b',n) and cohort(n) and not re.search(r'\b(?:dong thoi|sau do|hoc phi|hoc bong|viet email|lap lich|so sanh)\b',n):
        p=guard({'intent':'credit_cap','slots':{}},q,None)
        if all(k in p['slots'] for k in ('cohort','gpa','gpa_kind','semester','standard_credits','not_dismissed','all_counted')):return raw('credit_cap',**p['slots'])
    if re.search(r'\b(?:bat dau|ket thuc|ngay nao|khi nao)\b',n) and not re.search(r'\b(?:dang ky|rut|thi|nop|hoc bong)\b',n) and ('chuyen mon' not in n or re.search(r'\b(?:moc ke hoach|phan biet|hay ngay hoc chuyen mon)\b',n)):
        p=guard({'intent':'calendar','slots':{}},q,None)
        if p['slots'].get('academic_year') and p['slots'].get('semester'):return raw('calendar',**p['slots'])
    return None

def source_table(root, v):
    # Same fail-closed publication-hold gate used by the legacy direct table route.
    if not v:return None
    rows=[json.loads(x) for x in (Path(root)/'data/versioning/publication_holds.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    for h in rows:
        doc=str(h.get('doc_id','')); names=[str(h.get(k,'')) for k in ('source_path','content_path')]
        if h.get('content_sha256') in (v['sha256'],v.get('normalized_sha256',v['sha256'])) or v['path'] in names or (str(v['year']) in doc and (('diem-trung-tuyen' in doc and v.get('table_kind','admissions')=='admissions') or Path(v['path']).stem.lower().replace('_','-') in doc)):raise ValueError('source held')
    r=response(v['answer'],'semantic_source_table',['policy_reference'],[{'source_path':v['path'],'sha256':v['sha256']}]);r['metadata'].update(engine_mode='SOURCE_TABLE',source_path=v['path'],sha256=v['sha256'],effective_year=v['year'],source_label='Bảng nguồn cục bộ đã đối chiếu SHA-256',source_type='source_table',doc_title=Path(v['path']).name,source_url=v.get('source_url'));
    if v.get('doc_id'):r['metadata']['cited_doc_ids']=[v['doc_id']]
    return r

def execute(p,roster,root,question=''):
    i=p['intent'];s=p['slots'];
    if i in ('draft','counseling'):
        from semantic_communication import execute as communicate
        return communicate(p,roster)
    if i=='clarify':return clarification('Dạ cô, em chưa xác định được đối tượng hoặc dữ kiện cần thiết. Cô nêu rõ nội dung cần tra giúp em.')
    if i=='class_scope':return clarification('Dạ cô, không dùng số liệu lớp đang mở để thay thế lớp chưa có hồ sơ. Cần nạp đúng hồ sơ; có thể dùng mẫu tư vấn chung không chứa số liệu.')
    if i in PROFILE:
        ids=[s.get('student')]+([s.get('other_student')] if i=='student_compare' else [])
        if None in ids or len(set(ids))!=len(ids):return clarification('Dạ cô, cần xác định đúng mã sinh viên trước khi tra cứu hoặc so sánh.')
        if s.get('metric')=='cumulative_gpa':return clarification('Dạ cô, hồ sơ hiện tại chưa xác nhận CPA độc lập. Em không dùng GPA học kỳ thay cho CPA.')
        if s.get('metric') not in FIELDS:return clarification('Dạ cô, cần xác định chỉ số muốn tra: tín chỉ nợ, tín chỉ tích lũy hay GPA học kỳ.')
        field,label,upper=FIELDS[s['metric']]; students=[find_student(roster,x) for x in ids]
        if any(st is None for st in students):return clarification('Dạ cô, chưa tìm thấy đầy đủ sinh viên trong hồ sơ lớp hiện tại.')
        values=[valid(st.get(field),0,upper) for st in students]
        if any(v is None for v in values):return clarification('Dạ cô, hồ sơ chưa có đầy đủ chỉ số được yêu cầu.')
        a='; '.join(f'{sid}: {v:g} {label}' for sid,v in zip(ids,values))+'.'
        if len(values)==2:
            a+= ' Hai giá trị bằng nhau.' if values[0]==values[1] else f' {ids[values.index(max(values))]} cao hơn {abs(values[0]-values[1]):g}.'
        a+=' Theo hồ sơ '+str(roster.get('class_short',''))+', '+str(roster.get('semester','kỳ chưa rõ'))+'.'
        return response(a,i,['scope_check','student_signals'],category='STUDENT_STATUS',sid=ids[0])
    if i=='retake_plan':
        from workflow import debt_rows
        from course_planning import load_candidate,make_plan,REL,SHA,candidate_source,candidate_label
        st=find_student(roster,s.get('student'));cap=s.get('budget')
        if st is None or type(cap) is not int or not 1<=cap<=30:return clarification('Dạ cô, cần đúng hồ sơ sinh viên và mức tín chỉ nguyên mỗi đợt từ 1 đến 30.')
        table,why=load_candidate(root,roster)
        if not table:return clarification('Dạ cô, chưa xếp được lịch có tiên quyết vì '+str(why)+'.')
        rows,amb,unknown=debt_rows(st,roster.get('courses') or [])
        try:stages,excluded=make_plan(rows,table,st.get('bang_diem') or [],cap,first_course=s.get('first_course'))
        except ValueError:return clarification('Dạ cô, chưa chứng minh được lịch có môn yêu cầu ở đợt đầu dưới giới hạn hiện tại; có thể do tiên quyết, môn không xếp được hoặc quy mô bài toán. Em không tự bỏ ràng buộc.')
        k=sum(map(len,stages));total=sum(r[2] for b in stages for r in b)
        lines=[f'Dạ cô, {s["student"]}: {len(stages)} đợt cho {k} môn ({total} tín chỉ), mỗi đợt tối đa {cap} tín chỉ.']+[f'Đợt {idx}: '+', '.join(r[0] for r in b)+f' ({sum(r[2] for r in b)} TC).' for idx,b in enumerate(stages,1)]
        if s.get('first_course'):lines.append('Giữ ràng buộc '+s['first_course']+' ở đợt đầu.')
        if k:lines.append('Tối thiểu trên tập môn xếp được với các ràng buộc đã xác định.' if k<=12 else 'Phương án khả thi; chưa chứng minh tối ưu.')
        if excluded or amb or unknown:lines.append('Chưa xếp/đối chiếu: '+'; '.join([f'{c}: {v}' for c,v in sorted(excluded.items())]+amb+unknown)+'.')
        lines.append(f'Bảng {candidate_label(table)}; đây là đợt giả định, chưa xác nhận lịch mở lớp, môn mới hoặc giới hạn đăng ký chính thức.')
        return response('\n'.join(lines),'retake_plan',['scope_check','course_history','prerequisite_planning','credit_scenarios'],[candidate_source(table)],'STUDENT_STATUS',s['student'])
    if i in ('rank_check','credit_cap'):
        if s.get('cohort') not in (2022,2023,2024,2025):return clarification('Dạ cô, cần xác minh quy chế đúng khóa tuyển sinh trước khi áp dụng; em không suy diễn từ khóa khác.')
        if i=='rank_check':
            c=pinned(root,'Hạ hạng tốt nghiệp do học lại?')
            if not c or not all(x in norm(c['answer']) for x in ('vuot qua 5','xuat sac','gioi','canh cao')):return clarification('Dạ cô, chưa có điều khoản đủ căn cứ về hạ hạng tốt nghiệp.')
            if s.get('rank') not in ('excellent','good','fair','average'):return clarification('Dạ cô, cần hạng tốt nghiệp dự kiến để áp dụng điều kiện.')
            t=s.get('total_credits');r=s.get('repeat_credits');d=s.get('discipline')
            if type(t) is not int or type(r) is not int or not 0<=r<=t or not 1<=t<=1000:return clarification('Dạ cô, cần tổng tín chỉ chương trình và số tín chỉ phải học lại hợp lệ.')
            hit=100*r>5*t; a=f'Dạ cô, {r}/{t} tín chỉ = {100*r/t:.2f}%, '+('vượt' if hit else 'không vượt')+' ngưỡng 5%. '
            if s['rank'] in ('fair','average'):a+='Điều kiện hạ một hạng tại khoản này chỉ áp dụng hạng Giỏi hoặc Xuất sắc, không áp dụng hạng dự kiến đang xét.'
            elif hit:a+='Riêng tiêu chí học lại đã thỏa điều kiện hạ một hạng nếu hạng cuối cùng là Giỏi hoặc Xuất sắc.'
            elif d is True:a+='Tiêu chí học lại không thỏa, nhưng dữ kiện kỷ luật từ cảnh cáo trở lên có thể làm thỏa điều kiện.'
            elif d is False:a+='Theo hai dữ kiện giả định này, chưa thỏa điều kiện hạ hạng tại khoản này.'
            else:a+='Chưa đủ thông tin về kỷ luật để kết luận cả hai tiêu chí.'
            return source_response(a+' Căn cứ đối chiếu: khoản 7 Điều 47 QĐ 3626/QĐ-ĐHQGHN; cần xác nhận đúng khóa, hiệu lực và hạng cuối cùng.','rank',c)
        c=pinned(root,'Giới hạn tín chỉ đăng ký học kỳ chính?')
        if not c or not all(x in norm(c['answer']) for x in ('duoi 2 00','khong qua 18 tin chi','3 2 khoi luong trung binh')):return clarification('Dạ cô, chưa có điều khoản đủ căn cứ để tính tải đăng ký.')
        if s.get('semester')=='summer':return source_response('Dạ cô, không áp dụng tự động giới hạn học kỳ chính cho kỳ phụ. Cần thông báo đúng kỳ.','load',c)
        if s.get('gpa_kind')!='semester' or 'gpa' not in s:return clarification('Dạ cô, cần GPA học kỳ; không dùng GPA tích lũy thay thế.')
        if s.get('semester') not in ('main','main_1','main_2') or s.get('not_dismissed') is not True or s.get('all_counted') is not True or not 1<=s.get('standard_credits',0)<=60:return clarification('Dạ cô, cần xác nhận học kỳ chính, tình trạng chưa bị buộc thôi học, tải chuẩn và các môn đều tính tải trước khi tính trần.')
        standard=s['standard_credits'];base=standard*3//2;cap=min(base,18) if s['gpa']<2 else base
        a=f'Dạ cô, 1,5 × {standard} = {standard*1.5:g} tín chỉ. '+(f'GPA kỳ {s["gpa"]:g} dưới 2,00, nên lấy min({base}, 18) = {cap} tín chỉ.' if s['gpa']<2 else f'GPA kỳ {s["gpa"]:g} không dưới 2,00; trần theo giả định tải chuẩn là {cap} tín chỉ nguyên.')
        return source_response(a+' Đây là trần theo giả định các giới hạn cùng áp dụng, không phải mức nên đăng ký. Căn cứ Điều 21, 23 QĐ 3626; đối chiếu đúng khóa và kỳ.','load',c)
    if i=='calendar':
        from calendar_source import lookup_start,inspect_uploaded_calendar
        period=s.get('academic_year');semester=s.get('semester')
        if not period or semester not in ('main_1','main_2','summer'):return clarification('Dạ cô, cần xác định năm học và học kỳ cụ thể.')
        if re.search(r'\b(?:lich thi|ngay thi|ky thi|dang ky|rut bot|nop)\b',norm(question)):return clarification('Dạ cô, nguồn khoảng học kỳ không xác định mốc thi, đăng ký hoặc thủ tục khác.')
        hits=lookup_start(root,period,semester)
        if re.search(r'\bket thuc\b',norm(question)):
            # Only interval headings have verified start and end; never infer an end date from a start-only row.
            from calendar_source import DATE
            hits=[h for h in hits if len(list(DATE.finditer(h['excerpt'])))==2 and 'khoảng thời gian học kỳ' in h['excerpt']]
            if not hits:return clarification('Dạ cô, chưa có khoảng thời gian học kỳ đã xác minh đủ cả hai mốc.')
        if not hits:
            diagnostic={k:v for k,v in inspect_uploaded_calendar(root,period,semester).items() if k!='hits'}
            r=clarification(f'Dạ cô, chưa tìm thấy nguồn đã xác minh ngày bắt đầu học kỳ trong năm học {period}. Em không dùng lịch tuyển sinh hoặc hạn đăng ký thay thế.')
            r['metadata']['calendar_pack_diagnostic']=diagnostic
            return r
        label={'main_1':'học kỳ chính thứ nhất','main_2':'học kỳ chính thứ hai','summer':'học kỳ phụ/hè'}[semester]
        lines=[f'Dạ cô, các mốc kế hoạch đối chiếu cho {label}, năm học {period}:']
        for h in hits:
            lines.append(f'• {h["excerpt"]} — {h["scope"] or h["source_path"]}.')
            if h.get('qualification'):lines.append(h['qualification'])
        lines.append('Đây là mốc theo kế hoạch nguồn, không phải xác nhận việc học đã diễn ra. Nếu khác phạm vi, cần đối chiếu thông báo của đơn vị ban hành.')
        r=response('\n'.join(lines),'semantic_calendar',['policy_reference'],hits);r['metadata'].update(engine_mode='SOURCE_TABLE',source_label='Bản kế hoạch đối chiếu PDF cục bộ' if hits[0].get('qualification') else 'Dòng lịch học đã duyệt',source_path=hits[0]['source_path'],source_url=hits[0]['source_url'],sha256=hits[0]['sha256'],cited_doc_ids=list(dict.fromkeys(h['doc_id'] for h in hits if h['doc_id'])));return r
    if i=='admissions':
        y=s.get('year');m=s.get('method');program=s.get('program')
        methods=admission_methods(norm(question))
        if methods and (len(methods)!=1 or 'OTHER' in methods or next(iter(methods))!=m):return clarification('Dạ cô, chưa xác minh được đúng phương thức xét tuyển; không dùng điểm phương thức khác thay thế.')
        if not y or not program:return clarification('Dạ cô, cần xác định ngành và năm tuyển sinh trước khi tra điểm chuẩn.')
        if m not in (None,'THPT') or (m=='THPT' and y>=2025):return clarification('Dạ cô, chưa có bảng nguồn xác minh riêng đúng phương thức này và năm được hỏi. Không dùng điểm quy đổi hay phương thức khác thay thế.')
        v=lookup(root,f'Điểm chuẩn UET ngành {program} năm {y}')
        if v:
            v['source_url']={2024:'https://uet.vnu.edu.vn/diem-trung-tuyen-vao-truong-dh-cong-nghe-dhqghn-nam-2024-theo-phuong-thuc-thpt/',2025:'https://uet.vnu.edu.vn/truong-dai-hoc-cong-nghe-cong-bo-diem-chuan-dai-hoc-chinh-quy-nam-2025/'}.get(y)
        return source_table(root,v) or clarification('Dạ cô, chưa có dòng điểm chuẩn đúng ngành và năm trong bảng nguồn được kiểm tra.')
    if i=='tuition':
        from tuition import lookup_tuition,lookup_units
        n=norm(question); c=s.get('cohort'); y=s.get('academic_year'); program=s.get('program','')
        scopes=[{'standard':'chương trình chuẩn','dm':'ĐMKTKT','tt23':'Thông tư 23'}[v] for v in tuition_scopes(n)]
        if not scopes and s.get('tuition_scope') in ('standard','dm','tt23'):scopes=[{'standard':'chương trình chuẩn','dm':'ĐMKTKT','tt23':'Thông tư 23'}[s['tuition_scope']]]
        if c and y and re.search(r'\b(?:tan sinh vien|khoa moi)\b',n) and re.search(r'\b(?:co phai|co duoc|dung muc|ap muc)\b',n):
            v=lookup_units(root,int(y[:4]),c)
            if v:return source_table(root,v)
            return clarification('Dạ cô, không tự dùng định mức của tân sinh viên khóa mới. Cần đối chiếu dòng của khóa đang học trong văn bản đúng năm thu phí.')
        if y=='2022-2023':
            from tuition_history import adjusted_standard
            if scopes==['chương trình chuẩn']:
                v=adjusted_standard(root,c,question)
                if v:return source_table(root,v)
            return clarification('Dạ cô, mức ban đầu năm 2022–2023 đã có điều chỉnh. Chưa đủ căn cứ xác định đúng phạm vi chương trình hoặc mốc lịch sử được hỏi; em không dùng mức cũ thay thế.')
        if y=='2023-2024':
            return clarification('Dạ cô, nguồn hiện có là định mức dự kiến tạm thu công bố 07/11/2023. Có quyết định chính thức 279/QĐ-ĐHCN ngày 17/02/2024 nhưng chưa có bản gốc để xác định định mức cuối cùng; em không dùng mức tạm thu thay thế. Nguồn: https://uet.edu.vn/dieu-chinh-bo-sung-hp-trong-nam-hoc-2023-2024/')
        if c and y and len(scopes)==1:
            v=lookup_tuition(root,f'Học phí {scopes[0]} ngành {program} QH-{c} năm học {y}')
            if v:return source_table(root,v)
        # Asking about units does not require a unique fee amount. Use only headers
        # from the pinned undergraduate source; do not assume a collection schedule.
        unit_query=bool(re.search(r'\b(?:don vi|tinh theo|theo nam|theo ky|theo thang|nam ky hay thang)\b',n))
        if c and (unit_query or y) and not scopes:
            yr=int(y[:4]) if y else c
            v=lookup_units(root,yr,c,example=not y)
            if v:return source_table(root,v)
        missing=[]
        if not c:missing.append('khóa tuyển sinh')
        if not y:missing.append('năm học thu phí')
        if len(scopes)!=1:missing.append('loại chương trình (chuẩn, CLC hoặc ĐMKTKT)')
        return clarification('Dạ cô, khóa tuyển sinh và năm thu học phí là hai thông tin khác nhau; không tự áp mức tân sinh viên khóa mới. '+('Cần xác định thêm '+', '.join(missing)+'. ' if missing else '')+'Em chưa có dòng định mức đủ căn cứ để nêu số tiền.')
    return clarification('Dạ cô, nhiệm vụ này chưa có đường thực thi ngữ nghĩa đã kiểm chứng. Em chưa sử dụng số liệu hay suy diễn kết quả.')

def route(question,prior,explicit,classified,roster,root):
    if not candidate(question,prior) and not re.search(r'\b(?:rut (?:bot )?hoc phan|rut mon hoc)\b',norm(question)):return None
    started=time.monotonic(); attempted=False; stage='routing'; n=norm(question); old=prior.get('plan') if prior.get('kind')=='semantic_task' else None
    sig=snapshot(roster)
    def out(r,state=None):
        r['metadata'].update(semantic_planner_model=MODEL if attempted else None,semantic_pilot=True,semantic_elapsed_ms=round((time.monotonic()-started)*1000,2));return r,state or {}
    if re.search(r'\b(?:hutech|ulis|uit|bach khoa|thac si|tien si|5115|3079|thong tu|nghi dinh|tam khoa|chua duyet)\b',n):return None if not old else out(clarification('Dạ cô, cần đối chiếu nguồn riêng cho phạm vi mới; em không dùng kết quả trước.'))
    if old and prior.get('scope')!=sig:return out(clarification('Dạ cô, hồ sơ đã thay đổi. Cần xác định lại đối tượng và dữ kiện.'))
    if re.search(r'\b(?:lop khac|lop moi|lop chua)\b',n) or (re.search(r'\blop\b',n) and scope_error(n,roster)):
        return out(execute({'intent':'class_scope','slots':{}},roster,root))
    if historical_reference(n,old):
        from tuition_history import adjusted_standard, PIN
        if prior.get('verified_adjustment')!=PIN:
            return out(clarification('Dạ cô, phiên này chưa có mức điều chỉnh đã xác minh để đối chiếu. Cô hỏi lại định mức đúng khóa và năm học nhé.'))
        c=old['slots']['cohort']
        v=adjusted_standard(root,c,f'Học phí CTĐT chuẩn QH-{c} năm học 2022–2023 sau điều chỉnh')
        if v:
            v=dict(v,answer='Dạ cô, không. Mức vừa nêu là định mức sau điều chỉnh công bố ngày 12/04/2023, áp dụng cho năm học 2022–2023; không phải mức ban đầu. Muốn tra số tiền ban đầu cần đối chiếu văn bản gốc đúng khóa và chương trình.')
            try:return out(source_table(root,v),prior)
            except (OSError,ValueError,KeyError,TypeError):pass
        return out(clarification('Dạ cô, em chưa xác minh lại được nguồn điều chỉnh. Không dùng mức sau điều chỉnh thay cho mức ban đầu.'))
    if old and old.get('intent')=='tuition' and old.get('slots',{}).get('academic_year')=='2022-2023'  and re.search(r'\b(?:ban dau|truoc dieu chinh|truoc khi dieu chinh)\b',n) and re.search(r'\b(?:con so vua neu|muc vua neu|muc tren|muc da dieu chinh|muc ban dau|muc truoc dieu chinh)\b',n) and not re.search(r'\b(?:khoa khac|ctdt khac|nam hoc|thac si|tien si|thong tu|tt 23|nuoc ngoai)\b',n):
        return out(clarification('Dạ cô, không dùng mức điều chỉnh tháng 4/2023 thay cho mức ban đầu. Hai mức thuộc các phiên bản khác nhau. Muốn xác định mức ban đầu cần đối chiếu nguồn gốc đúng khóa, ngành và chương trình; bản lịch sử hiện chưa đủ điều kiện tra tự động.'),prior)
    if old and old.get('intent')=='retake_plan' and re.search(r'\bmo lop\b',n) and re.search(r'\b(?:chot|xac nhan|thuc te)\b',n):
        return out(clarification('Dạ cô, chưa thể chốt học kỳ thực tế khi chưa xác nhận lịch mở lớp. Cần lịch mở lớp, tiên quyết, lịch học và giới hạn đăng ký đúng kỳ; mọi lộ trình giả định chỉ là mô phỏng.'),prior)
    if old and old.get('intent')=='admissions' and re.search(r'\b(?:so sanh|doi chieu)\b',n) and not re.search(r'\b20\d{2}\b',n):
        return out(clarification('Dạ cô, chỉ so sánh trực tiếp khi đã xác minh cả hai giá trị có cùng phạm vi phương thức và thang điểm. Em chưa có đủ hai mức đã đối chiếu.'),prior)
    if re.search(r'\b(?:rut (?:bot )?hoc phan|rut mon hoc)\b',n):
        if re.search(r'\b(?:5115|3079|k71|khoa 2026|qh 2026|2020|2021|k65|k66|quy che cu|so sanh|quy che moi)\b',n):return out(clarification('Dạ cô, cần kiểm tra điều khoản rút học phần đúng phiên bản và khóa; em không áp dụng mặc định QĐ 3626.'))
        c=pinned(root,question)
        if c is None and re.search(r'\b3626\b',n):c=pinned(root,'Rút học phần theo QĐ 3626')
        if c:return out(source_response(c['answer'],'withdrawal',c))
        return out(clarification('Dạ cô, chưa tìm được điều khoản rút học phần đủ căn cứ; không dùng hạn của thủ tục khác thay thế.'))
    methods=admission_methods(n)
    admission_context=bool(re.search(r'\b(?:diem chuan|diem trung tuyen|nguong trung tuyen)\b',n) or (old and old.get('intent')=='admissions' and (re.search(r'\b(?:phuong thuc|xet tuyen)\b',n) or re.match(r'^(?:con|doi sang|chuyen sang|the)\b',n))))
    if admission_context and (len(methods)>1 or 'OTHER' in methods or (not methods and re.search(r'\b(?:phuong thuc khac|doi phuong thuc|chuyen phuong thuc)\b',n))):
        return out(clarification('Dạ cô, em chưa có nguồn đã xác minh đúng phương thức được hỏi. Không dùng điểm THPT hoặc phương thức khác thay thế.'))
    try:
        # Explicit selection is authoritative but cannot silently replace an explicit ID in the text.
        q=question
        if explicit and re.search(r'\b\d{8}\b',q) and str(explicit) not in re.findall(r'\b\d{8}\b',q):return out(clarification('Dạ cô, mã trong câu hỏi không khớp mã đang chọn. Cần xác nhận đối tượng.'))
        if explicit and re.fullmatch(r'\d{8}',str(explicit)) and not re.search(r'\b\d{8}\b',q):q+=' (MSSV được chọn: '+str(explicit)+')'
        stage='plan';raw=fast_delta(q,old)
        if raw is None:raw=structured_input(q,old,root)
        if raw is None:
            attempted=True;raw=infer(q,old)
        stage='validation';p,decision,_=checked_plan(raw,q,old)
        if p['intent'] not in ('draft','counseling'):p=guard(p,q,old if decision['reuse'] else None)
        if p['intent'] in ('draft','counseling'):
            from semantic_communication import guard as comm_guard
            p=comm_guard(p,q,old if decision['reuse'] else None)
            if scope_error(n,roster):return out(clarification('Dạ cô, cần xác định đúng lớp trước khi tiếp tục.'))
            if p['intent']=='draft' and p['slots'].get('audience')=='private' and explicit and str(explicit)!=p['slots'].get('student'):return out(clarification('Dạ cô, đối tượng lời mời chưa khớp hồ sơ được chọn.'))
        from semantic_communication import candidate as comm_candidate
        if comm_candidate(question) and p['intent'] not in ('draft','counseling','clarify'):
            return out(clarification('Dạ cô, em chưa xác định đúng nhiệm vụ trao đổi hoặc soạn thảo. Cô nêu rõ mục tiêu giúp em.'))
        if p['intent'] not in SUPPORTED:
            # Preserve existing behavior only for a new task, not ambiguous continuation of semantic state.
            return out(clarification('Dạ cô, em chưa xác định được cách tiếp tục nhiệm vụ này bằng công cụ đã kiểm chứng. Cô nêu lại yêu cầu đầy đủ giúp em.'))
        if p['intent']=='student_compare' and decision['reuse'] and old and old.get('intent') in PROFILE and p['slots'].get('student')!=old.get('slots',{}).get('student'):return out(clarification('Dạ cô, chưa xác định được đối tượng gốc cần so sánh.'))
        if p['intent'] in STUDENT and (scope_error(n,roster) or (explicit and str(explicit)!=p['slots'].get('student'))):return out(clarification('Dạ cô, cần chọn đúng hồ sơ lớp và sinh viên trước khi tra cứu.'))
        if admission_context and methods and p['intent']!='admissions':
            return out(clarification('Dạ cô, em chưa xác định được đúng ngành, năm và phương thức xét tuyển. Không dùng điểm của phương thức khác thay thế.'))
        stage='execution';r=execute(p,roster,root,question)
        if p['intent']=='admissions' and r['metadata'].get('engine_mode')=='SOURCE_TABLE' and not p['slots'].get('method') and p['slots'].get('year',9999)<=2024:
            p['slots']['method']='THPT' # scope from verified source table, not model inference
        # Only typed input parameters; never store roster values, generated prose, or raw chat transcript.
        state={'kind':'semantic_task','plan':p,'scope':sig} if p['intent'] not in ('class_scope','clarify') else {}
        if p['intent']=='tuition' and r['metadata'].get('engine_mode')=='SOURCE_TABLE':
            from tuition_history import PIN,REL
            if r['metadata'].get('sha256')==PIN and r['metadata'].get('source_path')==REL:state['verified_adjustment']=PIN
        return out(r,state)
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        r=clarification('Dạ cô, bộ phân tích ngữ nghĩa chưa xác minh được yêu cầu hoặc nguồn. Em chưa dùng kết quả không chắc chắn; cô nêu lại dữ kiện cần tra.');r['metadata']['semantic_rejection']={'stage':stage,'type':type(exc).__name__};return out(r)
