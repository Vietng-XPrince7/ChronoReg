"""Scoped multi-clause advice and dated language-notice guidance for Advisor Auto only."""
import re,json,hashlib
from pathlib import Path
from quality import norm
from quality_routes import pinned,source_response
from advisor_source_precision import public_result,src
from reference_knowledge import cohort_request,safe_public
from advisor_evidence import fresh_ledger

NOTE='tools/academic_advisor/advisor_language_notice.json'
PIN='3c8e8b70d0d7617da27f7a125024176556cecfc526ade70050d4ddf36380d8bd'

def language(root,q):
    n=norm(q);cy=cohort_request(q)
    if cy not in (2022,2023,2024,2025) or not re.search(r'\buet\b',n):return None
    if not re.search(r'\b(?:ngoai ngu|tieng anh|vstep|ielts|toefl|aptis)\b',n) or not re.search(r'\b(?:chuan dau ra|cdr)\b',n) or not re.search(r'\b(?:nop|cap nhat|thu tuc|cong nhan)\b',n):return None
    if re.search(r'\b(?:so sanh|mien hoc|mien thi|quy doi|chuyen doi diem|thac si|tien si|truong khac|khieu nai|ngoai le|truoc nam|hieu luc|moi nhat)\b',n):return None
    raw=(Path(root)/NOTE).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:return None
    ds=json.loads(raw)['documents'];selected=[d for d in ds if d['cohort_from']<=cy<=d.get('cohort_to',2025)]
    holds=fresh_ledger(Path(root))
    if any('1011' in str(h.get('doc_id','')) or 'mien-hoc-mien-thi' in str(h.get('doc_id','')) or h.get('content_sha256')==PIN or h.get('source_path')==NOTE or any(h.get('doc_id')==d['doc_id'] or h.get('source_url')==d['url'] for d in selected) for h in holds):return None
    text='theo các thông báo UET lưu tham chiếu về Hướng dẫn 1011 (khóa QH-'+str(cy)+'):\n\n**Căn cứ đã có**\n'+'\n'.join('- '+f for d in selected for f in d['facts'])
    text+='\n\n**Các bước đề xuất:** kiểm tra chuẩn ngoại ngữ của ngành, cơ sở cấp và hạn sử dụng chứng chỉ; chuẩn bị bản sao công chứng; hỏi Phòng Đào tạo kênh tiếp nhận đang áp dụng, nộp minh chứng và theo dõi trạng thái công nhận. Không dùng biểu mẫu đầu khóa đã hết hạn làm kênh nộp hiện tại.\n\n**Chưa xác minh:** mẫu đơn, phòng tiếp nhận cụ thể, kênh online và thời gian xử lý hiện nay; chưa thể xác nhận chứng chỉ cá nhân đã được công nhận.'
    return public_result(text,[dict(src(NOTE,PIN),doc_id=d['doc_id'],source_url=d['url'],publication_date=d['date']) for d in selected],'language_notice_reference')

def graduation(root,q):
    n=norm(q);cy=cohort_request(q)
    if cy not in (2022,2023,2024,2025) or not re.search(r'\buet\b',n) or not re.search(r'\b(?:tot nghiep|xet tot nghiep)\b',n):return None
    if not re.search(r'\b(?:chuan bi|luu y|ra soat|kiem tra|ke hoach)\b',n):return None
    if sum(bool(re.search(p,n)) for p in (r'\btin chi\b',r'\b(?:ngoai ngu|tieng anh)\b',r'\b(?:hoc phan|mon)(?: con)? no\b',r'\b(?:xep loai|hang|loai bang)\b'))<2:return None
    if re.search(r'\b(?:so sanh|neu|gia su|ngoai le|dac cach|thac si|tien si|5115|3079|thong tu|nghi dinh|quy che moi|quy che cu)\b',n):return None
    cs=[pinned(root,f'Điều {a} khoản {k} QĐ 3626') for a,k in [(46,1),(47,5),(47,7)]]
    if not all(cs):return None
    # Use each actual clause independently to avoid the single-answer length cap.
    combined=dict(cs[0]);combined['articles']=[a for c in cs for a in c['articles']];combined['answer']='\n\n'.join(c['answer'] for c in cs)
    excerpts=[]
    for c in cs:
        _,sep,body=c['answer'].partition('\n\nĐiều ')
        if not sep:return None
        excerpts.append('Điều '+body)
    text='Dạ cô, với khóa QH-'+str(cy)+', em tách căn cứ trong QĐ 3626 và kế hoạch rà soát. Cần xác nhận văn bản áp dụng đúng khóa.\n\n**Điều kiện và xếp hạng theo nguồn**\n\n'+'\n\n'.join(excerpts)+'\n\n**Lời khuyên cho cố vấn:** đối chiếu CTĐT đúng ngành, tổng tín chỉ và từng học phần còn nợ; kiểm tra hồ sơ chuẩn đầu ra ngoại ngữ và các học phần điều kiện; rà CPA, tín chỉ phải học lại và tình trạng kỷ luật; thống nhất lịch xử lý từng mục với sinh viên và Phòng Đào tạo. Chưa có hồ sơ thì không kết luận đủ điều kiện tốt nghiệp.'
    return source_response(text,'graduation_checklist',combined),{}

def route(root,q,prior):
    if prior or not safe_public(q):return None
    n=norm(q)
    if re.search(r'\b(?:mssv|lop|em ay|ban ay|hutech|uit|bach khoa|thac si|tien si|2026|2027|2028|k71|k72)\b',n):return None
    # Explicit scope conflicts: use existing clarification rather than choosing a cohort.
    ys={1955+int(x) for x in re.findall(r'\bk(6[5-9]|7[0-9])\b',n)}|{int(x) for x in re.findall(r'\b(?:qh|khoa) (20\d{2})\b',n)}
    if len(ys)>1:return None
    try:return graduation(root,q) or language(root,q)
    except (OSError,ValueError,KeyError,TypeError):return None
