import os, sys, unittest, json
from pathlib import Path
from types import SimpleNamespace
from scope import classify_with_scope
from scholarship import lookup_rates
from runtime_v5 import install
from test_runtime import Backend
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
LONG='Mức học bổng khuyến khích học tập loại xuất sắc của nhóm Đối với lớp chất lượng cao thuộc ngành Công nghệ thông tin; Các khóa từ QH-2021 trở về trước tại UET năm học 2023-2024 là bao nhiêu?'
# Simulate the actual classification defect: any literal lớp, or QH-2024,
# is treated as class scope. Actual main integration is separately checked below.
def mock_classifier(q, *, roster=None, mssv=None):
    q=q.lower(); ent={'mssv':mssv,'rule_topic':'học bổng'}
    if mssv or 'nguyễn văn a' in q:return 'STUDENT_STATUS',{'mssv':mssv or '24000001'}
    if 'tin mới nhất' in q:return 'EVENT_NEWS',ent
    if 'lớp' in q or 'qh-2024' in q or 'bảng điểm' in q or 'em nào' in q:return 'ELIGIBILITY_CHECK',ent
    return 'REGULATION',ent
class ScopeTests(unittest.TestCase):
 def test_original_long_question(self):
  self.assertEqual(classify_with_scope(mock_classifier,LONG)[0],'REGULATION')
  self.assertIn('2.070.000 đồng/tháng',lookup_rates(ROOT,LONG)['answer'])
 def test_paraphrase(self):
  for q in ['Mức học bổng giỏi lớp CLC CNTT khóa QH-2023 năm học 2023-2024?', 'Mức học bổng xuất sắc lớp chất lượng cao ngành CNTT khóa QH-2021 năm học 2023-2024?']:
   self.assertEqual(classify_with_scope(mock_classifier,q)[0],'REGULATION')
   self.assertIsNotNone(lookup_rates(ROOT,q))
 def test_cohort_not_class(self):
  q='Mức học bổng xuất sắc chương trình chuẩn khóa QH-2024 năm học 2025-2026?'
  self.assertEqual(classify_with_scope(mock_classifier,q)[0],'REGULATION')
 def test_preserve_real_class(self):
  for q in [LONG+' Trong lớp tôi có em nào đủ điều kiện?',LONG+' Bảng điểm lớp mình thế nào?',LONG+' Soi bảng điểm', 'Lớp chất lượng cao CNTT có em nào đủ điều kiện xét học bổng?',LONG+' Các em trong lớp có được nhận không?']:
   self.assertEqual(classify_with_scope(mock_classifier,q)[0],'ELIGIBILITY_CHECK')
 def test_preserve_student_and_news(self):
  self.assertEqual(classify_with_scope(mock_classifier,LONG,mssv='24000001')[0],'STUDENT_STATUS')
  self.assertEqual(classify_with_scope(mock_classifier,LONG+' Nguyễn Văn A')[0],'STUDENT_STATUS')
  self.assertEqual(classify_with_scope(mock_classifier,LONG+' Tin mới nhất')[0],'EVENT_NEWS')
 def test_install_classification_and_dispatch(self):
  b=Backend();server=SimpleNamespace(llm_backend=b,classify_query=mock_classifier,_run_rag_engine=lambda *a,**k:{'old':True},_build_metadata=lambda *a,**k:{})
  install(server,ROOT)
  category,entities=server.classify_query(LONG)
  ab={'category':category,'entities':entities,'roster_context':None if category=='REGULATION' else 'roster'}
  pred=server._run_rag_engine(LONG,'chrono_rag',advisor_bundle=ab)
  self.assertEqual(pred['inference_source'],'deterministic_source_table')
  self.assertIn('2.070.000 đồng/tháng',pred['predicted_answer'])
  self.assertEqual(server.classify_query(LONG,mssv='24000001')[0],'STUDENT_STATUS')
 @unittest.skipUnless((ROOT/'src/router/query_router.py').is_file(),'actual main router not present in source-only fixture')
 def test_actual_main_router(self):
  sys.path.insert(0,str(ROOT))
  try:
   from src.router.query_router import classify_query
   roster={'students':[],'courses':[]}
   self.assertEqual(classify_query(LONG,roster=roster)[0],'ELIGIBILITY_CHECK')
   self.assertEqual(classify_with_scope(classify_query,LONG,roster=roster)[0],'REGULATION')
   self.assertEqual(classify_with_scope(classify_query,LONG,roster=roster,mssv='24000001')[0],'STUDENT_STATUS')
   self.assertEqual(classify_with_scope(classify_query,'Trong lớp tôi có em nào đủ điều kiện xét học bổng?',roster=roster)[0],'ELIGIBILITY_CHECK')
  finally:sys.path.remove(str(ROOT))
if __name__=='__main__':unittest.main()
