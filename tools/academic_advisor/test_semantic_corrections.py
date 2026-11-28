import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from semantic_product import route,fast_delta,execute,guard
from quality_workflows import snapshot
from tuition import lookup_units
from test_quality_routes import RANK_SOURCE,LOAD_SOURCE

class Corrections(unittest.TestCase):
    def setUp(self):
        self.roster={'class_short':'K69-DEMO','cohort':'QH-2024 (K69)','semester':'2025.1','students':[], 'courses':[]}
        self.root=Path('.')
    def context(self,intent,**slots):return {'kind':'semantic_task','plan':{'intent':intent,'slots':slots},'scope':snapshot(self.roster)}
    def test_rank_edit_without_inference(self):
        old=self.context('rank_check',cohort=2024,rank='good',total_credits=130,repeat_credits=7,discipline=False)
        with patch('semantic_product.infer') as m,patch('semantic_product.pinned',return_value=RANK_SOURCE):
            a,old=route('Nếu thực tế chỉ học lại 6 tín chỉ thì kết luận thay đổi thế nào?',old,None,None,self.roster,self.root)
            self.assertIn('4.62%',a['answer']);self.assertIn('chưa thỏa',a['answer'])
            b,new=route('Nếu em đó chỉ dự kiến bằng Khá thì sao?',old,None,None,self.roster,self.root)
            self.assertIn('không áp dụng hạng dự kiến',b['answer']);self.assertEqual(new['plan']['slots']['rank'],'fair');m.assert_not_called()
    def test_load_edit(self):
        old=self.context('credit_cap',cohort=2024,semester='main',gpa=1.7,gpa_kind='semester',standard_credits=10,not_dismissed=True,all_counted=True)
        with patch('semantic_product.infer') as m,patch('semantic_product.pinned',return_value=LOAD_SOURCE):
            a,st=route('Cô sửa lại, trung bình là 14 tín chỉ. Những điều kiện khác giữ nguyên.',old,None,None,self.roster,self.root)
            self.assertIn('min(21, 18) = 18',a['answer']);self.assertEqual(st['plan']['slots']['gpa'],1.7);m.assert_not_called()
    def test_not_shortcut_new_conditions(self):
        p=self.context('rank_check',cohort=2024,rank='good',total_credits=130,repeat_credits=7,discipline=False)['plan']
        for q in ['Nếu học lại 6 tín chỉ và bị kỷ luật cảnh cáo thì sao?', 'Nếu em khác dự kiến bằng Khá thì sao?', 'Nếu không phải bằng Khá thì sao?', 'Nếu học lại 6,5 tín chỉ thì sao?', 'Nếu học lại 6 tín chỉ năm 2026 thì sao?']:
            self.assertIsNone(fast_delta(q,p),q)
    def test_unit_table_2024(self):
        h=['STT','Khóa tuyển sinh','Học lần đầu (đồng/1 năm học, 10 tháng)','Học lại, cải thiện điểm (đồng/1 tín chỉ)']
        rows=[['1','QH-2023, 2024: CTĐT chuẩn','32.000.000','869.000'],['2','QH-2023, 2024: ĐMKTKT','40.000.000','1.076.000']]
        with patch('tuition.read_table',return_value=([(None,[],[])]*4+[(None,h,rows)],'tuition.md','hash','norm')):
            v=lookup_units(self.root,2024,2024,example=True)
            self.assertIn('nếu đang hỏi năm nhập học',v['answer']);self.assertIn('đồng/1 năm học',v['answer']);self.assertIn('đồng/1 tín chỉ',v['answer']);self.assertNotIn('32.000.000',v['answer']);self.assertNotIn('40.000.000',v['answer'])
    def test_unit_table_2025(self):
        h=['STT','Khóa tuyển sinh','Học lần đầu (đồng/tháng)','Học lại (đồng/tín chỉ)']
        rows=[['3','Khóa 2023, 2024','3.200.000','869.000'],['III','ĐMKTKT','4.000.000','1.076.000']]
        with patch('tuition.read_table',return_value=([('ug',h,rows)],'tuition.md','hash','norm')):
            v=lookup_units(self.root,2025,2024);self.assertIn('đồng/tháng',v['answer']);self.assertIn('không phải lịch thu tiền',v['answer']);self.assertNotIn('3.200.000',v['answer'])
    def test_unit_missing_or_wrong_scope(self):
        with patch('tuition.read_table') as m:
            self.assertIsNone(lookup_units(self.root,2024,2025));self.assertIsNone(lookup_units(self.root,2025,2022));m.assert_not_called()
    def test_unit_hold(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'data/versioning';p.mkdir(parents=True);(p/'publication_holds.jsonl').write_text(json.dumps({'content_sha256':'hash'}))
            v={'answer':'secret','path':'fee.md','sha256':'hash','year':2024,'table_kind':'tuition_units'}
            with patch('tuition.lookup_units',return_value=v):
                with self.assertRaises(ValueError):execute({'intent':'tuition','slots':{'cohort':2024}},self.roster,root,'Học phí tính theo năm hay tháng?')
    def test_period_explicit(self):
        old={'intent':'tuition','slots':{'cohort':2024,'academic_year':'2024-2025'}}
        p=guard({'intent':'tuition','slots':{'cohort':2024}},'Năm học 2025–2026 cho khóa 2024 thì sao?',old)
        self.assertEqual(p['slots']['academic_year'],'2025-2026')
    def test_period_not_reasked(self):
        with patch('tuition.lookup_units',return_value=None):
            r=execute({'intent':'tuition','slots':{'cohort':2024,'academic_year':'2025-2026'}},self.roster,self.root,'Mức thu năm học 2025-2026?')
            self.assertNotIn('năm học thu phí',r['answer']);self.assertIn('loại chương trình',r['answer'])
if __name__=='__main__':unittest.main()
