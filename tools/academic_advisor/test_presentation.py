import unittest,json,os
from pathlib import Path
from test_knowledge import Backend
from regulation import lookup_regulation
from presentation import present,withdrawal_summary
class PresentationTests(unittest.TestCase):
 def setUp(self):
  self.backend=Backend();self.backend.text='{"priority":"A2"}'
  self.source=lookup_regulation(Path(os.environ['CHRONOREG_TEST_REPO']),'Quy trình rút bớt học phần?')['answer']
  self.pred={'engine_mode':'SOURCE_CLAUSE','predicted_answer':self.source,'model_name':None}
 def test_full_withdrawal(self):
  r=present(self.backend,'Quy trình rút bớt học phần?',self.pred)
  self.assertEqual(r['presentation_mode'],'LORA_ADVISOR_PRIORITY');self.assertEqual(r['advisor_priority']['id'],'A2')
  self.assertEqual(r['advisor_evidence'],self.source)
  for term in ['2 tuần','1 tuần','được trả lại học phí','điểm F','18 tín chỉ','khoản 1 Điều 21','Phòng Đào tạo','thủ trưởng','giấy báo']:
   self.assertIn(term,r['predicted_answer'])
  self.assertNotIn('Sinh viên không được rút học phần sau khi học kỳ chính bắt đầu',r['predicted_answer'])
  self.assertEqual(self.backend.calls[0]['format']['properties']['priority']['enum'],['A1','A2','A3'])
 def test_fallback_stays_complete(self):
  self.backend.text='{"priority":"A99"}';r=present(self.backend,'Quy trình rút bớt học phần?',self.pred)
  self.assertEqual(r['presentation_mode'],'SOURCE_ADVISOR_SUMMARY');self.assertIn('1 tuần',r['predicted_answer']);self.assertIsNone(r['model_name']);self.assertEqual(r['narrative_diagnostics'],['invalid_priority'])
 def test_scope(self):
  self.assertIsNone(withdrawal_summary('Quy trình rút bớt học phần?',self.source.replace('1 tuần kể từ đầu học kỳ phụ','')))
  self.assertIsNone(withdrawal_summary('Quy trình rút bớt học phần?',self.source+'\nĐiều 36 — khác'))
 def test_student(self):
  source='Hồ sơ demo: Nguyễn Văn A — 24020001.\n• GPA học kỳ: 1.39.\n• Tín chỉ nợ theo hồ sơ: 27.\nCPA độc lập chưa xác nhận.\n\nLộ trình đề xuất (không phải lịch học chính thức):\n1. Rà môn nợ.\n\nCăn cứ tham khảo:\nĐiều 21.'
  pred={'engine_mode':'ADVISOR_PLAN','predicted_answer':source,'roadmap':[{'title':'Rà nợ','detail':'Kiểm tra học phần nợ.'},{'title':'Rà GPA','detail':'Trao đổi về kết quả học tập.'}]}
  bundle={'student_id':'24020001','roster_obj':{'students':[{'full_name':'Nguyễn Văn A','student_id':'24020001'}]}}
  r=present(self.backend,'Tư vấn Nguyễn Văn A 24020001?',pred,bundle)
  self.assertEqual(r['presentation_mode'],'LORA_ADVISOR_PRIORITY');self.assertIn('27',r['predicted_answer']);self.assertIn('CPA độc lập',r['predicted_answer']);self.assertIn('Điều 21',r['predicted_answer']);self.assertEqual(r['roadmap'],pred['roadmap']);self.assertIn('Kiểm tra học phần nợ',r['predicted_answer']);self.assertNotIn('24020001',self.backend.calls[0]['messages'][1]['content']);self.assertNotIn('Nguyễn Văn A',self.backend.calls[0]['messages'][1]['content'])
 def test_bad_generation_cannot_change_fact(self):
  self.backend.text='{"priority":"A1","text":"Đăng ký 60 tín chỉ"}'
  r=present(self.backend,'Quy trình rút bớt học phần?',self.pred)
  self.assertNotIn('60 tín chỉ',r['predicted_answer']);self.assertIn('18 tín chỉ',r['predicted_answer'])
