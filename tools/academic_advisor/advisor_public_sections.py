"""Bounded public-document section extraction. Never upgrades source status."""
import hashlib,json,re,unicodedata
from pathlib import Path
from quality import norm,clean
from advisor_source_precision import programs,academic_year,public_result,src

ORG='data/raw/uet/markdown/2026/Danh_sach_phong_ban.md'
PG='data/raw/uet/markdown/2026/Tuyển_sinh_sau_đại_học_2026.md'
PINS={ORG:'13141255cfc0a74b1caeb57d2c2d8beaf9e391cd',PG:'3820e2fbe183a3324d91f2b1a97469d0147662d2'}
def digest(b):return hashlib.sha256(b).hexdigest()
def gitblob(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def read_source(root,rel,pin,doc_id=None,git=False):
    from advisor_evidence import fresh_ledger
    root=Path(root).resolve();p=(root/rel).resolve();p.relative_to(root)
    raw=p.read_bytes();lf=raw.replace(b'\r\n',b'\n');sha=digest(raw);canon=digest(lf)
    if pin not in ((gitblob(raw),gitblob(lf)) if git else (sha,canon)):raise ValueError('source changed')
    stem=norm(Path(rel).stem)
    for h in fresh_ledger(root):
        if h.get('content_sha256') in (sha,canon) or rel in (h.get('source_path'),h.get('content_path')) or (doc_id and h.get('doc_id')==doc_id) or stem in norm(str(h.get('doc_id',''))):raise ValueError('source held')
    return unicodedata.normalize('NFC',raw.decode('utf-8-sig')),sha

def org(root,q):
    n=norm(q)
    if academic_year(q)!=2026 or not re.search(r'\b(?:chuc nang|nhiem vu)\b',n) or re.search(r'\b(?:nhan su|lien he|email|dien thoai|dia chi|ai la|hien nay|hieu luc|quyen quyet dinh)\b',n):return None
    t,sha=read_source(root,ORG,PINS[ORG],git=True)
    headings=list(re.finditer(r'(?m)^#\s+([^\n]+)',t));matches=[]
    for i,m in enumerate(headings):
        title=norm(clean(m[1]));
        if len(title)>12 and re.search(r'\b'+re.escape(title)+r'\b',n):matches.append((i,m))
    if len(matches)!=1:return None
    i,m=matches[0];body=t[m.end():headings[i+1].start() if i+1<len(headings) else len(t)]
    # Only an explicitly labelled function section, ending at the next numbered section.
    lines=body.splitlines();selected=[];active=False
    for line in lines:
        v=clean(line).replace('\\.','.');nn=norm(v)
        if not active:
            if re.match(r'^1\s+chuc nang(?: nhiem vu)?\b',nn):active=True;selected.append(v)
        elif re.match(r'^\d+\s+(?:to chuc|nhan su|cong tac|co cau|lien he)\b',nn) or v.startswith('|') or line.startswith('#'):break
        elif v:selected.append(v)
    if not 2<=len(selected)<=20 or sum(map(len,selected))>2500:return None
    if any(re.search(r'\b(?:email|so tai khoan|mssv|cccd|ignore previous|system prompt)\b',norm(x)) for x in selected):return None
    return public_result('theo mục **'+clean(m[1])+'** trong tài liệu lưu trữ năm 2026:\n\n'+'\n'.join(selected)+'\n\nChỉ phản ánh chức năng ghi trong bản tài liệu, không xác nhận thay đổi sau đó.',[src(ORG,sha)],'organization_function_section')

def postgraduate(root,q):
    n=norm(q)
    if academic_year(q)!=2026 or 'tuyen sinh sau dai hoc' not in n or not re.search(r'\b(?:noi dung nao|noi dung gi|gom nhung gi|tong quan|tom tat)\b',n):return None
    if re.search(r'\b(?:thac si|tien si|dot [12]|hoc phi|le phi|chung chi|ngoai ngu|dieu kien|han nop|dang ky|chi tieu|bao nhieu)\b',n):return None
    t,sha=read_source(root,PG,PINS[PG],git=True);t=t.replace('\\.','.');t=' '.join(t.split())
    m=re.search(r'\bI\. TUYỂN SINH BẬC THẠC SĨ\b',t);p=re.search(r'\bII\. TUYỂN SINH BẬC TIẾN SĨ\b',t)
    if not m or not p or m.start()>=p.start():return None
    intro=t[:m.start()];period=re.search(r'tuyển sinh sau đại học 02 đợt vào tháng \d{1,2} và tháng \d{1,2}\.',intro,re.I)
    sections=[t[m.end():p.start()],t[p.end():]]
    names=[]
    for section in sections:
        # Enumerate titles supported by explicit headings, not fees or clipped snippets.
        rules=[('Danh mục ngành và chỉ tiêu',r'Danh mục các ngành và số lượng tuyển sinh'),('Đối tượng và điều kiện dự tuyển',r'1\. Đối tượng'),('Phương thức tuyển sinh',r'2\. Phương thức tuyển sinh'),('Đăng ký và lịch xét tuyển',r'(?:4\. Kế hoạch xét tuyển|8\. Đăng ký dự tuyển)'),('Lệ phí dự tuyển',r'(?:6\. Lệ phí dự tuyển|8\.2\. Lệ phí)'),('Tổ chức đào tạo, học phí và học bổng',r'(?:7|9)\. Tổ chức đào tạo, học phí, học bổng')]
        found=[label for label,pat in rules if re.search(pat,section,re.I)]
        if len(found)<5:return None
        names.append(found)
    return public_result('thông báo tuyển sinh sau đại học năm 2026 có hai phần riêng biệt. '+((period[0].capitalize()+' (theo phần giới thiệu của thông báo).') if period else '')+'\n\n**Thạc sĩ:** '+ '; '.join(names[0])+'.\n\n**Tiến sĩ:** '+ '; '.join(names[1])+'.\n\nCác phụ lục trình bày yêu cầu chi tiết. Cần tra riêng bậc đào tạo và đợt tuyển sinh trước khi áp dụng điều kiện, lệ phí hoặc mốc thời gian.',[src(PG,sha)],'postgraduate_document_outline')

def curriculum_total(root,q):
    from reference_knowledge import cohort_request
    n=norm(q);wanted=programs(q);cy=cohort_request(q)
    if len(wanted)!=1 or not cy or not re.search(r'\b(?:tong bao nhieu tin chi|tong so tin chi|tong tin chi|bao nhieu tin chi toan khoa)\b',n):return None
    if re.search(r'\b(?:hoc phan|tien quyet|tu chon|bat buoc|khoi kien thuc|hoc ky|hoc lai|tich luy duoc|con thieu|con no|clc|nhat ban|so sanh|dieu kien|tot nghiep)\b',n):return None
    root=Path(root);cat=json.loads((root/'data/raw/uet/curricula/catalog.json').read_text(encoding='utf-8-sig'));excluded=cat.get('owner_excluded_documents',[]);rows=[]
    for r in cat['records']:
        if r.get('collection')!='official_uet_extractions' or r.get('program_identifier') not in wanted or not isinstance(r.get('cohort_from'),int):continue
        if not r['cohort_from']<=cy or r.get('cohort_to') is not None and cy>r['cohort_to']:continue
        if any(r.get('doc_id')==e.get('doc_id') or r.get('content_path')==e.get('source_path') or r.get('content_sha256')==e.get('source_sha256') for e in excluded):continue
        rows.append(r)
    if len(rows)!=1:return None
    r=rows[0];rel=r['content_path'];t,sha=read_source(root,rel,r['content_sha256'],r['doc_id']);head=t.split('\n## ',1)[0]
    total=re.findall(r'(?m)^reported_total_credits:\s*(\d+)\s*$',head);line=re.findall(r'\*\*tổng tín chỉ theo nguồn:\*\*\s*(\d+)',head,re.I)
    if len(total)!=1 or line!=total or not 60<=int(total[0])<=250:return None
    name=re.search(r'(?m)^program_name_vi:\s*"([^"\n]+)"\s*$',head)
    if not name:return None
    return public_result(f'CTĐT **{name[1]}** theo bản lưu dành cho khóa QH-{cy} ghi tổng **{total[0]} tín chỉ**. Đây là tổng tín chỉ ghi trong nguồn; chưa xác minh độc lập toàn bộ bảng hoặc điều kiện tích lũy. ',[dict(src(rel,sha),source_url=r.get('source_url'))],'curriculum_total_reference')

def route(root,q,prior):
    from reference_knowledge import safe_public
    if prior or not safe_public(q):return None
    if re.search(r'\b(?:neu|gia su|so sanh|doi chieu|chenh lech|lop|mssv|em ay|ban ay|truong khac|hutech|ulis|uit|bach khoa|ngoai le|dac cach)\b',norm(q)):return None
    for fn in (org,postgraduate,postgraduate_language,research_dates,total_v2,outcomes_v2,curriculum_total):
        try:
            r=fn(root,q)
            if r is not None:return r
        except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError):continue
    return None

