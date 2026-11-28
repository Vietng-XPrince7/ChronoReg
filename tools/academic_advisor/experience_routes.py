"""Advisor-only typed continuation and scoped historical notice reference.
No research-engine changes, no publication approval, no personal decisions.
"""
import hashlib, re, json
from pathlib import Path
from quality import norm
from quality_routes import response
from whatif import simulate

NOTICE_PATH='data/raw/uet/markdown/2024/Chương_trình_đào_tạo_sau_đại_học_2024.md'
NOTICE_BLOB='d4b4c4186a3045748b6ddac7379394647dcc4f92'
NOTICE_URL='https://uet.vnu.edu.vn/thong-bao-tuyen-sinh-dao-tao-thac-si-dot-1-nam-2024/'
NOTICE_SCOPE='master_admission_2024_round1_language'
NUMBER=r'([+-]?\d{1,3}(?:[.,]\d{1,2})?)'


def _notice(root):
    root=Path(root); p=(root/NOTICE_PATH).resolve(); p.relative_to(root.resolve())
    raw=p.read_bytes(); canonical=raw.replace(b'\r\n',b'\n')
    if hashlib.sha1(b'blob '+str(len(canonical)).encode()+b'\0'+canonical).hexdigest()!=NOTICE_BLOB:
        raise ValueError('Notice source changed')
    shas={hashlib.sha256(x).hexdigest() for x in (raw,canonical,canonical.decode('utf-8-sig').encode('utf-8'))}
    ledger=root/'data/versioning/publication_holds.jsonl'
    for line in ledger.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():continue
        row=json.loads(line)
        if not row.get('doc_id') or not row.get('content_sha256'):raise ValueError('Invalid hold')
        if row['content_sha256'] in shas or 'chuong-trinh-dao-tao-sau-dai-hoc-2024' in row['doc_id']:
            raise ValueError('Notice held')
    text=canonical.decode('utf-8-sig')
    parts=re.split(r'(?m)^\*\*\*1\.2\. Yêu cầu về ngoại ngữ\*\*\*\s*$',text)
    if len(parts)!=2:raise ValueError('Missing exact section')
    section=re.split(r'(?m)^\*\*\*1\.3\. Yêu cầu khác\*\*\*\s*$',parts[1])[0]
    level=re.findall(r'Thí sinh có năng lực Tiếng Anh từ Bậc (\d) trở lên theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam',section)
    years=re.findall(r'trong thời hạn (\d+) năm kể từ ngày thi chứng chỉ/chứng nhận đến ngày đăng ký dự tuyển',section)
    online='không chấp nhận sử dụng chứng chỉ ngoại ngữ thi theo hình thức trực tuyến' in section
    if level!=['3'] or years!=['2'] or not online:raise ValueError('Scoped review assertions no longer match')
    return int(level[0]),int(years[0]),hashlib.sha256(raw).hexdigest()


def notice_route(q,prior,root):
    n=norm(q)
    if re.search(r'\b(?:tien si|dai hoc khac|truong khac|ulis|uit|hutech|bach khoa|mssv|\d{8}|ca lop|sinh vien nay|em ay|em nay|hoc phi|hoc bong|diem chuan|ielts|toeic|toefl|vstep|b1|b2|c1|chung chi cua|cua em|cua toi|du dieu kien|xet tuyen thang|mien ngoai ngu|so sanh|va dieu kien|nam hoc|hien nay|moi nhat)\b',n):return None
    years=set(re.findall(r'\b20\d{2}\b',n)); rounds=set(re.findall(r'\bdot (\d+)\b',n))
    explicit=bool(re.search(r'\bthac si\b',n) and re.search(r'\b(?:uet|dai hoc cong nghe|dh cong nghe)\b',n) and years=={'2024'} and rounds=={'1'})
    carry=prior.get('kind')=='advisor_experience_notice' and prior.get('scope')==NOTICE_SCOPE
    if not explicit and not (carry and not years and not rounds and not re.search(r'\b(?:thac si|tuyen sinh|truong khac|dot khac|nam khac)\b',n)):return None
    # For a continuation, require an explicit language-related question, not an arbitrary follow-up.
    lang=bool(re.search(r'\b(?:tieng anh|ngoai ngu|chung chi|chung nhan)\b',n))
    online=lang and bool(re.search(r'\b(?:truc tuyen|online)\b',n))
    validity=lang and bool(re.search(r'\b(?:hieu luc|thoi han|bao lau|may nam|bao nhieu nam|con han)\b',n))
    level=lang and bool(re.search(r'\b(?:bac|trinh do|toi thieu|yeu cau|nang luc)\b',n))
    # Only reference the checked fields, not general admissions eligibility or document equivalence.
    if not (online or validity or level) or re.search(r'\b(?:nganh nao|bang nao|bao nhieu diem|quy doi|tuong duong bao nhieu|dieu kien khac|ho so|thu tuc|nop gi|chung chi nao)\b',n):return None
    try: b,y,sha=_notice(root)
    except (OSError,ValueError,TypeError,UnicodeError,KeyError,AttributeError):return None
    lines=[]
    if level and not (online or validity):lines.append(f'Dạ cô, yêu cầu là năng lực tiếng Anh từ bậc {b} trở lên theo khung 6 bậc của Việt Nam.')
    if validity:lines.append(f'Chứng chỉ/chứng nhận tiếng Anh thuộc diện được chấp nhận phải còn trong thời hạn {y} năm, tính từ ngày thi đến ngày đăng ký dự tuyển.')
    if online:lines.append('Thông báo không chấp nhận chứng chỉ ngoại ngữ thi trực tuyến.')
    if not lines:return None
    text='\n'.join(lines)+'\n\nCăn cứ: mục 1.2, thông báo tuyển sinh thạc sĩ UET đợt 1 năm 2024. Đây là thông tin của đợt đó, không tự áp dụng cho đợt khác.\n'+NOTICE_URL
    r=response(text,'public_notice_reference',['policy_reference'],[{'source_path':NOTICE_PATH,'sha256':sha,'source_url':NOTICE_URL}]);r['metadata'].update(engine_mode='ADVISOR_EVIDENCE',inference_source='deterministic_scoped_notice',source_path=NOTICE_PATH,sha256=sha,source_url=NOTICE_URL,doc_title='Thông báo tuyển sinh thạc sĩ UET đợt 1 năm 2024',quality_qualified=False,review_scope='three language facts checked against official search excerpts and exact team source; not full document approval')
    return r,{'kind':'advisor_experience_notice','scope':NOTICE_SCOPE}


