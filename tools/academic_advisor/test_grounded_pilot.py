"""Real product streaming handler with synthetic roster and source boundary fixtures."""
import unittest,os
from unittest.mock import patch
import test_release_196 as fixtures
from grounded_product import route
from quality_workflows import snapshot

class GroundedPilot(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Continuity();self.f.setUp();self.addCleanup(self.f.doCleanups);self.roster=self.f.roster;self.root=self.f.root
  x=patch.dict(os.environ,{'CHRONOREG_GROUNDED_PILOT':'1'});x.start();self.addCleanup(x.stop)
 def test_fee_chain(self):
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('974.000' if '2026-2027' in q else '924.000')+' đồng.'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'},'routing':{}}):
   r=self.f.ask('Một sinh viên K69 CTĐT chuẩn nợ hai học phần 3 và 4 tín chỉ. Nếu học lại cả hai trong năm học 2026–2027, cô cần dự kiến kinh phí bao nhiêu?');self.assertIn('6.818.000',r['answer']);self.assertTrue(r['metadata']['grounded_pilot']);t=r['context_token'];self.assertEqual(self.f.ctx.read(t)['fee']['credits'],[3,4]);r=self.f.ask('So với việc học lại đúng hai học phần ấy ở năm học 2025–2026, khoản tiền chênh lệch thế nào?',t);self.assertIn('6.468.000',r['answer']);self.assertIn('350.000',r['answer']);r=self.f.ask('Nếu chỉ học lại môn 4 tín chỉ ở năm học 2025–2026 thì dự kiến bao nhiêu?',r['context_token']);self.assertIn('3.696.000',r['answer'])
 def test_study_chain_and_stale(self):
  t=self.f.legacy();q='Sau buổi gặp, cô muốn thử một tuần tự học 18 phút mỗi ngày cho em ấy. Nên tổ chức ra sao?';r=self.f.ask(q,t);self.assertIn('18 phút/ngày',r['answer']);self.assertTrue(r['metadata']['grounded_pilot']);t2=r['context_token'];self.assertEqual(self.f.ctx.read(t2)['states']['study']['minutes'],18)
  q2='Cuối tuần nên dựa vào dấu hiệu nào để quyết định giữ hay thay đổi phương án vừa lập?';r=self.f.ask(q2,t2);self.assertIn('18 phút',r['answer']);self.assertIn('bài tự làm',r['answer']);self.assertTrue(r['metadata']['grounded_pilot'])
  self.roster['students'][0]['owed_credits']=12;r=self.f.ask(q2,t2);self.assertIn('đã thay đổi',r['answer']);self.assertFalse(r['context_token'])
 def test_review_view_contract(self):
  t=self.f.legacy();r=self.f.ask('Sau buổi gặp, cô muốn thử một tuần tự học 18 phút mỗi ngày cho em ấy. Nên tổ chức ra sao?',t);t=r['context_token']
  r=self.f.ask('Em đánh giá xem phương án này có gì chưa chắc chắn, cô cần kiểm tra gì trước?',t);self.assertEqual(r['metadata']['review_views'],['risks']);self.assertIn('18 phút/ngày',r['answer']);self.assertIn('CPA',r['answer'])
  r=self.f.ask('Cuối tuần nên dựa vào dấu hiệu nào để quyết định giữ hay thay đổi phương án vừa lập?',t);self.assertEqual(r['metadata']['review_views'],['risks','next_steps']);self.assertIn('bài tự làm',r['answer'])
 def test_curriculum_chain(self):
  from types import SimpleNamespace
  def load(root,key):
   p,yr=key.split('_',1);return {'id':key,'source_url':'https://example.invalid/'+key,'cohorts':[2022,2023,2024] if yr=='2022_2024' else [2025,2026],'total':150 if p=='ktmt' else 136 if yr=='2022_2024' else 135,'thesis':7 if yr=='2022_2024' else 10}
  with patch('reviewed_sources.load',side_effect=load):
   r=self.f.ask('Cô cần đối chiếu tổng số tín chỉ của CNTT K69, CNTT K70 và Kỹ thuật máy tính K70 để tư vấn sinh viên.');self.assertTrue(r['metadata']['grounded_pilot']);self.assertIn('150',r['answer']);self.assertEqual(len(r['metadata']['advisor_sources']),3)
   r=self.f.ask('Riêng ngành CNTT, khóa luận tốt nghiệp của K69 và K70 khác nhau bao nhiêu tín chỉ?',r['context_token']);self.assertIn('Chênh lệch 3 tín chỉ',r['answer']);r=self.f.ask('Còn ngành CNTT K72 thì lấy số của K70 luôn được không?',r['context_token']);self.assertIn('không lấy bảng',r['answer']);self.assertNotIn('135',r['answer'])
 def test_policy_and_isolation(self):
  ctx={'kind':'advisor_agent','topic':'evidence_article','article':36,'clause':3};q='Khi muốn trở lại học thì phải nộp đơn trước mốc nào theo chính văn bản đó?';t=self.f.ctx.issue(ctx)
  c={'path':'fixture','sha256':'fixture','source_url':'https://example.invalid','articles':[{'article':36,'clause':3}],'answer':'Sinh viên nghỉ học tạm thời nếu muốn học tiếp phải có đơn ít nhất 2 tuần trước khi hết thời hạn nghỉ học.'}
  with patch('advisor_decision.source',return_value=c):
   r=self.f.ask(q,t);self.assertIn('2 tuần',r['answer']);self.assertTrue(r['metadata']['grounded_pilot']);r=self.f.ask(q,t+'x');self.assertNotIn('2 tuần',r['answer'])
   r=self.f.ask('Còn hồ sơ và phương án học lại của sinh viên cô vừa gặp ở phiên khác, em nhắc lại giúp cô.',t);self.assertIn('không lấy hồ sơ từ phiên khác',r['answer']);self.assertFalse(r['context_token'])
  with patch('advisor_decision.source',side_effect=ValueError('held')):
   r=self.f.ask(q,t);self.assertNotIn('2 tuần',r['answer'])
 def test_guardrails(self):
  p={};q='K69 CTĐT chuẩn học lại hai môn 3 và 4 tín chỉ năm 2026–2027 cần dự kiến kinh phí bao nhiêu?'
  self.assertIsNone(route(q,p,'99000001',None,self.roster,self.root))
  self.assertIsNone(route(q+' xin ngoại lệ',p,None,None,self.roster,self.root))
  self.assertIsNone(route(q+' và soạn thông báo',p,None,None,self.roster,self.root))
  r=self.f.ask('Xin ngoại lệ '+q);self.assertFalse(r['metadata'].get('grounded_pilot'))
  with patch.dict(os.environ,{'CHRONOREG_GROUNDED_PILOT':'0'}):
   r=self.f.ask(q);self.assertFalse(r['metadata'].get('grounded_pilot'))
if __name__=='__main__':unittest.main()
