"""Scoped, independently reviewed public facts for the advisor product only.
The reviewed table is not an approval of the raw archive or research corpus.
Recheck pack bytes, archive bytes and holds at use; never infer an unlisted edition.
"""
from pathlib import Path
import hashlib,json,re
from quality import norm
from quality_routes import response

PACK='data/advisor_sources/reviewed/source_review_20261127.json'
PIN='467481ea8cdd853e8b40bc205cf265497aa675adf5c9384f21056889fa955bb6'
HOLD='data/versioning/publication_holds.jsonl'
CODE=re.compile(r'(?<![A-Z0-9.])(?:UET\.[A-Z]{2,3}|[A-Z]{3})\d{4}(?![A-Z0-9.])',re.I)
OTHER=re.compile(r'\b(?:clc|chat luong cao|nhat ban|tt\s*23|dmktkt|dinh muc kinh te ky thuat|khoa hoc may tinh|ky thuat may tinh|he thong thong tin|tri tue nhan tao|mang may tinh|khoa hoc du lieu|hutech|ulis|uit|bach khoa|thac si|tien si)\b')
PERSONAL=re.compile(r'\b(?:\d{8}|mssv|ma sinh vien|ca lop|lop minh|em ay|em nay|em do|sinh vien nay|sinh vien do|sinh vien khac|danh sach|ho so cua|ngoai le|dac cach|cho phep|soan|viet|gui|so sanh|hoc lai|du dieu kien|mien|chuyen doi|tuong duong)\b')

def digest(b):return hashlib.sha256(b).hexdigest()
def local_path(root,rel):
    p=root/rel
    p.resolve().relative_to(root)
    if p.is_symlink():raise ValueError('symlink')
    return p

def load(root,ident):
    root=Path(root).resolve();raw=local_path(root,PACK).read_bytes()
    if digest(raw)!=PIN:raise ValueError('review pack changed')
    pack=json.loads(raw); recs=[r for r in pack['records'] if r['id']==ident]
    if len(recs)!=1 or recs[0]['review_status']!='approved_for_scoped_advisor_reference':raise ValueError('review absent')
    r=recs[0];rel=r.get('source_path'); sha=r.get('source_sha');aliases={ident};hashes={PIN};paths={PACK};urls={r['source_url']};urls.update([r['cohort_index_url']] if r.get('cohort_index_url') else [])
    if rel:
        b=local_path(root,rel).read_bytes();actual=digest(b);canonical=digest(b.decode('utf-8-sig').replace('\r\n','\n').encode());
        if canonical!=sha:raise ValueError('archive changed')
        hashes.update((actual,canonical));paths.add(rel)
        # Detect the related catalog document and any archived alias of this exact source.
        if r['kind']=='curriculum':
            catalog=json.loads(local_path(root,'data/raw/uet/curricula/catalog.json').read_text(encoding='utf-8-sig'))['records']
            hit=[v for v in catalog if v.get('content_path')==rel and v.get('content_sha256')==sha and v.get('program_identifier')=='cntt']
            if len(hit)!=1:raise ValueError('catalog changed')
            aliases.add(hit[0]['doc_id'])
    for line in local_path(root,HOLD).read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():continue
        h=json.loads(line)
        if not isinstance(h,dict) or not h.get('doc_id') or not h.get('content_sha256'):raise ValueError('malformed hold')
        # Check normalized identifiers, URL, content hash, and explicit paths.
        doc=norm(str(h['doc_id'])); stem=norm(Path(rel).stem) if rel else ''
        if h['doc_id'] in aliases or h['content_sha256'] in hashes or any(h.get(k) in paths for k in ('content_path','source_path')) or h.get('source_url') in urls or (stem and stem in doc) or (sha and sha[:8] in doc):raise ValueError('source held')
    return r

def curriculum_table(root,cohort):
    if cohort not in range(2022,2027):raise ValueError('unreviewed cohort')
    rec=load(root,'cntt_2022_2024' if cohort<=2024 else 'cntt_2025_2026')
    if cohort not in rec['cohorts']:raise ValueError('cohort outside reviewed scope')
    return rec,{c:(v['credits'],tuple(v['prerequisites'])) for c,v in rec['rows'].items()}

