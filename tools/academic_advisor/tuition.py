"""Pinned source table lookup, not a payment schedule or eligibility determination."""
import hashlib,re
from pathlib import Path
from quality import norm,clean
SOURCES={2024:('Dinh_muc_hoc_phi_dai_hoc_2024.md','3ad05a22390d4729d416bc6a9d84dc2030aae9291e043db4b884ea3a8d0f76b1'),2025:('Quy_dinh_muc_thu_hoc_phi_2025.md','377bdfb1d8c72eb6d23a0489e45edc5809da590bf244fa8e996aa10107eaed1c'),2026:('Quy_dinh_muc_thu_hoc_phi_2026.md','db8d31730c62caa7e9cdedb5ca5462a76696aee0245afd87648f5baceb6e5e32')}

def is_rate_query(q):
    n=norm(q)
    return bool(re.search(r'\bhoc phi\b',n) and re.search(r'\b(?:muc|dinh muc|bao nhieu|so tien|dong|hoc phi)\b',n) and not re.search(r'\b(?:hoc bong|mien|giam|ngoai le|gia han|nop|han dong|dong khi nao|thu tuc|bao luu|so sanh|chenh lech|tang|du kien|du doan|bao nhieu tin chi|tong hoc phi|tinh hoc phi|quoc tich|nuoc ngoai|don vi khac|ngoai chuong trinh|tieng anh|keo dai|bang kep|hutech|tphcm|tp ho chi minh|hoc ky|ca ky|ca khoa)\b',n))

def dimensions(question):
    if not is_rate_query(question):return None
    q=norm(question)
    cy=re.findall(r'(?i)\bQH[- ]*(20\d{2})\b',question)
    if len(cy)!=1:return None
    c=int(cy[0]); t=re.sub(r'(?i)\bQH[- ]*20\d{2}\b','',question)
    ys=re.findall(r'\b(20\d{2})\s*[-–/]\s*(20\d{2})\b',t)
    if ys:
        if len(ys)!=1 or int(ys[0][1])!=int(ys[0][0])+1:return None
        y=int(ys[0][0]); t=re.sub(r'\b20\d{2}\s*[-–/]\s*20\d{2}\b','',t)
        if re.search(r'\b20\d{2}\b',t):return None
    else:
        years=set(map(int,re.findall(r'\b20\d{2}\b',t)))
        if len(years)!=1:return None
        y=years.pop()
    if y not in SOURCES or not 2018<=c<=y:return None
    scopes=[]
    for key,pattern in [('master',r'\b(?:thac si|cao hoc)\b'),('phd',r'\b(?:tien si|nghien cuu sinh)\b'),('standard',r'\b(?:ctdt|chuong trinh(?: dao tao)?|he) chuan\b'),('tt23',r'\b(?:tt\s*23|thong tu 23)\b'),('dm',r'\b(?:dmktkt|dinh muc kinh te ky thuat)\b')]:
        if re.search(pattern,q):scopes.append(key)
    if len(scopes)!=1:return None
    g=scopes[0]
    if g=='standard' and re.search(r'\b(?:clc|chat luong cao)\b',q):return None
    # Standard cohort 2022 requires an explicit source subgroup; no guessing by major abbreviation.
    subgroup=None
    if g=='standard' and c==2022:
        if y==2024:
            # 2024 lists named majors per group, not an unrestricted 'other' group.
            groups=re.findall(r'\bnhom ([123])\b',q)
            if len(groups)==1:
                return y,c,g,{'1':'other','2':'build_space','3':'agri'}[groups[0]]
        sg=[]
        for key,pattern in [('agri',r'\b(?:cong nghe nong nghiep|cnnn)\b'),('build_space',r'\b(?:cong nghe hang khong vu tru|cong nghe xay dung giao thong|cnhkvt|cnktxdgt)\b'),('other',r'\b(?:cac nganh con lai|nganh con lai|cac nganh khac)\b')]:
            if re.search(pattern,q):sg.append(key)
        if len(sg)!=1:return None
        subgroup=sg[0]
        if y==2024 and subgroup=='other':return None
    return y,c,g,subgroup

