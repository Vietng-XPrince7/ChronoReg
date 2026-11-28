import unittest,json
from types import SimpleNamespace
from pathlib import Path
import os
from adaptive_counsel import propose,validated
from intelligence import dispatch
from conversation import resolve
ROOT=Path(os.environ.get('CHRONOREG_TEST_REPO','.')).resolve()

def backend(*responses):
 calls=[];it=iter(responses)
 def post(*args,**kw):
  calls.append(kw);v=next(it)
  if isinstance(v,Exception):raise v
  return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'done_reason':'stop','message':{'content':json.dumps(v,ensure_ascii=False)}})
 return SimpleNamespace(lora_model='local',ollama_url='local',ollama_timeout=180,_make_client=lambda *a,**kw:(SimpleNamespace(post=post),False)),calls

class AdaptiveTests(unittest.TestCase):
 def setUp(self):
  self.ab={'category':'STUDENT_STATUS','student_id':'24000001','entities':{'mssv':'24000001'},'roster_obj':{'class_short':'K69-CNTT1','cohort':'QH-2024 (K69)','students':[{'student_id':'24000001','full_name':'Demo A','gpa_semester':1.4,'owed_credits':7,'drl':68},{'student_id':'24000002','full_name':'Demo B'}],'courses':[]}}
  self.good={'questions':['Em muốn cô trao đổi riêng theo cách nào để em cảm thấy thoải mái hơn?'],'action':'private'}
 def test_novel_situation(self):
  b,c=backend(self.good);p=dispatch('Gặp riêng Demo A 24000001, nếu em ngại bạn bè đánh giá thì cô nên hỏi gì?',self.ab,ROOT,b)
  self.assertEqual(p['inference_source'],'local_slm_counseling');self.assertIn('local_counseling_proposal',p['workflow_tools']);self.assertIn(self.good['questions'][0],p['predicted_answer']);self.assertIn('7 tín chỉ nợ',p['predicted_answer']);self.assertNotIn('Demo B',p['predicted_answer']);self.assertNotIn('24000001',str(c));self.assertNotIn('Demo A',str(c));self.assertNotIn('Demo B',str(c));self.assertEqual(c[0]['timeout'],25)
 def test_semantic_tool_selection(self):
  b,c=backend({'goal':'meeting_preparation'},self.good);p=dispatch('Em này ngại chia sẻ với cô, cô nên làm thế nào?',self.ab,ROOT,b);self.assertEqual(p['advisor_intent'],'meeting_preparation');self.assertEqual(p['planner_source'],'local_slm_selection');self.assertEqual(len(c),2)
 def test_fail_closed(self):
  for response in [TimeoutError(),{'questions':['Em đã bị cảnh báo học vụ chưa?'],'action':'private'},{'questions':['Em có thể học 18 tín chỉ không?'],'action':'study'},{'questions':['Em muốn cô trao đổi với Demo B không?'],'action':'private'},{'questions':['Em muốn hỗ trợ thế nào?'],'action':'send_message'}]:
   b,_=backend(response);p=dispatch('Gặp riêng em này cô nên hỏi gì?',self.ab,ROOT,b);self.assertEqual(p['inference_source'],'deterministic_workflow_tools');self.assertNotIn('local_counseling_proposal',p['workflow_tools']);self.assertIn('7 tín chỉ nợ',p['predicted_answer'])
 def test_scope_before_model(self):
  b,c=backend(self.good);p=dispatch('Gặp riêng sinh viên này lớp K65 cô nên hỏi gì?',self.ab,ROOT,b);self.assertEqual(p['workflow_tools'],['scope_check']);self.assertEqual(c,[])
 def test_no_repeat(self):
  self.assertIsNone(validated(self.good,self.good['questions'][0],self.ab))
 def test_context(self):
  q='Em này ngại chia sẻ với cô, cô nên làm thế nào?';self.assertEqual(resolve(q,None,{'kind':'student','mssv':'24000001'})[1:],('24000001','student_followup'));self.assertEqual(resolve(q,None,{})[2],'clarify_student')
 def test_legal_not_adaptive(self):
  from counseling import open_support
  from quality import norm
  self.assertFalse(open_support(norm('Em này có được miễn học phí không, cô nên hỗ trợ thế nào?')))