def reply(rec,answer,year):
    r=response(answer,'reviewed_public_reference',['policy_reference'],[{'source_path':PACK,'sha256':PIN,'source_url':rec['source_url'],'review_id':rec['id'],'review_scope':rec['review_scope']}]);r['metadata'].update(engine_mode='SOURCE_TABLE',source_path=PACK,sha256=PIN,source_url=rec['source_url'],doc_title=rec['title'],source_label='Nguồn UET đã đối chiếu trong phạm vi dữ kiện',source_qualification=rec['review_scope'],source_type='reviewed_reference',effective_year=year,review_id=rec['id'],cited_doc_ids=[rec['id']]);return r

def fail(text):return response(text,'advisor_clarification'),{}

RATE_GROUPS = {
    ('standard',2021,None):0, ('standard',2022,'agri'):1,
    ('standard',2022,'build_space'):2, ('standard',2022,'other'):3,
    **{('standard',y,None):4 for y in (2023,2024,2025)},
    ('clc_cntt',2022,None):5,
    **{('tt23',y,None):6 for y in (2021,2022)},
    **{('dmktkt',y,None):7 for y in (2023,2024,2025)},
}
RATE_GROUPS_2026 = {
    ('standard',2022,'agri'):0, ('standard',2022,'build_space'):1, ('standard',2022,'other'):2,
    **{('standard',y,None):3 for y in range(2023,2027)},
    ('tt23',2022,'network'):4,
    **{('dmktkt',y,None):5 for y in range(2023,2027)},
}
def rate_value(root, year, group, cohort, sg, grade):
    table={2025:RATE_GROUPS,2026:RATE_GROUPS_2026}.get(year)
    if table is None:raise ValueError('year not reviewed')
    rec=load(root,f'scholarship_rates_{year}')
    if rec.get('year')!=f'{year}-{year+1}':raise ValueError('period mismatch')
    # The new TT23 row is narrower; explicit MMT scope is required.
    index=table[(group,cohort,sg if group=='standard' and cohort==2022 or group=='tt23' and year==2026 else None)]
    val=rec['rates'][index][GRADES[grade][0]]
    if type(val) is not int or val<=0:raise ValueError('invalid rate')
    return rec,val
RATE_LABELS={'standard':'CTĐT chuẩn','clc_cntt':'CLC CNTT','tt23':'CLC theo TT23','dmktkt':'ĐMKTKT'}
GRADES={'xuat sac':(0,'Xuất sắc'),'gioi':(1,'Giỏi'),'kha':(2,'Khá')}
COHORT_RE=r'\b(?:qh|khoa(?: tuyen sinh)?)\s*(20\d{2})\b'
K_RE=r'\bk(6[5-9]|7[0-9])\b'
def cohort_values(n):
    return set(map(int,re.findall(COHORT_RE,n)))|{1955+int(x) for x in re.findall(K_RE,n)}

