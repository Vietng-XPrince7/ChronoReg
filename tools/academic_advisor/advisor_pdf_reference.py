"""PDF-derived scoped reference facts; original source and research ledgers unchanged."""
import re,hashlib
from pathlib import Path
from quality import norm
from advisor_source_precision import public_result,src

SOURCES={'extended': {'pdf': 'data/advisor_sources/tuition_history/postgraduate_extended.pdf', 'sha': 'c16bee446e4656afc4f051cd5afa85eb59a17656072e8aaff0a6407af0549cb3', 'md': 'data/raw/uet/markdown/2022/Dinh_muc_hoc_phi_dao_tao_sau_dai_hoc_trong_thoi_gian_keo_dai_2022.md', 'md_sha': 'c922b8ca5100ff909459705f07083f6b2d25a5aa96c8ed807c70d4062f60aa93', 'alias': 'dinh-muc-hoc-phi-dao-tao-sau-dai-hoc-trong-thoi-gian-keo-dai-2022', 'raw_alias': None}, 'fee': {'pdf': 'data/raw/uet/source_pdfs/HP_2025-2026_2080_Appendix01.pdf', 'sha': '8aabf10dd99ab88487311efdccf881fecfc6f6f7b6659c22dbb0b5798363a8dd', 'md': 'data/raw/uet/markdown/2025/Quy_dinh_muc_thu_hoc_phi_2025.md', 'md_sha': '377bdfb1d8c72eb6d23a0489e45edc5809da590bf244fa8e996aa10107eaed1c', 'alias': 'quy-dinh-muc-thu-hoc-phi-2025', 'raw_alias': None}, 'r2023': {'pdf': 'data/raw/uet/source_archives/html_to_pdf/NCKH_2023_2024_FIT_HTML_snapshot.pdf', 'sha': 'df07d0019cabef84f45561a7a22d4ad34f8f2c278db524a90f9ecaeff3797a8c', 'md': 'data/raw/uet/source_archives/html_to_md/NCKH_2023_2024_FIT_HTML_snapshot.md', 'md_sha': '6b177f5254e7d16b705d9790fba64d9ad00c6ae48955a4adaae06b392228bd06', 'alias': 'nckh-hoi-nghi-cap-khoa-cntt-2023', 'raw_alias': ('data/raw/uet/markdown/2023/NCKH_hoi_nghi_cap_khoa_CNTT_2023.md', '13d281faf07aa391a45f200bc3a7e9603927c00a')}, 'r2024': {'pdf': 'data/raw/uet/source_archives/html_to_pdf/NCKH_2024_2025_AI_HTML_snapshot.pdf', 'sha': '4235141a400bd2e2391a571aa47a81ea0a7e6eeeb5a6eb3b297918fccf801c34', 'md': 'data/raw/uet/source_archives/html_to_md/NCKH_2024_2025_AI_HTML_snapshot.md', 'md_sha': '52d802ceb2859c2eb155977e622e589e1cabe6df4b9ea6600f3fc82de13f2666', 'alias': 'nckh-hoi-nghi-vien-ttnt-2024', 'raw_alias': ('data/raw/uet/markdown/2024/NCKH_hoi_nghi_vien_TTNT_2024.md', '7e6310f03c23e7a4fd52f909f3495a91b2efea0e')}, 'r2025': {'pdf': 'data/raw/uet/source_archives/html_to_pdf/NCKH_2025_2026_AI_HTML_snapshot.pdf', 'sha': 'f77639aa18191b5e0affebd0df189e73bf6751b0773a1cb7df75be39a2dda523', 'md': 'data/raw/uet/source_archives/html_to_md/NCKH_2025_2026_AI_HTML_snapshot.md', 'md_sha': '785656fdd80569d53f17cb3699e98785469b558eb45fba935154efd0a2545f69', 'alias': 'nckh-hoi-nghi-vien-ttnt-2025', 'raw_alias': ('data/raw/uet/markdown/2025/NCKH_hoi_nghi_vien_TTNT_2025.md', '71dbaac7c4f35e014afe8528cbc2b633dd9d6d6e')}}
FEES={'thac si': [[2021, 2021, 2775000, 865000, 865000], [2022, 2024, 3500000, 1144000, 1144000], [2025, 2025, None, None, 1144000]], 'tien si': [[2021, 2021, 4000000, 1212000, 1212000], [2022, 2024, 4200000, 1282000, 1282000], [2025, 2025, None, None, 1282000]]}
RESEARCH={2023: [['19/01–25/01/2024', 'Đăng ký đề tài, cán bộ hướng dẫn', 1], ['26/01/2024', 'Khoa tập hợp danh sách', 1], ['22/02/2024', 'Nộp báo cáo về VPK (P301, nhà E3)', 1], ['26/02/2024', 'Khoa gửi báo cáo cho phản biện', 1], ['05/03/2024', 'Thu phản biện', 2], ['08/03/2024', 'Công bố danh sách tiểu ban và địa điểm', 2], ['12/03/2024', 'Hội nghị cấp Khoa', 2], ['14/03/2024', 'Họp hội đồng thẩm định và công bố kết quả', 2]], 2024: [['01/02–14/02/2025', 'Đăng ký công trình, cán bộ hướng dẫn', 1], ['20/02/2025', 'Viện tập hợp danh sách', 1], ['27/02/2025', 'Nộp báo cáo về Văn phòng Viện (315-G2)', 1], ['05/03/2025', 'Công bố tiểu ban, địa điểm; gửi báo cáo phản biện', 1], ['06–15/03/2025', 'Hội nghị cấp Viện, thẩm định và công bố kết quả', 1]], 2025: [['01/02–25/02/2026', 'Đăng ký công trình, cán bộ hướng dẫn (bảng)', 1], ['26/02/2026', 'Viện tập hợp danh sách', 1], ['05/03/2026', 'Nộp báo cáo về Văn phòng Viện (315-G2)', 1], ['09/03/2026', 'Gửi báo cáo cho phản biện', 1], ['20/03/2026', 'Công bố tiểu ban và địa điểm', 1], ['23–27/03/2026', 'Hội nghị cấp Viện, thẩm định và công bố kết quả', 1]]}

