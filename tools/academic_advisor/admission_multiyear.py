"""Read-only historical admissions table access. Scope is source snapshot, not legal approval."""
import hashlib,re
from pathlib import Path
from quality import norm,parse as pinned_parse
from quality_routes import response
from advisor_evidence import fresh_ledger

SOURCES={
2022:('diem_trung_tuyen_2022.md','45cbe72c9ede72d9839bcc44dc9d0f6e4346a128',17),
2023:('thong_bao_diem_trung_tuyen_theo_thpt_2023.md','7a03412f2c71a5d90ec45630ed254647036010d6',17),
2024:('thong_bao_diem_trung_tuyen_2024.md','13cb963772d41f1fac2e88ed292d129c469cab86',17),
2025:('diem_trung_tuyen_2025.md','e21e9b499406b2bcbc4804998f808bb2195e10dc',20),
2026:('thong_bao_diem_trung_tuyen_2026.md','c4f7eae101ad61e6feb8973ff7f63b8447fc96db',20)}

def clean(s):
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>|\*|_', ' ',s)).strip()

def point(s):
    s=clean(s).replace(',','.')
    if not re.fullmatch(r'\d{1,2}(?:\.\d{1,2})?',s) or not 0<=float(s)<=30:raise ValueError('invalid point')
    return s.replace('.',',')

def parse_2022_methods(text,expected=17):
    out=[]
    for line in text.splitlines():
        line=line.strip()
        if not line.startswith('|') or not line.endswith('|'):continue
        c=line[1:-1].split('|')
        if not c or not re.fullmatch(r'CN\d{1,2}',clean(c[0])):continue
        if len(c)!=6:raise ValueError('ambiguous columns')
        out.append((clean(c[0]),clean(c[1]),[point(x) for x in c[2:]],''))
    if len(out)!=expected or len({x[0] for x in out})!=len(out):raise ValueError('incomplete or duplicate table')
    return out

def load(root,year,holds):
    file,pin,_=SOURCES[year];rel=f'data/raw/uet/markdown/{year}/{file}'
    p=(Path(root)/rel).resolve();p.relative_to(Path(root).resolve());raw=p.read_bytes();canonical=raw.replace(b'\r\n',b'\n')
    sha=hashlib.sha256(raw).hexdigest();cs=hashlib.sha256(canonical).hexdigest()
    if pin not in {hashlib.sha1(b'blob '+str(len(x)).encode()+b'\0'+x).hexdigest() for x in (raw,canonical)}:raise ValueError('source changed')
    for h in holds:
        if h.get('content_sha256') in (sha,cs) or (str(year) in str(h.get('doc_id','')) and re.search(r'diem-(?:trung-tuyen|chuan)',str(h.get('doc_id','')))):raise ValueError('held source')
    base,base_rel,base_sha=pinned_parse(root,year)
    if year==2022:
        rows=parse_2022_methods(canonical.decode('utf-8-sig'))
        if {code:ps[-1] for code,_,ps,_ in rows}!={code:v for code,(_,v,_) in base.items()}:raise ValueError('THPT cross-check failed')
    else:
        rows=[(code,name,[point(v)],tie) for code,(name,v,tie) in base.items()]
    return rows, {'source_path':rel,'sha256':sha,'review_status':'source_snapshot_not_legal_review','year':year}

ALIASES={'cntt':'CN1','khmt':'CN8','httt':'CN14','ktmt':'CN2','ktrb':'CN17','ttnt':'CN12'}
BLOCK=re.compile(r'\b(?:du doan|du bao|co hoi|kha nang|lieu|co do|co trung tuyen|du dieu kien|tinh diem|quy doi|nguong dau vao|ngoai le|dac cach|mssv|\d{8}|hutech|ulis|uit|bach khoa|truong khac|thac si|tien si|xet tuyen thang|act|toefl|phuong thuc khac|hoc phi|hoc bong|quy che|vi sao|cach tinh|tieu chi phu|to hop)\b')