def rate_route(n,prior,root):
    from scholarship import group_of,subgroup
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic')=='reviewed_rate' else {}
    rate=bool(re.search(r'\b(?:hoc bong|kkht)\b',n) and re.search(r'\b(?:muc|dinh muc|bao nhieu|so tien)\b',n))
    follow=bool(old and re.fullmatch(r'(?:con|the|vay|chuyen sang|doi sang) (?:loai )?(?:xuat sac|gioi|kha|k\d{2}|qh 20\d{2}|nam hoc 20\d{2} 20\d{2})(?: thi sao)?',n))
    if not (rate or follow) or re.search(r'\b(?:dieu kien|du dieu kien|xet cap|thuc nhan|nhan duoc|hoc phi|so sanh|chenh lech|thac si|tien si|hutech|ulis|uit|bach khoa|tong tien|ca nam|bao nhieu thang|moi ky|hoc ky|tin chi|tc)\b',n):return None
    cy=cohort_values(n);yeartext=re.sub(COHORT_RE,' ',n);ys=re.findall(r'\b20\d{2}\b',yeartext)
    if follow and not ys:ys=[str(old.get('year',2025)),str(old.get('year',2025)+1)]
    if len(ys)!=2 or int(ys[1])!=int(ys[0])+1:
        return fail('Dạ cô, cần xác định đúng một năm học để tra định mức KKHT.')
    year=int(ys[0]);period=f'{year}–{year+1}'
    if year==2023 and not follow:return None # retain historical verified source path
    if year not in (2025,2026):return fail(f'Dạ cô, chưa có bảng định mức KKHT đã đối chiếu cho năm học {period}; không lấy mức của năm khác.')
    group=group_of(n);sg=subgroup(n);grades=[g for g in GRADES if re.search(r'\b'+g+r'\b',n)]
    if follow:
        group=group or old.get('group');sg=sg or old.get('subgroup');cy=cy or {old.get('cohort')};grades=grades or [old.get('grade')]
    if len(cy)!=1 or not group or len(grades)!=1 or grades[0] not in GRADES:return fail(f'Dạ cô, để tra định mức KKHT {period} cần đúng khóa tuyển sinh, chương trình đào tạo và loại học bổng (Khá, Giỏi hoặc Xuất sắc).')
    y=next(iter(cy));grade=grades[0]
    if (group!='standard' and re.search(r'\bchuan\b',n)) or (group=='standard' and re.search(r'\b(?:clc|chat luong cao|nhat ban|chuan quoc te)\b',n)):return fail('Dạ cô, cần xác định một chương trình đào tạo cụ thể, không dùng chung hai nhóm định mức.')
    if group=='standard' and y==2022:
        if year==2026 and sg=='build_space' and not follow and not re.search(r'\b(?:xdgt|cn xdgt|hkvt|cn hkvt|hang khong vu tru|xay dung giao thong)\b',n):return fail('Dạ cô, năm 2026–2027 nhóm này ghi CN HKVT và CN XDGT; cần xác định đúng ngành.')
        if year==2026 and follow and old.get('year',2025)!=2026 and sg=='build_space':return fail('Dạ cô, cần xác nhận ngành theo nhóm CN HKVT/CN XDGT trong bảng năm mới.')
        if not sg:return fail(f'Dạ cô, CTĐT chuẩn QH-2022 năm {period} chia ba nhóm ngành; cần xác định ngành thuộc nhóm nào.')
    elif group=='tt23' and year==2026:
        if re.search(r'\b(?:mmt|mang may tinh|ttdl)\b',n) or follow and old.get('subgroup')=='network':sg='network'
        else:return fail('Dạ cô, bảng 2026–2027 chỉ ghi CLC TT23 QH-2022 ngành MMT&TTDL; cần xác nhận ngành này.')
    else:sg=None
    try:rec,val=rate_value(root,year,group,y,sg,grade)
    except (OSError,ValueError,KeyError,TypeError,IndexError):return fail(f'Dạ cô, chưa xác minh được dòng định mức KKHT {period} đúng khóa và chương trình; không dùng nhóm khác.')
    label=RATE_LABELS[group]; sub={'agri':' – Công nghệ nông nghiệp','build_space':(' – nhóm CN XDGT/CN HKVT' if year==2026 else ' – nhóm CNKTXD/CNHKVT'),'other':' – các ngành còn lại','network':' – MMT&TTDL'}.get(sg,'')
    amount=f'{val:,}'.replace(',','.')
    answer=f'Dạ cô, định mức học bổng KKHT năm học {period}, {label}{sub}, QH-{y}, loại {GRADES[grade][1]} là **{amount} đồng/tháng**. Đây là định mức công bố, không phải số tiền thực nhận hay xác nhận được cấp học bổng.'
    if year==2026:answer+=' Bảng áp dụng trong thời hạn đào tạo chuẩn, công bố ngày 25/11/2026.'
    return reply(rec,answer,year),{'kind':'advisor_agent','topic':'reviewed_rate','cohort':y,'group':group,'grade':grade,'subgroup':sg,'year':year}

