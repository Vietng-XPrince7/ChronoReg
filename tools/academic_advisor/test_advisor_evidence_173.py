import unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from advisor_evidence import direct_article,retrieve,verified_passages,fresh_ledger,rank,Passage
from knowledge import Index
from conversation import add_conversation
from stream_chat import install_stream
from test_quality_routes import Request

class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.v=self.root/'data/versioning';self.v.mkdir(parents=True);self.hold=self.v/'publication_holds.jsonl';self.hold.write_text('');self.p=self.root/'data/raw/uet/markdown/2025/giay_xac_nhan.md';self.p.parent.mkdir(parents=True)
  self.text='Thời hạn xử lý giấy xác nhận sinh viên là 14 ngày kể từ khi hồ sơ hợp lệ.';self.p.write_text('## Thủ tục cấp giấy xác nhận\n\n'+self.text,encoding='utf8');self.sha=hashlib.sha256(self.p.read_bytes()).hexdigest();self.rv={'doc_id':'g','content_sha256':self.sha,'review_status':'verified_against_source','academic_year':'2025-2026'};self.chunk={'doc_id':'g','content_sha256':self.sha,'policy_qa_ready':True,'eligible_for_policy_qa':True,'academic_year_verified':'2025-2026','text':self.text,'scope':'Thủ tục cấp giấy xác nhận'};self.write();self.index=Index(self.root);self.q='Thời hạn xử lý giấy xác nhận sinh viên UET năm học 2025–2026 là bao lâu?'
 def tearDown(self):self.tmp.cleanup()
 def write(self):
  (self.v/'reviewed_documents.jsonl').write_text(json.dumps(self.rv)+'\n',encoding='utf8');(self.v/'rag_chunks.jsonl').write_text(json.dumps(self.chunk)+'\n',encoding='utf8')
 def test_general_source_and_selector(self):
  r,c=retrieve(self.q,self.index,True,lambda q,ps:ps[0]);self.assertIn('14 ngày',r['answer']);self.assertEqual(r['metadata']['engine_mode'],'ADVISOR_EVIDENCE');self.assertEqual(r['metadata']['sha256'],self.sha);self.assertEqual(c,{})
  r,_=retrieve(self.q,self.index,True,lambda q,ps:None);self.assertNotIn('14 ngày',r['answer']);self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
  self.assertIsNone(retrieve(self.q,self.index,False));self.assertIsNone(retrieve(self.q.replace('2025–2026','2024–2025'),self.index,True));self.assertIsNone(retrieve('Hạn đăng ký nghiên cứu khoa học UET năm học 2025–2026?',self.index,True));self.assertIsNone(retrieve(self.q+' MSSV 99000001',self.index,True))
 def test_fresh_hold_and_source_change(self):
  self.hold.write_text(json.dumps({'doc_id':'g','content_sha256':self.sha}));self.assertIsNone(retrieve(self.q,self.index,True));self.hold.write_text('');self.p.write_text(self.text+' sửa');self.assertIsNone(retrieve(self.q,self.index,True))
 def test_revoke_review_and_chunk(self):
  self.chunk['eligible_for_policy_qa']=False;self.write();self.assertIsNone(retrieve(self.q,self.index,True));self.chunk['eligible_for_policy_qa']=True;self.rv['review_status']='needs_human_review';self.write();self.assertIsNone(retrieve(self.q,self.index,True))
 def test_nonliteral_reviewed(self):
  self.chunk['text']='Thời hạn xử lý giấy xác nhận sinh viên là 99 ngày kể từ khi hồ sơ hợp lệ.';self.write();self.assertIsNone(retrieve(self.q,Index(self.root),True))
 def test_direct_article_and_scope(self):
  articles={12:('Tên điều giả lập','1. Đây là nội dung điều khoản thử nghiệm.\n2. Đây là nội dung khoản hai dùng cho kiểm thử.')}
  with patch('advisor_evidence.read_articles',return_value=(articles,'fixture')):
   r,c=direct_article('Trích nguyên văn khoản 1 Điều 12 QĐ 3626',{},self.root);self.assertIn('nội dung điều khoản thử nghiệm',r['answer']);self.assertEqual(c['article'],12)
   r,c=direct_article('Còn khoản 2?',c,self.root);self.assertIn('khoản hai',r['answer']);self.assertIsNone(direct_article('Còn khoản 2?',{},self.root));self.assertIsNone(direct_article('Trích khoản 1 Điều 12 QĐ 3626 áp dụng K71?',{},self.root))
   self.hold.write_text(json.dumps({'doc_id':'qd3626','content_sha256':'fake'}));r,c=direct_article('Trích khoản 1 Điều 12 QĐ 3626',{},self.root);self.assertNotIn('nội dung điều khoản thử nghiệm',r['answer']);self.assertFalse(c)
 def test_http_product_only(self):
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:{},_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')),_advisor_evidence_index=self.index,_semantic_pilot=True)
  def dispatch(req):return {'answer':'legacy','routing':{'risk_tier':'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  add_conversation(s,dispatch,Request,self.root);h=next(r.endpoint for r in s.app.routes if r.path=='/api/advisor/chat');install_stream(s.app,h,interval=0);cl=TestClient(s.app)
  with patch('advisor_evidence.select_local',return_value=None),patch('advisor_evidence.retrieve',wraps=lambda q,i,enabled:retrieve(q,i,enabled,lambda q,ps:ps[0])):
   r=cl.post('/api/advisor/chat/stream',json={'question':self.q,'experience':'advisor'});self.assertEqual(r.status_code,200);events=[json.loads(x) for x in r.text.splitlines()];d=events[-1]['data'];self.assertEqual(''.join(x['text'] for x in events if x['event']=='delta'),d['answer']);self.assertIn('14 ngày',d['answer']);self.assertEqual(cl.post('/api/advisor/chat',json={'question':self.q}).json()['answer'],'legacy')
if __name__=='__main__':unittest.main()
