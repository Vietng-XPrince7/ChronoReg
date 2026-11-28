"""Bounded academic counseling and draft execution. No sending, personal prose,
external model calls or roster-derived details in messages. Typed slots only.
"""
import re
from quality import norm
from quality_routes import response, find_student
from workflow import screening

PUBLIC=re.compile(r'\b(?:ca lop|toan lop|cong khai|thong bao chung|email chung)\b')
DRAFT=re.compile(r'\b(?:email|tin nhan|thong bao|loi nhan|loi moi)\b')
WRITE=re.compile(r'\b(?:viet|soan|tao|cho|moi|chuyen|rut|giu|them|sua)\b')
COUNSEL=re.compile(r'\b(?:tu van|trao doi|ho tro|mo dau|tu hoc|hoc nhom)\b')
COMBINED=re.compile(r'\b(?:nhom can ho tro|sang loc|phan nhom|tom tat|bao cao noi bo)\b')
OTHER=re.compile(r'\b(?:hoc phi|hoc bong|diem chuan|quy che|tien quyet|ha hang|canh bao hoc vu)\b')

def candidate(q):
    n=norm(q)
    if OTHER.search(n):return False
    # Scope of this adapter: invitation emails, mixed screening+draft,
    # preparation of counseling openings and time-bounded support.
    return bool((DRAFT.search(n) and WRITE.search(n) and ('email' in n or (PUBLIC.search(n) and COMBINED.search(n)))) or (COUNSEL.search(n) and re.search(r'\b(?:mo dau|phut moi ngay|phut tu hoc)\b',n) and re.search(r'\b\d{8}\b',n)))

def guard(p,q,old):
    n=norm(q);i=p['intent'];s=p['slots'];before=(old or {}).get('slots',{}) if (old or {}).get('intent')==i else {}
    if i=='draft':
        # Privacy is a non-negotiable default for the academic invitation tool.
        s['exclude_private']=True
        if PUBLIC.search(n):s['audience']='class';s.pop('student',None)
        elif 'tin nhan rieng' in n or 'email rieng' in n:s['audience']='private'
        if 'email' in n:s['format']='email'
        elif 'thong bao' in n and PUBLIC.search(n):s['format']='notice'
        elif 'tin nhan' in n or 'loi nhan' in n:s['format']='message'
        counts=set(map(int,re.findall(r'\b(\d{1,3}) tu\b',n)))
        if len(counts)>1:raise ValueError('ambiguous word limit')
        if counts:s['max_words']=counts.pop()
        elif 'max_words' in before:s['max_words']=before['max_words']
        else:s.pop('max_words',None)
        ids=set(re.findall(r'\b\d{8}\b',q))
        if PUBLIC.search(n):s['audience']='class';s.pop('student',None)
        elif ids:
            if len(ids)>1:raise ValueError('ambiguous recipient')
            if s.get('student') not in (None,next(iter(ids))):raise ValueError('recipient mismatch')
            s['student']=next(iter(ids));s['audience']='private'
        elif s.get('audience')=='class':
            if before.get('audience')=='private':raise ValueError('audience change not requested')
            s.pop('student',None)
        # Only a neutral academic subject is allowed here. Do not echo an
        # arbitrary subject (which might contain personal information).
        subject=s.get('subject')
        neutral={'trao doi hoc tap','chuan bi tu van','moi trao doi hoc tap','tu van hoc tap','hen trao doi hoc tap','ke hoach hoc tap'}
        if not subject and 'tieu de' in n:
            m=re.search(r'(?i)tiêu đề\s*[:：]?\s*([^,;.]+)',q)
            if m and norm(m[1]) in neutral:subject=m[1].strip();s['subject']=subject
        if subject and subject!=before.get('subject'):
            if norm(subject) not in n:s.pop('subject',None)
            elif norm(subject) not in neutral:raise ValueError('non-neutral subject')
        if s.get('subject') and norm(s['subject']) not in neutral:raise ValueError('non-neutral subject')
        if re.search(r'\bgiu (?:nguyen )?tieu de\b',n):
            if not before.get('subject'):raise ValueError('missing original subject')
            s['subject']=before['subject']
        s['include_summary']=bool(PUBLIC.search(n) and COMBINED.search(n))
        if re.search(r'\b(?:chuan bi|mang theo)\b.*\b(?:van de|cau hoi)\b',n):s['prepare_issue']=True
        elif 'prepare_issue' in before:s['prepare_issue']=before['prepare_issue']
        else:s.pop('prepare_issue',None)
        # The planner must establish an invitation task; arbitrary writing is
        # not silently replaced with this specific academic template.
        if not (before.get('draft_purpose')=='invite' or re.search(r'\b(?:moi|hen|trao doi|tu van|ho tro)\b',n) or s.get('include_summary')):raise ValueError('unsupported draft purpose')
        s['draft_purpose']='invite'
    elif i=='counseling':
        if re.search(r'\b(?:rieng tu|bao mat|khong muon chia se|khong chia se)\b',n):s['counsel_action']='privacy'
        elif 'mo dau' in n:s['counsel_action']='opening'
        elif re.search(r'\b(?:phut|tu hoc|hoc nhom)\b',n):s['counsel_action']='study_plan'
        elif s.get('counsel_action')!=before.get('counsel_action'):raise ValueError('unsupported counseling action')
        for field,pattern in [('minutes',r'\b(\d{1,3}) phut\b'),('days',r'\b(\d{1,2}) ngay\b')]:
            vals=set(map(int,re.findall(pattern,n)))
            if len(vals)>1:raise ValueError('ambiguous duration')
            if vals:s[field]=vals.pop()
            elif field=='days' and 'mot tuan' in n:s[field]=7
            elif field in before:s[field]=before[field]
            else:s.pop(field,None)
        if re.search(r'\b(?:hoc mot minh|tu hoc mot minh|khong muon hoc nhom)\b',n):s['preference']='individual'
        elif 'hoc nhom' in n:s['preference']='group'
        elif 'preference' in before:s['preference']=before['preference']
        else:s.pop('preference',None)
        if s.get('counsel_action')=='opening':
            m=re.search(r'\b(\d|mot|hai|ba|bon|nam) (?:cach|loi|cau) mo dau\b',n)
            if m:s['opening_count']={'mot':1,'hai':2,'ba':3,'bon':4,'nam':5}.get(m[1],int(m[1]) if m[1].isdigit() else 0)
            elif 'opening_count' in before:s['opening_count']=before['opening_count']
            else:s.pop('opening_count',None)
    return p