# Catalog-wide field extraction, not a question/answer bank.
def catalog_rows(root,q,collection,kind):
    from reference_knowledge import cohort_request
    cy=cohort_request(q);wanted=programs(q);n=norm(q)
    if len(wanted)!=1 or cy is None or not 2022<=cy<=2026:return []
    if len(set(re.findall(r'\b20\d{2}\b',n)))>1:return []
    cat=json.loads((Path(root)/'data/raw/uet/curricula/catalog.json').read_text(encoding='utf-8-sig'))
    rows=[]
    for r in cat['records']:
        if r.get('collection')!=collection or r.get('content_kind')!=kind or r.get('program_identifier') not in wanted:continue
        if any(r.get('doc_id')==e.get('doc_id') or r.get('content_path')==e.get('source_path') or r.get('content_sha256')==e.get('source_sha256') for e in cat.get('owner_excluded_documents',[])):continue
        if collection=='official_uet_extractions':
            a,b=r.get('cohort_from'),r.get('cohort_to')
            if not isinstance(a,int) or cy<a or b is not None and cy>b:continue
        else:
            hint=r.get('cohort_hint_unverified') or '';ys=list(map(int,re.findall(r'20\d{2}',hint)))
            if not ((len(ys)==2 and ys[0]<=cy<=ys[1]) or (len(ys)==1 and ((cy>=ys[0] and 'onward' in hint) or (cy==ys[0] and 'onward' not in hint)))):continue
        rows.append(r)
    return rows