def route(q,root):
    n=norm(q)
    if not re.search(r'\b(?:diem chuan|diem trung tuyen)\b',n):return None
    check=n
    if set(re.findall(r'\b20\d{2}\b',n))=={'2026'} and re.search(r'\bcn\d{1,2}\b',n) and not re.search(r'\b(?:nghia la gi|la gi|giai thich|cach tinh|vi sao|the nao de|ap dung|du dieu kien)\b',n):
        check=re.sub(r'\btieu chi phu\b',' ',n)
    if BLOCK.search(check):return None
    years=sorted(set(map(int,re.findall(r'\b20\d{2}\b',n))))
    if not years or any(y not in SOURCES for y in years):return None
    # Only interpret explicit historical range when both endpoints present.
    if len(years)==2 and re.search(r'\b'+str(years[0])+r'\s*[-–]\s*'+str(years[-1])+r'\b',q):years=list(range(years[0],years[-1]+1))
    # Retain existing separately reviewed single-year 2026 all-program route.
    if years==[2026] and re.fullmatch(r'(?:(?:cho co |cho em |cho biet |tra cuu |liet ke |bang )?)(?:diem chuan|diem trung tuyen)(?: (?:tat ca|toan bo|cac) nganh(?: dao tao)?| (?:dai hoc )?chinh quy)?(?: (?:cua )?uet)?(?: nam)? 2026(?: (?:cua )?uet)?',n):return None
    methods=[(k,v) for k,v in [('thpt','THPT'),('sat','SAT'),('ielts','IELTS'),('hsa','ĐGNL'),('dgnl','ĐGNL'),('danh gia nang luc','ĐGNL')] if re.search(r'\b'+k+r'\b',n)]
    methods=list(dict.fromkeys(v for k,v in methods))
    if len(methods)>1:return None
    method=methods[0] if methods else None
    if method and any(y!=2022 and (method!='THPT' or y>=2025) for y in years):return None
    try:
        holds=fresh_ledger(root);tables={};sources=[]
        for y in years:
            table,source=load(root,y,holds);tables[y]=table;sources.append(source)
    except (OSError,ValueError,KeyError,TypeError,UnicodeError):return None
    codes=set(x.upper() for x in re.findall(r'\bcn\d{1,2}\b',n));explicit_codes=bool(codes)
    for a,c in ALIASES.items():
        if re.search(r'\b'+a+r'\b',n):
            if a=='cntt' and re.search(r'\b(?:nhat ban|chat luong cao)\b',n):return None
            if explicit_codes and c not in codes:return None
            codes.add(c)
    # Match longest full name first so CNTT Japan cannot become CN1.
    if tables:
        names=sorted({(norm(row[1]),row[0]) for t in tables.values() for row in t},key=lambda x:-len(x[0]))
        for name,c in names:
            if re.search(r'\b'+re.escape(name)+r'\b',n):
                if explicit_codes and c not in codes:return None
                codes.add(c);n=re.sub(r'\b'+re.escape(name)+r'\b',' ',n)
    allq=bool(re.search(r'\b(?:cac nganh|tat ca|toan bo|bang diem chuan|bang diem trung tuyen)\b',n))
    if not codes and not allq:return None
    if not codes and re.search(r'\bnganh\s+(?!dao tao\b|cua\b|uet\b|nam\b|202[2-6]\b)',n):return None
    # Unsupported names/methods must not silently become another program's answer.
    if codes and not all(c in {row[0] for t in tables.values() for row in t} for c in codes):return None
    if re.search(r'\b(?:cao nhat|thap nhat|tang nhieu nhat|giam nhieu nhat|xep hang)\b',n):return None
    lines=['Dạ cô, theo các bảng điểm trúng tuyển lưu trong kho UET (thang điểm 30):']
    for y,t in tables.items():
        selected=[row for row in t if not codes or row[0] in codes]
        lines+=['',f'**Năm {y} — '+('theo các phương thức' if y==2022 and not method else 'THPT' if y<=2024 and not method else method if method else 'điểm trúng tuyển công bố')+'**']
        if not selected:lines.append('Không tìm thấy mã ngành được hỏi trong bảng năm này.');continue
        labels=['SAT','ĐGNL','IELTS','THPT'] if y==2022 else ['Điểm']
        idx=list(range(len(labels))) if not method or y!=2022 else [labels.index(method)]
        labels=[labels[i] for i in idx]
        if y==2026:labels+=['Tiêu chí phụ']
        lines+=['| Mã XT | Ngành | '+' | '.join(labels)+' |','|---|---|'+'---:|'*len(labels)]
        for code,name,ps,tie in selected:
            vals=[ps[i] for i in idx]
            if y==2026:vals.append(tie.replace('<=','≤') or '—')
            lines.append('| '+ ' | '.join([code,name,*vals])+' |')
        missing=sorted(codes-{row[0] for row in selected})
        if missing:lines.append('Không có trong bảng này: '+', '.join(missing)+'.')
        lines.append('Nguồn: `'+next(s['source_path'] for s in sources if s['year']==y)+'`.')
    if len(years)>1:lines+=['','Lưu ý: phương thức, cách quy đổi và tên ngành có thể thay đổi giữa các năm; không suy ra tương đương chỉ từ cùng mã xét tuyển.']
    lines+=['','Thông tin theo bản tài liệu lưu trữ, không phải dự báo hay kết luận đủ điều kiện trúng tuyển.']
    r=response('\n'.join(lines),'admissions_history',['reference_search'],sources)
    r['metadata'].update(engine_mode='ADVISOR_EVIDENCE',inference_source='deterministic_historical_admissions',source_label='Bảng điểm trúng tuyển UET',reference_only=True,quality_qualified=False,source_path=sources[0]['source_path'],sha256=sources[0]['sha256'])
    return r,{}
