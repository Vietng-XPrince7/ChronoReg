"""Read annual KKHT rate tables, never infer missing rates or eligibility.

Supported sources: 2023-24 and 2025-26 published rate tables in main.
The 2026 eligibility decision is not a rate table. No extrapolation.
"""
from pathlib import Path
import hashlib,re
from quality import clean,norm

SOURCES={
 2023:('Dinh_muc_hoc_bong_kkht_2023.md',9,'3f810dc0ac46bfccaa177a75cd2850aa5887fa49b0b56bad56f7b8b538bb3922'),
 2025:('Quy_dinh_muc_hoc_bong_2025.md',8,'46c665cb743b7723af594dd780fdad7b1b90004a8737f4f3f50734e1311fe26b'),
}
GRADES={'xuat sac':'Xuất sắc','gioi':'Giỏi','kha':'Khá'}
GROUPS={'standard':'Chương trình chuẩn','clc_cntt':'Lớp CLC ngành CNTT','tt23':'CLC theo TT23','combined':'CLC theo TT23 hoặc định mức kinh tế kỹ thuật','dmktkt':'Định mức kinh tế kỹ thuật'}

def group_of(s):
    n=norm(s)
    tt=bool(re.search(r'\b(?:tt\s*23|thong tu 23)\b',n))
    dm=bool(re.search(r'\b(?:dmktkt|dinh muc kinh te ky thuat)\b',n))
    if tt and dm:return 'combined'
    if tt:return 'tt23'
    if dm:return 'dmktkt'
    if re.search(r'\b(?:clc|chat luong cao)\b',n) and re.search(r'\b(?:cntt|cong nghe thong tin)\b',n):return 'clc_cntt'
    if re.search(r'\bchuan\b',n):return 'standard'
    return None

def subgroup(s):
    n=norm(s)
    if re.search(r'\b(?:cnnn|cong nghe nong nghiep)\b',n):return 'agri'
    if re.search(r'\b(?:xdgt|cnktxd|cnkhkvt|cnhkvt|hkvt|xay dung|hang khong vu tru)\b',n):return 'build_space'
    if re.search(r'\b(?:cac nganh khac|cac nganh con lai|nganh khac|nganh con lai)\b',n):return 'other'
    return None

def cohorts(s):
    """Return years explicitly covered by a source row or question."""
    n=norm(s); m=re.search(r'\bqh (20\d{2})',n)
    if not m:return set()
    start=int(m[1]);tail=n[m.end():]
    if tail.startswith(' tro ve truoc'):return set(range(1900,start+1))
    r=re.match(r'\s+den (?:qh )?(20\d{2})',tail)
    if r:return set(range(start,int(r[1])+1))
    # Comma-separated cohort list; don't pick up academic years in prose.
    literal=re.search(r'(?i)QH[- ]*(20\d{2})((?:\s*,\s*(?:QH[- ]*)?20\d{2})*)',s)
    return {int(x) for x in re.findall(r'20\d{2}',literal[0])} if literal else {start}

def parse_rates(root,year):
    name,count,pin=SOURCES[year]; rel=f'data/raw/uet/markdown/{year}/{name}'
    raw=(Path(root)/rel).read_bytes(); text=raw.decode('utf-8-sig').replace('\r\n','\n')
    normalized=hashlib.sha256(text.encode()).hexdigest()
    if normalized!=pin:raise ValueError('Scholarship source changed; review required: '+rel)
    records=[]; group=None; grades=[]
    for line in text.splitlines():
        if year==2023 and not line.lstrip().startswith('|') and re.match(r'^\s*(?:#\s*)?\**[123]\.\s*Đối với',line,re.I):group=group_of(line)
        if not line.strip().startswith('|'):continue
        cells=[clean(c) for c in line.strip().strip('|').split('|')]
        if cells and all(re.fullmatch(r'[-: ]+',c) for c in cells):continue
        if cells and norm(cells[0]) in ('khoa hoc','chuong trinh dao tao'):
            grades=[]
            for c in cells[1:]:
                n=norm(c); matches=[g for g in GRADES if f' {g} ' in f' {n} ']
                if len(matches)!=1 or 'dong thang' not in n:raise ValueError('Unrecognized rate header')
                grades.append(matches[0])
            continue
        if not cells or not grades:continue
        if year==2025:group=group_of(cells[0])
        cy=cohorts(cells[0]); sg=subgroup(cells[0]); values={}
        if not group or not cy or len(cells)!=len(grades)+1:raise ValueError('Invalid scholarship row: '+line)
        for grade,c in zip(grades,cells[1:]):
            if not re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:đ)?',c):raise ValueError('Invalid rate: '+c)
            values[grade]=int(re.sub(r'\D','',c))
        records.append(dict(group=group,cohorts=cy,subgroup=sg,scope=cells[0],values=values))
    if len(records)!=count:raise ValueError(f'Incomplete rate table: {len(records)}/{count}')
    return records,rel,hashlib.sha256(raw).hexdigest(),normalized

