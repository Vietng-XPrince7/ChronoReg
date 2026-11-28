"""Release blockers: API continuity, finance routing, policy selection and negative controls."""
import unittest
from unittest.mock import patch
import test_release_196 as fixture
from mission_intent import eligible,explicit_views
from quality import norm
import advisor_bridge as bridge

class Release(unittest.TestCase):
 def setUp(self):
  self.f=fixture.Continuity();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.root=self.f.root;self.roster=self.f.roster
  self.ask=self.f.ask
 def test_review_and_draft(self):
  r=self.ask('Nếu chỉ học được 17 phút mỗi ngày thì nên thử việc gì?',self.f.legacy());t=r['context_token'];self.assertTrue(t)
  r=self.ask('Phương án này có điểm yếu nào và cô theo dõi kết quả như thế nào?',t);self.assertEqual(r['metadata']['review_views'],['risks','next_steps']);self.assertIn('17 phút',r['answer']);self.assertTrue(r['context_token'])
  r=self.ask('Chuyển thành lời nhắn riêng mời em ấy gặp cô, đừng ghi điểm hay số tín chỉ nợ.',r['context_token']);self.assertIn('Chào em',r['answer']);self.assertNotIn('99000001',r['answer']);self.assertNotIn('tín chỉ',r['answer']);self.assertNotIn('Tiêu đề',r['answer']);self.assertIn('draft',self.f.ctx.read(r['context_token'])['states'])
  self.assertFalse(eligible(norm('Đổi phương án này và theo dõi kết quả')))
  self.assertFalse(eligible(norm('Phương án này có điểm yếu gì, không đánh giá rủi ro')))
 def test_broad_id_not_word_limit(self):
  q='Cô muốn một phương án hỗ trợ tổng thể cho sinh viên demo 99000001, từ tìm hiểu tình hình đến chuẩn bị buổi trao đổi.'
  r=self.ask(q);p=self.f.ctx.read(r['context_token']);self.assertEqual(p['student'],'99000001');self.assertIn('profile',p['states']);self.assertIn('meeting',p['states'])
  r=self.ask('Em thấy thế nào về phương án này?',r['context_token']);self.assertEqual(r['metadata']['review_views'],['feasibility','risks'])
  r=self.ask('Bổ sung kế hoạch tự học 22 phút mỗi ngày, giữ những việc đã có.',r['context_token']);self.assertEqual(self.f.ctx.read(r['context_token'])['states']['study']['minutes'],22)
  r=self.ask(q+' Chỉ 20 từ.');self.assertIn('ràng buộc',r['answer']);self.assertFalse(r['context_token'])
 def test_fee_and_comparison(self):
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('924.000' if '2025-2026' in q else '974.000')+' đồng.'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'},'routing':{}}):
   r=self.ask('CTĐT chuẩn K69 học lại 4 tín chỉ năm học 2025–2026 cần dự trù bao nhiêu?');self.assertIn('3.696.000',r['answer']);self.assertTrue(r['context_token'])
   t=r['context_token'];r=self.ask('Vẫn 4 tín chỉ đó, sang 2026–2027 tăng thêm bao nhiêu?',t);self.assertIn('3.896.000',r['answer']);self.assertIn('200.000',r['answer'])
   r=self.ask('Vẫn 5 tín chỉ đó, sang 2026–2027 tăng thêm bao nhiêu?',t);self.assertNotIn('3.896.000',r['answer'])
 def test_policy_synonym(self):
  c={'answer':'Điểm thưởng dùng xét học bổng, không dùng để xếp loại học lực hoặc xác định hạng tốt nghiệp.','path':'fixture','sha256':'fixture','source_url':'https://example.invalid','articles':[{'article':32,'clause':1}]}
  with patch('advisor_decision.source',return_value=c):
   r,p=bridge.route('Theo cùng quyết định đó, phần thưởng NCKH có được cộng để xác định hạng tốt nghiệp không?',{'topic':'dual_degree'},None,None,self.roster,self.root);self.assertIn('không dùng điểm thưởng',r['answer'])
   self.assertIsNone(bridge.route('Theo cùng quyết định đó, phần thưởng NCKH có được cộng để xác định hạng tốt nghiệp không?',{},None,None,self.roster,self.root))
if __name__=='__main__':unittest.main()
