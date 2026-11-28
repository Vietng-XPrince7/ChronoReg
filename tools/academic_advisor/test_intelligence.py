import json,os,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from intelligence import dispatch,task_plan,policy_query,course_counts,explicit_gpa
from course_planning import REL, load_candidate, candidate_source, candidate_label
from regulation import TEXT,PDF
ROOT=Path(os.environ.get('CHRONOREG_TEST_REPO','.')).resolve()

class IntelligenceTests(unittest.TestCase):
 def setUp(self):
  courses=[{'ma_mon':c,'ten_mon':c,'so_tin_chi':k} for c,k in [('INT1008',3),('INT2210',4),('INT2204',3),('INT2212',4),('INT2211',4),('INT3306',3),('LAW1050',2),('MAT1042',4),('MAT1041',4)]]
  failed=[c['ma_mon'] for c in courses if c['ma_mon']!='MAT1041']
  self.student={'student_id':'24000001','full_name':'Demo A','gpa_semester':1.39,'drl':68,'owed_credits':27,'accumulated_credits':57,'bang_diem':[{'ma_mon':c,'dat':False} for c in failed]+[{'ma_mon':'MAT1041','dat':True}]}
  self.other={'student_id':'24000002','full_name':'Demo B','gpa_semester':3.5,'drl':90,'owed_credits':0,'bang_diem':[{'ma_mon':'INT1008','dat':True},{'ma_mon':'INT2210','dat':False},{'ma_mon':'INT2210','dat':True}]}
  self.roster={'major':'Công nghệ Thông tin','class_short':'K69-CNTT1','cohort':'QH-2024 (K69)','semester':'Học kỳ 2025.1 (Năm học 2025-2026)','students':[self.student,self.other],'courses':courses}
  self.cls={'category':'CLASS_STATS','roster_obj':self.roster,'entities':{}}
  self.ind={'category':'STUDENT_STATUS','roster_obj':self.roster,'student_id':'24000001','entities':{'mssv':'24000001'}}
  self.public={'category':'REGULATION','entities':{}}
 def source(self):
  if not (ROOT/TEXT).is_file() or not (ROOT/PDF).is_file():self.skipTest('Pinned regulation absent from fixture')
 def test_policy_vs_class(self):
  self.source()
  for q in ['Sinh viên lớp cô trượt một môn thì có bị hạ bằng không?','Sinh viên của lớp cô rớt 1 môn có bị hạ loại bằng không?','Một sinh viên lớp cô nợ môn thì có bị hạ hạng tốt nghiệp không?']:
   with self.subTest(q=q):
    p=dispatch(q,self.cls,ROOT);a=p['predicted_answer'];self.assertIn('không nhất thiết',a.split('\n')[0]);self.assertIn('5%',a);self.assertNotIn('Demo A',a);self.assertNotIn('Hồ sơ demo',a);self.assertEqual(p['engine_mode'],'SOURCE_CLAUSE');self.assertEqual(p['advisor_intent'],'policy_question')
 def test_credit_condition(self):
  self.source()
  for q in ['Sinh viên có GPA học kỳ 1,8 thì kỳ sau được đăng ký tối đa bao nhiêu tín chỉ?','GPA học kỳ 1.6, sinh viên được đăng ký bao nhiêu tín chỉ tối đa?','Điểm trung bình chung học kỳ là 1,9 thì được đăng ký bao nhiêu tín chỉ?']:
   p=dispatch(q,self.public,ROOT);a=p['predicted_answer'];self.assertIn('18 tín chỉ',a.split('\n')[0]);self.assertIn('chưa thuộc diện bị buộc thôi học',a);self.assertNotIn('24 tín chỉ',a);self.assertIn('Điều 21',a)
 def test_credit_boundary_and_summer(self):
  self.source()
  q='GPA học kỳ 2,0 thì được đăng ký tối đa bao nhiêu tín chỉ?';a=dispatch(q,self.public,ROOT)['predicted_answer'];self.assertIn('không thuộc điều kiện',a);self.assertIn('chưa thể xác định',a)
  q='GPA học kỳ 1,8 thì học kỳ phụ được đăng ký tối đa bao nhiêu tín chỉ?';a=dispatch(q,self.public,ROOT)['predicted_answer'];self.assertIn('không thể tự áp dụng cho kỳ phụ',a)
 def test_version_and_hold(self):
  for q in ['Sinh viên lớp cô QH-2026 trượt một môn có bị hạ bằng không?','So sánh quy định hạ bằng 3626 và 5115?','Trong lớp cô sinh viên nào có nguy cơ hạ bằng?']:
   self.assertIsNone(policy_query(q,self.cls),q)
  q='Sinh viên lớp cô trượt một môn thì có bị hạ bằng không?'
  with patch('intelligence.lookup_regulation',side_effect=ValueError('hold')):
   p=dispatch(q,self.cls,ROOT);self.assertEqual(p['engine_mode'],'SOURCE_CLAUSE_UNAVAILABLE');self.assertNotIn('5%',p['predicted_answer'])
 def test_hypothetical_not_roster(self):
  self.assertIsNone(policy_query('Sinh viên này trượt một môn có bị hạ bằng không?',self.ind))
  self.assertIsNone(explicit_gpa('GPA tích lũy 1,8'))
  self.assertIsNone(explicit_gpa('GPA học kỳ 5,0'))
 def test_student_full_review(self):
  if not (ROOT/REL).is_file():self.skipTest('Pinned curriculum absent')
  p=dispatch('Em hãy phân tích toàn diện tình hình học tập của sinh viên Demo A, mã sinh viên 24000001.',self.ind,ROOT);a=p['predicted_answer'];self.assertIn('ưu tiên gặp riêng',a.split('\n')[0]);self.assertIn('INT1008 là tiên quyết',a);self.assertIn('LAW1050',a);self.assertIn('Chưa xếp được',a);self.assertIn('57 tín chỉ tích lũy',a);self.assertNotIn('Demo B',a);self.assertIn('prerequisite_planning',p['workflow_tools']);self.assertIn('credit_scenarios',p['workflow_tools']);self.assertIn('chưa đủ',a);self.assertTrue(p['advisor_compact']);table,reason=load_candidate(ROOT,self.roster);self.assertIsNotNone(table,reason);self.assertIn(candidate_label(table),a);self.assertIn(candidate_source(table),p['advisor_sources'])
 def test_strategy(self):
  p=dispatch('Cô muốn tất cả sinh viên trong lớp tốt nghiệp đúng hạn. Em hãy phân tích những trở ngại hiện tại và đề xuất một chiến lược để cô đạt được mục tiêu đó.',self.cls,ROOT);a=p['predicted_answer'];self.assertEqual(p['advisor_intent'],'class_strategy');self.assertIn('1 sinh viên',a.split('\n')[0]);self.assertIn('Trước khi đăng ký',a);self.assertIn('Sau mỗi kỳ',a);self.assertIn('số tín chỉ nợ còn lại',a);self.assertIn('chưa có đủ dữ liệu',a);self.assertNotIn('Demo A',a);self.assertIn('graduation_checklist',p['workflow_tools'])
 def test_daily(self):
  p=dispatch('Nếu em là trợ lý riêng của cô, dựa vào toàn bộ thông tin hiện có về lớp, em nghĩ hôm nay cô nên ưu tiên làm những công việc gì?',self.cls,ROOT);a=p['predicted_answer'];self.assertEqual(p['advisor_intent'],'class_priorities');self.assertIn('Demo A',a);self.assertNotIn('Demo B',a);self.assertIn('Cuối buổi',a);self.assertIn('2025.1',a)
 def test_course_history_counts(self):
  self.assertIn(('INT2210',1,2,1),course_counts(self.roster['students']));self.assertEqual(course_counts([self.student,self.student]),[])
  p=dispatch('Lớp cô có những môn nào nhiều sinh viên không đạt?',self.cls,ROOT);self.assertEqual(p['advisor_intent'],'course_failure');self.assertIn('INT2210',p['predicted_answer']);self.assertIn('không phải tỷ lệ trượt của cả trường',p['predicted_answer'])
 def test_scope_and_no_data(self):
  p=dispatch('Hôm nay cô nên làm gì trước cho lớp K68?',self.cls,ROOT);self.assertEqual(p['workflow_tools'],['scope_check']);self.assertNotIn('Demo A',p['predicted_answer'])
  p=dispatch('Phân tích toàn diện tình hình học tập sinh viên này',{**self.ind,'student_id':'unknown'},ROOT);self.assertEqual(p['workflow_tools'],['scope_check']);self.assertNotIn('Demo A',p['predicted_answer'])
 def test_wrong_scope_earlier_cohorts(self):
  for k in ('K65','K66','K68','K71'):
   with self.subTest(k=k):
    a=dispatch('Hôm nay cô nên làm gì trước cho lớp '+k+'?',self.cls,ROOT)
    self.assertEqual(a['workflow_tools'],['scope_check']);self.assertEqual(a['advisor_intent'],'scope_clarification');self.assertNotIn('Demo A',a['predicted_answer']);self.assertNotIn('24000001',a['predicted_answer'])
  self.assertIsNone(dispatch('Quy chế năm 2021 về hạ bằng của sinh viên khóa K65?',self.public,ROOT))
 def test_rank_by_debt_not_id(self):
  from workflow import screening
  students=[dict(self.student,student_id='1',owed_credits=10,gpa_semester=1.1),dict(self.student,student_id='2',owed_credits=40,gpa_semester=1.8),dict(self.student,student_id='3',owed_credits=40,gpa_semester=1.0),dict(self.student,student_id='4',owed_credits=None,gpa_semester=1.0)]
  groups,_=screening(students);self.assertEqual([x[0] for x in groups[1]],['3','2','1']);self.assertEqual([x[0] for x in groups[2]],['4'])
  b={**self.cls,'roster_obj':{**self.roster,'students':students[:3]}}
  a=dispatch('Hôm nay cô nên làm gì trước cho lớp?',b,ROOT)['predicted_answer'];self.assertLess(a.index('(3)'),a.index('(2)'));self.assertLess(a.index('(2)'),a.index('(1)'));self.assertIn('không phải xếp hạng học vụ',a)
 def test_improvement_is_not_graduation(self):
  a=dispatch('Em hãy lập kế hoạch cải thiện kết quả học tập cho cả lớp trong học kỳ tới.',self.cls,ROOT)
  self.assertEqual(a['advisor_intent'],'class_improvement');self.assertNotIn('graduation_checklist',a['workflow_tools']);self.assertIn('giữa kỳ',a['predicted_answer']);self.assertNotIn('Điều 46',a['predicted_answer'])
  a=dispatch('Đề xuất giải pháp giảm tín chỉ nợ cho lớp cô.',self.cls,ROOT)
  self.assertEqual(a['advisor_intent'],'class_improvement')
 def test_compare_budgets_without_claiming_optimum(self):
  if not (ROOT/REL).is_file():self.skipTest('Pinned curriculum absent')
  a=dispatch('Đánh giá toàn diện tình hình học tập của sinh viên này',self.ind,ROOT)['predicted_answer']
  self.assertIn('tối đa 6 tín chỉ',a);self.assertIn('tối đa 12 tín chỉ',a);self.assertIn('phương án giảm tải',a);self.assertIn('chưa chọn mức đăng ký',a);self.assertIn('không đồng nghĩa số học kỳ',a)
 def test_preserve_other_tasks(self):
  for q,b in [('Lập báo cáo tư vấn và soạn thông báo cho lớp cô',self.cls),('So sánh phương án học lại tối đa 8 tín chỉ môn nợ',self.ind),('GPA trung bình lớp?',self.cls),('Hãy tư vấn lộ trình học tập cho sinh viên này',self.ind),('Em này cần ưu tiên điều gì trong lộ trình?',self.ind),('Điểm chuẩn UET năm 2024?',self.public)]:self.assertIsNone(task_plan(q,b),q)
 def test_local_model_plan(self):
  calls=[]
  def post(*a,**kw):
   calls.append(kw);return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'done_reason':'stop','message':{'content':json.dumps({'goal':'student_review'})}})
  b=SimpleNamespace(lora_model='local',ollama_timeout=1,ollama_url='local',_make_client=lambda *a,**k:(SimpleNamespace(post=post),False))
  q='Cô muốn có giải pháp giúp sinh viên Demo A 24000001'
  r=task_plan(q,self.ind,b);self.assertEqual(r.source,'local_slm_selection');self.assertEqual(r.goal,'student_review');self.assertNotIn('Demo A',str(calls));self.assertNotIn('24000001',str(calls));self.assertIsNone(task_plan(q,self.cls,b))
  with patch.object(b,'_make_client',side_effect=TimeoutError):self.assertIsNone(task_plan(q,self.ind,b))
 def test_advice_dedup(self):
  from slm_advisor import novel_advice
  base='Kiểm tra ngày bắt đầu học kỳ và thời hạn rút trước khi hướng dẫn sinh viên nộp đơn. Nếu quá hạn, học phần vẫn trong phiếu đăng ký; tự ý không học sẽ nhận điểm F và không được trả lại học phí.'
  self.assertIsNone(novel_advice('Cô có thể tham khảo: Kiểm tra ngày bắt đầu học kỳ và thời hạn rút trước khi hướng dẫn sinh viên nộp đơn. Nếu quá hạn, học phần vẫn trong phiếu đăng ký; tự ý không học sẽ nhận điểm F và không được trả lại học phí.',base))
  self.assertEqual(novel_advice('Cô nên kiểm tra ngày bắt đầu học kỳ và thời hạn rút trước khi hướng dẫn sinh viên nộp đơn. Cô nên trao đổi riêng về khó khăn của sinh viên.',base),'Cô nên trao đổi riêng về khó khăn của sinh viên.')
 def test_http_auto_only(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel
  import run_live,conversation
  from portable_runtime import install
  class Request(BaseModel):
   question:str;force_engine:str|None=None;mssv:str|None=None
  with patch.object(run_live,'answer',run_live.answer),patch.object(conversation,'next_context',conversation.next_context):
   app=FastAPI();backend=SimpleNamespace(lora_model='disabled',base_model='disabled',ollama_url='http://local')
   def route(q,student_context=None):return SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN',selected_engine='continual_lora',actual_engine_used='continual_lora',detected_signals=[],routing_reason='original')
   s=SimpleNamespace(app=app,llm_backend=backend,_router=SimpleNamespace(route_decision=route),_run_rag_engine=lambda *a,**k:{'predicted_answer':'original','engine_mode':'ORIGINAL','latency_ms':0},_build_metadata=lambda *a,**k:{})
   @app.post('/api/chat')
   def chat(req:Request):
    r=s._router.route_decision(req.question)
    if r.risk_tier=='RED':return {'routing':{'risk_tier':'RED'},'answer':'blocked'}
    mode=req.force_engine if req.force_engine not in (None,'auto') else r.selected_engine
    if mode=='continual_lora':return s._run_web_lora(req.question)
    p=s._run_rag_engine(req.question,mode,advisor_bundle=self.cls)
    return {'question':req.question,'answer':p['predicted_answer'],'metadata':s._build_metadata([],p['latency_ms'],pred=p)}
   install(s,ROOT);client=TestClient(app);q='Hôm nay cô nên làm gì trước cho lớp?';body={'question':q,'force_engine':'auto'}
   r=client.post('/api/chat',json=body).json();self.assertEqual(r['metadata']['advisor_intent'],'class_priorities');self.assertTrue(r['metadata']['advisor_compact']);self.assertEqual(client.post('/api/chat',json={**body,'force_engine':'chrono_rag'}).json()['answer'],'original');self.assertEqual(client.post('/api/chat',json={**body,'question':q+' xin ngoại lệ'}).json()['routing']['risk_tier'],'RED')

if __name__=='__main__':unittest.main()
