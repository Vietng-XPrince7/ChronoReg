"""Scoped multi-clause advice and dated language-notice guidance for Advisor Auto only."""
import re,json,hashlib
from pathlib import Path
from quality import norm
from quality_routes import pinned,source_response,response
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

def graduation_conditions(root,q):
    """General graduation-eligibility questions, regardless of word order.
    No inference of personal eligibility or cohort from the displayed roster.
    Narrow grammar excludes rank, credit calculations and other mixed tasks.
    """
    n=norm(q)
    if not safe_public(q):return None
    # Separate cohort tokens before intent matching; explicit unknown scopes
    # must not fall through to a 2022 rule presented as current policy.
    years={1955+int(x) for x in re.findall(r'\bk(\d{2})\b',n)}|{int(x) for x in re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?) (20\d{2})\b',n)}
    if re.search(r'\b(?:nam hoc|nam) 20\d{2}\b',n):return None
    t=re.sub(r'\b(?:k\d{2}|(?:qh|khoa(?: tuyen sinh)?) 20\d{2}|uet|dhqghn)\b',' ',n)
    t=' '.join(t.split())
    if 'tot nghiep' not in t or re.search(r'\b(?:co du dieu kien|da du dieu kien|du dieu kien tot nghiep khong)\b',t):return None
    # Only general information, not an eligibility decision for a transcript.
    grammar=r'(?:toi|em|minh|co|sinh vien|dai hoc|muon|can|de|duoc|xet|cong nhan|tot nghiep|dieu kien|yeu cau|gi|nhung|cac|nao|la|gom|co|phai|dap ung|dat|du|hoan thanh|nhu the nao|the nao|cho|hoi|biet|giup|voi|a|thi|nhung gi|gi vay|gi nhi|nhung dieu kien|can thiet|chuan bi|xin|liet ke|lam)'
    if not re.fullmatch(grammar+r'(?: '+grammar+r')*',t):return None
    if not re.search(r'\b(?:dieu kien|yeu cau|can|phai|dap ung)\b',t):return None
    if len(years)>1 or (years and not years.issubset({2022,2023,2024,2025})):
        return response('Dạ cô, em chưa xác minh được điều kiện tốt nghiệp theo khóa được hỏi. Cần đối chiếu quy chế đúng khóa tuyển sinh; em không tự áp dụng QĐ 3626 cho khóa khác.','graduation_scope_clarification'),{}
    c=pinned(root,'Điều 46 khoản 1 QĐ 3626')
    if not c:return response('Dạ cô, em chưa xác minh được nguồn Điều 46 để trả lời điều kiện tốt nghiệp. Cần kiểm tra lại tài liệu và khóa tuyển sinh; em không thay bằng đoạn quy định không liên quan.','graduation_source_unavailable'),{}
    _,sep,body=c['answer'].partition('\n\nĐiều 46, khoản 1')
    if not sep:return response('Dạ cô, em chưa đọc được đầy đủ khoản 1 Điều 46. Cần đối chiếu lại tài liệu gốc.','graduation_source_unavailable'),{}
    scope=('Với khóa QH-'+str(next(iter(years)))+', ' if years else 'Nếu thuộc khóa tuyển sinh 2022–2025, ')
    # Condense only when every required element of the pinned clause is present.
    # Keep the complete clause in source_response metadata, not the main answer.
    anchors=('thoi gian hoc tap toi da','khong dang trong thoi gian bi truy cuu trach nhiem hinh su','tich luy du so tin chi','tu 2 00 tro len','tu 2 50 tro len','tai nang','chat luong cao','ngoai ngu','hoc phan chuyen mon dac thu','giao duc quoc phong','giao duc the chat','ky nang bo tro','co don gui phong dao tao','som hoac muon')
    if all(x in norm(body) for x in anchors):
        main=('Điều 46, khoản 1 — Điều kiện tốt nghiệp:\n'
              '- Tích lũy đủ tín chỉ theo chương trình đào tạo và đáp ứng các yêu cầu bằng văn bản về học phần chuyên môn đặc thù (nếu có).\n'
              '- CPA toàn khóa từ 2,00 trở lên; chương trình tài năng hoặc chất lượng cao từ 2,50 trở lên.\n'
              '- Đạt chuẩn ngoại ngữ theo khoản 3 Điều 13; đạt các học phần giáo dục quốc phòng – an ninh, giáo dục thể chất và kỹ năng bổ trợ.\n'
              '- Nằm trong thời gian học tập tối đa và không đang bị truy cứu trách nhiệm hình sự tại thời điểm xét.\n'
              '- Nếu tốt nghiệp sớm hoặc muộn so với thời gian thiết kế, cần gửi đơn đề nghị xét tốt nghiệp tới Phòng Đào tạo.')
    else:main='Điều 46, khoản 1'+body
    text='Dạ cô, '+scope+'các điều kiện tốt nghiệp theo khoản 1 Điều 46 của Quyết định 3626/QĐ-ĐHQGHN gồm:\n\n'+main+'\n\n**Cần làm gì:** đối chiếu tổng tín chỉ và các học phần còn thiếu theo CTĐT đúng ngành, CPA, chuẩn ngoại ngữ, các học phần điều kiện và thời gian đào tạo. Đây là căn cứ chung, chưa xác nhận cá nhân đủ điều kiện. '+('Cần xác nhận quy chế áp dụng đúng khóa và các thông báo bổ sung của UET.' if years else 'Cô cho em biết khóa tuyển sinh và ngành để đối chiếu cụ thể hơn.')
    return source_response(text,'graduation_conditions',c),{}