def total_v2(root,q):
    from reference_knowledge import cohort_request
    n=norm(q);cy=cohort_request(q)
    if not ('tin chi' in n and re.search(r'\b(?:tong|toan khoa|khoi luong toan khoa)\b',n)):return None
    if re.search(r'\b(?:hoc phan|tien quyet|tu chon|bat buoc|khoi kien thuc|hoc ky|hoc lai|tich luy duoc|con thieu|con no|clc|nhat ban|so sanh|dieu kien|tot nghiep|bao nhieu mon|muc toi thieu|toi da)\b',n):return None
    rows=catalog_rows(root,q,'official_uet_extractions','curriculum')
    if not rows:return None
    data=[]
    for r in rows:
        rel=r['content_path'];t,sha=read_source(root,rel,r['content_sha256'],r['doc_id']);head=t.split('\n## ',1)[0]
        total=re.findall(r'(?m)^reported_total_credits:\s*(\d+)\s*$',head);line=re.findall(r'\*\*tổng tín chỉ theo nguồn:\*\*\s*(\d+)',head,re.I)
        name=re.search(r'(?m)^program_name_vi:\s*"([^"\n]+)"\s*$',head)
        if len(total)!=1 or line!=total or not 60<=int(total[0])<=250 or not name:return None
        label=str(r.get('edition') or Path(rel).stem);data.append((name[1],total[0],label,dict(src(rel,sha),source_url=r.get('source_url'))))
    if len(data)==1:
        name,amount,label,source=data[0];answer=f'CTĐT **{name}** theo bản lưu dành cho khóa QH-{cy} ghi tổng **{amount} tín chỉ**.'
    else:
        answer=f'Có {len(data)} phiên bản CTĐT {data[0][0]} cho phạm vi khóa QH-{cy}:\n'+ '\n'.join(f'- {label}: **{amount} tín chỉ**.' for name,amount,label,source in data)+'\nChưa đủ căn cứ xác định phiên bản thay thế hoặc phiên bản áp dụng cho hồ sơ cụ thể.'
    return public_result(answer+'\nĐây là tổng tín chỉ ghi trong bản lưu, chưa xác minh độc lập toàn bộ bảng hoặc điều kiện tích lũy.',[x[3] for x in data],'curriculum_total_reference')

