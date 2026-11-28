"""Cross-tool advisory synthesis. Facts are recomputed from the scoped roster and
current candidate curriculum; never infer causes, eligibility, or opening dates.
The output is a proposal, not an official plan. No additional model calls.
"""
from workflow import valid,debt_rows
from course_planning import load_candidate,make_plan,REL,SHA,candidate_source,candidate_label

def synthesize(st,roster,root,states,pending,views=None):
    debt=valid(st.get('owed_credits'),0,1000);gpa=valid(st.get('gpa_semester'),0,4)
    fmt=lambda x:f'{x:g}'.replace('.',',')
    lead=[];actions=[];sources=[];tools=['scope_check','student_signals','action_strategy']
    if gpa is not None and gpa<2 and debt is not None and debt>0:
        lead.append(f'Với GPA học kỳ {fmt(gpa)} và {fmt(debt)} tín chỉ nợ, em ưu tiên giúp sinh viên hoàn thành được môn nền tảng trước khi tăng tải. Không thể suy ra nguyên nhân từ điểm số.')
    elif debt is not None and debt>0:
        lead.append(f'Hồ sơ còn {fmt(debt)} tín chỉ nợ. Em ưu tiên rà danh sách học phần chưa đạt trước khi quyết định tải học.')
    else:
        lead.append('Em ưu tiên xác nhận nhu cầu hỗ trợ và hồ sơ cập nhật trước khi quyết định kế hoạch.')
    actions.append('Trong buổi gặp, hỏi điều gì đang cản trở việc học; xác nhận bảng điểm mới, CPA và lịch học hiện tại. Thống nhất mục tiêu với sinh viên, không kết luận nguyên nhân từ hồ sơ.')
    plan=states.get('retake',{}).get('plan',{});budget=plan.get('budget');minutes=states.get('study',{}).get('minutes')
    target=None; verified=None; excluded_names=[]; table=None; study_checks=[]
    if type(budget) is int and 1<=budget<=30:
        try:
            table,_=load_candidate(root,roster)
            if not table:raise ValueError('candidate unavailable')
            rows,amb,unknown=debt_rows(st,roster.get('courses') or [])
            stages,excluded=make_plan(rows,table,st.get('bang_diem') or [],budget)
            if not stages:raise ValueError('no feasible stages')
            included={r[0] for batch in stages for r in batch};total=sum(r[2] for batch in stages for r in batch)
            verified=(total,len(stages));excluded_names=sorted(set(excluded)|set(amb)|set(unknown))
            blockers=sorted(((c,sum(c in table[x][1] for x in included)) for c in included),key=lambda p:(-p[1],p[0]))
            if blockers and blockers[0][1]>0:target=blockers[0][0]
            tools.extend(['course_history','prerequisite_planning','credit_scenarios']);sources.append(candidate_source(table))
            actions.append(f'Rà phương án {budget} tín chỉ/đợt: mô phỏng hiện xếp được {total} tín chỉ trong {len(stages)} đợt. '+('Xác minh thêm '+', '.join(sorted(set(excluded)|set(amb)|set(unknown)))+' trước khi coi là đã xử lý đủ môn nợ. ' if excluded or amb or unknown else '')+('Số tín chỉ xếp được khác tổng nợ trong hồ sơ; cần đối chiếu lại. ' if debt is not None and total!=debt else '')+f'Đây là {candidate_label(table)}, không phải lịch đăng ký chính thức.')
        except (OSError,ValueError,RuntimeError,TypeError,KeyError):
            actions.append('Chưa thể xác minh lại lộ trình từ bảng tiên quyết hiện có; không dùng kết quả cũ để chốt đăng ký.')
    elif 'retake' in pending:
        actions.append('Chưa chốt được lộ trình. Cần xác nhận trần tín chỉ hoặc bổ sung bảng tiên quyết phù hợp.')
    if type(minutes) is int and 5<=minutes<=180 and not budget:
        try:
            table,_=load_candidate(root,roster)
            if not table:study_checks.append('Chưa xác minh được bảng tiên quyết hiện có; cần chọn nội dung tự học cùng sinh viên, không dựa vào gợi ý môn cũ.')
            rows,amb,unknown=debt_rows(st,roster.get('courses') or [])
            pending_codes={c for c,_,k in rows if table and c in table and table[c][0]==k}
            ranked=sorted(((c,sorted(x for x in pending_codes if c in table[x][1])) for c in pending_codes),key=lambda x:(-len(x[1]),x[0]))
            if ranked and ranked[0][1]:
                target,children=ranked[0]
                tools.extend(['course_history','prerequisite_planning']);sources.append(candidate_source(table))
                study_checks.append(f'Xác minh {target} còn nợ và sinh viên thực sự đang vướng phần kiến thức nào. Theo {candidate_label(table)}, môn này là tiên quyết trực tiếp của {", ".join(children)}; đây là căn cứ ưu tiên rà, không phải kết luận về năng lực.')
            if amb or unknown:study_checks.append('Đối chiếu mã hoặc lần đạt/chưa đạt chưa rõ: '+', '.join(sorted(set(amb+unknown)))+'.')
        except (OSError,ValueError,RuntimeError,TypeError,KeyError):
            study_checks.append('Chưa xác minh lại được bảng tiên quyết; không dựa vào gợi ý môn cũ để chọn nội dung.')
        study_checks.append(f'Thử tối đa {minutes} phút mỗi ngày: thống nhất một dạng bài nhỏ, ghi số buổi thực hiện và một bài tự làm được; cuối tuần hỏi sinh viên điều còn vướng rồi điều chỉnh. Không coi 7 buổi là bắt buộc.')
        if minutes<=20:study_checks.append('Nếu không hoàn thành một bài ngắn trong thời gian này, giảm độ khó hoặc đổi cách hỗ trợ trước khi tăng thời lượng.')
    if type(minutes) is int and 5<=minutes<=180:
        tools.append('study_constraint_review')
        text=f'Thử tự học tối đa {minutes} phút/ngày trong một tuần.'
        if target:text+=f' Có thể bắt đầu củng cố {target} nếu xác minh đúng tiên quyết; việc tự học chuẩn bị không đồng nghĩa đã đăng ký môn.'
        if type(budget) is int:text+=' Thời lượng tự học này chưa đủ để suy ra tải tín chỉ phù hợp; không tăng tải chỉ dựa vào số đợt mô phỏng.'
        if minutes<=20:text+=' Giữ một mục tiêu nhỏ, có thể nghỉ nếu mệt.'
        actions.append(text+' Sau một tuần, cùng sinh viên rà việc đã làm được, điểm còn vướng và điều chỉnh tải nếu cần.')
    elif 'study' in pending:actions.append('Hỏi thời gian tự học khả thi trước khi lập kế hoạch một tuần.')
    if 'draft' in states:actions.append('Dùng lời mời riêng đã soạn để thống nhất thời gian gặp; bản nháp chưa gửi.')
    if not minutes:actions.append('Thống nhất một mốc đánh giá lại sau buổi gặp và một mục tiêu có thể kiểm tra được.')
    if views and len(set(views))>1:
        # Render each fact and caveat once, even when several views overlap.
        # Separate assessment from proposed actions and use the current scoped
        # tool result, not the model's prose or prior cached round counts.
        return combined(views,debt,gpa,budget,minutes,verified,excluded_names,target,states,pending,table,study_checks),tools,sources
    if views:
        # Same fresh evidence, different decision questions. Never estimate
        # probability of success, lawful load or actual timetable.
        parts=[]
        for view in views:
            if view=='summary':
                items=[]
                if debt is not None:items.append(f'{fmt(debt)} tín chỉ nợ')
                if gpa is not None:items.append(f'GPA học kỳ {fmt(gpa)}')
                lines=['**Tóm tắt phương án hiện tại**','Hồ sơ: '+', '.join(items)+'.' if items else 'Chưa đủ chỉ số hồ sơ.']
                if verified:lines.append(f'Học lại: tối đa {budget} tín chỉ/đợt, xếp được {verified[0]} tín chỉ trong {verified[1]} đợt mô phỏng.')
                elif budget or 'retake' in pending:lines.append('Chưa thể xác minh lại lộ trình học lại.')
                if excluded_names:lines.append('Còn cần đối chiếu: '+', '.join(excluded_names)+'.')
                if type(minutes) is int:lines.append(f'Tự học: tối đa {minutes} phút/ngày trong một tuần.')
                if 'draft' in states:lines.append('Lời mời riêng: bản nháp chưa gửi.')
                if pending:lines.append('Một số phần còn thiếu tham số hoặc dữ liệu, chưa hoàn thành.')
                if verified:lines.append(f'{candidate_label(table)}; đợt không phải học kỳ, chưa xác nhận lịch mở lớp hay tải đăng ký.')
                parts.append('\n\n'.join(lines))
            elif view=='feasibility':
                lines=['**Đánh giá khả thi**','Có thể bắt đầu bằng buổi trao đổi và mục tiêu nhỏ, nhưng chưa đủ căn cứ để chốt toàn bộ phương án học tập.']
                if verified:lines.append(f'Về mô hình tiên quyết, {verified[0]} tín chỉ xếp được trong {verified[1]} đợt với trần {budget} tín chỉ/đợt. Đó là kết quả mô phỏng, không phải lịch đăng ký chính thức.')
                elif budget or 'retake' in pending:lines.append('Chưa thể xác minh lại lộ trình; chưa nên dùng số đợt cũ để quyết định.')
                if type(minutes) is int:lines.append(f'Tự học tối đa {minutes} phút/ngày có thể thử trong một tuần; chưa thể quy đổi thành tải học phần. Nếu quá sức thì giảm mục tiêu hoặc số buổi.');lines.extend(study_checks)
                else:lines.append('Chưa có thời gian tự học thực tế của sinh viên; cần hỏi trước khi đề xuất tải.')
                if excluded_names:lines.append('Cần đối chiếu '+', '.join(excluded_names)+'; chưa coi là đã xử lý hết nợ.')
                lines.append('Điều kiện để chốt: bảng điểm/CPA cập nhật, môn đang học, CTĐT đúng khóa đã duyệt, lịch mở lớp và giới hạn đăng ký. Đánh giá lại sau buổi gặp hoặc tuần thử nghiệm.')
                parts.append('\n\n'.join(lines))
            elif view=='risks':
                lines=['**Điểm cần kiểm tra trước khi thực hiện**']
                if debt is not None and gpa is not None:lines.append(f'Hồ sơ có {fmt(debt)} tín chỉ nợ và GPA học kỳ {fmt(gpa)}; không suy ra nguyên nhân hoặc khả năng hoàn thành từ hai chỉ số này.')
                if verified:lines.append(f'Trần {budget} tín chỉ/đợt chỉ là ràng buộc mô phỏng; {candidate_label(table)}, chưa có lịch mở lớp và tải học phần mới.')
                elif budget or 'retake' in pending:lines.append('Chưa thể xác minh lại lộ trình từ dữ liệu hiện có.')
                if excluded_names:lines.append('Chưa đối chiếu: '+', '.join(excluded_names)+'.')
                if type(minutes) is int:lines.append(f'{minutes} phút/ngày là giới hạn tự học thử, không phải bằng chứng đủ sức học dồn.')
                else:lines.append('Chưa có thời gian tự học thực tế; chưa thể chọn khối lượng học phù hợp.')
                if not verified and not budget:lines.extend(study_checks);lines.append('Chưa có lộ trình học lại đã đối chiếu với CTĐT đúng khóa.')
                lines.append('Cần xác minh CPA, hoàn cảnh thực tế, CTĐT đúng khóa, lịch học hiện tại, lịch mở lớp và quy chế đăng ký; không tự kết luận sinh viên đủ điều kiện đăng ký.')
                parts.append('\n\n'.join(lines))
            elif view=='next_steps':
                lines=['**Việc tiếp theo**','1. Hẹn trao đổi riêng; hỏi khó khăn, thời gian thực tế và mục tiêu của sinh viên.','2. Rà bảng điểm và CTĐT, thống nhất một mục tiêu nhỏ có thể đo được.']
                if type(minutes) is int:lines.append(f'3. Thử tối đa {minutes} phút/ngày trong một tuần, ghi lại việc làm được và câu hỏi còn vướng.')
                lines.append('Sau buổi gặp hoặc tuần thử nghiệm, đánh giá lại mức hoàn thành, phản hồi của sinh viên và cập nhật phương án. Chưa quyết định tải đăng ký khi thiếu lịch và quy chế đúng khóa.')
                parts.append('\n\n'.join(lines))
            elif view=='priority':
                # Existing detailed prioritized advice remains available.
                parts.append('\n\n'.join(lead)+'\n\n'+'\n'.join(f'{i}. {a}' for i,a in enumerate(actions,1)))
        if parts:return '\n\n'.join(parts),tools,sources
    return '\n\n'.join(lead)+'\n\n'+'\n'.join(f'{i}. {a}' for i,a in enumerate(actions,1)),tools,sources


