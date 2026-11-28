import json,os,tempfile,unittest
from pathlib import Path
from advisor import plan
from knowledge import Index,answer,requested_period,matches_period
from test_knowledge import Backend

class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(os.environ.get('CHRONOREG_TEST_REPO','/tmp/chronoreg_fixture_v2'))
        self.roster={'class_short':'K69-CNTT1','cohort':'QH-2024','students':[
            {'student_id':'001','full_name':'Sinh viên A','gpa_semester':1.6,'cpa':1.6,'drl':65,'owed_credits':4,'accumulated_credits':40,'bang_diem':[{'ma_mon':'INT1001','dat':False}]},
            {'student_id':'002','full_name':'Sinh viên B','gpa_semester':3.5,'cpa':3.5,'drl':85,'owed_credits':0,'accumulated_credits':55}]}
    def test_student_roadmap(self):
        r=plan('Vẽ roadmap học tập',{'category':'STUDENT_STATUS','student_id':'001','roster_obj':self.roster},self.root)
        self.assertEqual(r['engine_mode'],'ADVISOR_PLAN');self.assertIsNone(r['model_name']);self.assertIn('INT1001',r['predicted_answer']);self.assertIn('CPA độc lập',r['predicted_answer']);self.assertNotIn('Sinh viên B',r['predicted_answer']);self.assertGreaterEqual(len(r['roadmap']),3)
    def test_missing_student(self):
        r=plan('Vẽ roadmap',{'category':'STUDENT_STATUS','student_id':'999','roster_obj':self.roster},self.root)
        self.assertNotIn('Sinh viên A',r['predicted_answer']);self.assertIn('Không xác định',r['predicted_answer']);self.assertFalse(r['roadmap'])
    def test_class(self):
        r=plan('Liệt kê sinh viên nào cần hỗ trợ học vụ',{'category':'CLASS_STATS','roster_obj':self.roster},self.root)
        self.assertIn('Sinh viên A',r['predicted_answer']);self.assertNotIn('Sinh viên B',r['predicted_answer']);self.assertIn('2 sinh viên',r['predicted_answer']);self.assertIn('không phải quyết định',r['predicted_answer'])
    def test_overload(self):
        r=plan('Sinh viên này có được học vượt 24 tín chỉ?',{'category':'STUDENT_STATUS','student_id':'002','roster_obj':self.roster},self.root)
        self.assertIn('Không xác nhận được phép',r['predicted_answer']);self.assertNotIn('Đủ điều kiện đăng ký',r['predicted_answer'])
    def test_class_stats_calculated(self):
        r=plan('GPA trung bình lớp và ai cao nhất?',{'category':'CLASS_STATS','roster_obj':self.roster},self.root)
        self.assertIn('trung bình 2.55',r['predicted_answer']);self.assertIn('cao nhất 3.50',r['predicted_answer']);self.assertIn('Sinh viên B',r['predicted_answer'])
    def test_wrong_class(self):
        r=plan('Liệt kê sinh viên lớp K68-CNTT1 cần hỗ trợ',{'category':'CLASS_STATS','roster_obj':self.roster},self.root)
        self.assertIn('không phải lớp được hỏi',r['predicted_answer']);self.assertNotIn('Sinh viên A',r['predicted_answer']);self.assertFalse(r['roadmap'])
    def test_unscoped(self): self.assertIsNone(plan('Quy chế?',{'category':'REGULATION'},self.root))
    def test_requested_period(self):
        self.assertEqual(requested_period('năm học 2025–2026, khóa QH-2022'),({2025},True))
        self.assertEqual(requested_period('so sánh 2023 với 2026'),({2023,2026},False))
    def test_version_and_conflict(self):
        idx=Index(self.root);b=Backend();q='Thông báo hoạt động nghiên cứu khoa học cấp Viện TTNT năm học 2025-2026 có nội dung gì?'
        hits=idx.search(q);self.assertTrue(hits);self.assertTrue(all('2024' not in c.path for c in hits));r=answer(idx,b,q);self.assertEqual(r['engine_mode'],'KNOWLEDGE_EXCERPTS');self.assertIn('15/02/2026',r['predicted_answer']);self.assertIn('25/02/2026',r['predicted_answer']);self.assertFalse(b.calls)
    def test_conflicting_notice_overview_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)/'data/raw/uet/markdown/2025';d.mkdir(parents=True)
            (d/'NCKH_hoi_nghi_vien_TTNT_2025.md').write_text('# Thông báo hoạt động sinh viên nghiên cứu khoa học cấp Viện TTNT\n\n## Kế hoạch triển khai\n| Hoạt động | Thời gian |\n| Đăng ký | 01/02–25/02/2026 |\n**Chú ý về hai mốc khác nhau trong nguồn:** đăng ký chậm nhất ngày 15/02/2026. Giữ nguyên cả hai mốc, không tự quyết định mốc nào thay thế mốc nào.\n',encoding='utf8')
            b=Backend();idx=Index(folder);q='Thông báo hoạt động nghiên cứu khoa học cấp Viện TTNT năm học 2025-2026 có nội dung gì?';r=answer(idx,b,q)
            self.assertEqual(r['engine_mode'],'KNOWLEDGE_EXCERPTS');self.assertIn('15/02/2026',r['predicted_answer']);self.assertIn('25/02/2026',r['predicted_answer']);self.assertFalse(b.calls)
    def test_missing_year(self):
        idx=Index(self.root);self.assertFalse(idx.search('Nghiên cứu khoa học cấp Viện TTNT năm học 2027-2028'))

if __name__=='__main__':unittest.main()
