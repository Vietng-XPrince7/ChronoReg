"""Evidence-bound preparation for a private advising conversation.
No persistent notes, diagnoses, or invented reasons. User-mentioned circumstances
are discussion hypotheses, not fields in the official student record.
"""
import re
from quality import norm
from workflow import valid, debt_rows, scope_error, DRAFT_TASK, REPORT_TASK, STUDENT_TASK
from course_planning import load_candidate, REL, SHA,candidate_source,candidate_label
from meeting_context import update_topics, state_for, focus, question_count

MEETING = re.compile(r'\b(?:gap rieng|buoi (?:gap|tu van|trao doi)|noi gi|hoi gi|hoi nhung gi|bat dau cuoc tro chuyen|trao doi (?:gi|nhu the nao|the nao))\b')
SUPPORT = re.compile(r'\b(?:tu van|ho tro|giup|nen lam gi|can lam gi|nen uu tien|khuyen|xu ly|giai phap)\b')
# Do not steal explicit numerical, legal, comparative, or production tasks.
EXCLUDE = re.compile(r'\b(?:quy che|quy dinh|co duoc|co phai|co bi|bao nhieu|toi da|toi thieu|hoc bong|muc hoc phi|canh bao|buoc thoi hoc|bao luu|ngoai le|so sanh|tinh gpa|tinh cpa|dieu kien tot nghiep|chuan dau ra)\b')

def requested_context(q):
    return update_topics(q)[0]

def open_support(q):
    return bool(not (EXCLUDE.search(q) or DRAFT_TASK.search(q) or REPORT_TASK.search(q) or STUDENT_TASK.search(q)) and (SUPPORT.search(q) or re.search(r'\b(?:nen lam the nao|nen lam sao|nen xu ly the nao|nen tiep can the nao)\b',q)))

def meeting_intent(q):
    return bool(not (EXCLUDE.search(q) or DRAFT_TASK.search(q) or REPORT_TASK.search(q) or STUDENT_TASK.search(q)) and (MEETING.search(q) or (SUPPORT.search(q) and requested_context(q))))

