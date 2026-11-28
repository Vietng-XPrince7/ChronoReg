import unittest, tempfile, shutil, json, os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from calendar_source import inspect_uploaded_calendar, pack_status, lookup_start
from conversation import Context, add_conversation, next_context
from regulation import TEXT_SHA
from semantic_product import route
from policy_followup import return_to_study

QUESTION='Theo cùng quyết định, nếu xin học tiếp sau thời gian tạm nghỉ thì hạn nộp đơn tính từ mốc nào?'
CLAUSE='Sinh viên nghỉ học tạm thời nếu muốn học tiếp phải có đơn đề nghị thủ trưởng đơn vị đào tạo giải quyết chậm nhất 2 tuần trước khi hết thời hạn nghỉ học tạm thời.'
SOURCE={'answer':CLAUSE,'path':'a.md','sha256':TEXT_SHA,'source_url':'https://uet.vnu.edu.vn/'}

class LiveTokenRegression(unittest.TestCase):
    def test_real_signed_token_http(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pydantic import BaseModel
        class Req(BaseModel):
            question:str
            force_engine:str|None=None
            mssv:str|None=None
        root=Path('.')
        s=SimpleNamespace(app=FastAPI(),_semantic_pilot=True,_get_active_roster=lambda:{},_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')))
        calls=[]
        def dispatch(req):
            calls.append(req.question)
            return {'answer':CLAUSE,'metadata':{'engine_mode':'SOURCE_CLAUSE','sha256':TEXT_SHA},'routing':{'risk_tier':'GREEN'}}
        add_conversation(s,dispatch,Req,root)
        client=TestClient(s.app)
        def ask(q,token=None):
            r=client.post('/api/advisor/chat',json={'question':q,'context_token':token,'force_engine':'auto'});self.assertEqual(r.status_code,200);return r.json()
        with patch('policy_followup.pinned',return_value=SOURCE) as pin,patch('semantic_product.infer',side_effect=AssertionError('unexpected model call')):
            r=ask('Theo QĐ 3626, xin nghỉ học tạm thời vì lý do cá nhân?');self.assertTrue(r['context_token'])
            follow=ask(QUESTION,r['context_token']);self.assertIn('2 tuần trước khi hết thời hạn',follow['answer']);self.assertTrue(follow['context_token']);self.assertEqual(len(calls),1)
            self.assertNotIn('2 tuần',ask(QUESTION)['answer'])
            self.assertNotIn('2 tuần',ask(QUESTION,r['context_token']+'x')['answer'])
            self.assertNotIn('2 tuần',ask(QUESTION+' Khóa 2026.',r['context_token'])['answer'])
            pin.assert_called_once()
    def test_missing_context_does_not_fall_through(self):
        r,state=return_to_study(QUESTION,{},Path('.'));self.assertEqual(state,{});self.assertIn('chưa xác định',r['answer'])
    @unittest.skipUnless(os.getenv('CHRONOREG_CALENDAR_PACK_TEST'),'original pack path absent')
    def test_pack_status_and_calendar_api_route(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dest=root/'data/advisor_sources/calendar';hold=root/'data/versioning/publication_holds.jsonl';hold.parent.mkdir(parents=True)
            hold.write_text('');self.assertEqual(inspect_uploaded_calendar(root,'2024-2025','main_2')['status'],'PACK_MANIFEST_MISSING')
            shutil.copytree(Path(os.environ['CHRONOREG_CALENDAR_PACK_TEST']),dest)
            self.assertEqual([x['status'] for x in pack_status(root)],['READY']*6)
            with patch('calendar_source.Index',return_value=SimpleNamespace(errors=[],chunks=[])),patch('semantic_product.infer',side_effect=AssertionError('no model needed')):
                r,st=route('Theo kế hoạch học tập UET năm học 2024–2025, học kỳ II bắt đầu ngày nào?',{},None,None,{},root);self.assertIn('03/02/2025',r['answer']);self.assertIn('không có chữ ký số',r['answer'])
                r,st=route('Theo kế hoạch học tập UET năm học 2025–2026, học kỳ II bắt đầu ngày nào?',st,None,None,{},root);self.assertIn('23/02/2026',r['answer']);self.assertNotIn('03/02/2025',r['answer'])
                hold.write_text(json.dumps({'doc_id':'uet-advisor-calendar-2024-2025'})+'\n');r,st=route('Theo kế hoạch học tập UET năm học 2024–2025, học kỳ II bắt đầu ngày nào?',{},None,None,{},root);self.assertEqual(r['metadata']['calendar_pack_diagnostic']['status'],'EXACT_PUBLICATION_HOLD');self.assertNotIn('03/02/2025',r['answer'])
            hold.write_text(json.dumps({'doc_id':'uet-ke-hoach-hoc-tap-2025-other'})+'\n');self.assertEqual(inspect_uploaded_calendar(root,'2024-2025','main_2')['status'],'POSSIBLE_RELATED_PUBLICATION_HOLD')
            hold.write_text(''); (dest/'Ke_hoach_hoc_tap_2024.md').write_text('changed');self.assertEqual(inspect_uploaded_calendar(root,'2024-2025','main_2')['status'],'MARKDOWN_HASH_MISMATCH')
            hold.unlink();self.assertEqual(inspect_uploaded_calendar(root,'2025-2026','main_2')['status'],'HOLD_LEDGER_MISSING')
if __name__=='__main__':unittest.main()
