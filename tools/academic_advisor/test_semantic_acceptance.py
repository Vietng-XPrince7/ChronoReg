import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from semantic_product import route,structured_input,guard,execute
from semantic_planner import checked_plan
from quality_workflows import snapshot
from test_quality_routes import RANK_SOURCE,LOAD_SOURCE
from knowledge import Chunk
from calendar_source import lookup_start
from tuition import lookup_tuition

class AcceptanceRepairs(unittest.TestCase):
    def setUp(self):
        self.root=Path('.')
        self.roster={'class_short':'K68-DEMO','cohort':'QH-2023 (K68)','semester':'2025.1','students':[{'student_id':'99000001','accumulated_credits':53,'owed_credits':21,'gpa_semester':1.9},{'student_id':'99000002','accumulated_credits':46,'owed_credits':32,'gpa_semester':1.4}], 'courses':[]}
    def ask(self,q,prior=None):return route(q,prior or {},None,None,self.roster,self.root)
    def state(self,i,**s):return {'kind':'semantic_task','scope':snapshot(self.roster),'plan':{'intent':i,'slots':s}}
    def test_structured_rank_and_relative_update(self):
        with patch('semantic_product.infer') as m,patch('semantic_product.pinned',return_value=RANK_SOURCE):
            a,st=self.ask('Khóa 2023 dự kiến tốt nghiệp loại Giỏi, CTĐT 160 tín chỉ, học lại 8 tín chỉ, không bị kỷ luật. Xét giảm hạng bằng.')
            self.assertIn('5.00%',a['answer']);self.assertIn('không vượt',a['answer'])
            a,st=self.ask('Nếu học lại thêm hai tín chỉ nữa, các điều kiện còn lại giữ nguyên?',st)
            self.assertIn('10/160',a['answer']);self.assertEqual(st['plan']['slots']['discipline'],False)
            a,st=self.ask('Thay sinh viên khác, thuộc khóa 2026, có được áp nguyên điều khoản đó không?',st)
            self.assertIn('xác minh quy chế đúng khóa',a['answer']);self.assertNotIn('10/160',a['answer']);m.assert_not_called()
    def test_load_cpa_correction(self):
        with patch('semantic_product.infer') as m,patch('semantic_product.pinned',return_value=LOAD_SOURCE):
            a,st=self.ask('K68, GPA học kỳ vừa rồi 1,8; bình quân theo kế hoạch 14 tín chỉ một kỳ chính, chưa thuộc diện buộc thôi học, mọi học phần đều tính tải. Xét mức tối đa.')
            self.assertIn('min(21, 18) = 18',a['answer'])
            a,st=self.ask('Điểm 1,8 là CPA chứ không phải điểm của kỳ vừa rồi; có còn đủ căn cứ dùng trần 18 không?',st)
            self.assertIn('không dùng GPA tích lũy',a['answer']);m.assert_not_called()
    def test_profile_metric_and_second_ref(self):
        with patch('semantic_product.infer') as m:
            a,st=self.ask('Hồ sơ 99000001 tích lũy được bao nhiêu tín chỉ? Chỉ trả lời chỉ số đó.')
            self.assertIn('53 tín chỉ tích lũy',a['answer']);self.assertNotIn('GPA',a['answer'])
            a,st=self.ask('Đối chiếu cùng chỉ số với 99000002.',st)
            self.assertIn('46 tín chỉ tích lũy',a['answer']);self.assertIn('cao hơn 7',a['answer'])
            a,st=self.ask('Giờ chỉ xem GPA tích lũy của bạn thứ hai, không dùng điểm học kỳ thay thế.',st)
            self.assertIn('chưa xác nhận CPA',a['answer']);self.assertEqual(st['plan']['slots']['student'],'99000002');m.assert_not_called()
    def test_remove_course_constraint(self):
        old={'intent':'retake_plan','slots':{'student':'99000001','budget':10,'first_course':'ABC1001'}}
        p=guard({'intent':'retake_plan','slots':dict(old['slots'],budget=6)},'Bỏ yêu cầu ưu tiên môn đó, nhưng giảm xuống 6 tín chỉ mỗi đợt.',old)
        self.assertNotIn('first_course',p['slots']);self.assertEqual(p['slots']['budget'],6)
    def test_counseling_to_draft_and_word_limit(self):
        st=self.state('counseling',student='99000001',counsel_action='study_plan',minutes=20,days=5)
        with patch('semantic_product.infer') as m:
            a,st=self.ask('Soạn lời mời trao đổi cho bạn này bằng email, tiêu đề Trao đổi học tập, không đề cập điểm hay mã.',st)
            self.assertIn('Tiêu đề: Trao đổi học tập',a['answer']);self.assertNotIn('99000001',a['answer'])
            a,st=self.ask('Phần thân tối đa 15 từ, giữ nguyên tiêu đề.',st)
            self.assertLessEqual(len(a['answer'].split('\n\n')[1].split()),15);self.assertIn('Tiêu đề: Trao đổi học tập',a['answer']);m.assert_not_called()
    def test_admission_program_from_source(self):
        rows={'CN1':('Kỹ thuật máy tính','25,5',''),'CN2':('Khoa học máy tính','26,5','')}
        with patch('semantic_product.parse',return_value=(rows,'a.md','x')):
            p=structured_input('Năm 2024, ngành Kỹ thuật máy tính UET có điểm trúng tuyển THPT bao nhiêu?',None,self.root)
            self.assertEqual(p['slots'],{'year':2024,'program':'Kỹ thuật máy tính','method':'THPT'})
        st=self.state('admissions',year=2024,program='Kỹ thuật máy tính',method='THPT')
        with patch('semantic_product.infer') as m:
            a,st=self.ask('Đổi sang phương thức HSA, vẫn ngành và năm ấy.',st);self.assertIn('chưa có bảng nguồn',a['answer']);self.assertEqual(st['plan']['slots']['method'],'HSA');m.assert_not_called()
    def test_admissions_source_and_scale_conjunction(self):
        rows={'CN2':('Kỹ thuật máy tính','26,97',''),'CN8':('Khoa học máy tính','27,58',''),'CN1':('Công nghệ thông tin','27,8','')}
        with patch('semantic_product.parse',return_value=(rows,'a.md','x')):
            for q in ('Năm 2024, ngành Kỹ thuật máy tính UET có điểm trúng tuyển THPT bao nhiêu? Nêu thang điểm và nguồn.', 'Điểm chuẩn CN2 năm 2024 theo THPT, cho biết điểm và nguồn?'):
                p=structured_input(q,None,self.root);self.assertEqual(p['slots']['year'],2024);self.assertEqual(p['slots']['method'],'THPT')
            self.assertIsNone(structured_input('Điểm chuẩn Kỹ thuật máy tính và Khoa học máy tính năm 2024?',None,self.root))
            self.assertIsNone(structured_input('Điểm chuẩn CN8 Kỹ thuật máy tính năm 2024?',None,self.root))
            self.assertIsNone(structured_input('Điểm chuẩn Kỹ thuật máy tính và ngành chưa có tên trong bảng năm 2024?',None,self.root))
            self.assertIsNone(structured_input('Điểm chuẩn CN2 năm 2024 và học phí?',None,self.root))
            self.assertIsNone(structured_input('Điểm chuẩn CN2 năm 2024 không phải THPT?',None,self.root))
        prior=self.state('admissions',year=2024,program='Kỹ thuật máy tính',method='THPT')
        with patch('semantic_product.infer') as m:
            a,st=self.ask('Đổi sang phương thức HSA, vẫn ngành và năm ấy.',prior);self.assertIn('chưa có bảng nguồn',a['answer']);self.assertEqual(st['plan']['slots']['program'],'Kỹ thuật máy tính');m.assert_not_called()
            a,st=self.ask('Còn năm 2025, cùng ngành và phương thức?',st);self.assertEqual(st['plan']['slots']['year'],2025);self.assertEqual(st['plan']['slots']['method'],'HSA');m.assert_not_called()
    def test_admissions_full_route_and_source_hold(self):
        from tempfile import TemporaryDirectory
        import json
        rows={'CN2':('Kỹ thuật máy tính','26,97',''),'CN8':('Khoa học máy tính','27,58','')}
        with TemporaryDirectory() as d:
            self.root=Path(d);hold=self.root/'data/versioning/publication_holds.jsonl';hold.parent.mkdir(parents=True);hold.write_text('')
            with patch('semantic_product.parse',return_value=(rows,'a.md','sha')),patch('quality.parse',return_value=(rows,'a.md','sha')),patch('semantic_product.infer') as model:
                a,st=self.ask('Điểm chuẩn CN2 năm 2024 theo THPT, cho biết điểm và nguồn?')
                self.assertIn('26,97',a['answer']);self.assertEqual(a['metadata']['engine_mode'],'SOURCE_TABLE');self.assertTrue(a['metadata']['source_url'].startswith('https://uet.vnu.edu.vn/'))
                a,st=self.ask('Đổi sang phương thức HSA, vẫn ngành và năm ấy.',st);self.assertNotIn('26,97',a['answer']);self.assertIn('chưa có bảng nguồn',a['answer']);model.assert_not_called()
                hold.write_text(json.dumps({'content_sha256':'sha'})+'\n')
                a,st=self.ask('Điểm chuẩn CN2 năm 2024 theo THPT, cho biết điểm và nguồn?');self.assertNotIn('26,97',a['answer']);self.assertEqual(a['metadata']['semantic_rejection']['stage'],'execution');model.assert_not_called()
    def test_calendar_header_ranges(self):
        def c(txt,yrs=(2023,2024),status='reviewed',heading='Kế hoạch học tập đại học chính quy 2023-2024'):
            return Chunk('data/raw/uet/markdown/2023/Ke_hoach_hoc_tap_2023.md','sha',txt,heading,status,yrs,'doc','',temporal_verified=True)
        ix=SimpleNamespace(errors=[],chunks=[c('## **HỌC KỲ I** (28/08/2023  28/01/2024)\n|18/09/2023|Học chuyên môn|'),c('## Học kỳ I (03/09/2024 – 14/02/2025)',(2024,2025)),c('## Học kỳ I (01/09/2023 – 01/02/2024)',status='unreviewed'),c('## Học kỳ I (01/09/2023 – 01/02/2024)',heading='Kế hoạch nghiên cứu khoa học')])
        h=lookup_start(self.root,'2023-2024','main_1',ix);self.assertEqual(len(h),1);self.assertEqual(h[0]['date'],'2023-08-28');self.assertIn('không đồng nghĩa',h[0]['excerpt'])
        self.assertEqual(lookup_start(self.root,'2023-2024','main_2',ix),[])
    def test_tuition_excludes_external_column(self):
        h=['TT','Khóa','Học lần đầu (đồng/tháng)','Học lại (đồng/tín chỉ)','Học phí đối với sinh viên các đơn vị đào tạo trực thuộc ĐHQGHN (đồng/tín chỉ)']
        rows=[['3','Khóa 2023 về sau','3.400.000','924.000','999.000']]
        with patch('tuition.read_table',return_value=([('ug',h,rows)],'a.md','sha','norm')):
            r=lookup_tuition(self.root,'Học phí CTĐT chuẩn QH-2023 năm học 2025-2026?');self.assertNotIn('999.000',r['answer']);self.assertIn('3.400.000',r['answer'])
    def test_tuition_scope_transition(self):
        st=self.state('tuition',cohort=2024,program='CNTT')
        with patch('semantic_product.infer') as m,patch('tuition.lookup_units',return_value=None):
            a,st=self.ask('Nếu cô hỏi mức thu năm học 2025–2026 cho chính khóa 2024 thì có phải dùng mức tân sinh viên 2025 không?',st)
            self.assertIn('không tự dùng định mức',a['answer']);self.assertEqual(st['plan']['slots']['academic_year'],'2025-2026');m.assert_not_called()
    def test_wrong_legal_scope(self):
        with patch('semantic_product.pinned') as m:
            a,st=self.ask('Hạn rút học phần khóa 2026 theo QĐ 3626?');self.assertIn('đúng phiên bản',a['answer']);m.assert_not_called()
    def test_explicit_withdrawal_source(self):
        source=dict(RANK_SOURCE,answer='Điều 23. Rút bớt học phần; nội dung nguồn mẫu.')
        with patch('semantic_product.pinned',return_value=source),patch('semantic_product.infer') as m:
            a,st=self.ask('Nếu hỏi hạn rút học phần của học kỳ chính theo QĐ 3626 thì tính từ thời điểm nào?');self.assertIn('Điều 23',a['answer']);m.assert_not_called()
if __name__=='__main__':unittest.main()
