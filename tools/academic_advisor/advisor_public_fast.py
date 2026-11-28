"""Fast public source paths, without inferring programme type or official eligibility."""
import re, json, hashlib
from pathlib import Path
from quality import norm,clean
from advisor_source_precision import family,programs,academic_year,public_result,src


def fee(root,q):
    from tuition import lookup_units,lookup_tuition
    from semantic_product import source_table,tuition_scopes
    from reference_knowledge import cohort_request
    n=norm(q);y=academic_year(re.sub(r'\bK\d{2}\b','',q,flags=re.I));c=cohort_request(q)
    if family(q)!='tuition' or re.search(r'\b(?:so sanh|tang bao nhieu|chenh lech|hoc bong|ngoai le|mien|giam|thac si|tien si|nuoc ngoai|hoc ky|ca ky|tong tien|nop|lich thu|ke hoach thu|ban dau|truoc dieu chinh|tt 23|thong tu 23|chat luong cao|clc|nhat ban|ap dung cho|co duoc|du kien)\b',n):return None
    if re.search(r'\b(?:tinh tong|tinh tien|tinh hoc phi|tinh so tien|tinh cho|tinh bao nhieu)\b',n):return None
    if y==2022 and c is None and not tuition_scopes(n) and re.search(r'\bdieu chinh\b',n) and 'dai hoc' in n:
        from tuition_history import adjusted_standard
        v=adjusted_standard(root,2022,'Học phí CTĐT chuẩn QH-2022 năm học 2022-2023 sau điều chỉnh')
        if not v:return None
        v=dict(v,answer=v['answer']+'\nĐây là ví dụ cho khóa QH-2022, chương trình chuẩn. Cần đối chiếu khóa và loại chương trình nếu hỏi trường hợp khác.')
        return source_table(root,v),{}
    # Preserve existing explicit-scope and conversational lookup paths.
    if y not in (2024,2025,2026) or c not in (2023,2024) or c>y or tuition_scopes(n):return None
    if re.search(r'\b(?:don vi|tinh theo|theo nam hay|theo thang hay)\b',n):
        v=lookup_units(root,y,c)
        return (source_table(root,v),{}) if v else None
    if re.search(r'\b(?:hoc lai|cai thien|bang kep|tu chon|thoi han|gia han|bao luu|ngoai chuong trinh|tieng anh|keo dai|tan sinh vien|khoa moi)\b',n):return None
    if len(programs(q))!=1:return None
    vals=[lookup_tuition(root,f'Học phí {scope} QH-{c} năm học {y}-{y+1}') for scope in ('chương trình chuẩn','ĐMKTKT')]
    if not all(vals):return None
    if len({(v['path'],v['sha256']) for v in vals})!=1:return None
    lines=[f'Dạ cô, bảng học phí năm học {y}–{y+1} cho khóa QH-{c} có các mức sau tùy loại chương trình. Chưa xác định được ngành được hỏi thuộc dòng nào:']
    for v in vals:
        # The existing pinned reader preserves both amount and unit.
        lines.append('\n'+v['answer'].split('Đây là định mức theo đơn vị')[0].strip())
    lines.append('\nCần xác định chương trình chuẩn hay ĐMKTKT (hoặc chương trình đặc thù khác nếu có) trước khi áp dụng. Định mức theo tháng trong bảng không phải lịch thu tiền hằng tháng; không tự quy đổi thành số phải nộp một kỳ.')
    return source_table(root,dict(vals[0],answer='\n'.join(lines))),{}