def is_rate_query(question):
    q=norm(question)
    if not re.search(r'\b(?:hoc bong|kkht)\b',q) or not re.search(r'\b(?:muc|dinh muc|bao nhieu tien|bao nhieu dong|so tien)\b',q):return False
    if re.search(r'\b(?:hoc phi|dieu kien|du dieu kien|xet cap|canh bao|ngoai le|so sanh|chenh lech|tang|giam|mien|du doan|thac si|tien si|hutech|tphcm|tp ho chi minh|sinh vien trong lop|lop minh|lop toi)\b',q):return False
    return True

def lookup_rates(root,question):
    if not is_rate_query(question):return None
    q=norm(question)
    # Cohort and academic year are independent dimensions. Remove cohort expressions first.
    yeartext=re.sub(r'(?i)QH[- ]*20\d{2}(?:\s*,\s*(?:QH[- ]*)?20\d{2})*(?:\s+đến\s+(?:QH[- ]*)?20\d{2})?', '', question)
    years=re.findall(r'\b(20\d{2})\s*[-–/]\s*(20\d{2})\b',yeartext)
    if years:
        if len(years)!=1 or int(years[0][1])!=int(years[0][0])+1:return None
        y=int(years[0][0]); remainder=re.sub(r'\b20\d{2}\s*[-–/]\s*20\d{2}\b','',yeartext)
        if re.search(r'\b20\d{2}\b',remainder):return None
    else:
        ys=set(map(int,re.findall(r'\b20\d{2}\b',yeartext)))
        if len(ys)!=1:return None
        y=ys.pop()
    if y not in SOURCES:return None
    group=group_of(question); cy=cohorts(question); sg=subgroup(question)
    # Multiple programme scopes require disambiguation, not the first match.
    if group!='standard' and re.search(r'\b(?:chuong trinh|he) (?:dao tao )?chuan\b',q):return None
    if group=='combined' or (group in ('tt23','dmktkt') and re.search(r'\b(?:clc|chat luong cao) (?:nganh |thuoc nganh )?(?:cntt|cong nghe thong tin)\b',q)):return None
    if len(re.findall(r'(?i)QH[- ]*20\d{2}',question))>1 and not re.search(r'(?i)QH[- ]*20\d{2}\s+đến\s+QH[- ]*20\d{2}',question):return None
    grades=[g for g in GRADES if f' {g} ' in f' {q} ']
    if not group or not cy or len(grades)!=1:return None
    rows,rel,sha,normalized=parse_rates(root,y)
    grade=grades[0]
    candidates=[r for r in rows if (r['group']==group or (r['group']=='combined' and group in ('tt23','dmktkt'))) and cy<=r['cohorts'] and (r['subgroup'] is None or r['subgroup']==sg)]
    if len(candidates)!=1 or grade not in candidates[0]['values']:return None
    r=candidates[0]; val=f"{r['values'][grade]:,}".replace(',','.')
    return {'answer':f"Theo bảng định mức học bổng KKHT UET – ĐHQGHN năm học {y}-{y+1}:\n• {GROUPS[r['group']]} — {r['scope']}, loại {GRADES[grade]}: {val} đồng/tháng.\nĐây là định mức, không phải xác nhận sinh viên chắc chắn được cấp học bổng.", 'year':y,'path':rel,'sha256':sha,'normalized_sha256':normalized,'row_count':1,'table_kind':'scholarship_rate'}
