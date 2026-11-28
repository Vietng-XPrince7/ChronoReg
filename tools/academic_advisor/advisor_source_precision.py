"""Public document routing. No personal decisions, no source-status upgrades."""
import re, hashlib, json, unicodedata
from pathlib import Path
from quality import norm, clean

PROGRAMS={
 'cntt':('cong nghe thong tin','cntt'), 'khmt':('khoa hoc may tinh','khmt'),
 'httt':('he thong thong tin','httt'), 'ktmt':('ky thuat may tinh','ktmt'),
 'ktrb':('ky thuat robot','ktrb'), 'ktvt':('ky thuat dien tu vien thong','cong nghe ky thuat dien tu vien thong','ktvt'),
 'mmtttdl':('mang may tinh va truyen thong du lieu','mmtttdl','mmtthdl'),
 'agricultural-technology':('cong nghe nong nghiep','cnnn'), 'artificial-intelligence':('tri tue nhan tao','ttnt'),
 'biotechnology':('cong nghe sinh hoc','cong nghe ky thuat sinh hoc'), 'civil-engineering':('cong nghe ky thuat xay dung','ky thuat xay dung'),
 'control-and-automation':('ky thuat dieu khien va tu dong hoa',), 'data-science':('khoa hoc du lieu','khoa hoc va ky thuat du lieu'),
 'energy-engineering':('ky thuat nang luong',), 'engineering-mechanics':('co ky thuat',), 'engineering-physics':('vat ly ky thuat',),
 'industrial-graphic-design':('thiet ke cong nghiep va do hoa',), 'materials-engineering':('ky thuat vat lieu','cong nghe vat lieu'),
 'mechatronics-engineering':('ky thuat co dien tu','cong nghe ky thuat co dien tu'), 'space-engineering':('ky thuat khong gian','cong nghe hang khong vu tru')}

def programs(q):
    n=norm(q); found=[(key,alias) for key,aliases in PROGRAMS.items() for alias in aliases if re.search(r'\b'+re.escape(alias)+r'\b',n)]
    return {key for key,a in found if not any(key!=k and a!=b and (' '+a+' ') in (' '+b+' ') for k,b in found)}

def family(q):
    n=norm(q)
    def has(p):return bool(re.search(p,n))
    if has(r'\b(?:nckh|nghien cuu khoa hoc)\b'):return 'research'
    if has(r'\b(?:hoc phi|muc thu)\b'):return 'tuition'
    if has(r'\b(?:hoc bong|kkht)\b'):return 'scholarship'
    if has(r'\b(?:tuyen sinh sau dai hoc|thac si|tien si|cao hoc)\b'):return 'postgraduate'
    if has(r'\b(?:xac nhan nhap hoc|nhap hoc|nop minh chung|xet tuyen|diem chuan|tuyen sinh)\b'):return 'admissions'
    if has(r'\b(?:ctdt|chuong trinh dao tao|chuan dau ra|tien quyet|hoc phan|tin chi|khoa luan)\b') and programs(q):return 'curriculum'
    if has(r'\b(?:ke hoach (?:nam hoc|hoc tap)|lich hoc|lich thi|hoc ky|ky chinh|ky phu)\b') and not has(r'\b(?:quy che|dieu khoan|cpa|gpa|quyet dinh)\b'):return 'calendar'
    if has(r'\b(?:viec lam|co hoi nghe nghiep)\b') and has(r'\b(?:trang|website|cong thong tin|link)\b'):return 'career'
    if has(r'\b(?:hoi dong khoa hoc va dao tao|phong ban|ban giam hieu)\b'):return 'organization'
    if has(r'\b(?:ctdt|chuong trinh dao tao|chuan dau ra|tien quyet|hoc phan|tin chi|khoa luan)\b') and programs(q):return 'curriculum'
    return None

def eligible(c,q,program_map):
    f=family(q); p=norm(c.path); n=norm(q)
    if f=='calendar':return 'ke hoach hoc tap' in p or 'calendar' in p
    if f=='postgraduate':return bool(re.search(r'\b(?:sau dai hoc|thac si|tien si|cao hoc|postgraduate)\b',p))
    if f=='admissions':
        if 'xac nhan nhap hoc' in n:return 'nhap hoc' in p
        if 'nop minh chung' in n:return 'minh chung' in p
    if f=='career':return 'viec lam' in p
    if f=='organization':return 'phong ban' in p
    if f=='research':return bool(re.search(r'\b(?:nckh|nghien cuu khoa hoc)\b',p))
    if f=='curriculum':
        wanted=programs(q); identifier=program_map.get(c.path,''); identifier='mmtttdl' if identifier=='mmtthdl' else identifier
        if identifier not in wanted:return False
        if 'chuan dau ra' in n:
            return 'chuan dau ra' in norm(c.heading) or 'chuan dau ra' in p or 'plo' in norm(c.text)
        if 'khoi kien thuc' in n:return 'khoi kien thuc' in norm(c.text)
    return True

