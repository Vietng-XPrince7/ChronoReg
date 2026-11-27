"""Source-bound clause retrieval, not a QA answer bank or a legal determination."""
import hashlib, json, re
from pathlib import Path
from quality import norm

DIR = 'experiments/qlora7b_course_20261126/training/chronoreg_course/dataset/sources/source_review'
TEXT = DIR + '/QD3626_text.md'
PDF = DIR + '/QD3626_official_mirror.pdf'
TEXT_SHA = '5a8f8e04fa90bed19284e9ad0287aed191f92098e78157811a1f763be1157da9'
PDF_SHA = '244addf2f614dec7a8804264a5ac966c3785bc7a49d8f23daf1069df05298f93'
SOURCE_URL = 'https://uet-test.uet.edu.vn/wp-content/uploads/2022/12/Quy-che-DTDH-3626.pdf'
SCOPE_URL = 'https://fepn.uet.vnu.edu.vn/dao-tao/dai-hoc/quy-che-dao-tao-dai-hoc-tai-dhqghn-ban-hanh-theo-quyet-dinh-so-3626-qd-dhqghn-ngay-21-thang-10-nam-2022.html?categoryId=101745610'
NOTICE_URL = 'https://uet-test.uet.edu.vn/quy-dinh-tieu-chi-xet-canh-bao-ket-qua-hoc-tap/'
NOTICE = ('Riêng tại UET, thông báo ngày 17/02/2023 quy định từ đợt xử lý học vụ HKII 2022–2023: '
          'dùng điểm a khoản 1 Điều 44 (CPA theo năm thứ) để xét cảnh báo; điểm b và c '
          '(GPA học kỳ, tín chỉ không đạt/nợ đọng) để xét nhắc nhở. Không quá hai lần cảnh báo liên tiếp. '
          'Cần kiểm tra thông báo áp dụng cho kỳ đang xét trước khi ra quyết định chính thức.\n'
          'Nguồn thông báo UET: '+NOTICE_URL)

# Only high-precision topic anchors, no fuzzy answer-bank matching. (article, clause or None)
GRADUATION_RANK = re.compile(r"\b(?:ha (?:hang|loai|bac|bang)(?: tot nghiep)?|giam (?:hang|loai|bac)(?: tot nghiep)?|hang tot nghiep|xep loai (?:bang|tot nghiep)|bang (?:gioi|xuat sac)|loai (?:bang tot nghiep|tot nghiep))\b")

TOPICS = (
    (r'\b(?:rut (?:bot )?hoc phan|rut mon hoc|huy hoc phan)\b', (23,None)),
    (r'\b(?:bao luu ket qua(?: hoc tap| da hoc)?|xin bao luu|thu tuc bao luu|nghi hoc tam thoi|tam dung hoc|hoc tro lai sau khi bao luu)\b', (36,3)),
    (r'\b(?:canh bao hoc vu|canh bao hoc tap|canh bao ket qua hoc tap|nhac nho ket qua hoc tap|nhac nho hoc tap|tieu chi xu ly hoc vu|xu ly hoc vu)\b', (44,1)),
    (r'\bbuoc thoi hoc\b', (44,2)),
    (r'\b(?:hoc vuot|gioi han (?:khoi luong|tin chi)|dang ky (?:hoc )?(?:toi da|toi thieu|24 tin chi)|so tin chi (?:toi da|toi thieu))\b', (21,1)),
    (r'\b(?:xep loai hoc luc|phan loai hoc luc)\b', (45,None)),
    (r'\b(?:dieu kien tot nghiep|dieu kien xet tot nghiep|cpa de tot nghiep)\b', (46,1)),
    (r'\b(?:chuyen nganh|doi nganh hoc)\b', (28,None)),
)
_REAL_SCOPE = re.compile(r'\b(?:lop minh|lop toi|trong lop|toan lop|ca lop|cua lop|bang diem|danh sach sinh vien|sinh vien nao|em nao|nhung em|cac em|bao nhieu em|si so|mssv|ma sinh vien|cntt1)\b')
# Explicit version differences or other instruments are outside this single-source adapter.
_OUTSIDE = re.compile(r'\b(?:5115|3079|thong tu|nghi dinh|so sanh|so voi|thay doi|quy che cu|truoc day|truoc nam 2022|2020|2021|k65|k66|k64|thac si|tien si|ngoai le|dac cach|cuu xet|hoc bong|hoc phi|diem chuan)\b')

def selection(question):
    q=norm(question)
    if _REAL_SCOPE.search(q) or _OUTSIDE.search(q): return []
    if re.search(r'\b20(?:1\d|2[7-9]|[3-9]\d)\b',q): return []
    # The new 2026 cohort requires a separately adjudicated regulation; never extrapolate.
    if GRADUATION_RANK.search(q) and re.search(r'\b(?:qh 2026|k71|khoa 2026|2026)\b',q): return []
    if re.search(r'\b2022\b',q) and not re.search(r'\b(?:qh 2022|3626|2022 2023)\b',q): return []
    # Reject outside institutions (this adapter is for UET / VNU).
    if re.search(r'\b(?:hutech|tp ho chi minh|bach khoa|uit|ulis|neu)\b',q): return []
    explicit=re.findall(r'\bdieu (\d{1,2})\b',q)
    if explicit:
        if '3626' not in q: return []
        if any(int(n) not in {21,23,28,36,44,45,46,47} for n in explicit): return []
        # Explicit article requests are limited to the supported clause(s), with labels.
        default={21:1,23:None,28:None,36:3,44:1,45:None,46:1,47:7}
        refs=[(int(n),default[int(n)]) for n in explicit]
        if len(refs)==1:
            k=re.search(r'\bkhoan (\d+)\b',q)
            if k:
                n=int(k.group(1))
                if (refs[0][0],n) not in {(21,1),(21,3),(21,4),(21,5),(23,1),(23,2),(23,3),(28,1),(28,2),(28,3),(36,3),(44,1),(44,2),(45,1),(45,2),(46,1),(47,5),(47,7)}: return []
                refs=[(refs[0][0],n)]
        return list(dict.fromkeys(refs)) if len(refs)<=2 else []
    refs=list(dict.fromkeys(ref for pat,ref in TOPICS if re.search(pat,q)))
    if GRADUATION_RANK.search(q):
        reduction=re.search(r'\b(?:ha|giam|truot|rot|hoc lai|no mon|diem f|ky luat)\b',q)
        refs.append((47,7) if reduction else (47,5))
    if len(refs)>2:return []
    return refs

