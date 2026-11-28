"""Scoped invitation drafting. Typed revision state, no generated prose or grades in tokens.
The drafts are deliberately bounded; no message delivery or external model calls.
"""
import re
from quality import norm
from quality_routes import response,find_student
from quality_workflows import snapshot
from workflow import scope_error

WRITE=re.compile(r'\b(?:soan|viet|tao|chuan bi)\b')
FORMAT=re.compile(r'\b(?:email|tin nhan|loi nhan|thong bao|thu moi)\b')
PUBLIC=re.compile(r'\b(?:ca lop|toan lop|thong bao chung|cong khai|nhom lop)\b')
INVITE=re.compile(r'\b(?:moi|hen|trao doi|tu van)\b')
EDIT=re.compile(r'\b(?:viet lai|viet ngan|ngan gon|ngan hon|rut gon|than thien|nhe nhang|khong gay ap luc|trang trong|doi giong|sua|giu nguyen|tieu de|chuyen sang|doi sang|chuyen (?:tu )?(?:email|tin nhan|loi nhan|thong bao|thu moi) sang|doi (?:tu )?(?:email|tin nhan|loi nhan|thong bao|thu moi) sang)\b')
OTHER=re.compile(r'\b(?:hoc phi|hoc bong|diem chuan|quy che|lich hoc|tien quyet|ha hang|canh bao hoc vu|bao cao|phan tich|sang loc|gui ngay|gui email|soan email gui|cham diem|dinh kem)\b')

