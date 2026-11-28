import unittest
from pathlib import Path
from unittest.mock import patch
from advisor_fact_application import route,numeric_slots
from advisor_quality_gate import scholarship_policy,finalize
from decimal import Decimal

class FactApplication(unittest.TestCase):
 def setUp(self):
  self.root=Path('.')
  self.clauses={(47,5):'Xuất sắc: 3,60 đến 4,00; Giỏi: 3,20 đến 3,59; Khá: 2,50 đến 3,19.',(47,7):'hạng xuất sắc hoặc giỏi, hạng tốt nghiệp sẽ bị hạ một hạng nếu bị kỷ luật từ mức cảnh cáo trở lên hoặc học lại vượt quá 5%.',(21,1):'khối lượng tối đa không vượt quá 3/2 khối lượng trung bình một học kỳ',(23,1):'Điểm trung bình chung học kỳ dưới 2,00 nhưng chưa thuộc diện bị buộc thôi học, sinh viên được đăng ký học không quá 18 tín chỉ trong mỗi học kỳ chính.',(36,3):'Bị ốm, thai sản hoặc tai nạn phải điều trị thời gian dài có chứng nhận của cơ sở khám bệnh, chữa bệnh. Vì lý do cá nhân khác nhưng phải học tối thiểu 01 học kỳ và đạt điểm trung bình chung tích lũy tổi thiểu 2,0. Các đối tượng ở điểm a, b,c khoản 3 thời gian nghỉ học tạm thời không tính vào thời gian tối đa được phép học.'}
 def get(self,root,a,k):
  return dict(path='rules.md',sha256='a'*64,source_url='https://example.test/rules',answer=self.clauses[a,k],articles=[])
 def ask(self,q):
  with patch('advisor_fact_application.get',side_effect=self.get):
   r=route(self.root,q,{})
   self.assertIsNotNone(r,q);return finalize(r[0],q)['answer']
 def test_slots(self):
  self.assertEqual(numeric_slots('GPA kỳ trước 2,1 nhưng CPA 1,8.'),{'gpa':Decimal('2.1'),'cpa':Decimal('1.8')});self.assertEqual(numeric_slots('CPA 2,3 hoặc CPA 3,2'),{});self.assertEqual(numeric_slots('CPA 9,2'),{})
 def test_rank(self):
  for value,rank,after in [('3,25','giỏi','Khá'),('3.90','xuất sắc','Giỏi')]:
   q=f'K68 muốn nhận bằng {rank}, nếu CPA {value} nhưng bị cảnh cáo kỷ luật thì có giữ được hạng không?';self.assertIn('xuống **'+after,self.ask(q))
 def test_load(self):
  for value,phrase in [('2,1','không kích hoạt'),('2.0','không kích hoạt'),('1,99','18 tín chỉ')]:
   self.assertIn(phrase,self.ask(f'K69 học kỳ chính, GPA kỳ trước {value} nhưng CPA 1,8. Chỉ dựa vào CPA có thể khẳng định trần 18 tín chỉ không?'))
 def test_leave(self):
  for v,expected in [('1,8','chưa đáp ứng'),('2.0','đáp ứng riêng')]:self.assertIn(expected,self.ask(f'K69 đã học một học kỳ, CPA {v} và muốn bảo lưu vì lý do cá nhân; có đáp ứng ngưỡng CPA theo QĐ 3626 không?'))
  self.assertIn('Không tính vào thời gian',self.ask('Theo QĐ 3626, nghỉ giữa chừng do tai nạn phải điều trị dài ngày có bị tính vào thời gian đào tạo tối đa không?'))
 def test_scope_and_ambiguity(self):
  for q in ['K71 CPA 3,25 bằng giỏi bị cảnh cáo kỷ luật','K68 CPA 3,25 bằng giỏi không bị cảnh cáo kỷ luật','K69 CPA 2,1 hoặc CPA 1,8 bảo lưu vì lý do cá nhân','K69 GPA kỳ trước 1,8 CPA 2,0 kỳ phụ trần 18 tín chỉ','K69 CPA 1,8 bảo lưu lý do cá nhân theo QĐ 5115']:
   with patch('advisor_fact_application.get',side_effect=self.get):self.assertIsNone(route(self.root,q,{}),q)
  with patch('advisor_fact_application.get',return_value=None):self.assertIsNone(route(self.root,'K69 CPA 1,8 bảo lưu vì lý do cá nhân',{}))
 def test_pg_compare(self):
  t='I. TUYỂN SINH BẬC THẠC SĨ Tiếng Anh từ Bậc 3 trở lên trong thời hạn 2 năm. II. TUYỂN SINH BẬC TIẾN SĨ Chứng chỉ ngoại ngữ đạt trình độ tương đương Bậc 4 trở lên trong thời hạn 2 năm.'
  q='Tuyển sinh thạc sĩ và tiến sĩ UET 2026: nếu sử dụng chứng chỉ, yêu cầu bậc ngoại ngữ tối thiểu khác nhau ra sao?'
  with patch('advisor_public_sections.read_source',return_value=(t,'a'*64)):
   r,_=route(self.root,q,{});self.assertIn('3/6',r['answer']);self.assertIn('4/6',r['answer']);self.assertIsNone(route(self.root,q.replace('2026','2025'),{}))
 def test_compare_versions(self):
  q='Ngành Robot QH-2025 và QH-2024 có cùng cách trình bày chuẩn đầu ra không?'
  def rows(root,q,*a):return [dict(content_path=q,content_sha256='a'*64,doc_id=q)]
  with patch('advisor_public_sections.catalog_rows',side_effect=rows),patch('advisor_public_sections.read_source',side_effect=[('old','a'*64),('new','b'*64)]),patch('advisor_public_sections.parse_plo',side_effect=[[('PLO1','text'),('PLO2','text')],[]]),patch('advisor_public_sections.grouped_outcomes',return_value=[('Kiến thức',['a']),('Kỹ năng',['b'])]):
   r,_=route(self.root,q,{});self.assertIn('2 yêu cầu có nhãn PLO',r['answer']);self.assertIn('2 nhóm',r['answer']);self.assertEqual(len(r['metadata']['advisor_sources']),2)
 def test_deadline(self):
  from test_advisor_administration_reference import AdministrationReference
  t=AdministrationReference('test_admission');t.setUp();self.addCleanup(t.temp.cleanup)
  q='Hạn nộp minh chứng xét tuyển trực tuyến của tân sinh viên UET QH-2026 theo thông báo cập nhật là ngày nào?'
  r,_=route(t.root,q,{});self.assertIn('03/09/2026',r['answer']);self.assertIsNone(route(t.root,q.replace('QH-2026','QH-2025'),{}))
 def test_scholarship(self):
  t='; '.join(['điểm rèn luyện đạt loại tốt trở lên','điểm trung bình chung học kỳ và điểm rèn luyện đều đạt loại xuất sắc','điểm rèn luyện đều đạt loại khá','hoàn thành ít nhất 15 tín chỉ','mức thấp hơn giữa kết quả học tập và kết quả rèn luyện','áp dụng từ học kỳ I năm học 2026-2027','học kỳ II năm học 2025-2026','không bị kỷ luật từ mức khiển trách trở lên','thay thế cho các văn bản được ban hành trước đó'])
  q='Theo quy định KKHT áp dụng từ HKI 2026-2027, nếu kết quả học tập xuất sắc nhưng rèn luyện chỉ khá thì xét loại gì?'
  with patch('advisor_public_sections.read_source',return_value=(t,'a'*64)):
   for academic,i in [('khá',0),('giỏi',1),('xuất sắc',2)]:
    for conduct,j in [('khá',0),('tốt',1),('xuất sắc',2)]:
     query=f'Theo quy định KKHT áp dụng từ HKI 2026-2027, nếu kết quả học tập {academic} nhưng rèn luyện chỉ {conduct} thì xét loại gì?'
     r,_=scholarship_policy(self.root,query);self.assertIn('mức xét là '+['khá','giỏi','xuất sắc'][min(i,j)],r['answer'].lower())
