import unittest
from unittest.mock import patch
from advisor_composer import compose,clarify
from advisor_evidence import Passage,retrieve,direct_article,select_local
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from test_advisor_evidence_173 import EvidenceTests

class ComposerTests(unittest.TestCase):
 def test_focus_exact_and_context(self):
  text='Điểm kết thúc học phần là bắt buộc và có trọng số không dưới 60% điểm của học phần.'
  p=Passage(text,'Điều 37, khoản 1','p','h','','',37,1)
  r=compose('Trọng số tối thiểu?',p,'trọng số không dưới 60%');self.assertIn('**trọng số không dưới 60%**',r);self.assertIn(text,r)
  for bad in ('trọng số tối thiểu 75%','dưới 60% điểm của học phần','<script>alert(1)</script>'):
   self.assertNotIn('**'+bad+'**',compose('?',p,bad))
 def test_negative_focus(self):
  text='Điểm thưởng dùng xét học bổng, không dùng để xếp loại học lực hoặc xác định hạng tốt nghiệp.'
  p=Passage(text,'Điều 32, khoản 1','p','h','','',32,1)
  self.assertIn('**không dùng để xếp loại học lực hoặc xác định hạng tốt nghiệp**',compose('Có dùng không?',p,'không dùng để xếp loại học lực hoặc xác định hạng tốt nghiệp'))
  self.assertNotIn('**dùng để xếp loại học lực**',compose('?',p,'dùng để xếp loại học lực'))
 def test_clarification(self):
  self.assertIn('điều nào',clarify('Còn khoản 4?',{}));self.assertIsNone(clarify('Còn khoản 4?',{'kind':'advisor_agent','topic':'evidence_article','article':37}))
  self.assertIn('loại học bổng',clarify('Hồ sơ đăng ký học bổng năm học 2025–2026 cần giấy tờ nào?',{}));self.assertIsNone(clarify('Hồ sơ học bổng khuyến khích học tập năm học 2025–2026?',{}))
  self.assertIn('khoa/viện',clarify('Thông báo hoạt động nghiên cứu khoa học UET năm học 2025–2026 quy định hạn đăng ký là khi nào?',{}));self.assertIsNone(clarify('Hạn đăng ký NCKH cấp trường?',{}))

 def test_selector_contract(self):
  p=Passage('Điểm kết thúc học phần có trọng số không dưới 60% điểm học phần.','Điều 37','p','h','','',37,1)
  fake=MagicMock();fake.__enter__.return_value=fake
  with patch('advisor_evidence.urllib.request.build_opener') as opener:
   opener.return_value.open.return_value=fake
   fake.read.return_value=json.dumps({'done_reason':'stop','message':{'content':json.dumps({'id':'P1','sentence':1})}})
   self.assertEqual(select_local('?', [p]),(p,p.text))
   fake.read.return_value=json.dumps({'done_reason':'stop','message':{'content':json.dumps({'id':'P2','sentence':1})}})
   self.assertIsNone(select_local('?', [p]))

class EvidenceContextTests(EvidenceTests):
 def test_semantic_context_and_follow(self):
  articles={37:('Đánh giá kết quả học phần','1. Điểm kết thúc học phần là bắt buộc và có trọng số không dưới 60% điểm của học phần.\n2. Điểm đánh giá thường xuyên được công bố theo quy định.')}
  with patch('advisor_evidence.read_articles',return_value=(articles,'fixture')):
   r,c=retrieve('Theo QĐ 3626, trọng số điểm kết thúc học phần tối thiểu là bao nhiêu?',self.index,True,lambda q,ps:(ps[0],'trọng số không dưới 60%'))
   self.assertIn('60%',r['answer']);self.assertEqual(c['article'],37);self.assertEqual(r['metadata']['articles'],[{'article':37,'clause':1}]);r,c=direct_article('Còn khoản 2?',c,self.root);self.assertIn('Điểm đánh giá thường xuyên',r['answer'])