def route(q,n,prior,explicit,classified,roster):
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic')=='draft' else {}
    # Bridge existing validated semantic invitation tasks (no model-generated prose).
    if not old and prior.get('kind')=='semantic_task' and prior.get('plan',{}).get('intent')=='draft':
        s=prior['plan'].get('slots',{})
        if s.get('draft_purpose')=='invite':old={'scope':prior.get('scope'),'audience':s.get('audience'),'format':s.get('format'),'student':s.get('student'),'subject':s.get('subject'),'max_words':s.get('max_words',80),'tone':'friendly','short':False,'prepare':bool(s.get('prepare_issue'))}
    # A public invitation phrased as an intention to send still produces only
    # a draft. Actual sending is not implemented or claimed.
    wants_public_invite=bool(re.search(r'\b(?:muon|can|du dinh) gui thong bao(?: chung)?\b',n) and PUBLIC.search(n) and INVITE.search(n))
    new=bool((WRITE.search(n) or wants_public_invite) and FORMAT.search(n) and INVITE.search(n))
    edit=bool(old and EDIT.search(n) and (FORMAT.search(n) or re.search(r'\b(?:ban nhap|noi dung|phan than|tieu de|giong|than thien|nhe nhang|ngan gon|ngan hon|viet ngan|rut gon|trang trong|khong gay ap luc)\b',n)))
    public_switch=bool(old and WRITE.search(n) and FORMAT.search(n) and PUBLIC.search(n))
    if not (new or edit or public_switch) or OTHER.search(n):return None
    # Do not swallow aggregate/class agenda requests or unrelated new tasks.
    if re.search(r'\b(?:\d+ phut|chuong trinh buoi|ke hoach buoi|lop khac|sinh vien khac|hutech|ulis|uit|bach khoa)\b',n):return None
    def fail(text,state=None):return response('Dạ cô, '+text,'draft_clarification'),state or {}
    sig=snapshot(roster);ids=set(re.findall(r'\b\d{8}\b',q))
    if len(ids)>1:return fail('cô xác nhận một người nhận cho bản nháp riêng.')
    sid=next(iter(ids),None) or explicit or classified
    if explicit and ids and str(explicit) not in ids:return fail('mã sinh viên trong yêu cầu không khớp hồ sơ được chọn.')
    if old and not new and old.get('scope')!=sig:return fail('hồ sơ đã thay đổi, cô xác nhận lại người nhận trước khi chỉnh sửa.')
    if scope_error(n,roster):return fail('cô xác nhận lớp hoặc hồ sơ đúng phạm vi.')
    carry=old if edit and not (public_switch and not FORMAT.search(n)) and old.get('scope')==sig else {}
    if public_switch and old.get('audience')=='private' and not edit:carry={}
    public=bool(PUBLIC.search(n)) or (not sid and carry.get('audience')=='class')
    if public and (ids or explicit or classified):return fail('em không đưa mã sinh viên vào thông báo chung. Cô xác nhận gửi chung hay soạn riêng?')
    sid=None if public else str(sid or carry.get('student') or '')
    if not public and not find_student(roster,sid):return fail('cô chọn hồ sơ sinh viên cần mời, hoặc cho em biết nếu đây là thông báo chung.')
    conversions=re.findall(r'\b(?:chuyen|doi)(?: tu)?(?: email| tin nhan| loi nhan| thong bao| thu moi)? sang (email|tin nhan|loi nhan|thong bao|thu moi)\b',n)
    if len(set(conversions))>1:return fail('cô xác nhận một định dạng đích cho bản nháp.',carry)
    target=conversions[0] if conversions else None
    fmt=({'email':'email','thu moi':'email','tin nhan':'message','loi nhan':'message','thong bao':'notice'}[target] if target else 'email' if 'email' in n or 'thu moi' in n else 'message' if 'tin nhan' in n or 'loi nhan' in n else 'notice' if 'thong bao' in n else carry.get('format','email'))
    # Only neutral titles and invitation purposes. Don't insert invented dates, locations or details.
    safe_n=re.sub(r'\bkhong (?:tiet lo|neu|cong khai) (?:thong tin ca nhan|diem|ten|ma)(?: ca nhan)?\b','',n)
    if re.search(r'\b(?:ngay \d|luc \d|\d+ gio|phong \d|dia diem|tiet lo|neu diem|neu ten|neu ma)\b',safe_n):return None
    subject=carry.get('subject') or 'Mời trao đổi học tập'
    if norm(subject) not in {'moi trao doi hoc tap','trao doi hoc tap','chuan bi tu van','tu van hoc tap','hen trao doi hoc tap','ke hoach hoc tap'}:subject='Mời trao đổi học tập'
    if 'tieu de' in n and not re.search(r'\bgiu (?:nguyen )?tieu de\b',n):return None
    tone='formal' if 'trang trong' in n else 'friendly' if re.search(r'\b(?:than thien|nhe nhang|khong gay ap luc)\b',n) else carry.get('tone','friendly')
    short=bool(re.search(r'\b(?:ngan gon|ngan hon|rut gon|viet ngan)\b',n)) or bool(carry.get('short'))
    limits=set(map(int,re.findall(r'\b(\d{1,3}) tu\b',n)))
    if len(limits)>1:return fail('cô xác nhận một giới hạn số từ.')
    limit=next(iter(limits),carry.get('max_words',80));prepare=bool(re.search(r'\b(?:chuan bi|mang theo)\b.*\b(?:van de|cau hoi)\b',n)) or bool(carry.get('prepare'))
    if not 1<=limit<=300:return fail('giới hạn phần thân cần từ 1 đến 300 từ.')
    if public:
        full='Các em thân mến,\n\nCô muốn có một buổi trao đổi về việc học và những điều các em cần hỗ trợ. Các em có thể chuẩn bị câu hỏi trước buổi gặp. Nếu có vấn đề riêng, các em cứ trao đổi trực tiếp với cô nhé.\n\nThời gian và địa điểm cô sẽ thông báo sau.'
        brief='Các em thân mến, cô mời các em trao đổi về việc học. Các em chuẩn bị câu hỏi nhé.'
    else:
        full=('Chào em,\n\nCô muốn hẹn em một buổi trao đổi về việc học, lắng nghe những khó khăn em đang gặp và cùng tìm cách hỗ trợ phù hợp. Em cho cô biết thời gian thuận tiện để mình sắp xếp nhé.\n\nCảm ơn em,\nCô')
        brief='Chào em, cô muốn hẹn em trao đổi về việc học và hỗ trợ em nếu cần. Em chọn thời gian thuận tiện nhé.'
    if tone=='formal':
        full=('Các em thân mến,\n\nCô mời các em tham gia buổi trao đổi về tình hình học tập và kế hoạch hỗ trợ. Thời gian, địa điểm sẽ được thông báo sau.' if public else 'Chào em,\n\nCô mời em tham gia buổi trao đổi về tình hình học tập để thống nhất phương án hỗ trợ phù hợp. Em vui lòng phản hồi thời gian có thể tham gia.\n\nTrân trọng,\nCô')
        brief=('Cô mời các em trao đổi về tình hình học tập. Thời gian sẽ được thông báo sau.' if public else 'Cô mời em trao đổi về tình hình học tập. Em vui lòng phản hồi thời gian thuận tiện.')
    if prepare and not public:full+='\nEm có thể chuẩn bị một câu hỏi muốn trao đổi trước buổi gặp.';brief+=' Em chuẩn bị một câu hỏi nhé.'
    candidates=[brief] if short else [full,brief]
    body=next((x for x in candidates if len(x.split())<=limit),None)
    if body is None:return fail('giới hạn từ chưa đủ để giữ ý lời mời; cô có thể tăng giới hạn.',carry)
    text=('**Tiêu đề:** '+subject+'\n\n' if fmt=='email' else '')+body
    if wants_public_invite:text='**Bản nháp thông báo chung (chưa gửi)**\n\n'+text
    state={'kind':'advisor_agent','topic':'draft','scope':sig,'audience':'class' if public else 'private','format':fmt,'subject':subject,'tone':tone,'short':short,'max_words':limit,'prepare':prepare}
    if not public:state['student']=sid
    return response(text,'communication_draft',['scope_check','communication_draft'],category='CLASS_STATS' if public else 'STUDENT_STATUS'),state