def sha(b):return hashlib.sha256(b).hexdigest()
def source(root,key):
    from advisor_evidence import fresh_ledger
    root=Path(root).resolve();v=SOURCES[key]; paths=[]; hashes=set()
    for rel,pin in [(v['pdf'],v['sha']),(v['md'],v['md_sha'])]:
        p=(root/rel).resolve();p.relative_to(root);b=p.read_bytes();h=sha(b)
        canonical=sha(b.replace(b'\r\n',b'\n')) if rel.endswith('.md') else h
        if pin not in (h,canonical):raise ValueError('Source changed: '+rel)
        paths.append(rel);hashes.update((h,canonical))
    if v['raw_alias']:
        rel,pin=v['raw_alias'];p=(root/rel).resolve();p.relative_to(root);b=p.read_bytes();c=b.replace(b'\r\n',b'\n')
        def blob(t):return hashlib.sha1(f'blob {len(t)}\0'.encode()+t).hexdigest()
        if pin not in (blob(b),blob(c)):raise ValueError('Raw alias changed: '+rel)
        hashes.update((sha(b),sha(c)));paths.append(rel)
    for h in fresh_ledger(root):
        if h.get('content_sha256') in hashes or v['alias'] in str(h.get('doc_id','')) or any(h.get(k) in paths for k in ('source_path','content_path')):raise ValueError('Publication hold')
    return src(v['pdf'],v['sha'])

def period(q):
    # Explicit academic period, independent of cohort.
    m=re.findall(r'\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b',q)
    if len(m)!=1 or int(m[0][1])!=int(m[0][0])+1:return None
    rest=re.sub(r'\b20\d{2}\s*[-–—/]\s*20\d{2}\b','',q)
    rest=re.sub(r'(?i)\b(?:qh[- ]*|khóa\s+(?:tuyển sinh\s+)?)(20\d{2})\b','',rest)
    if re.search(r'\b20\d{2}\b',rest):return None
    return int(m[0][0])

