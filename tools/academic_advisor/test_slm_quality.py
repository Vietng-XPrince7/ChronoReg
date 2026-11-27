import json,os,unittest
from pathlib import Path
from types import SimpleNamespace
from knowledge import Index
from slm_advisor import course_credits,suggest_detailed,present
from presentation import present as source_present
from regulation import lookup_regulation
from portable_runtime import fix_response
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
Q='tôi bị trượt 1 môn có bị hạ bằng k'
def model(*responses):
 calls=[];it=iter(responses)
 def post(*a,**kw):
  calls.append(kw);v=next(it)
  if isinstance(v,Exception):raise v
  return SimpleNamespace(json=lambda:{'message':{'content':json.dumps(v,ensure_ascii=False)},'done_reason':'stop'},raise_for_status=lambda:None)
 return SimpleNamespace(lora_model='model',ollama_url='local',ollama_timeout=1,_make_client=lambda *a,**kw:(SimpleNamespace(post=post),False)),calls
class QualityTests(unittest.TestCase):
 def test_course_exact(self):
  idx=Index(ROOT);r=course_credits(idx,'Học phần EPN2062 trong chương trình Kỹ thuật vật lý QH-2022 có bao nhiêu tín chỉ?')
  self.assertIn('EPN2062 – Vật lý chất rắn có 3 tín chỉ',r['predicted_answer']);self.assertIn('chưa được xác nhận',r['predicted_answer']);self.assertEqual(r['engine_mode'],'SOURCE_COURSE_ROW')
  self.assertIsNone(course_credits(idx,'EPN2062 ngành CNTT QH-2022 có bao nhiêu tín chỉ?'))
  self.assertIsNone(course_credits(idx,'EPN2062 ngành Vật lý kỹ thuật có bao nhiêu tín chỉ?'))
 def pred(self):return {'engine_mode':'SOURCE_CLAUSE','predicted_answer':lookup_regulation(ROOT,Q)['answer'],'latency_ms':0}
 def test_free_advice(self):
  b,c=model({'advice':'Cô nên cùng sinh viên rà lại các học phần đã học lại.'});r=present(source_present,b,Q,self.pred(),{});self.assertEqual(r['presentation_mode'],'SLM_ADVISOR');self.assertIn('5%',r['predicted_answer']);self.assertEqual(len(c),1)
 def test_priority_fallback(self):
  b,c=model({'advice':'Sinh viên chắc chắn đủ điều kiện.'},{'priority':'A2'});r=present(source_present,b,Q,self.pred(),{});self.assertEqual(r['presentation_mode'],'SLM_ADVISOR_PRIORITY');self.assertEqual(r['advisor_priority']['selected_by'],'slm');self.assertEqual(r['narrative_diagnostics'],['unverified_assertion']);self.assertEqual(len(c),2);self.assertIn('5%',r['predicted_answer']);self.assertEqual(fix_response({'metadata':r},'local-slm')['metadata']['inference_source'],'local_slm_priority')
 def test_client_failure_no_retry(self):
  b,c=model(TimeoutError());r=present(source_present,b,Q,self.pred(),{});self.assertEqual(r['presentation_mode'],'SOURCE_ADVISOR_SUMMARY');self.assertEqual(r['narrative_diagnostics'],['client_TimeoutError']);self.assertEqual(len(c),1)
 def test_invalid_priority(self):
  b,c=model({'advice':'Cô yêu cầu thêm 100 tín chỉ.'},{'priority':'A999'});r=present(source_present,b,Q,self.pred(),{});self.assertEqual(r['presentation_mode'],'SOURCE_ADVISOR_SUMMARY');self.assertEqual(r['narrative_diagnostics'],['numeric_advice','invalid_priority']);self.assertEqual(len(c),2)
if __name__=='__main__':unittest.main()