def academic_year(q):
    t=re.sub(r'(?i)\bQH[- ]*20\d{2}\b','',q)
    pair=re.findall(r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b',t)
    if pair:
        if len(pair)!=1 or int(pair[0][1])!=int(pair[0][0])+1:return None
        rest=re.sub(r'\b20\d{2}\s*[-–—/]\s*20\d{2}\b','',t)
        return int(pair[0][0]) if not re.search(r'\b20\d{2}\b',rest) else None
    ys=set(map(int,re.findall(r'\b20\d{2}\b',t)));return next(iter(ys)) if len(ys)==1 else None

# Exact snapshots of locally inventoried sources. Do not read held or changed bytes.
PINS={'data/raw/uet/markdown/2023/Dinh_muc_hoc_bong_kkht_2023.md': '3f810dc0ac46bfccaa177a75cd2850aa5887fa49b0b56bad56f7b8b538bb3922', 'data/raw/uet/markdown/2023/Ke_hoach_thu_hoc_phi_2023.md': '1ed3c843233bf148991141591bbed46c290642506dbeb2d5ac8831e9d6104de6', 'data/raw/uet/markdown/2024/Quy_dinh_ve_hoc_bong_2024.md': 'aea624fe612513a58a269f889b1d7adc9bd8490f4eb1b3e471b90f4550a05cc3', 'data/raw/uet/markdown/2025/Quy_dinh_muc_hoc_bong_2025.md': '46c665cb743b7723af594dd780fdad7b1b90004a8737f4f3f50734e1311fe26b', 'data/raw/uet/markdown/2026/Ke_hoach_hoc_tap_2026.md': '5bfa3bef29029ff4e2ed4a81d8a05aaaa7d4e6a698655a032678d8c64478d2ec', 'data/raw/uet/markdown/2026/Gioi_thieu_viec_lam.md': '724c1ea123d4f1c40bdc2acc264fa0ac15136b028149d18b0e010770a79fc676'}

def document(root,rel):
    root=Path(root).resolve();p=(root/rel).resolve();p.relative_to(root);raw=p.read_bytes();txt=raw.decode('utf-8-sig');sha=hashlib.sha256(raw).hexdigest();canon=hashlib.sha256(txt.replace('\r\n','\n').encode()).hexdigest()
    if PINS.get(rel) not in (sha,canon):raise ValueError('source changed')
    from advisor_evidence import fresh_ledger
    for h in fresh_ledger(root):
        if h.get('content_sha256') in (sha,canon) or rel in (h.get('content_path'),h.get('source_path')) or Path(rel).stem.lower().replace('_','-') in str(h.get('doc_id','')):raise ValueError('source held')
    return txt,sha

def public_result(text,src,goal):
    from quality_routes import response
    r=response('Dạ cô, '+text,goal,['reference_search'],src);r['metadata'].update(engine_mode='ADVISOR_EVIDENCE',source_label='Tài liệu UET đối chiếu',source_path=src[0]['source_path'],sha256=src[0]['sha256'],reference_only=True,quality_qualified=False);return r,{}

def src(rel,sha):return {'source_path':rel,'sha256':sha}

def route(root,q,prior):
    from reference_knowledge import safe_public
    if not safe_public(q):return None
    n=norm(q);y=academic_year(q);f=family(q)
    # No inherited private identity, compound policy decision, or context-dependent task.
    if re.search(r'\b(?:neu|so sanh|chenh lech|doi sang|thay doi|truong hop|tinh tien|ngoai le|sinh vien nao|khoa khac|lop|hoc lai|mien giam)\b',n):return None
    if prior and prior.get('kind') not in ('public_year','policy_clause'):return None
    try:
        if f=='scholarship' and y in (2023,2025) and re.search(r'\b(?:dinh muc|muc hoc bong|cac muc|bang muc)\b',n) and not re.search(r'\b(?:qh|k\d{2}|chuong trinh chuan|ctdt chuan|loai gioi|loai kha|loai xuat sac|dieu kien|tieu chi|xet cap|quy trinh|bao nhieu|so tien)\b',n):
            from scholarship import parse_rates,GRADES,GROUPS
            rows,rel,sha,_=parse_rates(root,y);document(root,rel)
            lines=[f'định mức KKHT năm học {y}–{y+1} (đồng/tháng) theo bảng nguồn:', '', '| Chương trình / khóa | Xuất sắc | Giỏi | Khá |','|---|---:|---:|---:|']
            for row in rows:
                v=row['values'];vals=[f"{v[k]:,}".replace(',','.') if k in v else '—' for k in ('xuat sac','gioi','kha')];lines.append('| '+GROUPS[row['group']]+' — '+row['scope']+' | '+' | '.join(vals)+' |')
            return public_result('\n'.join(lines)+'\n\nĐây là định mức công bố trong tài liệu lưu trữ; không phải xác nhận được cấp học bổng.',[src(rel,sha)],'scholarship_overview')
        if f=='calendar' and y in (2022,2024,2025) and re.search(r'\b(?:hoc ky|ky chinh|ky phu|cac ky)\b',n) and not re.search(r'\b(?:dang ky|thi|nghi|chuyen mon|tuan|k\d{2}|qh|lop|lich hoc tung)\b',n):
            from calendar_source import inspect_uploaded_calendar,SEM
            sems=[s for s,pattern in SEM.items() if re.search(pattern,n)]
            if not sems and 'cac ky' in n:sems=list(SEM)
            if not sems:return None
            results=[inspect_uploaded_calendar(root,f'{y}-{y+1}',s) for s in sems]
            if any(v['status']!='READY' for v in results):return None
            rows=[v['hits'][0] for v in results]
            text=f'theo kế hoạch học tập năm học {y}–{y+1}:\n\n'+'\n'.join('- '+x['excerpt'] for x in rows)+'\n\nĐây là khoảng thời gian học kỳ theo kế hoạch nguồn, không phải lịch học chuyên môn từng khóa. '+str(rows[0].get('qualification',''))
            return public_result(text,[src(x['source_path'],x['sha256']) for x in rows],'calendar_interval')
        if f=='tuition' and y==2023 and re.search(r'\b(?:ke hoach thu|lich thu) hoc phi\b',n):
            rel='data/raw/uet/markdown/2023/Ke_hoach_thu_hoc_phi_2023.md';t,sha=document(root,rel)
            m=re.search(r'(?im)^#{1,6}[^\n]*Dự kiến lịch thu học phí[^\n]*\n(.*?)(?=^#{1,6}\s|\Z)',t,re.S|re.M)
            if not m:return None
            lines=[clean(x) for x in m[1].splitlines() if x.strip() and re.search(r'\d{1,2}/\d{1,2}/20\d{2}',x)]
            if not lines:return None
            return public_result('lịch thu dự kiến trong thông báo năm học 2023–2024:\n\n'+'\n'.join('- '+x for x in lines)+'\n\nĐây là lịch dự kiến được ghi trong nguồn, không phải xác nhận lịch thu cuối cùng hoặc định mức chính thức.',[src(rel,sha)],'tuition_schedule')
        if f=='calendar' and y==2026 and re.search(r'\b(?:dang ky hoc|dang ky mon|dang ky hoc phan)\b',n):
            rel='data/raw/uet/markdown/2026/Ke_hoach_hoc_tap_2026.md';t,sha=document(root,rel)
            lines=[clean(x) for x in t.splitlines() if re.search(r'\b(?:dang ky|dangky|dkhp|dk hoc)\b',norm(x)) and re.search(r'\d{1,2}/\d{1,2}/20\d{2}',x)]
            if lines:return public_result('các dòng có mốc đăng ký học trong bản kế hoạch 2026–2027:\n\n'+'\n'.join('- '+x for x in lines[:8])+'\n\nCần xác nhận lịch chi tiết trên cổng đào tạo.',[src(rel,sha)],'calendar_registration')
            return public_result('bản kế hoạch học tập 2026–2027 lưu trong kho chưa thể hiện rõ mốc đăng ký học phần trong văn bản trích xuất. Cần đối chiếu thông báo đăng ký học phần của Phòng Đào tạo; không lấy lịch đăng ký nguyện vọng tuyển sinh thay thế.',[src(rel,sha)],'calendar_registration')
        if f=='career':
            rel='data/raw/uet/markdown/2026/Gioi_thieu_viec_lam.md';t,sha=document(root,rel)
            urls=re.findall(r'https://vieclam\.uet\.vnu\.edu\.vn/co-hoi-nghe-nghiep\b',t.replace('\\',''))
            if urls:return public_result('có thể xem cơ hội nghề nghiệp tại cổng việc làm UET: '+urls[0]+'.',[src(rel,sha)],'career_portal')
        if f=='scholarship' and y==2024 and re.search(r'\b(?:cac muc|cac loai|muc hoc bong)\b',n) and not re.search(r'\b(?:qh|k\d{2}|bao nhieu tien|dong|thang)\b',n):
            rel='data/raw/uet/markdown/2024/Quy_dinh_ve_hoc_bong_2024.md';t,sha=document(root,rel)
            lines=[clean(x) for x in t.splitlines() if re.match(r'^[abc]\) Học bổng loại (?:khá|giỏi|xuất sắc):',x.strip(),re.I)]
            if len(lines)==3:return public_result('tài liệu quy định học bổng lưu trong kho năm 2024 nêu ba mức KKHT:\n\n'+'\n'.join('- '+x for x in lines)+'\n\nĐây là nguyên tắc phân loại, không phải bảng số tiền cụ thể của UET.',[src(rel,sha)],'scholarship_categories')
    except (OSError,ValueError,KeyError,TypeError,IndexError):return None
    return None
