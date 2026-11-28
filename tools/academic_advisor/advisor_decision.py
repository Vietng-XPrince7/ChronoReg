"""Read-only, source-pinned decisions for explicit historical QD 3626 questions.
Never authorize an action or infer current applicability. No model-generated facts.
"""
import re, unicodedata
from quality import norm
from quality_routes import response,source_response
from advisor_evidence import fresh_ledger,blocked_qd
from regulation import read_articles,clause,TEXT,SOURCE_URL

OUTSIDE=re.compile(r'\b(?:k\d{2}|qh|20\d{2}|\d{8}|mssv|ma sinh vien|em ay|em nay|ho so|lop|ngoai le|dac cach|cuu xet|vuot quy che|lach|bo qua|khong can|gia mao|publication hold|tam khoa|chua duyet|hieu luc|ap dung|thong tu|nghi dinh|5115|3079|hutech|ulis|uit|bach khoa|so sanh|va neu|dong thoi tinh|soan|gui|phe duyet|quyet dinh cho)\b')
EXAM=re.compile(r'\b(?:du thi|thi ket thuc hoc phan)\b')
DEGREE=re.compile(r'\bvan bang thu hai\b')
CREDIT=re.compile(r'\b(?:bao luu|cong nhan)\b.*\b(?:ket qua|hoc phan|tin chi)\b')

def source(root,article,k):
    holds=fresh_ledger(root)
    if blocked_qd(holds):raise ValueError('held')
    data,sha=read_articles(root);title,body=data[article];text=' '.join(clause(body,k).split())
    if not text:raise ValueError('empty')
    return {'answer':text,'path':TEXT,'sha256':sha,'source_url':SOURCE_URL,'articles':[{'article':article,'clause':k}]}

def ascii_text(q):
    return ''.join(c for c in unicodedata.normalize('NFKD',q.lower().replace('đ','d')) if not unicodedata.combining(c))