def execute(p,roster):
    i=p['intent'];s=p['slots'];sid=s.get('student')
    def fail(msg):return response('Dạ cô, '+msg,'semantic_clarification')
    if i=='draft':
        audience=s.get('audience');fmt=s.get('format');limit=s.get('max_words',80)
        if audience not in ('private','class') or fmt not in ('email','message','notice') or not 1<=limit<=300:return fail('cần xác định đối tượng, hình thức và giới hạn từ phù hợp.')
        if audience=='private' and (not sid or find_student(roster,sid) is None):return fail('cần xác định sinh viên trong hồ sơ đang mở.')
        if audience=='class':
            choices=['Các em thân mến, cô muốn trao đổi về tình hình học tập. Các em chuẩn bị một vấn đề muốn trao đổi nhé.' if s.get('prepare_issue') else 'Các em thân mến, cô mời các em trao đổi về tình hình học tập và những vấn đề cần hỗ trợ.', 'Các em chuẩn bị một vấn đề muốn trao đổi với cô nhé.' if s.get('prepare_issue') else 'Các em có thể trao đổi với cô về việc học khi thuận tiện.']
        else:
            choices=['Chào em! Cô muốn trao đổi về việc học và những hỗ trợ em cần. Em nhắn cô thời gian thuận tiện nhé.', 'Chào em, cô mời em trao đổi về việc học. Em nhắn cô thời gian thuận tiện nhé.', 'Chào em, cô mời em trao đổi học tập khi thuận tiện nhé.']
            if s.get('prepare_issue'):choices=['Chào em, cô mời em trao đổi về việc học. Em chuẩn bị một vấn đề muốn trao đổi nhé.']
        body=next((b for b in choices if len(b.split())<=limit),None)
        if not body:return fail('giới hạn từ chưa đủ để giữ trọn ý lời mời; cô có thể tăng giới hạn.')
        if fmt=='email':
            subject=s.get('subject') or 'Mời trao đổi học tập';s['subject']=subject;body='Tiêu đề: '+subject+'\n\n'+body
        tools=['scope_check','communication_draft']
        if s.pop('include_summary',False):
            if audience!='class' or not roster.get('students'):return fail('cần hồ sơ lớp đúng phạm vi để tóm tắt.')
            groups,dup=screening(roster['students']);tools.insert(1,'screening')
            body='Nội bộ — không công bố: '+f'{len(groups[1])} sinh viên ưu tiên hỗ trợ; {len(groups[2])} cần trao đổi thêm; {len(groups[3])} thiếu dữ liệu; {dup} bản ghi trùng/thiếu mã. Đây là sàng lọc, không phải kết luận học vụ.\n\nThông báo chung — bản nháp:\n'+body
        return response(body,'communication_draft',tools,category='CLASS_STATS' if audience=='class' else 'STUDENT_STATUS')
    if not sid or find_student(roster,sid) is None:return fail('cần xác định hồ sơ sinh viên trước khi tư vấn cá nhân.')
    action=s.get('counsel_action')
    if action=='opening':
        options=['Cô muốn hiểu việc học đang diễn ra thế nào với em. Em thấy điều gì cần hỗ trợ nhất?', 'Mình cùng tìm cách để việc học nhẹ nhàng hơn nhé. Em muốn bắt đầu từ vấn đề nào?', 'Cô không muốn vội kết luận từ bảng điểm. Em có thể chia sẻ điều gì đang cản trở việc học?', 'Em thấy môn nào đang khó nhất? Mình cùng tìm bước nhỏ có thể thực hiện trước nhé.', 'Cô muốn nghe góc nhìn của em trước. Em mong được hỗ trợ theo cách nào?']
        count=s.get('opening_count',2)
        if not 1<=count<=len(options):return fail('có thể đề xuất từ một đến năm cách mở đầu.')
        text='\n'.join(f'{k}. {v}' for k,v in enumerate(options[:count],1))
    elif action=='privacy':
        text='Dạ cô, trao đổi qua kênh riêng do sinh viên đồng ý; không đưa hoàn cảnh hoặc kết quả học tập lên nhóm lớp. Hỏi em muốn ai tham gia hỗ trợ, chỉ chia sẻ thông tin tối thiểu khi có sự đồng ý và đúng quy định. Thống nhất một mốc kiểm tra riêng, không hứa bảo mật tuyệt đối nếu có nghĩa vụ báo cáo.'
    elif action=='study_plan':
        minutes=s.get('minutes');days=s.get('days')
        if type(minutes) is not int or type(days) is not int or not 1<=minutes<=180 or not 1<=days<=14:return fail('cần thời lượng mỗi ngày và số ngày để lập phương án vừa sức (1–180 phút, 1–14 ngày).')
        stages=['Chọn một nội dung chưa hiểu, đọc lại ví dụ và ghi câu hỏi.','Ôn kiến thức nền; làm một bài ngắn và ghi lỗi.','Thử giải lại ví dụ không nhìn đáp án; ghi chỗ còn vướng.','Làm bài tương tự, đối chiếu lời giải và sửa lỗi.','Ôn lại các lỗi hay gặp, thử tự giải một bài mới.']
        mode=' Nếu em đồng ý, dùng thời gian đó để học cùng nhóm nhỏ.' if s.get('preference')=='group' else ' Ưu tiên tự học và trao đổi riêng khi cần.'
        text=f'Dạ cô, theo thời gian em vừa nêu: {minutes} phút/ngày trong {days} ngày. Đây là đề xuất, chưa ghi vào hồ sơ.'+mode+'\n'+'\n'.join(f'Ngày {d}: {minutes} phút — '+(stages[(d-1)%len(stages)] if d<days else 'Tự kiểm tra một nội dung, ghi câu hỏi còn vướng và phản hồi với cô.') for d in range(1,days+1))+'\nCô thống nhất nội dung cùng em và xem lại tiến độ sau đợt này; không mặc định em đã thực hiện.'
    else:return fail('chưa rõ cô muốn chuẩn bị mở đầu, lập lịch tự học hay trao đổi về bảo mật.')
    return response(text,'meeting_preparation',['scope_check','meeting_preparation'],category='STUDENT_STATUS',sid=sid)