def fee(root,q):
    n=norm(q)
    if 'hoc phi' not in n or period(q)!=2025:return None
    levels=[v for v in FEES if re.search(r'\b'+v+r'\b',n)]
    if not levels and 'sau dai hoc' not in n:return None
    if re.search(r'\b(?:mien|giam|ho tro|hoc bong|nuoc ngoai|tinh tien|tong tien|nop|lich thu|bao nhieu tien phai|so sanh|chenh lech|hoc ky|dai hoc chinh quy|ngoai chuong trinh|dinh muc theo nam|muc nam|ca nam|mot nam|1 nam|nam bao nhieu|qd 248|quyet dinh 248|qd 347|quyet dinh 347)\b',n):return None
    extended=bool(re.search(r'\b(?:keo dai|gia han)\b',n))
    if extended:
        if len(levels)!=1 or re.search(r'\b(?:tinh so tien|hoc lai|cai thien|tu chon|bao nhieu dong|bao nhieu tien)\b',n):return None
        a=source(root,'fee');b=source(root,'extended')
        text='Phụ lục 01 QĐ 2080, trang 3, dẫn QĐ 347/QĐ-KHTC ngày 16/05/2022 về học phí trong thời gian đào tạo kéo dài. '
        text+=('Bản quy định kéo dài ghi: học phí thạc sĩ tính theo số tín chỉ thực tế đăng ký trong học kỳ kéo dài nhân định mức tín chỉ tương ứng.' if levels[0]=='thac si' else 'Bản quy định kéo dài ghi: học phí tiến sĩ tính theo niên chế, bằng 50% học phí trong thời gian đào tạo chuẩn của năm học tương ứng.')
        return public_result(text+' Chưa tính số tiền phải nộp; cần xác định định mức áp dụng.',[a,b],'pdf_postgraduate_extended')
    c=re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?)\s*(20\d{2})\b',n)
    if len(set(c))>1:return None
    cy=int(c[0]) if c else None
    if cy is not None and cy>2025:return None
    # If a cohort is older, the source explicitly says 2021 or earlier.
    a=source(root,'fee'); lines=['theo Phụ lục 01 QĐ 2080/QĐ-ĐHCN ngày 29/09/2025, trang 2, bảng định mức sau đại học năm học 2025–2026:', '', '| Bậc / khóa | Lần đầu (đồng/tháng) | Lần đầu (đồng/tín chỉ) | Học lại, cải thiện, tự chọn tự do (đồng/tín chỉ) |','|---|---:|---:|---:|']
    def fmt(x):return f'{x:,}'.replace(',','.') if x is not None else 'Theo QĐ 248 ngày 10/02/2025'
    for level in levels or list(FEES):
        for lo,hi,m,first,again in FEES[level]:
            if cy is not None and not ((lo==2021 and cy<=2021) or lo<=cy<=hi):continue
            group='QH-2021 trở về trước' if lo==2021 else ('QH-2022–2024' if lo==2022 else 'QH-2025')
            lines.append(f'| {"Thạc sĩ" if level=="thac si" else "Tiến sĩ"} — {group} | {fmt(m)} | {fmt(first)} | {fmt(again)} |')
    if len(lines)==4:return None
    lines.append('\nĐịnh mức theo tháng không phải lịch thu tiền. Với QH-2025, bảng dẫn chiếu QĐ 248 cho học lần đầu; không suy đoán mức tiền. Bảng không xác nhận số tiền phải nộp hoặc miễn giảm cá nhân.')
    return public_result('\n'.join(lines),[a],'pdf_postgraduate_table')

def research(root,q):
    n=norm(q);y=period(q)
    if y not in RESEARCH or not re.search(r'\b(?:nckh|svnckh|nghien cuu khoa hoc)\b',n):return None
    if not re.search(r'\b(?:khoa cntt|khoa cong nghe thong tin)\b' if y==2023 else r'\b(?:vien ttnt|vien tri tue nhan tao|vien ai)\b',n):return None
    if re.search(r'\b(?:cap truong|mien|diem thuong|thay the|quy doi|bao cao gom|mau bao cao|email|lien he|thanh vien|so sanh|tat ca cac khoa|tat ca cac vien)\b',n):return None
    if not re.search(r'\b(?:lich|ke hoach|thoi gian|han|ngay nao|khi nao|moc|ngay may)\b',n):return None
    if y==2023 and re.search(r'\b(?:vien ttnt|vien ai|vien tri tue nhan tao)\b',n):return None
    if y!=2023 and re.search(r'\b(?:khoa cntt|khoa cong nghe thong tin)\b',n):return None
    # Return complete schedule only for explicit scoped timeline questions, rather than a partial date selected incorrectly.
    a=source(root,'r'+str(y)); label='Khoa CNTT' if y==2023 else 'Viện Trí tuệ nhân tạo'
    lines=[f'theo bản lưu kế hoạch {label}, năm học {y}–{y+1} (đối chiếu bản PDF):','','| Thời gian | Công việc | Trang |','|---|---|---:|']
    lines.extend(f'| {d} | {task} | {p} |' for d,task,p in RESEARCH[y])
    if y==2025:lines.append('\n**Mâu thuẫn trong nguồn:** bảng trang 1 ghi đăng ký 01/02–25/02/2026, nhưng chú ý trang 2 ghi chậm nhất **15/02/2026**. Cần xác nhận với Viện; không khẳng định một hạn duy nhất.')
    lines.append('\nĐây là lịch trong bản lưu, không xác nhận thay đổi sau công bố hoặc lịch cấp Trường.')
    rel=SOURCES['r'+str(y)]['raw_alias'][0];raw=(Path(root)/rel).read_bytes()
    return public_result('\n'.join(lines),[src(rel,sha(raw)),a],'pdf_research_timeline')

def route(root,q,prior):
    from reference_knowledge import safe_public
    if prior or not safe_public(q):return None
    n=norm(q)
    if re.search(r'\b(?:toi|minh|cua em|cua co|cua ban|cua toi|em ay|ban ay|ho so|mssv|lop|neu|gia su|so sanh|doi chieu|du dieu kien|ap dung cho|hien nay|hieu luc|du doan|tinh giup|ngoai le|dac cach|truong khac|k\d{2})\b',n):return None
    for fn in (fee,research):
        try:
            a=fn(root,q)
            if a is not None:return a
        except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError):return None
    return None