def parse_plo(text):
    # Preserve both hierarchical labels (PLO2.1) and flat labels (PLO12).
    t=unicodedata.normalize('NFC',text).replace('**','').replace('\\.','.')
    t=re.split(r'(?im)^\s*(?:#+\s*)?(?:\d+[.)]\s*)?(?:vị trí việc làm|khả năng học tập|ma trận quan hệ|ma trận đối sánh)',t,maxsplit=1)[0]
    ms=list(re.finditer(r'(?im)(?<![\w.])PLO\s*(\d+(?:\.\d+)*)(?:\s*[:.]\s*|\s+(?=\S))',t));out=[]
    for i,m in enumerate(ms):
        tail=t[m.end():ms[i+1].start() if i+1<len(ms) else len(t)]
        # Trim next heading, bullets and whitespace; do not concatenate unrelated sections.
        tail=re.split(r'(?m)^\s*(?:#+\s*|\d+[.)]\s+)(?=\S)',tail,maxsplit=1)[0]
        tail=' '.join(tail.split()).strip(' -*–•')
        if not 15<=len(tail)<=1100 or '|' in tail or re.search(r'\b(?:ignore previous|system prompt|mssv|cccd)\b',norm(tail)):continue
        out.append(('PLO'+m[1],tail))
    if len({x[0] for x in out})!=len(out) or not 2<=len(out)<=60:return []
    return out

def grouped_outcomes(text):
    """Extract explicitly counted outcomes in labelled prose groups; never infer PLO numbers."""
    t=unicodedata.normalize('NFC',text).replace('**','').replace('\\.','.')
    m=re.search(r'(?im)^\s*#*\s*A\.\s*Chuẩn đầu ra(?:\s*\(PLO\))?\s*$',t)
    if not m:return []
    t=t[m.end():]
    count=re.search(r'(?i)các mục\s*\(1\)\s*đến\s*\((\d+)\)',t)
    if not count or not 2<=int(count[1])<=60:return []
    groups=[]; items=None
    for line in t.splitlines():
        line=line.strip(); h=re.match(r'^#*\s*(\d+)\.\s*(.+)$',line)
        if h:
            heading=norm(h[2])
            if heading.startswith(('vi tri viec lam','kha nang hoc tap','ma tran')):break
            if heading not in ('cdr kien thuc','cdr ky nang','cdr muc tu chu va trach nhiem'):return []
            items=[];groups.append((h[2],items));continue
        if items is None or not line:continue
        if line.startswith(('- ','– ','• ')):
            v=line[2:].strip()
            if not 15<=len(v)<=1100 or re.search(r'[|<>#]|https?://',v) or not v.endswith(('.', ';')) or re.search(r'\b(?:ignore previous|system prompt|mssv|cccd)\b',norm(v)):return []
            items.append(v)
        else:return []
    if len(groups)!=3 or len({norm(x[0]) for x in groups})!=3 or any(not v for _,v in groups) or sum(len(v) for _,v in groups)!=int(count[1]):return []
    return groups

def outcomes_v2(root,q):
    from reference_knowledge import cohort_request
    n=norm(q);cy=cohort_request(q)
    if not re.search(r'\b(?:chuan dau ra|plo)\b',n) or re.search(r'\b(?:tieng anh|ngoai ngu|so sanh|dieu kien|tot nghiep|clc|nhat ban|bao nhieu|tuong duong|ap dung|hieu luc)\b',n):return None
    rows=catalog_rows(root,q,'team_original_uploads','learning_outcomes')
    if len(rows)!=1:return None
    r=rows[0];rel=r['content_path'];t,sha=read_source(root,rel,r['content_sha256'],r['doc_id']);plos=parse_plo(t)
    explicit=re.search(r'(?i)\bPLO\s*(\d+(?:\.\d+)*)\b',q)
    if not plos:
        groups=grouped_outcomes(t)
        if not groups or explicit:return None
        a=f'bản chuẩn đầu ra lưu trữ, có nhãn khóa QH-{cy}, ghi {sum(len(v) for _,v in groups)} yêu cầu thuộc {len(groups)} nhóm:\n\n'+'\n\n'.join('**'+k+'**\n'+'\n'.join('- '+x for x in v) for k,v in groups)+'\n\nPhạm vi theo nhãn bản lưu; chưa xác minh độc lập hiệu lực. Không sử dụng bảng ma trận OCR bị lỗi để suy ra mã PLO.'
        return public_result(a,[dict(src(rel,sha),source_url=r.get('source_url'))],'curriculum_outcomes_grouped_reference')
    if explicit:plos=[v for v in plos if v[0]=='PLO'+explicit[1] or v[0].startswith('PLO'+explicit[1]+'.')]
    if not plos or sum(len(x[1]) for x in plos)>12000:return None
    a=f'bản chuẩn đầu ra lưu trữ, có nhãn khóa QH-{cy}, ghi các yêu cầu sau:\n\n'+'\n'.join('- '+k+': '+v for k,v in plos)+'\n\nPhạm vi theo nhãn bản lưu; chưa xác minh độc lập hiệu lực và điều kiện áp dụng.'
    return public_result(a,[src(rel,sha)],'curriculum_outcomes_reference')

