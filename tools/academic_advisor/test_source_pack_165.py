import unittest, tempfile, shutil, json, os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from semantic_product import route, candidate
from policy_followup import return_to_study
from conversation import next_context
from regulation import TEXT_SHA
from calendar_source import lookup_start, uploaded_calendar
from tuition import lookup_tuition
class Repairs(unittest.TestCase):
    def test_fee_scope_follow(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p=root/'data/versioning/publication_holds.jsonl';p.parent.mkdir(parents=True);p.write_text('')
            def fake(root,q):
                self.assertIn('chương trình chuẩn',q);self.assertIn('QH-2024',q)
                year=2025 if '2025-2026' in q else 2024
                return dict(answer=f'fee {year}',path='a.md',sha256='x',year=year,table_kind='tuition_rate')
            with patch('tuition.lookup_tuition',side_effect=fake),patch('semantic_product.infer') as infer:
                r,st=route('Khóa QH-2024 theo CTĐT chuẩn, năm học 2024–2025, định mức học lần đầu và học lại là bao nhiêu?',{},None,None,{},root)
                self.assertIn('fee 2024',r['answer']);self.assertEqual(st['plan']['slots']['tuition_scope'],'standard')
                r,st=route('Sang năm học 2025–2026 thì sao, vẫn khóa và CTĐT đó?',st,None,None,{},root)
                self.assertIn('fee 2025',r['answer']);self.assertEqual(st['plan']['slots']['cohort'],2024);infer.assert_not_called()
        self.assertFalse(candidate('Thủ tục miễn giảm học phí như thế nào?',{}))
    def test_policy_context(self):
        meta={'engine_mode':'SOURCE_CLAUSE','sha256':TEXT_SHA}; prior=next_context('Theo QĐ 3626, xin nghỉ học tạm thời vì lý do cá nhân?',{'metadata':meta})
        self.assertEqual(prior['article'],36)
        c={'answer':'Sinh viên nghỉ học tạm thời nếu muốn học tiếp phải có đơn đề nghị thủ trưởng đơn vị đào tạo giải quyết chậm nhất 2 tuần trước khi hết thời hạn nghỉ học tạm thời.','path':'a.md','sha256':TEXT_SHA,'source_url':'https://uet.vnu.edu.vn/'}
        with patch('policy_followup.pinned',return_value=c) as pin:
            q='Theo cùng quyết định, nếu xin học tiếp sau thời gian tạm nghỉ thì hạn nộp đơn tính từ mốc nào?'
            self.assertEqual(return_to_study(q,{},Path('.'))[1],{})
            r,st=return_to_study(q,prior,Path('.'));self.assertIn('2 tuần trước khi hết thời hạn',r['answer']);self.assertEqual(st,prior)
            pin.assert_called_once()
            r,st=return_to_study(q+' Khóa 2026.',prior,Path('.'));self.assertNotIn('2 tuần',r['answer']);self.assertEqual(st,{})
    @unittest.skipUnless(os.getenv('CHRONOREG_CALENDAR_PACK_TEST'),'original uploaded pack test path absent')
    def test_real_pack_all_periods_and_hold(self):
        source=Path(os.environ['CHRONOREG_CALENDAR_PACK_TEST']);
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'data/versioning/publication_holds.jsonl';p.parent.mkdir(parents=True);p.write_text('')
            dest=root/'data/advisor_sources/calendar';shutil.copytree(source,dest)
            for y,expected in [('2024-2025',['2024-09-04','2025-02-03','2025-07-07']),('2025-2026',['2025-09-03','2026-02-23','2026-07-06'])]:
                for sem,dt in zip(('main_1','main_2','summer'),expected):
                    hit=lookup_start(root,y,sem,SimpleNamespace(errors=[],chunks=[]));self.assertEqual([h['date'] for h in hit],[dt]);self.assertIn('qualification',hit[0])
            p.write_text(json.dumps({'doc_id':'uet-advisor-calendar-2024-2025'})+'\n');self.assertEqual(uploaded_calendar(root,'2024-2025','main_1'),[])
            p.write_text(''); (dest/'Ke_hoach_hoc_tap_2025.md').write_text('changed');self.assertEqual(uploaded_calendar(root,'2025-2026','main_1'),[])
            p.unlink();self.assertEqual(uploaded_calendar(root,'2024-2025','main_1'),[])
if __name__=='__main__':unittest.main()