SUMMARY_PROGRAMS={'khmt':r'\b(?:khmt|khoa hoc may tinh)\b','httt':r'\b(?:httt|he thong thong tin)\b','ktmt':r'\b(?:ktmt|ky thuat may tinh)\b'}
def summary_route(n,prior,root):
    if re.search(r'\b(?:hoc bong|kkht|hoc phi|dang ky|gioi han|canh bao|diem chuan|tuyen sinh|thac si|tien si|hutech|ulis|uit|bach khoa|tien quyet|hoc truoc)\b',n):return None
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic')=='reviewed_summary' else {}
    majors=[k for k,v in SUMMARY_PROGRAMS.items() if re.search(v,n)]
    cy=cohort_values(n)
    follow=bool(old and re.fullmatch(r'(?:con|the|vay|chuyen sang) (?:k\d{2}|qh 20\d{2}|khoa 20\d{2})(?: thi sao)?',n))
    total=bool(re.search(r'\b(?:tong(?: so)?(?: tin chi| tc)|bao nhieu tin chi|khoa luan|do an tot nghiep)\b',n))
    if not follow and (not total or not majors or re.search(r'\b(?:mon|hoc phan|(?:uet )?[a-z]{2,3}\d{4})\b',n)):return None
    if follow:majors=[old.get('program')]
    if len(majors)!=1 or re.search(r'\b(?:cntt|cong nghe thong tin|tri tue nhan tao|mang may tinh|khoa hoc du lieu|clc|chat luong cao|nhat ban|tt\s*23|chuan quoc te)\b',n):return fail('Dạ cô, cần đúng một ngành và phiên bản CTĐT; không dùng chung số tín chỉ giữa các chương trình.')
    if len(cy)!=1 or 'nam hoc' in n:return fail('Dạ cô, cần khóa tuyển sinh cụ thể để tra CTĐT, không dùng năm học thay cho khóa.')
    y=next(iter(cy));key=majors[0];mode=old.get('mode') if follow else ('thesis' if re.search(r'\b(?:khoa luan|do an tot nghiep)\b',n) else 'total')
    if y not in range(2022,2027):return fail('Dạ cô, chưa có CTĐT đã đối chiếu cho khóa này; không dùng dữ kiện khóa khác.')
    try:rec=load(root,key+('_2022_2024' if y<=2024 else '_2025_2026'))
    except (OSError,ValueError,KeyError,TypeError):return fail('Dạ cô, chưa xác minh được nguồn CTĐT đúng ngành và khóa.')
    if y not in rec['cohorts'] or rec.get(mode) is None:return fail('Dạ cô, dữ kiện này chưa được đối chiếu đủ rõ trong CTĐT đúng khóa.')
    what='tổng số tín chỉ' if mode=='total' else 'khóa luận/đồ án tốt nghiệp'
    text=f'Dạ cô, CTĐT ngành {rec["program"]} QH-{y}: {what} là **{rec[mode]} tín chỉ**. '
    if mode=='total':text+='Không tính GDTC, GDQP-AN và kỹ năng bổ trợ bắt buộc không tích lũy. '
    text+='Căn cứ trang CTĐT UET liên kết đúng khóa; chưa xác nhận sửa đổi riêng cho từng hồ sơ.'
    return reply(rec,text,y),{'kind':'advisor_agent','topic':'reviewed_summary','program':key,'cohort':y,'mode':mode}