def _calc_response(result):
    r=response('Dạ cô, '+result['answer'][:1].lower()+result['answer'][1:],'hypothetical_cpa',['cpa_calculator']);r['metadata'].update(engine_mode='ADVISOR_SIMULATION',inference_source='deterministic_calculator',simulation=result)
    return r,{'kind':'advisor_experience_cpa','inputs':result['inputs']} if result['status']=='calculated' else {}


def cpa_route(q,prior,delta_only=False):
    result=None if delta_only else simulate(q)
    if result is not None:return _calc_response(result)
    if prior.get('kind')!='advisor_experience_cpa':return None
    # Full-match delta only: never ignore extra requirements or reuse actual student data.
    m=re.fullmatch(r'\s*(?:còn nếu|nếu|thế nếu|vậy nếu)\s+(?:(?:học )?kỳ (?:tới|sau)\s+)?(?:chỉ\s+)?(?:đạt\s+)?GPA\s*(?:là|=|đạt)?\s*'+NUMBER+r'\s*(?:thì sao|thế nào|thì thế nào)?[?!.\s]*',q,re.I)
    field='gpa'
    if not m:
        m=re.fullmatch(r'\s*(?:còn nếu|nếu|thế nếu|vậy nếu)\s+(?:(?:học )?kỳ (?:tới|sau)\s+)?(?:chỉ\s+)?(?:học|học thêm|tích lũy thêm)\s*'+NUMBER+r'\s*(?:tín chỉ|tc)\s*(?:thì sao|thế nào|thì thế nào)?[?!.\s]*',q,re.I);field='new'
    if not m:
        # Accept a bounded natural-language delta, including polite trailing requests.
        m=re.fullmatch(r'\s*(?:còn nếu|nếu|thế nếu|vậy nếu)\s+(?:(?:học )?kỳ (?:tới|sau|tiếp theo)\s+)?(?:chỉ\s+)?(?:đạt\s+)?GPA\s*(?:là|=|đạt)?\s*'+NUMBER+r'\s*(?:thì (?:kết quả |CPA )?(?:thay đổi |sẽ )?(?:thế nào|như thế nào|ra sao|bao nhiêu)|thì sao)?[?!.\s]*',q,re.I)
        field='gpa'
    if not m:
        m=re.fullmatch(r'\s*(?:thay bằng|đổi thành|giảm còn|tăng lên|chỉ học|học thêm)\s*'+NUMBER+r'\s*(?:tín chỉ|tc)\s*(?:thôi)?\s*(?:,\s*(?:còn )?(?:các )?giả định khác giữ nguyên(?: nhé)?)?[?!.\s]*',q,re.I)
        field='new'
    if not m:return None
    values=prior.get('inputs',{})
    if set(values)!={'cpa','earned','new','gpa'} or any(not isinstance(x,str) or not re.fullmatch(NUMBER,x) for x in values.values()):return None
    vals=dict(values);vals[field]=m[1]
    expanded='Giả sử CPA hiện tại {cpa}; đã tích lũy {earned} tín chỉ; học thêm {new} tín chỉ; GPA kỳ tới {gpa}. Tính CPA mới.'.format(**vals)
    result=simulate(expanded)
    if result is None:return None
    return _calc_response(result)


def route(q,prior,root,allow_calculation=True):
    if allow_calculation:
        calculated=cpa_route(q,prior)
        if calculated and (calculated[1] or prior.get('kind')=='advisor_experience_cpa'):
            return calculated
    return notice_route(q,prior,root)
