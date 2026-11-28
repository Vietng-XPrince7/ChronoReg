import unittest,tempfile,json,shutil,os
from pathlib import Path
from unittest.mock import patch
from semantic_product import route,guard,execute,structured_input
from quality_workflows import snapshot
from tuition_history import REL,PIN,DOC

class Release191(unittest.TestCase):
    def setUp(self):
        self.roster={}; self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.ledger=self.root/'data/versioning/publication_holds.jsonl';self.ledger.parent.mkdir(parents=True);self.ledger.write_text('')
    def state(self,intent,**slots):return {'kind':'semantic_task','scope':snapshot(self.roster),'plan':{'intent':intent,'slots':slots}}
    def ask(self,q,state):return route(q,state,None,None,self.roster,self.root)
    def test_admissions_method_delta(self):
        old=self.state('admissions',year=2024,program='CN8',method='THPT')
        with patch('semantic_product.infer',side_effect=AssertionError('no model')),patch('semantic_product.lookup') as lookup:
            for q in ('Còn phương thức HSA năm 2024?','Còn phương thức ĐGNL năm 2024?','Còn phương thức đánh giá năng lực?','Chuyển sang SAT năm 2023.'):
                r,st=self.ask(q,old);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertNotEqual(st['plan']['slots']['method'],'THPT')
            lookup.assert_not_called()
    def test_method_guard_against_stale_model(self):
        old={'intent':'admissions','slots':{'year':2024,'program':'CN8','method':'THPT'}}
        p=guard({'intent':'admissions','slots':dict(old['slots'])},'Nếu xét theo HSA năm 2024 thì sao?',old)
        self.assertEqual(p['slots']['method'],'HSA')
        with patch('semantic_product.lookup') as m:
            r=execute(old,self.roster,self.root,'Còn phương thức HSA?');self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');m.assert_not_called()
    def test_unsupported_and_conflicting_methods(self):
        old=self.state('admissions',year=2024,program='CN8',method='THPT')
        with patch('semantic_product.infer',side_effect=AssertionError('no model')),patch('semantic_product.lookup') as m:
            for q in ('Còn phương thức IELTS năm 2024?','Còn phương thức HSA và THPT?','Còn phương thức học bạ?'):
                r,st=self.ask(q,old);self.assertEqual(st,{});self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
            m.assert_not_called()
    def test_year_and_method_switch(self):
        old=self.state('admissions',year=2024,program='CN8',method='HSA')
        v={'answer':'fixture 27,58','path':'fixture.md','sha256':'fixture','year':2024}
        with patch('semantic_product.lookup',return_value=v) as m,patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,st=self.ask('Còn phương thức THPT năm 2024?',old);self.assertEqual(st['plan']['slots']['method'],'THPT');self.assertIn('27,58',r['answer']);m.assert_called_once()
    def test_calendar_delta(self):
        old=self.state('calendar',academic_year='2022-2023',semester='main_1')
        with patch('semantic_product.infer',side_effect=AssertionError('no model')),patch('semantic_product.execute',return_value={'answer':'fixture','metadata':{}}) as ex:
            r,st=self.ask('Còn học kỳ hè năm học 2022–2023?',old);self.assertEqual(st['plan']['slots'],{'academic_year':'2022-2023','semester':'summer'});self.assertEqual(ex.call_args.args[0],st['plan'])
            r,st=self.ask('Còn năm học 2024–2025?',st);self.assertEqual(st['plan']['slots'],{'academic_year':'2024-2025','semester':'summer'})
            r,st=self.ask('Còn học kỳ II?',st);self.assertEqual(st['plan']['slots']['semester'],'main_2')
    def test_calendar_not_shortcut_other_targets(self):
        old=self.state('calendar',academic_year='2022-2023',semester='main_1')['plan']
        for q in ('Còn hạn đăng ký học kỳ hè?','Còn học kỳ hè năm học 2022–2024?','Còn học kỳ hè và học kỳ II?','Còn ngày học chuyên môn học kỳ hè?'):
            self.assertIsNone(structured_input(q,old,self.root),q)
    def test_history_reference_rechecks_source(self):
        old=self.state('tuition',cohort=2022,academic_year='2022-2023',tuition_scope='standard');old['verified_adjustment']=PIN
        v={'answer':'adjusted','year':2022,'path':REL,'sha256':PIN,'doc_id':DOC,'table_kind':'tuition_rate'}
        with patch('semantic_product.infer',side_effect=AssertionError('no model')),patch('tuition_history.adjusted_standard',return_value=v) as src:
            r,st=self.ask('Đây có phải mức ban đầu không?',old);self.assertIn('không.',r['answer']);self.assertEqual(r['metadata']['engine_mode'],'SOURCE_TABLE');self.assertEqual(st,old);src.assert_called_once()
            self.ledger.write_text(json.dumps({'content_sha256':PIN}));r,st=self.ask('Mức này có phải là mức ban đầu không?',old);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertEqual(st,{})
    def test_history_missing_source(self):
        old=self.state('tuition',cohort=2022,academic_year='2022-2023',tuition_scope='standard');old['verified_adjustment']=PIN
        with patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,st=self.ask('Đây có phải mức ban đầu không?',old);self.assertIn('chưa xác minh lại',r['answer']);self.assertEqual(st,{})
    def test_no_prior_verified_adjustment(self):
        old=self.state('tuition',cohort=2022,academic_year='2022-2023',tuition_scope='standard')
        with patch('tuition_history.adjusted_standard') as src,patch('semantic_product.infer') as m:
            r,st=self.ask('Đây có phải mức ban đầu không?',old);self.assertIn('chưa có mức điều chỉnh',r['answer']);self.assertEqual(st,{});src.assert_not_called();m.assert_not_called()
    def test_history_actual_pack_roundtrip(self):
        pack=Path(os.getenv('CHRONOREG_HISTORY_PACK_TEST','__missing_pack__'))
        if not (pack/REL).is_file():self.skipTest('local verified historical source pack unavailable')
        shutil.copytree(pack/'data',self.root/'data',dirs_exist_ok=True)
        with patch('semantic_product.infer',side_effect=AssertionError('no model')):
            r,st=self.ask('Học phí đào tạo đại học chính quy CTĐT chuẩn QH-2022 sau điều chỉnh năm học 2022–2023 là bao nhiêu?',{});self.assertEqual(st['verified_adjustment'],PIN);self.assertIn('315.000',r['answer'])
            r,st=self.ask('Đây có phải mức ban đầu không?',st);self.assertIn('không.',r['answer']);self.assertEqual(r['metadata']['sha256'],PIN)
if __name__=='__main__':unittest.main()