def route(q,prior,root,*,red=False):
    n=norm(q);a=ascii_text(q)
    # Carry only explicitly supplied hypothetical inputs, not actual record grades.
    # A new topic, cohort, person or unrestricted continuation cannot inherit them.
    if not red and prior.get('kind')=='advisor_agent' and prior.get('topic')=='evidence_article' and not OUTSIDE.search(n):
        previous=prior.get('decision');facts=prior.get('facts',{})
        if previous=='exam' and re.fullmatch(r'(?:con |the |vay )?(?:neu )?diem (?:danh gia )?bo phan (?:bang |la |dat )?\d+(?: \d+)?(?: thi sao| co duoc du thi khong| khong)?',n):
            m=re.search(r'\bdiem (?:danh gia )?bo phan (?:bang |la |dat )?(\d+(?:[.,]\d+)?)',a)
            if not m:return None
            fee=' và đã đóng đủ học phí' if facts.get('fee') is True else ' và chưa đóng đủ học phí' if facts.get('fee') is False else ''
            q='Theo QĐ 3626, nếu điểm đánh giá bộ phận bằng '+m[1]+fee+' thì có đủ điều kiện dự thi kết thúc học phần không?'
        elif previous=='degree' and re.fullmatch(r'(?:con |the |vay )?(?:neu )?(?:noi dung )?tuong duong \d{1,3}(?: \d+)?(?: thi sao| khong)?',n):
            m=re.search(r'(\d{1,3}(?:[.,]\d+)?)\s*%',a)
            if not m:return None
            grade=' và điểm học phần '+facts['grade'] if facts.get('grade') in ('F','D','D+','C','C+','B','B+','A','A+','P') else ''
            q='Theo QĐ 3626, sinh viên có thể bảo lưu kết quả học tập khi học văn bằng thứ hai nếu nội dung tương đương '+m[1]+'%'+grade+' không?'
        elif previous=='degree' and type(facts.get('pct')) in (int,float) and 0<=facts['pct']<=100 and re.fullmatch(r'(?:con |the |vay )?(?:neu )?diem (?:hoc phan )?(?:la |bang |dat )?[abcdfp](?: thi sao| khong)?',n):
            m=re.search(r'\bdiem (?:hoc phan )?(?:la |bang |dat )?([abcdfp]\+?)(?=\s|[?.!,]|$)',a)
            if not m:return None
            q='Theo QĐ 3626, sinh viên có thể bảo lưu kết quả học tập khi học văn bằng thứ hai nếu nội dung tương đương '+str(facts['pct'])+'% và điểm học phần '+m[1]+' không?'
        n=norm(q);a=ascii_text(q)
    # Strict edition, no other instrument / date / personal record, no action.
    if not re.match(r'^(?:theo |can cu )?(?:qd|quyet dinh) 3626\b',n) or OUTSIDE.search(n) or len(q)>450:return None
    if re.search(r'\b(?:va (?:tinh|lap|viet|soan|tu van|gui)|hoac theo|quy che khac|van ban khac|ngoai quy dinh|khong theo quy dinh)\b',n):return None
    exam=bool(EXAM.search(n) and re.search(r'\b(?:dieu kien|co duoc|duoc khong|co the|co du|du thi khong)\b',n))
    degree=bool(DEGREE.search(n) and CREDIT.search(n))
    if exam==degree or len(re.findall(r'\b(?:qd|quyet dinh) \d+\b',n))!=1:return None
    if re.search(r'\b(?:khong phai|khong dung|thay vi|gia su khong|tru khi|hoac neu|ca hai truong hop|cho hai truong hop)\b',n):return None
    # Red branch is restricted to read-only equivalency interpretation: the
    # exact source is revalidated including the current hold ledger. No override
    # for exceptions, user-provided documents, record changes or general RED.
    if red and not (degree and re.search(r'\b(?:co the|co duoc|dieu kien|the nao|nhu the nao|duoc khong|khong|bao nhieu)\b',n) and not re.search(r'\b(?:xin|yeu cau|ho tro|giup|cho phep|chap thuan|xac nhan|quyet dinh|phe duyet|thuc hien|tra cuu ho so|dua vao he thong)\b',n.removeprefix('theo quyet dinh 3626').removeprefix('can cu quyet dinh 3626').removeprefix('quyet dinh 3626'))):return None
    nums=re.findall(r'\bdieu (\d+)\b',n); pars=re.findall(r'\bkhoan (\d+)\b',n)
    art,k=(38,1) if exam else (25,2)
    if nums and nums!=[str(art)] or pars and pars!=[str(k)]:return None
    try:
        c=source(root,art,k);s=norm(c['answer'])
        if exam:
            if not all(v in s for v in ('diem danh gia bo phan lon hon 0','tra hoc phi day du','dap ung cac dieu kien ket thuc hoc phan do thu truong don vi phu trach hoc phan quy dinh')):return None
            # Only evaluate a point if explicitly provided and unambiguous.
            points=re.findall(r'\bdiem (?:danh gia )?bo phan (?:bang |la |dat )?(\d+(?:[.,]\d+)?)\b',a)
            if len(points)>1 or re.search(r'\bdiem (?:danh gia )?bo phan (?:bang |la |dat )?-\s*\d',a):return None
            point=float(points[0].replace(',','.')) if points else None
            if point is not None and not 0<=point<=10:return None
            if re.search(r'\b(?:khong|chua) (?:dong|tra|nop) (?:du|day du) hoc phi\b',n):fee=False
            elif re.search(r'\b(?:da )?(?:dong|tra|nop) (?:du|day du) hoc phi\b',n):fee=True
            else:fee=None
            if point==0:lead='Dạ cô, **không đủ điều kiện dự thi theo QĐ 3626**, vì điểm đánh giá bộ phận bằng 0, kể cả đã đóng đủ học phí.' if fee is True else 'Dạ cô, **không đủ điều kiện dự thi theo QĐ 3626**, vì điểm đánh giá bộ phận phải lớn hơn 0.'
            elif fee is False:lead='Dạ cô, **chưa đủ điều kiện dự thi theo QĐ 3626** nếu chưa đóng đầy đủ học phí.'
            elif point is not None or fee is True:lead='Dạ cô, dữ kiện cô nêu đáp ứng '+('điều kiện điểm bộ phận và học phí' if point is not None and fee is True else 'điều kiện điểm bộ phận' if point is not None else 'điều kiện học phí')+', nhưng chưa đủ để kết luận sinh viên được dự thi.'
            else:lead='Dạ cô, theo QĐ 3626, sinh viên phải đáp ứng đồng thời ba điều kiện để dự thi kết thúc học phần.'
            body='\n\n- Điểm đánh giá bộ phận lớn hơn 0.\n- Đã trả học phí đầy đủ.\n- Đáp ứng các điều kiện kết thúc học phần do thủ trưởng đơn vị phụ trách học phần quy định.'
            tail='\n\nCô nên kiểm tra với giảng viên phụ trách và đơn vị đào tạo nếu có vấn đề về điểm hoặc học phí.'
        else:
            if not all(v in s for v in ('80 tro len noi dung tuong duong','diem hoc phan dat tu diem d tro len','50 den duoi 80','khong duoc bao luu ket qua hoc tap nhung co the tu hoc va du thi de lay diem','duoi 50','phai du hoc moi duoc du thi')):return None
            vals=re.findall(r'\b(\d{1,3}(?:[.,]\d+)?)\s*%',a)
            if len(vals)>1 or re.search(r'-\s*\d+(?:[.,]\d+)?\s*%',a):return None
            pct=float(vals[0].replace(',','.')) if vals else None
            if pct is not None and not 0<=pct<=100:return None
            # Source does not let us decide equivalence or actual credit recognition.
            grade_matches=re.findall(r'\bdiem (?:hoc phan )?(?:dat |la |bang )?([abcdfp](?:\+)?)\b',a)
            if len(grade_matches)>1:return None
            grade=grade_matches[0].upper() if grade_matches else None
            if pct is not None and pct>=80 and grade=='F':lead='Dạ cô, **không đáp ứng điều kiện bảo lưu** theo khoản này: nội dung đạt ngưỡng nhưng điểm F không đạt từ D trở lên.'
            elif pct is not None and pct>=80 and grade in ('D','D+','C','C+','B','B+','A','A+'):lead='Dạ cô, theo dữ kiện giả định, mức tương đương và điểm học phần đều đạt ngưỡng của khoản này. Đơn vị đào tạo vẫn phải xác định việc bảo lưu cụ thể.'
            elif pct is None:lead='Dạ cô, QĐ 3626 phân loại theo mức nội dung tương đương và điểm học phần.'
            elif pct>=80:lead='Dạ cô, mức tương đương này đạt ngưỡng nội dung, **nhưng còn phải có điểm học phần từ D trở lên** mới đáp ứng điều kiện bảo lưu theo khoản này.'
            elif pct>=50:lead='Dạ cô, theo khoản này **không được bảo lưu kết quả**, nhưng người học có thể tự học và dự thi để lấy điểm.'
            else:lead='Dạ cô, theo khoản này người học phải dự học mới được dự thi theo quy định chung.'
            body='\n\n- Từ 80% trở lên: bảo lưu nếu điểm học phần từ D trở lên.\n- Từ 50% đến dưới 80%: không bảo lưu, có thể tự học và dự thi.\n- Dưới 50% hoặc chưa học: phải dự học trước khi dự thi.'
            tail='\n\nViệc xác định nội dung tương đương và công nhận cụ thể cần được đơn vị đào tạo thẩm định; đây không phải quyết định công nhận tín chỉ.'
        r=source_response(lead+body+tail+f'\n\nCăn cứ: khoản {k} Điều {art} QĐ 3626. Đây là đối chiếu văn bản được hỏi, chưa xác nhận hiệu lực cho trường hợp cụ thể.','bounded_decision',c)
        r['metadata']['workflow_tools']=['policy_reference','condition_evaluation'];r['metadata']['decision_scope']='document_only'
        return r,{'kind':'advisor_agent','topic':'evidence_article','article':art,'decision':'exam' if exam else 'degree','facts':{'fee':fee,'point':point} if exam else {'pct':pct,'grade':grade}}
    except (OSError,ValueError,KeyError,TypeError):return None
