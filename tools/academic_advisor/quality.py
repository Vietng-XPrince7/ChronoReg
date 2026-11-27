"""Source-bound admissions lookup and conservative generation checks. No QA bank."""
from pathlib import Path
from decimal import Decimal
import hashlib, re, unicodedata

SOURCES = {
 2022: ('diem_trung_tuyen_2022.md',17,'5e098c970d3e9d80db448070ce8ee86ddd9beca1d28cc531af174bacf2a55bf8'),
 2023: ('thong_bao_diem_trung_tuyen_theo_thpt_2023.md',17,'dd4718c83e9a5686da520da40bfe3d1237b98eb5b672a13f62b6fedcf1d6c014'),
 2024: ('thong_bao_diem_trung_tuyen_2024.md',17,'bb90e841bc4b438ca103863287730d148373bc53faab4da37a945e58a1e51be4'),
 2025: ('diem_trung_tuyen_2025.md',20,'91dc6859837b39f916942af4918408723d8362f4b4b7e01acaa9c59735605370'),
 2026: ('thong_bao_diem_trung_tuyen_2026.md',20,'d189b953e7fab7c459167a7d21d0a7c4c28eea5ef128e82af0e42a9695b3d0f6'),
}
SYSTEM = 'Bạn là trợ lý hỏi đáp quy định UET. Trả lời theo năm học được hỏi. Nếu thiếu bằng chứng, nói rõ không đủ thông tin. Không bịa nguồn hoặc số liệu.'
def norm(s):
    s=unicodedata.normalize('NFKD', s.lower().replace('đ','d'))
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',''.join(c for c in s if not unicodedata.combining(c))).split())
def clean(s):
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>|\*','',re.sub(r'<br\s*/?>',' ',s,flags=re.I))).strip()
def parse(root,year):
    name,count,pin=SOURCES[year]; rel=f'data/raw/uet/markdown/{year}/{name}'
    raw=(Path(root)/rel).read_bytes(); s=raw.decode('utf-8-sig').replace('\r\n','\n')
    if hashlib.sha256(s.encode()).hexdigest()!=pin: raise ValueError('Source changed; review required: '+rel)
    result={}
    def add(code,name,value,extra=''):
        name=clean(name); value=clean(value).replace(',','.')
        if not re.fullmatch(r'CN\d+',code) or not name or not re.fullmatch(r'\d{1,2}(?:\.\d{1,2})?',value) or not 0<=Decimal(value)<=30 or code in result: raise ValueError('Invalid or duplicate admission row: '+code)
        result[code]=(name,value.replace('.',','),clean(extra))
    for line in s.splitlines():
        if year==2024:
            m=re.fullmatch(r'\s*(CN\d+)\s+(.+?)\s+(\d{1,2}(?:[,.]\d{1,2})?)\s*',line)
            if m: add(*m.groups())
            continue
        if not line.strip().startswith('|'): continue
        cells=line.strip().strip('|').split('|') if year!=2026 else line.strip()[1:-1].split('|')
        if year in (2022,2023):
            if cells and re.fullmatch(r'CN\d+',clean(cells[0])):
                if len(cells)!=(6 if year==2022 else 3): raise ValueError('Unexpected table width')
                add(clean(cells[0]),cells[1],cells[-1])
        elif year==2025:
            if len(cells)==4 and re.fullmatch(r'CN\d+',clean(cells[1])): add(clean(cells[1]),cells[2],cells[3])
        elif year==2026:
            if len(cells)!=6 or not re.match(r'CN\d+',clean(cells[3])): continue
            cols=[re.split(r'<br\s*/?>',cells[i],flags=re.I) for i in (3,4,5)]
            # Names sometimes wrap within a single cell; only split a joint multi-program row.
            codes=cols[0]; names=[cells[2]] if len(codes)==1 else re.split(r'<br\s*/?>',cells[2],flags=re.I)
            if len(codes)==1: cols[2]=[cells[5]]
            if not len(codes)==len(names)==len(cols[1])==len(cols[2]): raise ValueError('Joint row alignment error')
            for c,n,v,e in zip(codes,names,cols[1],cols[2]): add(clean(c),n,v,e)
    if len(result)!=count: raise ValueError(f'Incomplete source: {year}: {len(result)}/{count}')
    return result,rel,hashlib.sha256(raw).hexdigest()

