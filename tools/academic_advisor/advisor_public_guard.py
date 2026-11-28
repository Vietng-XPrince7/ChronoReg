"""Narrow public-document intent guard. No changes to personal-query filters."""
import re
from quality import norm

PRIVATE=re.compile(r'\b(?:cua toi|cua em|cua co|cua minh|cua ban|ban ay|em ay|ho so|mssv|ma sinh vien|\d{8}|lop|k\d{2}|qh|neu|gia su|so sanh|doi chieu|hieu luc|hien nay|ap dung|ngoai le|dac cach|du dieu kien|co duoc|5115|3079|truong khac|hutech|ulis|uit|bach khoa)\b')

def guard_kind(q):
    from reference_knowledge import safe_public
    n=norm(q)
    if not 5<=len(q)<=700 or PRIVATE.search(n):return None
    # Only remove the country phrase in an explicit generic doctoral/master question.
    if ('cong dan viet nam' in n and 'uet' in n and re.search(r'\b(?:thac si|tien si)\b',n) and re.search(r'\b(?:du tuyen|tuyen sinh)\b',n) and re.search(r'\b(?:ngoai ngu|tieng anh|chung chi)\b',n) and safe_public(n.replace('cong dan viet nam','cong dan'))):
        return 'pg'
    if re.search(r'\b(?:qd|quyet dinh)\s+3626\b',n) and 'nghi hoc tam thoi' in n and 'ly do ca nhan' in n and re.search(r'\b(?:cpa|diem trung binh chung tich luy|diem trung binh tich luy)\b',n) and re.search(r'\b(?:toi thieu|bao nhieu|muc diem)\b',n):
        if safe_public('quy che '+re.sub(r'\bcpa\b','diem trung binh tich luy',n)):return 'cpa'
    # Negative factual lookup, not predictions; keep existing historic route untouched.
    if 'uet' in n and re.search(r'\b(?:diem chuan|diem trung tuyen)\b',n) and re.search(r'\b(?:chinh thuc|da cong bo)\b',n):
        years=set(map(int,re.findall(r'\b20\d{2}\b',n)))
        check=re.sub(r'\bkhong (?:du bao|du doan)\b','',n)
        if len(years)==1 and next(iter(years))>2026 and safe_public(check) and not re.search(r'\b(?:du bao|du doan|hoc phi|hoc bong|thac si|tien si|tinh diem|co hoi|kha nang|bao nhieu diem de)\b',check):return 'outside'
    return None

def route(root,q,prior):
    if prior:return None
    kind=guard_kind(q)
    try:
        if kind=='pg':
            from advisor_public_sections import postgraduate_language
            return postgraduate_language(root,q)
        if kind=='cpa':
            from advisor_evidence import fresh_ledger,blocked_qd
            from regulation import TEXT,SOURCE_URL,read_articles,clause
            from quality_routes import source_response
            if blocked_qd(fresh_ledger(root)):return None
            articles,sha=read_articles(root);title,body=articles[36];t=clause(body,3)
            if not all(x in norm(t) for x in ('nghi hoc tam thoi','ly do ca nhan','diem trung binh chung tich luy')):return None
            # Confirm a single explicit threshold in point d, not a number elsewhere.
            m=re.search(r'(?im)^\s*\*{0,2}d\)\s*(.*?)(?=\n\s*\n|\Z)',t,re.S)
            if not m:return None
            line=' '.join(m[1].replace('**','').split())
            z=re.search(r'điểm trung bình chung tích lũy\s+t[ốổ]i thiểu\s+(\d+[,.]\d+)',line,re.I)
            if not z:return None
            v={'answer':t,'path':TEXT,'sha256':sha,'source_url':SOURCE_URL,'articles':[{'article':36,'clause':3}]}
            return source_response(f'Dạ cô, mức CPA tối thiểu ghi tại điểm d khoản 3 Điều 36 QĐ 3626 là **{z[1]}**.\n\n'+line+'\n\nĐây là nội dung văn bản được hỏi, chưa xác nhận hiệu lực hay điều kiện của hồ sơ cụ thể.','leave_cpa_reference',v),{'kind':'policy_clause','article':36,'clause':3,'instrument':'3626'}
        if kind=='outside':
            from quality_routes import response
            y=re.search(r'\b20\d{2}\b',q)[0]
            r=response(f'Dạ cô, kho bảng điểm trúng tuyển UET hiện chỉ có dữ liệu giai đoạn 2022–2026, chưa có bảng công bố năm {y}. Em không thể đưa ra điểm chuẩn chính thức cho năm đó.','admissions_outside_corpus',[],[])
            r.setdefault('metadata',{}).update(engine_mode='CONTEXT_CLARIFICATION',quality_qualified=False,reference_only=False)
            return r,{}
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError):return None
    return None