def team_outcomes(root,q):
    from advisor_evidence import fresh_ledger
    from reference_knowledge import cohort_request
    n=norm(q);wanted=programs(q);cy=cohort_request(q)
    if family(q)!='curriculum' or len(wanted)!=1 or cy is None or not re.search(r'\b(?:chuan dau ra|plo)\b',n):return None
    # A scoped overview, not a particular PLO, language requirement or evaluation.
    if re.search(r'\b(?:tieng anh|ngoai ngu|plo\s*\d+|so sanh|dieu kien|tot nghiep|clc|nhat ban|bao nhieu|tuong duong|ap dung|hieu luc|theo quyet dinh)\b',n):return None
    catalog=json.loads((Path(root)/'data/raw/uet/curricula/catalog.json').read_text(encoding='utf-8-sig'))
    excluded={x.get('doc_id') for x in catalog.get('owner_excluded_documents',[])};paths={x.get('source_path') for x in catalog.get('owner_excluded_documents',[])}
    records=[]
    for r in catalog.get('records',[]):
        if r.get('program_identifier') not in wanted or r.get('collection')!='team_original_uploads' or r.get('content_kind')!='learning_outcomes' or r.get('doc_id') in excluded or r.get('content_path') in paths:continue
        hint=r.get('cohort_hint_unverified') or '';ys=list(map(int,re.findall(r'20\d{2}',hint)))
        if (len(ys)==2 and ys[0]<=cy<=ys[1]) or (len(ys)==1 and 'onward' in hint and cy>=ys[0]):records.append(r)
    if len(records)!=1:return None
    r=records[0];rel=r['content_path'];root=Path(root).resolve();p=(root/rel).resolve();p.relative_to(root)
    raw=p.read_bytes();t=raw.decode('utf-8-sig');sha=hashlib.sha256(raw).hexdigest();canonical=hashlib.sha256(t.replace('\r\n','\n').encode()).hexdigest()
    if r['content_sha256'] not in (sha,canonical):return None
    if any(h.get('doc_id')==r['doc_id'] or h.get('content_sha256') in (sha,canonical) or rel in (h.get('source_path'),h.get('content_path')) for h in fresh_ledger(root)):return None
    # Parse only explicit PLO labels. Join a wrapped paragraph, stop at other sections.
    lines=[];active=False
    for line in t.splitlines():
        v=clean(line);nn=norm(v)
        if re.search(r'\b(?:vi tri viec lam|kha nang hoc tap|noi dung chuong trinh)\b',nn) and active:break
        if re.match(r'^\s*[-* ]*PLO\s*\d+\s*:',v,re.I):lines.append(v.lstrip('- '));active=True
        elif active and v and not line.lstrip().startswith(('#','|','-')) and not re.search(r'\b(?:chuan dau ra|muc tu chu|nguon)\b',nn) and len(lines[-1])<500 and not re.search(r'[.!?]$',lines[-1]):lines[-1]+=' '+v
    ids=[int(re.search(r'PLO\s*(\d+)',v,re.I)[1]) for v in lines]
    if not 3<=len(lines)<=25 or ids!=list(range(1,len(ids)+1)) or sum(map(len,lines))>4500:return None
    if any(re.search(r'\b(?:ignore previous|system prompt|bo qua chi dan|mssv|so cccd)\b',norm(v)) for v in lines):return None
    return public_result(f'bản chuẩn đầu ra lưu trữ của nhóm, có nhãn khóa QH-{cy}, ghi các yêu cầu sau:\n\n'+'\n'.join('- '+v for v in lines)+'\n\nPhạm vi khóa và ngành lấy theo metadata của bản lưu; chưa xác minh độc lập với văn bản chính thức. Chỉ dùng để tham khảo, không xác nhận điều kiện tốt nghiệp.',[src(rel,sha)],'curriculum_outcomes_reference')


def regulation(root,q):
    from advisor_evidence import fresh_ledger,blocked_qd
    from regulation import TEXT,SOURCE_URL,read_articles,clause
    from quality_routes import source_response
    n=norm(q)
    if not re.search(r'\b3626\b',n) or not re.search(r'\bnghi hoc tam thoi\b',n) or not re.search(r'\b(?:tro lai hoc|hoc tiep)\b',n):return None
    if re.search(r'\b(?:k\d{2}|qh|neu|hieu luc|hien nay|ap dung|so sanh|dieu kien cua|truong hop|bao nhieu|co duoc|quy che moi|5115|3079)\b',n):return None
    if blocked_qd(fresh_ledger(root)):return None
    articles,sha=read_articles(root);title,body=articles[36];t=clause(body,3)
    if not all(x in norm(t) for x in ('nghi hoc tam thoi','hoc tiep','2 tuan')):return None
    v={'answer':t,'path':TEXT,'sha256':sha,'source_url':SOURCE_URL,'articles':[{'article':36,'clause':3}]}
    return source_response('Dạ cô, theo khoản 3 Điều 36 QĐ 3626:\n\n'+t+'\n\nĐây là nội dung của văn bản được hỏi; cần kiểm tra hiệu lực và phạm vi áp dụng trước khi xử lý hồ sơ cụ thể.','leave_return_reference',v),{'kind':'policy_clause','article':36,'clause':3,'instrument':'3626'}


def route(root,q,prior):
    from reference_knowledge import safe_public
    if prior or not safe_public(q):return None
    n=norm(q)
    if re.search(r'\b(?:neu|gia su|so sanh|doi chieu|chenh lech|sinh vien nao|lop|dac cach|ngoai le|hutech|ulis|uit|bach khoa|truong khac)\b',n):return None
    for fn in (fee,team_outcomes,regulation):
        try:
            result=fn(root,q)
            if result is not None:return result
        except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError):continue
    return None