def read_articles(root):
    root=Path(root); raw=(root/TEXT).read_bytes(); pdf=(root/PDF).read_bytes()
    decoded=raw.decode('utf-8-sig').replace('\r\n','\n')
    if hashlib.sha256(decoded.encode()).hexdigest()!=TEXT_SHA or hashlib.sha256(pdf).hexdigest()!=PDF_SHA:
        raise ValueError('QD3626 source pins mismatch; review required')
    matches=list(re.finditer(r'^[ \t]*Điều\s+(\d+)\.[ \t]+([^\n]+)',decoded,re.M))
    if [int(m[1]) for m in matches]!=list(range(1,52)):raise ValueError('Expected exactly articles 1–51')
    articles={}
    for i,m in enumerate(matches):
        body=decoded[m.end():matches[i+1].start() if i+1<len(matches) else len(decoded)]
        # Page numbers and headings between articles are not legal clause content.
        body=re.sub(r'(?m)^[ \t]*\d{1,2}[ \t]*$','',body)
        body=re.split(r'(?m)^[ \t]*Chương [IVX]+[ \t]*$',body,maxsplit=1)[0]
        articles[int(m[1])]=(m[2].strip(),body.strip())
    return articles,hashlib.sha256(raw).hexdigest()

def clause(body,n):
    if n is None:return body
    marks=list(re.finditer(r'(?m)^[ \t]*(\d+)\.[ \t]+',body))
    for i,m in enumerate(marks):
        if int(m[1])==n:return body[m.start():marks[i+1].start() if i+1<len(marks) else len(body)].strip()
    raise ValueError('Clause not found')

def compact(text):
    return '\n'.join(re.sub(r'\s+',' ',p).strip() for p in re.split(r'\n\s*\n',text) if p.strip())

def lookup_regulation(root,question):
    refs=selection(question)
    if not refs:return None
    root=Path(root);hold=root/'data/versioning/publication_holds.jsonl'
    if not hold.is_file():raise ValueError('Missing publication hold ledger')
    held=[json.loads(line) for line in hold.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    if any('3626' in str(h.get('doc_id','')) or 'quy-che-dao-tao-dai-hoc-dhqghn-2022' in str(h.get('doc_id','')) or h.get('content_sha256') in (TEXT_SHA,PDF_SHA) for h in held):
        raise ValueError('QD3626 on publication hold')
    articles,sha=read_articles(root)
    q=norm(question)
    lines=['Tham chiếu Quyết định 3626/QĐ-ĐHQGHN ngày 21/10/2022, áp dụng từ khóa tuyển sinh 2022 trở đi. Đối chiếu quy định bổ sung của UET và kỳ đang xét trước khi áp dụng.']
    if (44,1) in refs:
        # The school-specific criterion is not interchangeable with the VNU framework.
        if '2022 2023' in q and re.search(r'\b(?:hk\s*i|hk\s*1|hoc ky (?:i|1|thu nhat|dau))\b',q):return None
        lines.append(NOTICE)
    if (21,1) in refs:
        # The GPA restriction in article 23 is relevant to credit load, but no individual determination.
        lines.append('Học vượt: không thể kết luận được đăng ký 24 tín chỉ chỉ từ GPA/CPA. Cần biết kế hoạch học tập chuẩn và các giới hạn áp dụng.')
    for n,k in refs:
        title,body=articles[n]
        lines.append(f'Điều {n}'+(f', khoản {k}' if k else '')+f' — {title}:\n'+compact(clause(body,k)))
    if (21,1) in refs and (23,None) not in refs:
        # Extract the actual article 23.1(c) rather than encoding a numerical threshold in a template.
        s=clause(articles[23][1],1)
        m=re.search(r'(?m)^[ \t]*c\)\s*(.+)',s,re.S)
        if not m:raise ValueError('Article 23.1(c) missing')
        lines.append('Điều 23, khoản 1(c): '+compact(m[1]))
    answer='\n\n'.join(lines)
    # Never silently cut legal clauses in the existing UI (which truncates at 2800 chars).
    if len(answer)>2700:return None
    return dict(answer=answer,year=2022,path=TEXT,sha256=sha,normalized_sha256=TEXT_SHA,pdf_sha256=PDF_SHA,
                source_url=SOURCE_URL,scope_url=SCOPE_URL,notice_url=NOTICE_URL if (44,1) in refs else None,
                articles=[{'article':n,'clause':k} for n,k in refs],table_kind='regulation_clause')