def graduation_rank(root,q):
    """Topic-first classification: rank of a degree is not scholarship rank.
    Public, non-personal guidance only; keep numeric simulations and mixed tasks separate.
    """
    n=norm(q)
    # Accent stripping already handles xuât/xuất; repair only local spelling variants.
    n=re.sub(r'\b(?:suat sac|xuat xac)\b','xuat sac',n)
    degree=re.search(r'\b(?:tot nghiep|bang tot nghiep|bang dai hoc|ra truong|bang (?:loai )?(?:xuat sac|gioi|kha|trung binh))\b',n)
    rank=re.search(r'\b(?:xuat sac|gioi|kha|trung binh|xep (?:hang|loai)|hang|loai bang|phan loai)\b',n)
    if not degree or not rank:return None
    if re.search(r'\b(?:chuan bi|luu y|ra soat|kiem tra|ke hoach)\b',n) and sum(bool(re.search(p,n)) for p in (r'\btin chi\b',r'\b(?:ngoai ngu|tieng anh)\b',r'\b(?:hoc phan|mon)(?: con)? no\b',r'\b(?:xep loai|hang|loai bang)\b'))>=2:return None
    if not safe_public(re.sub(r'\b(?:cpa|gpa)\b','diem',n)+' tot nghiep'):return None
    if re.search(r'\b(?:hoc bong|kkht|hoc phi|tuyen sinh|thac si|tien si|so sanh|so voi|quy che cu|quy che moi|thong tu|nghi dinh|5115|3079|ngoai le|dac cach|neu|gia su|hoc lai|thi lai|truot|rot|ky luat|ha (?:hang|bang|loai)|giam (?:hang|loai)|bao nhieu tin chi|con lai|hien tai|cua toi|cua em|cua minh|cua co|cua ban|duoc khong|co the khong)\b',n):return None
    # Do not decide personal eligibility, infer a cohort or confuse calendar year with cohort.
    if re.search(r'\b\d+(?: \d+)?\s*(?:tin chi|tc|diem|cpa|gpa)\b|\b(?:cpa|gpa|diem)\s*\d',n):return None
    years={1955+int(x) for x in re.findall(r'\bk(\d{2})\b',n)}|{int(x) for x in re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?) (20\d{2})\b',n)}
    all_years={int(x) for x in re.findall(r'\b20\d{2}\b',n)}
    if len(years)>1 or not years.issubset({2022,2023,2024,2025}) or not all_years.issubset(years) or re.search(r'\bnam(?: hoc)? 20\d{2}\b',n):
        return response('Dạ cô, cần xác minh quy chế xếp hạng tốt nghiệp đúng khóa tuyển sinh. Em chưa thể áp dụng ngưỡng của QĐ 3626 cho khóa hoặc thời điểm được hỏi.','graduation_rank_scope'),{}
    cs=[pinned(root,f'Điều {a} khoản {k} QĐ 3626') for a,k in [(46,1),(47,5),(47,7)]]
    def unavailable():return response('Dạ cô, em chưa xác minh đủ Điều 46 và Điều 47 của QĐ 3626. Em không dùng mức xếp loại học bổng thay cho xếp hạng tốt nghiệp.','graduation_rank_source_unavailable'),{}
    if not all(cs):return unavailable()
    # Extract the actual four rank ranges from the pinned clause; no numeric answer-bank.
    t=cs[1]['answer']; ranges={}
    for label,low,high in re.findall(r'(Xuất sắc|Giỏi|Khá|Trung bình)\s*:\s*Điểm trung bình chung tích lũy từ\s*(\d[,.]\d{2})\s*đến\s*(\d[,.]\d{2})',t,re.I):
        ranges[norm(label)]=(label,low.replace('.',','),high.replace('.',','))
    reduction=cs[2]['answer']; pct=re.search(r'vượt quá\s*(\d+(?:[,.]\d+)?)\s*%',reduction,re.I)
    if set(ranges)!={'xuat sac','gioi','kha','trung binh'} or not pct or 'canh cao' not in norm(reduction) or 'xuat sac' not in norm(reduction) or 'gioi' not in norm(reduction):return unavailable()
    if not all(x in norm(cs[0]['answer']) for x in ('tin chi','ngoai ngu','thoi gian','giao duc the chat')):return unavailable()
    rank_words=re.sub(r'\bdiem trung binh(?: chung)?(?: tich luy)?\b','diem',n)
    selected=[k for k in ('xuat sac','gioi','kha','trung binh') if re.search(r'\b'+k+r'\b',rank_words)]
    scope=('Với khóa QH-'+str(next(iter(years))) if years else 'Nếu thuộc khóa tuyển sinh 2022–2025')
    text='Dạ cô, '+scope+' và áp dụng QĐ 3626, '
    if len(selected)==1:
        key=selected[0];label,low,high=ranges[key]
        text+='mức CPA toàn khóa tương ứng với hạng tốt nghiệp **'+label+'** (trước khi xét hạ hạng) là **'+low+'–'+high+'/4,00** (khoản 5 Điều 47).'
        if key=='xuat sac':text+=' Ngoài ngưỡng CPA, cần tránh các trường hợp bị hạ hạng.'
    else:
        text+='xếp hạng tốt nghiệp căn cứ CPA toàn khóa (khoản 5 Điều 47):\n'+'\n'.join('- '+label+': '+low+'–'+high for label,low,high in ranges.values())
    text+='\n\n**Điều kiện khác cần lưu ý:**\n- Theo khoản 7 Điều 47, hạng Giỏi hoặc Xuất sắc bị hạ một hạng nếu khối lượng học phần phải học lại vượt quá '+pct[1]+'% tổng tín chỉ toàn CTĐT hoặc bị kỷ luật từ mức cảnh cáo trở lên.\n- Phải đáp ứng điều kiện tốt nghiệp tại khoản 1 Điều 46: đủ tín chỉ, CPA tối thiểu theo chương trình, chuẩn ngoại ngữ, các học phần điều kiện và những yêu cầu khác, trong thời gian đào tạo tối đa.\n\n**Cách thực hiện (lời khuyên):** theo dõi CPA tích lũy chứ không chỉ GPA từng kỳ; ưu tiên đạt kết quả tốt, hạn chế học lại; kiểm tra các học phần còn nợ và chuẩn đầu ra theo CTĐT đúng ngành. Chưa có bảng điểm và số tín chỉ thì không thể tính mức GPA cần đạt ở các kỳ còn lại.\n\nCăn cứ: khoản 1 Điều 46, khoản 5 và 7 Điều 47 QĐ 3626/QĐ-ĐHQGHN. Cần xác nhận văn bản áp dụng đúng khóa.'
    combined=dict(cs[0]);combined['articles']=[a for c in cs for a in c['articles']];combined['answer']='\n\n'.join(c['answer'] for c in cs)
    return source_response(text,'graduation_rank_advice',combined),{}

def route(root,q,prior):
    ranked=graduation_rank(root,q)
    if ranked is not None:return ranked
    simple=graduation_conditions(root,q)
    if simple is not None:return simple
    if prior or not safe_public(q):return None
    n=norm(q)
    if re.search(r'\b(?:mssv|lop|em ay|ban ay|hutech|uit|bach khoa|thac si|tien si|2026|2027|2028|k71|k72)\b',n):return None
    # Explicit scope conflicts: use existing clarification rather than choosing a cohort.
    ys={1955+int(x) for x in re.findall(r'\bk(6[5-9]|7[0-9])\b',n)}|{int(x) for x in re.findall(r'\b(?:qh|khoa) (20\d{2})\b',n)}
    if len(ys)>1:return None
    try:return graduation(root,q) or language(root,q)
    except (OSError,ValueError,KeyError,TypeError):return None
