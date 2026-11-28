"""Regression of observed free-form failures using synthetic roster/source fixtures."""
import unittest
from unittest.mock import patch
import test_reviewed_sources_192 as fixtures_sources
import test_advisor_tasks_172 as fixtures_tasks
import advisor_bridge as bridge
import advisor_mission as mission
import reviewed_sources as rs
from quality_workflows import snapshot
from quality import norm
class Bridge(unittest.TestCase):
 def setUp(self):
  self.sources=fixtures_sources.Review192();self.sources.setUp();self.addCleanup(self.sources.doCleanups);self.t=fixtures_tasks.Tasks();self.t.setUp();self.root=self.sources.root;self.roster=self.t.roster
 def ask(self,q,p=None):return bridge.route(q,p or {},None,None,self.roster,self.root)
 def test_compare_sources_and_replace(self):
  r,p=self.ask('So sánh tổng tín chỉ toàn khóa và khóa luận ngành CNTT K68 và K71.');self.assertIn('| CNTT QH-2023 | 136 | 7 |',r['answer']);self.assertIn('| CNTT QH-2026 | 135 | 10 |',r['answer']);self.assertEqual(len(r['metadata']['advisor_sources']),2)
  r,p=self.ask('Thay K71 bằng ngành HTTT, giữ CNTT K68.',p);self.assertIn('| Hệ thống thông tin QH-2026 | 135 | 10 |',r['answer']);self.assertIn('| CNTT QH-2023 | 136 | 7 |',r['answer']);self.assertIn('không thể xác nhận',self.ask('Có thể dùng mã INT3306 tương đương không?',p)[0]['answer'])
  self.assertIsNone(self.ask('So sánh CTĐT CNTT CLC K68 và K71 tổng tín chỉ.'))
  self.assertIsNone(self.ask('Thay K71 bằng ngành HTTT, giữ CNTT K68.'))
 def test_fee_workflow(self):
  def lookup(root,q):return {'answer':'• Học lại, cải thiện điểm (đồng/tín chỉ): '+('924.000' if '2025-2026' in q else '974.000')+' đồng.'}
  with patch('tuition.lookup_tuition',side_effect=lookup),patch('advisor_agent.source_table',side_effect=lambda root,v:{'answer':v['answer'],'metadata':{'engine_mode':'SOURCE_TABLE'},'routing':{}}):
   r,p=self.ask('K69 chương trình chuẩn học lại ba môn, mỗi môn 2 tín chỉ năm học 2025–2026 dự trù bao nhiêu tiền?');self.assertIn('5.544.000',r['answer']);self.assertEqual(p['fee']['quantity'],6)
   r,p=self.ask('Chuyển sang năm học 2026–2027 tổng tiền tăng bao nhiêu?',p);self.assertIn('5.844.000',r['answer']);self.assertIn('300.000',r['answer'])
   r,p=self.ask('Mức học bổng KKHT loại Giỏi của em này năm học 2025–2026?',p);self.assertIn('3.500.000',r['answer'])
   r,p=self.ask('Giả định nhận 4 tháng, tổng tiền bao nhiêu?',p);self.assertIn('14.000.000',r['answer'])
  self.assertIsNone(self.ask('K69 CLC học lại 2 môn mỗi môn 3 tín chỉ năm học 2025–2026 hết bao nhiêu tiền?'))
 def test_policy_scope(self):
  c={'answer':'Điểm trung bình chung đạt từ 2,5 trở lên và đáp ứng ngưỡng bảo đảm chất lượng đầu vào hoặc từ 2,0 trở lên và đáp ứng điều kiện trúng tuyển; sinh viên có đơn xin học thêm và trả học phí.','path':'fixture','sha256':'fixture','source_url':'https://example.invalid','articles':[{'article':26,'clause':1}]}
  with patch('advisor_decision.source',return_value=c):
   r,p=self.ask('Theo QĐ 3626, GPA chung các học phần 2,4 có đủ đăng ký học cùng lúc hai CTĐT?');self.assertIn('chưa đủ',r['answer']);self.assertEqual(p['topic'],'dual_degree');self.assertIn('chưa đủ',self.ask('Nếu GPA tăng 2,7 thì tự động đủ điều kiện không?',p)[0]['answer'])
  c['answer']='Điểm thưởng dùng xét học bổng, không dùng để xếp loại học lực hoặc xác định hạng tốt nghiệp.';c['articles']=[{'article':32,'clause':1}]
  with patch('advisor_decision.source',return_value=c):self.assertIn('không dùng điểm thưởng',self.ask('Theo quyết định đó, điểm thưởng NCKH có tăng hạng tốt nghiệp không?',p)[0]['answer'])
  self.assertIsNone(self.ask('Theo QĐ 3626 và QĐ 9999, học hai CTĐT?'))
 def test_notice(self):
  r,p=rs.route('Hạn NCKH Viện TTNT năm học 2025–2026?',{},self.root);r,p=self.ask('Mốc gửi đề xuất từ Khoa lên cấp Trường là ngày nào?',p);self.assertIn('31/03/2026',r['answer']);self.assertEqual(p['academic_year'],'2025-2026')
  with patch('semantic_product.execute',return_value={'answer':'fixture','metadata':{'engine_mode':'SOURCE_TABLE'}}) as exe:
   self.ask('Ngày kết thúc học kỳ II cùng năm học?',p);self.assertEqual(exe.call_args.args[0]['slots'],{'academic_year':'2025-2026','semester':'main_2'})
 def test_mission(self):
  t=self.t;p={}
  with patch('quality_routes.load_candidate',return_value=(t.table,None)),patch('course_planning.load_candidate',return_value=(t.table,None)),patch('mission_review.load_candidate',return_value=(t.table,None)),patch('advisor_compare.load_candidate',return_value=(t.table,None)):
   def go(q,p):return mission.route(q,p,None,None,self.roster,self.root,False)
   r,p=go('Cô muốn biết vì sao nên ưu tiên môn nền tảng trước. Xem hồ sơ sinh viên 99000001 và lập phương án học lại không quá 9 tín chỉ mỗi đợt.',p);self.assertIn('1,4',r['answer']);self.assertEqual(set(p['states']),{'profile','retake'})
   r,p=go('Em ấy chỉ có 15 phút tự học mỗi ngày. Em bổ sung kế hoạch nhẹ nhàng, giữ nguyên lộ trình.',p);self.assertEqual(p['states']['study']['minutes'],15);self.assertEqual(p['states']['retake']['plan']['budget'],9)
   r,p=go('Nếu em ấy muốn tăng tải lên 12 tín chỉ thì em có đồng ý không?',p);self.assertIn('15 phút/ngày',r['answer']);self.assertEqual(p['states']['retake']['plan']['budget'],9)
   r,p=go('Soạn lời nhắn riêng 3 câu, không nhắc điểm số hay số tín chỉ, để cô mời em ấy trao đổi.',p);self.assertIn('draft',p['states']);self.assertNotIn('99000001',r['answer']);self.assertNotIn('Tiêu đề',r['answer'])
   r,p=go('Cô muốn quay lại lộ trình, giảm còn 3 tín chỉ mỗi đợt.',p);self.assertEqual(p['states']['retake']['plan']['budget'],3);self.assertEqual(set(p['states']),{'profile','retake','study','draft'})
   old={'kind':'semantic_task','scope':snapshot(self.roster),'plan':{'intent':'retake_plan','slots':{'student':'99000001','budget':6}}};self.assertEqual(bridge.promote_retake(old,self.roster,self.root)['kind'],'advisor_mission');old['plan']['slots']['first_course']='ABC0001';self.assertIsNone(bridge.promote_retake(old,self.roster,self.root))
if __name__=='__main__':unittest.main()
