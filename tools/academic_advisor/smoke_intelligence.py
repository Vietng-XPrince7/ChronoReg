"""Live Advisor intelligence regression. --full includes the existing unit/workflow suites.
--show-demo prints the actual answers for qualitative review. Demo data only.
"""
import argparse,html,json,os,re,subprocess,sys,urllib.request,urllib.error
from pathlib import Path
from workflow import screening,debt_rows
from quality import norm


def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--full',action='store_true');p.add_argument('--show-demo',action='store_true');a=p.parse_args()
 folder=Path(__file__).resolve().parent;root=folder.parents[1]
 def call(path,data=None):
  req=urllib.request.Request(f'http://127.0.0.1:{a.port}'+path,data=None if data is None else json.dumps(data,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json; charset=utf-8'})
  try:
   with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=450) as resp:return json.load(resp)
  except urllib.error.HTTPError as e:
   raise SystemExit(f'HTTP {e.code} from {path}; inspect the server traceback (do not share private records).') from e
 status=call('/api/knowledge/status');print('INDEX:',json.dumps(status,ensure_ascii=False),flush=True)
 if status.get('intelligence_revision')!='2.0.0-pilot' or status.get('deployment_profile')!='local-slm' or status.get('errors'):raise SystemExit('Expected fresh Advisor Intelligence 1.9.9 local-SLM server')
 if a.full:
  exe=root/'.venv-chronoreg-advisor'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
  if not exe.is_file():raise SystemExit('Expected team venv')
  env={**os.environ,'CHRONOREG_TEST_REPO':str(root),'PYTHONUTF8':'1'}
  if subprocess.run([str(exe),'-m','unittest','discover','-s',str(folder),'-p','test_*.py'],cwd=root,env=env).returncode:raise SystemExit('Unit suite failed')
  if subprocess.run([str(exe),str(folder/'smoke_workflow.py'),'--port',str(a.port)],cwd=root,env=env).returncode:raise SystemExit('Workflow regression failed')
 roster=call('/api/class-roster');students=roster.get('students') or [];groups,dup=screening(students)
 if not students:raise SystemExit('Expected demo roster')
 sid=lambda s:str(s.get('student_id') or s.get('mssv') or '')
 pair=next((s for s in students if {'INT1008','INT2210'}<={r[0] for r in debt_rows(s,roster.get('courses') or [])[0]}),None)
 if pair is None:raise SystemExit('Expected demo record with unresolved INT1008 and INT2210')
 target=sid(pair);others={sid(s) for s in students if sid(s) and sid(s)!=target}
 first=lambda t:t.split('\n',1)[0]
 intent=lambda m,k:m.get('advisor_intent')==k
 cases=[
  ('policy_not_class',{'question':'Sinh viên lớp cô trượt một môn thì có bị hạ bằng không?'},lambda t,m:'không nhất thiết' in first(t).lower() and '5%' in t and 'Hồ sơ demo' not in t and intent(m,'policy_question')),
  ('policy_paraphrase',{'question':'Một sinh viên lớp cô bị rớt 1 môn có bị hạ loại bằng không?'},lambda t,m:'không nhất thiết' in first(t).lower() and '5%' in t and intent(m,'policy_question')),
  ('credit_direct',{'question':'Sinh viên có GPA học kỳ 1,8 thì kỳ sau được đăng ký tối đa bao nhiêu tín chỉ?'},lambda t,m:'18 tín chỉ' in first(t) and 'chưa thuộc diện bị buộc thôi học' in t and '24 tín chỉ' not in t and intent(m,'policy_question')),
  ('credit_boundary',{'question':'GPA học kỳ 2,0 thì được đăng ký tối đa bao nhiêu tín chỉ?'},lambda t,m:'không thuộc điều kiện' in first(t) and 'chưa thể xác định' in t and intent(m,'policy_question')),
  ('credit_summer',{'question':'GPA học kỳ 1,8 thì học kỳ phụ được đăng ký tối đa bao nhiêu tín chỉ?'},lambda t,m:'không thể tự áp dụng cho kỳ phụ' in t and intent(m,'policy_question')),
  ('student_review',{'question':'Em hãy phân tích toàn diện tình hình học tập của sinh viên '+target+'.','mssv':target},lambda t,m:intent(m,'student_review') and 'prerequisite_planning' in m.get('workflow_tools',[]) and 'INT1008 là tiên quyết' in t and 'INT2210' in t and target in t and all(x not in t for x in others) and 'chưa duyệt' in t),
  ('daily_priorities',{'question':'Nếu em là trợ lý riêng của cô, dựa vào toàn bộ thông tin hiện có về lớp, em nghĩ hôm nay cô nên ưu tiên làm những công việc gì?'},lambda t,m:intent(m,'class_priorities') and f'{len(groups[1])} ưu tiên gặp riêng' in t and 'Cuối buổi' in t and 'không phải lịch đã đặt' in t and all(t.find(x[0])>=0 for x in groups[1]) and [t.find(x[0]) for x in groups[1]]==sorted(t.find(x[0]) for x in groups[1])),
  ('class_strategy',{'question':'Cô muốn tất cả sinh viên trong lớp tốt nghiệp đúng hạn. Em hãy phân tích những trở ngại hiện tại và đề xuất một chiến lược để cô đạt được mục tiêu đó.'},lambda t,m:intent(m,'class_strategy') and 'Trước khi đăng ký' in t and 'Sau mỗi kỳ' in t and 'số tín chỉ nợ còn lại' in t and 'chưa có đủ dữ liệu' in t and all(sid(s) not in t for s in students if sid(s))),
  ('wrong_scope',{'question':'Hôm nay cô nên làm gì trước cho lớp K65?'},lambda t,m:m.get('workflow_tools')==['scope_check'] and all(sid(s) not in t for s in students if sid(s))),
  ('improve_class',{'question':'Em hãy lập kế hoạch cải thiện kết quả học tập cho cả lớp trong học kỳ tới.'},lambda t,m:intent(m,'class_improvement') and 'graduation_checklist' not in m.get('workflow_tools',[]) and 'giữa kỳ' in t),
  ('class_course_failures',{'question':'Lớp cô có những môn nào nhiều sinh viên không đạt?'},lambda t,m:intent(m,'course_failure') and 'class_course_statistics' in m.get('workflow_tools',[]) and 'không phải tỷ lệ trượt của cả trường' in t),
  ('old_general_synthesis',{'question':'Thí sinh dự tuyển thạc sĩ UET đợt 1 năm 2024 cần năng lực tiếng Anh tối thiểu nào?'},lambda t,m:bool(re.search(r'\bbậc\s*3\b',t,re.I)) and m.get('inference_source')=='local_slm_knowledge'),
  ('red_unchanged',{'question':'Xin ngoại lệ học vượt quy chế cho sinh viên lớp cô.'},lambda t,m:False),
 ]
 passed=0
 for name,body,check in cases:
  r=call('/api/chat',{**body,'force_engine':'auto'});m=r.get('metadata') or {};t=html.unescape(re.sub(r'</?mark>','',str(r.get('answer',''))));ok=r.get('routing',{}).get('risk_tier')=='RED' if name=='red_unchanged' else bool(check(t,m));passed+=ok
  print('PASS' if ok else 'REVIEW',name,m.get('advisor_intent'),m.get('engine_mode'),m.get('inference_source'),flush=True)
  if a.show_demo:print(t+'\n',flush=True)
 # Sequential requests exercise the same signed context endpoint as the browser.
 def follow(question, token=None, mssv=None):
  return call('/api/advisor/chat',{'question':question,'force_engine':'auto','context_token':token,'mssv':mssv})
 def clean(r):return html.unescape(re.sub(r'</?mark>','',str(r.get('answer',''))))
 seed=follow('Em hãy phân tích toàn diện tình hình học tập của sinh viên '+target+'.',mssv=target)
 a1=follow('Nếu cô gặp riêng sinh viên này, cô nên nói gì và cần tìm hiểu thêm những thông tin nào?',seed.get('context_token'))
 a2=follow('Nếu em này vừa đi làm vừa học, cô nên hỗ trợ như thế nào?',a1.get('context_token'))
 a3=follow('Trong buổi gặp đó cô nên hỏi gì?',a2.get('context_token'))
 fresh=follow('Trong buổi gặp đó cô nên hỏi gì?')
 def valid_meeting(r,phrase):
  m=r.get('metadata') or {};t=clean(r)
  return bool(m.get('advisor_intent')=='meeting_preparation' and target in t and all(x not in t for x in others) and phrase in t and r.get('context_resolution',{}).get('kind')=='student_followup' and r.get('context_token'))
 checks=[('meeting_followup',a1,valid_meeting(a1,'Những điều nên hỏi')),('conditional_work_support',a2,valid_meeting(a2,'lịch ca') and 'chưa được ghi nhận' in clean(a2)),('meeting_referent',a3,valid_meeting(a3,'Những điều nên hỏi') and 'lịch ca' in clean(a3) and 'chưa được ghi nhận' in clean(a3)),('meeting_fresh_tab',fresh,fresh.get('metadata',{}).get('engine_mode')=='CONTEXT_CLARIFICATION' and all(sid(s) not in clean(fresh) for s in students))]
 for name,r,ok in checks:
  passed+=bool(ok);print('PASS' if ok else 'REVIEW',name,r.get('metadata',{}).get('advisor_intent'),flush=True)
  if a.show_demo:print(clean(r)+'\n',flush=True)
 # Independent follow-up branch: exact count, correction, isolation and reset.
 short=follow('Chỉ cho cô 2 câu hỏi',a2.get('context_token'))
 corrected=follow('Em ấy không còn đi làm nữa.',a2.get('context_token'))
 after=follow('Trong buổi gặp đó cô nên hỏi gì?',corrected.get('context_token'))
 for name,r,ok in [
  ('focused_two_questions',short,valid_meeting(short,'Những điều nên hỏi') and clean(short).count('• ')==2 and 'lịch ca' in clean(short) and 'Hồ sơ demo:' not in clean(short)),
  ('correction_removes_work',corrected,valid_meeting(corrected,'đính chính') and 'lịch ca' not in clean(corrected)),
  ('correction_persists',after,valid_meeting(after,'Những điều nên hỏi') and 'lịch ca' not in clean(after)),
 ]:
  checks.append((name,r,ok));passed+=bool(ok);print('PASS' if ok else 'REVIEW',name,r.get('metadata',{}).get('advisor_intent'),flush=True)
  if a.show_demo:print(clean(r)+'\n',flush=True)
 # A new situation outside the deterministic context categories. A model fallback
 # is reported as REVIEW, not counted as evidence of adaptive reasoning.
 novel=follow('Nếu cô gặp riêng sinh viên này và em ấy ngại bị bạn bè đánh giá, cô nên hỏi gì?',seed.get('context_token'))
 nm=novel.get('metadata') or {};nt=clean(novel)
 ok=valid_meeting(novel,'Những điều nên hỏi') and nm.get('inference_source')=='local_slm_counseling' and 'local_counseling_proposal' in nm.get('workflow_tools',[])
 passed+=bool(ok);print('PASS' if ok else 'REVIEW','live_adaptive_counseling',nm.get('inference_source'),flush=True)
 if a.show_demo:print(nt+'\n',flush=True)
 total=len(cases)+len(checks)+1
 print(f'INTELLIGENCE_PROBE: {passed}/{total} checks; manual wording review required',flush=True)
 return int(passed!=total)
if __name__=='__main__':sys.exit(main())
