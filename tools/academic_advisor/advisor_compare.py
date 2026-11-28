"""Compare explicit credit-load alternatives on the same validated student scope."""
import re
from quality import norm
from quality_routes import response,find_student
from quality_workflows import snapshot
from workflow import scope_error,debt_rows,valid
from course_planning import load_candidate,make_plan,REL,SHA,candidate_source,candidate_label


def route(q,prior,explicit,classified,roster,root):
    n=norm(q)
    if not re.search(r'\b(?:so sanh|doi chieu|phuong an nao|muc nao)\b',n) or not re.search(r'\b(?:hoc lai|mon no|tra no|tien quyet|moi dot)\b',n):return None
    if re.search(r'\b(?:hoc phi|chi phi|bao nhieu tien|lop khac|lop moi|ca lop|toan lop|cong khai|gui|sinh vien khac|em khac|tru mon|bo mon|uu tien mon|mon truoc|hoc cung|lich mo lop|quy che|hoc ky|moi ky|khong qua|khong tinh|them mon|muc toi thieu)\b',n):return None
    if re.search(r'\b[A-Z]{3}\d{4}\b',q):return None
    # Only two or three explicit, separately qualified alternative caps.
    values=re.findall(r'\b(\d{1,2})\s+(?:tin chi|tc)\b',n)
    if re.search(r'\d[.,]\d+\s*(?:tín chỉ|tc)',q,re.I) or not 2<=len(values)<=3 or len(set(values))!=len(values) or not all(1<=int(x)<=30 for x in values):return None
    old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic') in ('retake','profile','retake_compare') else {}
    ids=set(re.findall(r'\b\d{8}\b',q)); chosen=str(explicit or classified or '')
    def ask(t):return response('Dạ cô, '+t,'advisor_clarification'),{}
    if len(ids)>1 or chosen and ids and chosen not in ids or scope_error(n,roster):return ask('cô xác nhận một hồ sơ đúng phạm vi để so sánh.')
    sig=snapshot(roster)
    if not ids and not chosen and old and old.get('scope')!=sig:return ask('hồ sơ đã thay đổi; cần xác nhận lại sinh viên.')
    sid=next(iter(ids),None) or chosen or old.get('student')
    st=find_student(roster,sid)
    if not st:return ask('cô chọn hồ sơ sinh viên cần so sánh.')
    table,why=load_candidate(root,roster)
    if not table:return ask('chưa có bảng tiên quyết phù hợp; chưa thể so sánh chính xác.')
    rows,amb,unknown=debt_rows(st,roster.get('courses') or [])
    results=[]
    try:
        for cap in sorted(map(int,values)):
            stages,excluded=make_plan(rows,table,st.get('bang_diem') or [],cap)
            included={row[0] for batch in stages for row in batch};total=sum(row[2] for batch in stages for row in batch)
            results.append((cap,len(stages),total,included,excluded))
    except (ValueError,RuntimeError,TypeError,KeyError):return ask('chưa xác minh được các phương án tiên quyết.')
    lines=['Dạ cô, em so sánh các mức tải trên cùng hồ sơ '+str(sid)+':','', '| Trần tín chỉ/đợt | Số đợt mô phỏng | Môn xếp được | Tín chỉ xếp được |','|---:|---:|---:|---:|']
    for cap,k,total,inc,exc in results:
        lines.append(f'| {cap} | {k} | {len(inc)} | {total} |')
    same=bool(results[0][3]) and all(r[3]==results[0][3] for r in results)
    if same:
        smallest=min(results,key=lambda x:(x[1],x[0]));lines.append(f'\nTrong mô hình này, mức {smallest[0]} tín chỉ/đợt cần {smallest[1]} đợt; đây là mức tải nhỏ nhất trong các phương án có số đợt ít nhất, trên cùng tập học phần.')
    else:lines.append('\nCác phương án không xếp được cùng tập học phần; không thể coi phương án ít đợt nhất là tốt nhất.')
    for cap,k,total,inc,exc in results:
        if exc:lines.append(f'- Mức {cap}: chưa xếp '+ '; '.join(f'{c}: {v}' for c,v in sorted(exc.items()))+'.')
    if amb or unknown:lines.append('- Cần đối chiếu thêm: '+'; '.join(amb+unknown)+'.')
    g=valid(st.get('gpa_semester'),0,4)
    if g is not None and g<2:lines.append('GPA học kỳ trong hồ sơ dưới 2,00; em đề xuất ưu tiên tải vừa sức, đánh giá lại sau từng đợt thay vì chọn tải lớn nhất chỉ để trả nợ nhanh.')
    lines.append(f'Đây là mô phỏng trên {candidate_label(table)}; đợt không phải học kỳ. Cần xác minh lịch mở lớp, tải học phần mới, giới hạn đăng ký và thời gian tự học trước khi chốt.')
    return response('\n'.join(lines),'retake_compare',['scope_check','course_history','prerequisite_planning','credit_scenarios','action_strategy'],[candidate_source(table)],'STUDENT_STATUS',str(sid)),{'kind':'advisor_agent','topic':'retake_compare','student':str(sid),'scope':sig,'caps':sorted(map(int,values))}
