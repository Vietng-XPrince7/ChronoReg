import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from advisor_quality_gate import administrative_reference,public_policy,finalize
from advisor_source_precision import public_result

class AdministrationReference(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  p=self.root/'tools/academic_advisor/advisor_administration_notes.json';p.parent.mkdir(parents=True);p.write_bytes(Path(__file__).with_name(p.name).read_bytes());self.note=p
  self.ledger=self.root/'data/versioning/publication_holds.jsonl';self.ledger.parent.mkdir(parents=True);self.ledger.write_text('')
 def test_historical_office(self):
  r,_=administrative_reference(self.root,'Phòng Đào tạo có nhiệm vụ gì?',{});self.assertIn('2017',r['answer']);self.assertIn('chưa xác minh',r['answer']);self.assertIn('tuyển sinh',r['answer']);self.assertEqual(finalize(r,'Phòng Đào tạo có nhiệm vụ gì?')['metadata']['quality_gate'],'DISPLAY_CHECKED_NOT_SEMANTIC_APPROVAL')
 def test_admission(self):
  for q in ['Quy trình xác nhận nhập học UET 2026 như thế nào?','K71 nhập học cần làm gì?']:
   r,_=administrative_reference(self.root,q,{});self.assertIn('21/08/2026',r['answer']);self.assertIn('StudentHub',r['answer']);self.assertIn('03/09/2026',r['answer']);self.assertEqual(len(r['metadata']['advisor_sources']),2)
 def test_wrong_scope(self):
  for q in ['K70 xác nhận nhập học như thế nào?','Quy trình xác nhận nhập học UET 2025?','Quy trình xác nhận nhập học UET 2026 có gia hạn không?', 'Phòng Đào tạo hiện nay phụ trách gì?', 'Quy trình nhập học thạc sĩ 2026?', 'Quy trình xác nhận nhập học HUTECH 2026?', 'K70 xác nhận nhập học 2026?', 'Phòng Đào tạo có nhiệm vụ gì năm 2026?']:
   self.assertIsNone(administrative_reference(self.root,q,{}),q)
  self.assertIsNone(administrative_reference(self.root,'Phòng Đào tạo có nhiệm vụ gì?',{'kind':'student'}))
 def test_hold_and_tamper(self):
  q='Phòng Đào tạo có nhiệm vụ gì?'
  self.ledger.write_text(json.dumps({'doc_id':'other','content_sha256':'a'*64,'source_url':'https://uet.vnu.edu.vn/phong-dao-tao/'})+'\n');self.assertIsNone(administrative_reference(self.root,q,{}))
  self.ledger.write_text('');self.note.write_text('{}');self.assertRaises(ValueError,administrative_reference,self.root,q,{})
 def test_leave_compare(self):
  c={'path':'rules.md','sha256':'a'*64,'source_url':'https://example.test/rules','articles':[]}
  cs=[dict(c,answer='Bảo lưu. Xin học tiếp 2 tuần trước khi hết hạn.'),dict(c,answer='Buộc thôi học. Không đăng ký học 2 học kỳ liên tiếp. Hết hạn nghỉ học tạm thời.')]
  with patch('advisor_quality_gate.get',side_effect=cs):
   r,_=public_policy(self.root,'Nghỉ học tạm thời khác buộc thôi học ở điểm nào?',{});self.assertIn('Hai hình thức không đồng nhất',r['answer']);self.assertIn('2 tuần',r['answer'])
