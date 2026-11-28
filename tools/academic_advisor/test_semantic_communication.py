import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from semantic_product import route
from semantic_communication import guard,execute
from calendar_source import lookup_start
from knowledge import Chunk
from tuition import lookup_units

class SemanticCommunication(unittest.TestCase):
    def setUp(self):
        self.root=Path('.')
        self.roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'99000001','full_name':'PRIVATE PERSON','owed_credits':19,'gpa_semester':1.8,'drl':69},{'student_id':'99000002','full_name':'OTHER PERSON','owed_credits':0,'gpa_semester':3,'drl':80}]}
    def ask(self,q,intent,slots,prior=None,reuse=False):
        with patch('semantic_product.infer',return_value={'intent':intent,'reuse':reuse,'slots':slots}):return route(q,prior or {},None,None,self.roster,self.root)
    def test_email_chain(self):
        r,st=self.ask('Viết email mời sinh viên 99000001 trao đổi về học tập, có tiêu đề, không nhắc tên, điểm.', 'draft',{'student':'99000001','format':'email','audience':'private','exclude_private':False})
        self.assertIn('Tiêu đề:',r['answer']);self.assertNotIn('99000001',r['answer']);self.assertTrue(st['plan']['slots']['exclude_private'])
        a,new=self.ask('Rút nội dung xuống 18 từ, giữ tiêu đề.', 'draft',{'max_words':18},st,True)
        self.assertEqual(a['answer'].split('\n')[0],r['answer'].split('\n')[0]);self.assertLessEqual(len(a['answer'].split('\n\n')[1].split()),18)
        b,new=self.ask('Chuyển thành thông báo chung cả lớp, không có thông tin cá nhân.', 'draft',{'audience':'class','format':'notice'},new,True)
        self.assertNotIn('student',new['plan']['slots']);self.assertNotIn('99000001',b['answer']);self.assertIn('Các em',b['answer'])
    def test_counseling_chain(self):
        a,st=self.ask('Cô gặp 99000001, gợi ý hai cách mở đầu buổi trao đổi.', 'counseling',{'student':'99000001','opening_count':2})
        self.assertEqual(len(a['answer'].splitlines()),2)
        b,st=self.ask('Em ấy khó hiểu bài nhưng có thể dành 30 phút tự học mỗi ngày trong một tuần.', 'counseling',{},st,True)
        self.assertEqual(b['answer'].count('Ngày '),7);self.assertIn('30 phút/ngày',b['answer']);self.assertIn('chưa ghi vào hồ sơ',b['answer'])
        c,st=self.ask('Em không muốn chia sẻ với các bạn khác, giữ hỗ trợ riêng tư thế nào?', 'counseling',{},st,True)
        self.assertIn('kênh riêng',c['answer']);self.assertIn('đồng ý',c['answer']);self.assertNotIn('PRIVATE PERSON',c['answer'])
    def test_combined_public_revision_and_scope(self):
        a,st=self.ask('Cho cô tóm tắt nhóm cần hỗ trợ, rồi một lời nhắn công khai cả lớp.', 'draft',{'audience':'class','format':'notice','include_summary':True})
        internal,public=a['answer'].split('Thông báo chung — bản nháp:');self.assertIn('1 sinh viên ưu tiên',internal);self.assertNotRegex(public,r'\d|PRIVATE PERSON|99000001')
        b,st=self.ask('Chỉ giữ lời nhắn, thêm yêu cầu chuẩn bị một vấn đề muốn trao đổi.', 'draft',{},st,True)
        self.assertIn('chuẩn bị một vấn đề',b['answer']);self.assertNotIn('Nội bộ',b['answer'])
        with patch('semantic_product.infer') as m:
            c,new=route('Một lớp khác chưa có hồ sơ có được dùng số liệu lớp hiện tại không?',st,None,None,self.roster,self.root)
            self.assertIn('không dùng số liệu',c['answer']);self.assertEqual(new,{});m.assert_not_called()
    def test_draft_subject_and_scope(self):
        p={'intent':'draft','slots':{'audience':'class','format':'email','subject':'PRIVATE PERSON','draft_purpose':'invite'}}
        with self.assertRaises(ValueError):guard(p,'Viết email cả lớp tiêu đề PRIVATE PERSON, mời trao đổi học tập.',None)
        a,st=self.ask('Viết email mời sinh viên 99000003 trao đổi học tập.', 'draft',{'student':'99000003','audience':'private','format':'email'})
        self.assertIn('cần xác định sinh viên',a['answer']);self.assertNotIn('PRIVATE PERSON',a['answer'])
    def test_tuition_filters_empty_and_external(self):
        h=['STT','Khóa','Học lần đầu (đồng/tháng)','Học lần đầu (đồng/tín chỉ)','Học lại (đồng/tín chỉ)','Học phí đối với sinh viên các đơn vị đào tạo trực thuộc ĐHQGHN (đồng/tín chỉ)']
        rows=[['3','Khóa 2023, 2024','3.200.000','-','869.000','999.000'],['III','ĐMKTKT','-','1.000.000','1.076.000','999.000']]
        with patch('tuition.read_table',return_value=([('ug',h,rows)],'tuition.md','hash','norm')):
            v=lookup_units(self.root,2025,2024);self.assertIn('CTĐT chuẩn',v['answer']);self.assertIn('CTĐT ĐMKTKT',v['answer']);self.assertNotIn('trực thuộc',v['answer']);self.assertNotIn('999.000',v['answer']);self.assertEqual(v['answer'].count('đồng/tháng'),1)
    def test_calendar_scope(self):
        def c(text,year=(2025,2026),status='reviewed',heading='Kế hoạch đào tạo đại học'):
            return Chunk('data/raw/uet/ke_hoach_dao_tao.md','hash',text,heading,status,year,'doc','https://example.org',temporal_verified=True)
        idx=SimpleNamespace(errors=[],chunks=[c('Học kỳ II bắt đầu ngày 15/01/2026'),c('Học kỳ II bắt đầu đăng ký ngày 10/01/2026'),c('Học kỳ II bắt đầu ngày 15/01/2025',(2024,2025)),c('Học kỳ II bắt đầu ngày 25/01/2026',status='unreviewed'),c('Học kỳ II bắt đầu ngày 26/01/2026',heading='Kế hoạch đào tạo sau đại học')])
        rows=lookup_start(self.root,'2025-2026','main_2',idx);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['date'],'2026-01-15')
        with patch('calendar_source.lookup_start',return_value=rows):
            a,st=self.ask('Ngày bắt đầu học kỳ chính thứ hai năm học 2025-2026?', 'calendar',{'academic_year':'2025-2026','semester':'main_2'});self.assertIn('15/01/2026',a['answer']);self.assertEqual(a['metadata']['cited_doc_ids'],['doc'])
        with patch('calendar_source.lookup_start',return_value=[]) as m:
            b,st=self.ask('Còn năm học 2024-2025 thì sao?', 'calendar',{'academic_year':'2024-2025'},st,True);m.assert_called_once_with(self.root,'2024-2025','main_2');self.assertIn('chưa tìm thấy',b['answer']);self.assertNotIn('15/01/2026',b['answer'])
if __name__=='__main__':unittest.main()