RESEARCH_SOURCES={2023:('data/raw/uet/markdown/2023/NCKH_hoi_nghi_cap_khoa_CNTT_2023.md','13d281faf07aa391a45f200bc3a7e9603927c00a',r'\b(?:khoa cntt|khoa cong nghe thong tin)\b','Khoa CNTT'),2024:('data/raw/uet/markdown/2024/NCKH_hoi_nghi_vien_TTNT_2024.md','7e6310f03c23e7a4fd52f909f3495a91b2efea0e',r'\b(?:vien ttnt|vien tri tue nhan tao)\b','Viện Trí tuệ nhân tạo')}
def research_dates(root,q):
    n=norm(q);y=academic_year(q)
    if y not in RESEARCH_SOURCES or not re.search(r'\b(?:nckh|nghien cuu khoa hoc)\b',n) or not re.search(r'\b(?:ngay nao|khi nao|han dang ky|thoi gian|lich)\b',n):return None
    rel,pin,scope,label=RESEARCH_SOURCES[y]
    if not re.search(scope,n) or re.search(r'\b(?:cap truong|tat ca|khoa khac|vien khac|nop bao cao|phan bien|ket qua|thamdinh|tham dinh)\b',n):return None
    t,sha=read_source(root,rel,pin,git=True);target='dang ky' if 'dang ky' in n else 'hoi nghi'
    found=[]
    for line in t.splitlines():
        cells=[clean(c) for c in line.strip().strip('|').split('|')]
        if len(cells)!=2 or not re.search(r'\d{1,2}/\d{1,2}/20\d{2}',cells[1]):continue
        k=norm(cells[0]);
        if (target=='dang ky' and 'dang ky' in k) or (target=='hoi nghi' and k.startswith('hoi nghi') and 'cong bo' not in k):found.append(cells)
    if len(found)!=1:return None
    k,v=found[0];return public_result(f'theo kế hoạch {label}, năm học {y}–{y+1}: **{k}: {v}**. Đây là lịch công bố trong tài liệu lưu trữ; không thay cho lịch cấp Trường hoặc đơn vị khác.',[src(rel,sha)],'research_schedule')

def postgraduate_language(root,q):
    n=norm(q)
    if academic_year(q)!=2026 or not re.search(r'\b(?:ngoai ngu|tieng anh|chung chi)\b',n) or not re.search(r'\b(?:tuyen sinh|du tuyen)\b',n):return None
    levels=[k for k in ('thac si','tien si') if k in n]
    if len(levels)!=1 or re.search(r'\b(?:mien|quy doi|ielts|toefl|vstep|nuoc ngoai|chung chi cua toi|du dieu kien)\b',n):return None
    t,sha=read_source(root,PG,PINS[PG],git=True);t=' '.join(t.replace('\\.','.').split())
    m=re.search(r'\bI\. TUYỂN SINH BẬC THẠC SĨ\b',t);p=re.search(r'\bII\. TUYỂN SINH BẬC TIẾN SĨ\b',t)
    if not m or not p or m.start()>=p.start():return None
    section=t[m.end():p.start()] if levels[0]=='thac si' else t[p.end():]
    if levels[0]=='thac si':pattern=r'b\. Yêu cầu về ngoại ngữ (.*?)(?=c\. Yêu cầu khác)';label='Thạc sĩ'
    else:pattern=r'b\) Người dự tuyển là công dân Việt Nam (.*?)(?=c\) Người dự tuyển là công dân nước ngoài)';label='Tiến sĩ (công dân Việt Nam)'
    hit=re.search(pattern,section,re.I)
    if not hit:return None
    a=hit[1];
    if not re.search(r'\b(?:bac may|bac nao|toi thieu|online|chung chi)\b',n):return None
    if 'online' in n:
        match=re.search(r'Nhà trường không chấp nhận chứng chỉ thi online\.',a,re.I)
        if not match:return None
        a=match[0]
    else:
        match=re.search(r'(?:Một trong các chứng chỉ[^;]*?Bậc \d trở lên[^;]*?trong thời hạn 2 năm[^;]*?đăng ký dự tuyển)',a,re.I)
        if not match:return None
        a=match[0].rstrip('.')+'.'
    return public_result(f'{label}, thông báo tuyển sinh 2026: {a}\nĐây là nội dung trong bản lưu của đúng bậc đào tạo, không xác nhận điều kiện hồ sơ cá nhân.',[src(PG,sha)],'postgraduate_language_reference')