def prepare(question, bundle, root, backend=None):
    q=norm(question); roster=bundle.get('roster_obj') or {}; sid=str(bundle.get('student_id') or '')
    matches=[s for s in roster.get('students') or [] if sid and str(s.get('student_id') or s.get('mssv'))==sid]
    error=scope_error(q,roster)
    if error or len(matches)!=1:
        return 'Dạ cô, em chưa xác định được hồ sơ phù hợp. Cô chọn đúng sinh viên hoặc cung cấp MSSV giúp em.', ['scope_check'], [], []
    st=matches[0]; name=str(st.get('full_name') or 'sinh viên')
    g=valid(st.get('gpa_semester'),0,4); o=valid(st.get('owed_credits'),0,1000); d=valid(st.get('drl'),0,100)
    rows,amb,unknown=debt_rows(st,roster.get('courses') or [])
    prior=state_for(sid); contexts,touched=update_topics(question,prior.get('topics',[])); view=focus(question); facts=[]; ask=[]; actions=[]; sources=[]; tools=['scope_check','student_signals','course_history','meeting_preparation']
    if g is not None:facts.append(f'GPA học kỳ {g:.2f}')
    if o is not None:facts.append(f'{o:g} tín chỉ nợ')
    if d is not None:facts.append(f'điểm rèn luyện {d:g}')
    # Lead with the actual meeting goal, not a duplicated full analysis.
    lead=f'Dạ cô, với {name} ({sid}), em đề xuất buổi gặp tập trung vào tìm nguyên nhân và thống nhất một bước hỗ trợ khả thi, thay vì chỉ nhắc nhở về điểm.'
    if g is not None and g<2 and o is not None and o>0:
        ask.append('“Em thấy khó nhất ở khâu nào: hiểu bài, thời gian tự học, hay khối lượng môn? Em đã thử cách nào rồi?”')
        actions.append('Rà bảng điểm cập nhật và chọn các học phần nền tảng cần ưu tiên; chưa chốt tải học khi chưa biết khả năng thực tế.')
    elif g is not None and g<2:
        ask.append('“Điều gì ảnh hưởng đến kết quả kỳ vừa rồi, và em muốn thay đổi điều gì trước?”')
        actions.append('Thống nhất cách học và mốc kiểm tra kết quả sớm trong kỳ tới.')
    elif o is not None and o>0:
        ask.append('“Những môn chưa hoàn thành có vướng lịch, kiến thức nền hay điều kiện khác không?”')
        actions.append('Đối chiếu môn nợ, lần học lại và lịch mở lớp trước khi chốt.')
    if d is not None and d<70:
        ask.append('“Em có vướng mắc gì khi tham gia hoạt động hoặc ghi nhận minh chứng rèn luyện không?”')
        actions.append('Kiểm tra cách ghi nhận điểm rèn luyện và hỗ trợ phù hợp; không coi điểm thấp là thiếu cố gắng.')
    table,_=load_candidate(root,roster)
    if table and rows:
        pending={c for c,_,k in rows if c in table and table[c][0]==k}
        blockers=sorted(((c,sorted(x for x in pending if c in table[x][1])) for c in pending),key=lambda x:(-len(x[1]),x[0]))
        if blockers and blockers[0][1]:
            c,children=blockers[0];actions.append(f'Rà {c} trước: bảng {candidate_label(table)} ghi mã này là tiên quyết của {", ".join(children)}; xác minh với CTĐT đúng khóa.')
            sources.append(candidate_source(table));tools.append('prerequisite_planning')
    if 'time' in contexts:
        ask.insert(0,'“Nếu em đang đi làm, lịch ca và thời gian tự học thực tế mỗi tuần như thế nào? Có khoảng thời gian nào em có thể bảo vệ để học không?”')
        actions.insert(0,'Nếu lịch làm việc là trở ngại, cùng em lập thời gian biểu và chọn tải học vừa sức; kiểm tra giới hạn đăng ký, không tự hứa được giảm tải.')
    if 'finance' in contexts:
        ask.insert(0,'“Nếu tài chính đang gây áp lực, em muốn được hỗ trợ tìm thông tin về khoản chi, thời hạn hay chính sách hỗ trợ nào?”')
        actions.insert(0,'Nếu em xác nhận khó khăn tài chính, hỗ trợ tra chính sách đúng kỳ và kênh hỗ trợ của trường; không hứa cấp học bổng hay miễn giảm.')
    if 'confidence' in contexts:
        ask.insert(0,'“Gần đây điều gì khiến em khó duy trì việc học? Em muốn cô hỗ trợ phần nào trước?”')
        actions.insert(0,'Nếu em đang mất động lực, thống nhất một mục tiêu nhỏ có thể thực hiện, lắng nghe và gợi ý kênh hỗ trợ phù hợp nếu em cần.')
    if 'foundation' in contexts:
        ask.insert(0,'“Em đang vướng kiến thức nền ở phần nào? Có bài tập hoặc chủ đề cụ thể nào em muốn được hỗ trợ?”')
        actions.insert(0,'Nếu kiến thức nền là trở ngại, trao đổi với giảng viên bộ môn về tài liệu ôn tập hoặc nhóm học phù hợp.')
    if 'family' in contexts:
        ask.insert(0,'“Nếu trách nhiệm gia đình đang ảnh hưởng đến việc học, khoảng thời gian nào em có thể dành ổn định cho việc học?”')
        actions.insert(0,'Nếu sinh viên xác nhận vướng việc gia đình, cùng em chọn thời gian học khả thi và thống nhất cách trao đổi khi lịch thay đổi.')
    if 'commute' in contexts:
        ask.insert(0,'“Nếu việc đi lại mất nhiều thời gian, lịch học nào khiến em khó duy trì việc học nhất?”')
        actions.insert(0,'Nếu đi lại là trở ngại, đối chiếu lịch mở lớp để giảm xung đột thời gian; chưa cam kết đổi lớp.')
    if not ask:ask.append('“Kỳ vừa rồi em thấy việc học tiến triển thế nào? Có điều gì em muốn cô hỗ trợ không?”')
    ask.append('“Sau buổi này, em muốn thử bước nào trước và khi nào mình trao đổi lại?”')
    lines=[lead, 'Hồ sơ demo: '+('; '.join(facts) or 'chưa có đủ chỉ số hợp lệ')+'.', 'Cô có thể mở lời: “Cô muốn hiểu tình hình của em để cùng tìm cách hỗ trợ. Mình trao đổi riêng, em cứ chia sẻ những gì em thấy phù hợp nhé.”', 'Những điều nên hỏi:\n'+'\n'.join('• '+x for x in ask)]
    if contexts:lines.append('Hoàn cảnh cô nêu là thông tin cần xác nhận với sinh viên, chưa được ghi nhận trong hồ sơ demo.')
    if not actions:actions.append('Thống nhất một nhu cầu hỗ trợ cụ thể nếu sinh viên có nhu cầu; không suy diễn vấn đề từ hồ sơ hiện có.')
    if amb or unknown:actions.append('Đối chiếu mã học phần hoặc lần học lại còn chưa rõ.')
    lines += ['Sau khi nghe sinh viên, em đề xuất:\n'+'\n'.join('• '+x for x in actions), 'Chốt một mục tiêu, người thực hiện và mốc gặp lại do hai bên thống nhất. Cô cần xác nhận bảng điểm mới nhất, GPA tích lũy và tình trạng học vụ; em không suy ra nguyên nhân hoặc quyết định chính thức từ hồ sơ cũ.']
    # Model can tailor questions to unfamiliar circumstances without authoring
    # factual claims or policy. Keep all deterministic advice and scope boundaries.
    from adaptive_counsel import propose
    flags=[label for label,enabled in [('điểm học kỳ thấp',g is not None and g<2),('có tín chỉ nợ',o is not None and o>0),('cần rà điểm rèn luyện',d is not None and d<70)] if enabled]
    # A genuinely new, non-template hypothetical situation may still benefit
    # from the local model on a follow-up, but format-only requests need no model.
    novel=bool(re.search(r'\b(?:neu|gia su|vi em|do em)\b',q)) and not touched
    extra=propose(backend,question,bundle,flags,'\n\n'.join(lines)) if view=='full' and ((not prior and not contexts) or novel) else None
    if extra:
        questions,action=extra
        ask=['“'+x+'”' for x in questions]+ask
        if action:actions.insert(0,action)
        lines[3]=lines[3].replace('Những điều nên hỏi:\n','Những điều nên hỏi:\n'+'\n'.join('• “'+x+'”' for x in questions)+'\n',1)
        if action:lines.insert(-1,'Hướng hỗ trợ thêm để cô cân nhắc: '+action)
        tools.append('local_counseling_proposal')
    # On a scoped follow-up, answer the new request rather than replay the intake.
    # Hypotheses stay conditional and are never added to the official roster.
    if prior or view!='full':
        removed=set(prior.get('topics',[]))-set(contexts)
        prefix=f'Dạ cô, với {name} ({sid}), '
        if removed:prefix+='em sẽ không tiếp tục dùng hoàn cảnh vừa được cô đính chính làm giả định. '
        note='Hoàn cảnh cô nêu là giả định cần xác nhận, chưa được ghi nhận trong hồ sơ demo.' if contexts else ''
        if view=='questions':
            count=question_count(question)
            # Fill a requested small count with distinct, open prompts; no invented facts.
            pool=list(dict.fromkeys(ask+['“Em muốn cô hỗ trợ việc gì trước?”','“Mình có thể kiểm tra lại tiến độ bằng cách nào?”','“Điều gì có thể giúp em duy trì kế hoạch này?”']))
            lines=[prefix+'cô có thể hỏi trực tiếp như sau:', 'Những điều nên hỏi:\n'+'\n'.join('• '+x for x in pool[:count])]
            if note:lines.append(note)
        elif view=='actions':
            lines=[prefix+'em đề xuất các bước sau:', '\n'.join('• '+x for x in actions[:4]), 'Thống nhất việc cụ thể, người thực hiện và mốc gặp lại; chưa coi đề xuất là quyết định chính thức.']
            if note:lines.append(note)
        else:
            # Focus on the newly stated circumstances. Preserve safety/conditionality.
            count=min(3,max(1,len(contexts))) if touched else 2
            lines=[prefix+'em đề xuất tập trung vào nội dung này trong buổi gặp:', 'Những điều nên hỏi:\n'+'\n'.join('• '+x for x in ask[:count]), 'Việc cô có thể làm:\n'+'\n'.join('• '+x for x in actions[:count]), 'Thống nhất một việc khả thi và mốc gặp lại; kiểm tra hồ sơ mới trước khi chốt phương án học tập.']
            if note:lines.append(note)
        tools.append('focused_counseling')
    return '\n\n'.join(lines),tools,[('Chuẩn bị buổi gặp','Xác nhận dữ kiện, hỏi nguyên nhân và thống nhất bước hỗ trợ.')],sources