def route(question,prior,root):
    n=norm(question)
    # Drop only a clearly separated cancellation of a previous public topic.
    # Do not strip a negation inside the actual scholarship question.
    parts=re.split(r'[,;.!?]\s*',question,maxsplit=1)
    if len(parts)==2 and re.fullmatch(r'(?:co |em )?khong (?:hoi|can tra|muon hoi) (?:ve )?(?:hoc lai|hoc phi|diem chuan|lich hoc) nua',norm(parts[0])):
        tail=norm(parts[1])
        if re.search(r'\b(?:hoc bong|kkht)\b',tail) and not PERSONAL.search(tail):n=tail
    if PERSONAL.search(n) or re.search(r'\b(?:truong khac|quyet dinh 3079|qd 3079|quyet dinh 3626|qd 3626|va hoc phi|diem chuan)\b',n):return None
    direct=rate_route(n,prior,root)
    if direct is not None:return direct
    direct=summary_route(n,prior,root)
    if direct is not None:return direct
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic')=='reviewed_curriculum' else {}
    # Explicit program + cohort. An academic year is not a cohort.
    program=bool(re.search(r'\b(?:cntt|cong nghe thong tin)\b',n)) and not OTHER.search(n)
    cy=set(int(x) for x in re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?)\s*(20\d{2})\b',n))|{1955+int(x) for x in re.findall(r'\bk(6[5-9]|7[0-9])\b',n)}
    codes={x.upper() for x in CODE.findall(question)}
    request_course=bool(codes and re.search(r'\b(?:tin chi|tien quyet|hoc truoc)\b',n))
    request_total=bool(re.search(r'\b(?:tong(?: so)? tin chi|bao nhieu tin chi|khoi kien thuc|khoa luan|tong so tc)\b',n)) and not codes
    follow=bool(old and re.fullmatch(r'(?:con|the|vay|chuyen sang) (?:k\d{2}|qh 20\d{2}|khoa 20\d{2})(?: thi sao)?',n))
    if follow and len(cy)==1:
        program=True;codes=set(old.get('codes',[]));request_course=bool(codes);request_total=not codes
    if not program and re.search(r'\b(?:cntt|cong nghe thong tin)\b',n) and re.search(r'\b(?:clc|chat luong cao|nhat ban|tt\s*23|chuan quoc te)\b',n) and (request_course or request_total) and not re.search(r'\b(?:hoc bong|kkht|hoc phi|dang ky|gioi han|canh bao|rut hoc phan|diem chuan|tuyen sinh)\b',n):
        return fail('Dạ cô, chưa có bảng CTĐT đã đối chiếu đúng chương trình CNTT này và khóa tuyển sinh được hỏi; không dùng bảng CNTT chuẩn thay thế.')
    if (program and (request_course or request_total) and not re.search(r'\b(?:hoc bong|kkht|hoc phi|dang ky|gioi han|canh bao|rut hoc phan|diem chuan|tuyen sinh)\b',n)) or follow:
        if len(cy)!=1:return fail('Dạ cô, cần nêu đúng khóa tuyển sinh (ví dụ K69 hay K70) để tra CTĐT CNTT; năm học không thay thế khóa tuyển sinh.')
        year=next(iter(cy)); all_years=set(map(int,re.findall(r'\b20\d{2}\b',n)))
        if re.search(r'\bnam hoc\b',n) or (all_years and all_years!={year}) or len(codes)>8:return None
        if year not in range(2022,2027):return fail('Dạ cô, em chưa có CTĐT CNTT đã đối chiếu cho khóa này. Không dùng bảng của khóa khác thay thế.')
        try:rec,table=curriculum_table(root,year)
        except (OSError,ValueError,KeyError,TypeError):return fail('Dạ cô, nguồn CTĐT đã thay đổi, thiếu hoặc đang tạm khóa; em chưa thể xác minh dữ kiện.')
        mode='course' if request_course else ('thesis' if re.search(r'\bkhoa luan\b',n) and not re.search(r'\b(?:tong|khoi kien thuc)\b',n) else 'total')
        if follow:mode=old.get('mode',mode)
        if mode=='course':
            lines=[]
            for code in sorted(codes):
                if code not in table:lines.append(f'- **{code}:** chưa có dòng khớp mã trong bảng đúng khóa; không tự quy đổi mã cũ/mới.');continue
                credit,pre=table[code];lines.append(f'- **{code}:** {credit} tín chỉ; '+('tiên quyết: '+', '.join(pre)+'.' if pre else 'cột tiên quyết của bảng không liệt kê mã môn.'))
            text=f'Dạ cô, theo CTĐT ngành CNTT khóa QH-{year}:\n\n'+'\n'.join(lines)+'\n\nĐây là dữ kiện trong bảng CTĐT, không xác nhận đủ điều kiện đăng ký hoặc tương đương học phần.'
        else:
            if mode=='thesis':text=f'Dạ cô, khóa luận tốt nghiệp trong CTĐT CNTT QH-{year} có **{rec["thesis"]} tín chỉ**.'
            else:text=f'Dạ cô, CTĐT CNTT QH-{year} có **{rec["total"]} tín chỉ** tích lũy.\n\n'+'\n'.join(f'- {k}: {v} tín chỉ' for k,v in rec['blocks'].items())+'\n\nKhông tính GDTC, GDQP-AN và học phần kỹ năng bổ trợ bắt buộc không tích lũy; vẫn phải hoàn thành các điều kiện tốt nghiệp.'
            text+='\nCăn cứ bảng CTĐT trên website UET; cần kiểm tra các sửa đổi áp dụng cho hồ sơ cụ thể.'
        return reply(rec,text,year),{'kind':'advisor_agent','topic':'reviewed_curriculum','cohort':year,'codes':sorted(codes),'mode':mode}
    # Historical academic-year notices, not general rules. Must match exact year.
    years=re.findall(r'\b20\d{2}\b',n)
    if years!=['2025','2026']:return None
    research=bool(re.search(r'\b(?:nckh|sv nckh|svnckh|nghien cuu khoa hoc)\b',n))
    if research and re.search(r'\b(?:han|khi nao|ngay nao|thoi gian|lich|nop bao cao|dang ky)\b',n):
        ai=bool(re.search(r'\b(?:vien ttnt|vien tri tue nhan tao)\b',n));school=bool(re.search(r'\b(?:cap truong|toan truong)\b',n));
        if ai==school:return None
        if re.search(r'\b(?:khoa cntt|khoa cong nghe thong tin|khoa dien tu|khoa co hoc)\b',n):return None
        try:rec=load(root,'research_ai_2025' if ai else 'research_uet_2025')
        except (OSError,ValueError,KeyError,TypeError):return fail('Dạ cô, chưa xác minh được thông báo đúng đơn vị và năm học.')
        f=rec['facts'];
        if ai:
            text=f'Dạ cô, thông báo của Viện TTNT năm học 2025–2026 ghi:\n- Khoảng đăng ký: {f["registration_window"]}.\n- Mốc yêu cầu liên hệ giảng viên và đăng ký: chậm nhất **{f["contact_registration_deadline"]}**.\n- Nộp báo cáo: {f["report_date"]}; hội nghị: {f["conference"]}.\n\nHai mốc đăng ký khác nhau; cần xác nhận với Viện, không tự chọn hạn muộn hơn. Đây là lịch theo thông báo, không xác nhận lịch đã diễn ra.'
        else:
            text=f'Dạ cô, Thông báo số 1 cấp Trường năm học 2025–2026 nêu:\n- Khoa/Viện gửi kết quả và đề xuất đề tài trước **{f["unit_report_before"]}**.\n- Nộp poster và video trước **{f["poster_video_before"]}**.\n- Triển lãm poster {f["poster_exhibit"]}; hội nghị chính thức dự kiến {f["conference_planned"]}.\n\nĐây không phải hạn đăng ký ban đầu của mọi sinh viên. Hạn đó cần tra theo Khoa/Viện; lịch trên là kế hoạch, chưa xác nhận thay đổi sau công bố.'
        return reply(rec,text,2025),{'kind':'advisor_agent','topic':'reviewed_notice','academic_year':'2025-2026','notice':'research'}
    if re.search(r'\b(?:kkht|hoc bong khuyen khich hoc tap)\b',n) and re.search(r'\b(?:dieu kien|tieu chi)\b',n) and re.search(r'\b(?:hoc ky i|hoc ky 1|ky i|ky 1|hki|hk1)\b',n) and not re.search(r'\b(?:ky ii|ky 2|hkii|hk2|ky phu|hoc he)\b',n):
        try:rec=load(root,'scholarship_award_2025')
        except (OSError,ValueError,KeyError,TypeError):return fail('Dạ cô, em chưa xác minh lại được thông báo cấp học bổng kỳ này.')
        f=rec['facts'];text=f'Dạ cô, theo thông báo cấp KKHT HKI 2025–2026 ngày 04/12/2025, đối tượng là sinh viên trong thời gian đào tạo chuẩn, có tên trong danh sách cấp học bổng. Kết quả xét thuộc {f["assessment_period"]}:\n\n- Học tập và rèn luyện từ Khá; riêng CNTT CLC: học tập từ Giỏi, rèn luyện từ Tốt.\n- Hoàn thành ít nhất {f["minimum_credits"]} tín chỉ; ít hơn cần đề xuất của Khoa/Viện.\n- Số suất phụ thuộc {f["fund_pct"]}% nguồn thực thu học phí theo CTĐT, ngành và khóa.\n\nĐây là điều kiện của đợt cấp cụ thể; không bảo đảm mọi sinh viên đủ điểm đều được nhận, không áp dụng mặc định cho học kỳ khác.'
        return reply(rec,text,2025),{'kind':'advisor_agent','topic':'reviewed_notice'}
    return None

def status(root):
    """Explicit scope readiness; not a change to index review/hold counts."""
    ids=('cntt_2022_2024','cntt_2025_2026','research_uet_2025','research_ai_2025','scholarship_rates_2025','scholarship_award_2025','khmt_2022_2024','khmt_2025_2026','httt_2022_2024','httt_2025_2026','ktmt_2022_2024','ktmt_2025_2026','scholarship_rates_2026')
    out=[]
    for ident in ids:
        try:
            r=load(root,ident);out.append({'review_id':ident,'status':'READY','scope':r['review_scope'],'rows':len(r.get('rows',r.get('rates',[]))),'source_url':r['source_url']})
        except (OSError,ValueError,KeyError,TypeError):out.append({'review_id':ident,'status':'BLOCKED_SOURCE_CHECK'})
    return out