def lookup(root,question):
    q=norm(question)
    if not re.search(r'\bdiem (?:chuan|trung tuyen)\b',q): return None
    if re.search(r'\b(?:hutech|tphcm|tp ho chi minh|thac si|tien si|du doan|du kien|diem san|nguong|so sanh|chenh lech|tang|giam|cao nhat|thap nhat|vi sao|cach tinh|tieu chi phu|to hop|xet tuyen thang|hoc phi|hoc bong|bao luu|rut hoc phan|canh bao|sinh vien trong lop|ngoai le|sat|act|hsa|dgnl|ielts|toefl|danh gia nang luc|phuong thuc khac)\b',q): return None
    years=set(map(int,re.findall(r'\b20\d{2}\b',q)))
    if len(years)!=1 or next(iter(years)) not in SOURCES: return None
    year=next(iter(years)); rows,rel,sha=parse(root,year)
    explicit=set(re.findall(r'\bcn\d+\b',q))
    # Full-name boundary match. Longer name wins over contained name (e.g. CN16/CN1).
    matches=[(len(norm(n)),c) for c,(n,_,_) in rows.items() if f' {norm(n)} ' in f' {q} ']
    if explicit:
        codes=[c for c in rows if c.lower() in explicit]
        if len(codes)!=len(explicit): return None
        if matches and any(c not in codes for _,c in matches if _==max(k for k,_c in matches)): return None
    elif re.search(r'\b(?:tat ca|cac nganh|toan bo|danh sach|bang diem chuan)\b',q): codes=list(rows)
    elif matches:
        # Reject genuinely multiple named programs except contained names.
        top=max(n for n,c in matches); codes=[c for n,c in matches if n==top]
        if len(codes)!=1: return None
        if re.search(r'\b(?:va|voi)\b',q) and len(matches)>1: return None
    else: return None
    if not codes: return None
    scope='phương thức THPT' if year<=2024 else 'điểm trúng tuyển công bố (quy đổi thang 30)'
    lines=[f'Điểm chuẩn UET – ĐHQGHN năm {year} ({scope}, thang 30):']
    for c in sorted(codes,key=lambda x:int(x[2:])):
        n,v,e=rows[c]; lines.append(f'• {c} – {n}: {v} điểm'+(f' (tiêu chí phụ: {e})' if e else ''))
    return {'answer':'\n'.join(lines),'year':year,'path':rel,'sha256':sha,'row_count':len(codes)}

# Compare numeric atoms, not semantic equivalence. Fail closed for unfamiliar units/format.
def number_atoms(text):
    text=re.sub(r'(?m)^\s*\d+[.)]\s+','',text)
    out=set()
    for raw in re.findall(r'(?<!\d)\d+(?:[.,/]\d+)*(?!\d)',text):
        if re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+',raw): raw=re.sub(r'[.,]','',raw)
        if '/' not in raw:
            try: raw=str(Decimal(raw.replace(',','.')).normalize())
            except Exception: pass
        out.add(raw)
    return out

def unsupported_numbers(answer,context): return number_atoms(answer)-number_atoms(context)

def messages_for(model,prompt,lora):
    if model==lora:
        m=re.fullmatch(r'Năm học được hỏi: (20\d{2}-20\d{2})\.\n(.+)',prompt,re.S)
        if m and 'Hãy dùng nguyên vẹn dữ liệu' not in m[2]: prompt=f'Năm học: {m[1]}\nCâu hỏi: {m[2]}'
        return [{'role':'system','content':SYSTEM},{'role':'user','content':prompt}]
    return [{'role':'system','content':'Bạn là trợ lý UET – ĐHQGHN. Chỉ dùng bằng chứng được cung cấp; không suy diễn số liệu, không nhầm trường. Nếu thiếu thông tin, nói rõ.'},{'role':'user','content':prompt}]