def read_table(root,y):
    name,pin=SOURCES[y];rel=f'data/raw/uet/markdown/{y}/{name}'
    raw=(Path(root)/rel).read_bytes();text=raw.decode('utf-8-sig').replace('\r\n','\n'); normalized=hashlib.sha256(text.encode()).hexdigest()
    if normalized!=pin:raise ValueError('Tuition source changed; review required: '+rel)
    tables=[];section=None;header=None;rows=[]
    for line in text.splitlines():
        n=norm(line)
        if n.startswith('a cac chuong trinh dao tao bac dai hoc'):section='ug'
        if n.startswith('b cac chuong trinh dao tao bac sau dai hoc'):section='pg'
        if not line.strip().startswith('|'):continue
        cells=[clean(c) for c in line.strip()[1:-1].split('|')]
        if not cells or all(re.fullmatch(r'[-: ]+',c) for c in cells):continue
        if norm(cells[0]) in ('tt','stt'):
            header=cells;rows=[];tables.append((section,header,rows));continue
        if header is not None:rows.append(cells)
    return tables,rel,hashlib.sha256(raw).hexdigest(),normalized

def select_row(tables,y,c,g,sg):
    if y==2024:
        if g=='standard' and c<=2021: ti,ri=0,0
        elif g=='tt23' and c<=2021:ti,ri=1,0 if c==2018 else 1
        elif g=='standard' and c==2022:ti,ri=2,{'agri':2,'build_space':1,'other':0}[sg]
        elif g=='tt23' and c==2022:ti,ri=3,0
        elif g in ('standard','dm') and c in (2023,2024):ti,ri=4,0 if g=='standard' else 1
        else:return None
        if len(tables)<5:raise ValueError('2024 tuition table structure changed')
        _,h,rows=tables[ti];row=rows[ri]
        return h,row
    ug=g in ('standard','tt23','dm')
    section='ug' if ug else 'pg';matches=[(h,r) for s,h,r in tables if s==section]
    if len(matches)!=1:raise ValueError('Unexpected tuition table sections')
    h,rows=matches[0]
    if g=='standard':
        if c<=2021:code='1' if y==2025 else 'I.1'
        elif c==2022:code=('2.' if y==2025 else 'I.2.')+{'agri':'1','build_space':'2','other':'3'}[sg]
        else:code='3' if y==2025 else 'I.3'
    elif g=='tt23':code='II'
    elif g=='dm':code='III'
    elif y==2025:
        # Identical row numbers in two PG subsections; group boundaries matter.
        group='I' if g=='master' else 'II';active=False;rr=[]
        for row in rows:
            if row[0] in ('I','II'):active=row[0]==group;continue
            if active:rr.append(row)
        code='1' if c<=2021 else '2' if c<=2024 else '3';rows=rr
    else:
        # 2026 table has no row for pre-2022 masters. Do not extrapolate.
        if g=='master' and c<=2021:return None
        code=('ThS.'+('1' if c<=2024 else '2')) if g=='master' else ('TS.'+('1' if c<=2021 else '2' if c<=2024 else '3'))
    rr=[r for r in rows if r[0]==code]
    if len(rr)!=1:raise ValueError('Missing/duplicate tuition source row '+code)
    return h,rr[0]

def lookup_tuition(root,question):
    dims=dimensions(question)
    if not dims:return None
    y,c,g,sg=dims;tables,rel,sha,normalized=read_table(root,y);pair=select_row(tables,y,c,g,sg)
    if not pair:return None
    h,row=pair
    if len(h)!=len(row) or len(row)<4:raise ValueError('Tuition column alignment error')
    labels={'standard':'CTĐT chuẩn','tt23':'CLC theo Thông tư 23','dm':'CTĐT theo ĐMKTKT','master':'Thạc sĩ','phd':'Tiến sĩ'}
    lines=[f'Định mức học phí UET – ĐHQGHN năm học {y}-{y+1}, {labels[g]}, khóa QH-{c}:',f'• Phạm vi dòng nguồn: {row[1]}.']
    if y==2024 and g=='standard' and c<=2021:lines.append('• Điều 1: áp dụng chương trình chuẩn/CLC ngành CNTT, các khóa từ 2021 trở về trước.')
    for label,val in zip(h[2:],row[2:]):
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})+',val): lines.append(f'• {label}: {val} đồng.')
        elif val=='-':lines.append(f'• {label}: văn bản không ghi mức.')
        elif val.startswith('Theo Quyết định số'):lines.append(f'• {label}: {val} (cần tra văn bản được dẫn chiếu).')
        else:raise ValueError('Unrecognized tuition amount: '+val)
    if y==2026 and g in ('master','phd') and c>=2025:lines.append('• Ghi chú nguồn: khóa từ QH-2025 còn áp dụng Quyết định 248/QĐ-ĐHCN ngày 10/02/2025.')
    lines.append('Đây là định mức theo đơn vị ghi trong văn bản, không phải lịch thu tiền hay số tiền thực tế phải nộp trong một kỳ.')
    return {'answer':'\n'.join(lines),'year':y,'path':rel,'sha256':sha,'normalized_sha256':normalized,'row_count':1,'table_kind':'tuition_rate'}