def combined(views,debt,gpa,budget,minutes,verified,excluded,target,states,pending,table=None,study_checks=()):
    """Shared evidence ledger for multi-view review. No new facts are generated.
    Each relevant fact, constraint and proposed action appears at most once.
    Views are requested purposes, not independent documents to concatenate.
    """
    wants=set(views);fmt=lambda x:f'{x:g}'.replace('.',',')
    summary='summary' in wants
    assess=bool(wants & {'feasibility','risks'})
    recommend=bool(wants & {'priority','next_steps'})
    lines=[]
    if 'feasibility' in wants:
        lines.append('Dạ, có thể bắt đầu bằng buổi trao đổi và mục tiêu nhỏ; chưa đủ căn cứ để chốt toàn bộ phương án học tập.')
    elif 'priority' in wants:
        lines.append('Em ưu tiên khả năng hoàn thành học phần hơn việc tăng tải để trả nợ nhanh.')
    # The outer advisor already adds a greeting.
    if lines and lines[0].startswith('Dạ, '):lines[0]=lines[0][4:];lines[0]=lines[0][:1].upper()+lines[0][1:]
    facts=[]
    if debt is not None:facts.append(f'{fmt(debt)} tín chỉ nợ')
    if gpa is not None:facts.append(f'GPA học kỳ {fmt(gpa)}')
    items=[]
    if facts:items.append('Hồ sơ: '+', '.join(facts)+'.')
    else:items.append('Chưa đủ chỉ số hồ sơ.')
    if verified:items.append(f'Học lại: tối đa {budget} tín chỉ/đợt, xếp được {verified[0]} tín chỉ trong {verified[1]} đợt mô phỏng.')
    elif budget or 'retake' in pending:items.append('Chưa thể xác minh lại lộ trình từ bảng tiên quyết hiện có.')
    elif assess:items.append('Chưa có lộ trình học lại được đối chiếu.')
    if type(minutes) is int:items.append(f'Tự học: tối đa {minutes} phút/ngày trong một tuần.')
    elif assess:items.append('Chưa biết thời gian tự học thực tế.')
    if 'draft' in states:items.append('Lời mời riêng: bản nháp chưa gửi.')
    if pending:items.append('Một số phần còn thiếu tham số hoặc dữ liệu, chưa hoàn thành.')
    lines.append('**Tóm tắt phương án hiện tại**' if summary else '**Dữ kiện đang có**')
    lines.append('\n'.join('- '+x for x in items))
    limits=[]
    if assess or recommend:limits.append('Không thể suy ra nguyên nhân hoặc khả năng hoàn thành từ điểm số.')
    if excluded:limits.append('Còn cần đối chiếu: '+', '.join(excluded)+'.')
    if verified and debt is not None and verified[0]!=debt:limits.append('Số tín chỉ xếp được khác tổng nợ; chưa coi là đã xử lý hết.')
    if verified:limits.append(f'{candidate_label(table)}; đợt không phải học kỳ, chưa xác nhận lịch mở lớp hay tải đăng ký.')
    if assess or recommend:
        if type(minutes) is int:limits.append('Thời lượng tự học thử chưa đủ căn cứ để quy đổi thành tải tín chỉ.')
        limits.append('Cần xác minh bảng điểm/CPA, thời gian thực tế, môn đang học, CTĐT và quy chế đúng khóa, lịch mở lớp trước khi chốt đăng ký.')
    if assess and study_checks:limits.extend(study_checks)
    if limits:lines.extend(['**Điều kiện và rủi ro cần lưu ý**' if assess else '**Giới hạn của phương án**','\n'.join('- '+x for x in limits)])
    if recommend:
        steps=['Hẹn trao đổi riêng và xác định khó khăn, mục tiêu cùng sinh viên.','Rà các môn nợ, ưu tiên môn nền tảng đã xác minh; chưa tăng tải chỉ vì số đợt mô phỏng.']
        if type(minutes) is int:
            steps.append(('Thử củng cố '+target+' nếu xác minh đúng tiên quyết; ' if target else 'Thử kế hoạch tự học; ')+'ghi lại bài đã làm được và câu hỏi còn vướng.')
        else:steps.append('Hỏi thời gian tự học khả thi rồi thống nhất một mục tiêu nhỏ có thể kiểm tra.')
        steps.append('Đánh giá lại sau buổi gặp hoặc tuần thử nghiệm, điều chỉnh phương án theo kết quả thực tế.')
        lines.extend(['**Việc nên làm tiếp theo**','\n'.join(f'{i}. {x}' for i,x in enumerate(steps,1))])
    return '\n\n'.join(lines)
