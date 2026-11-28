import unittest,tempfile,shutil,json,hashlib
from pathlib import Path
from unittest.mock import patch
from quality import norm
from advisor_public_sections import grouped_outcomes,route as sections
from advisor_release_counsel import route,NOTE
from advisor_tasks import withdrawal

OUTCOMES='''# **A. Chuẩn đầu ra (PLO)**
**CĐR bao gồm các mục (1) đến (3) như sau:**
# **1. CĐR kiến thức**
- **Có khả năng giải quyết các vấn đề kỹ thuật phức tạp.**
# **2. CĐR kỹ năng**
- **Có khả năng giao tiếp hiệu quả với nhiều đối tượng.**
# **3. CĐR mức tự chủ và trách nhiệm**
- **Có khả năng nhận thức trách nhiệm đạo đức và nghề nghiệp.**
**4. Vị trí việc làm mà sinh viên có thể đảm nhiệm sau khi tốt nghiệp**
- Không được trích phần này.
|PLO1|Nội dung lỗi OCR|
'''
EN='Sinh viên UET K69 có chứng chỉ VSTEP B2 muốn cập nhật chuẩn đầu ra ngoại ngữ thì cần làm những thủ tục gì? Nếu tài liệu chưa đủ, nêu rõ phần cần xác minh.'
GRAD='Sinh viên UET K69 cần lưu ý gì khi chuẩn bị tốt nghiệp: tín chỉ, ngoại ngữ, học phần còn nợ và xếp loại bằng? Phân biệt điều kiện chính thức và lời khuyên.'
class ReleaseCounselTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.put('data/versioning/publication_holds.jsonl',''); self.put(NOTE,(Path(__file__).parent/'advisor_language_notice.json').read_text(encoding='utf8'))
 def put(self,rel,text):
  p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode('utf8'));return hashlib.sha256(p.read_bytes()).hexdigest()
 def test_grouped_parser(self):
  self.assertEqual([len(v) for _,v in grouped_outcomes(OUTCOMES)],[1,1,1]);self.assertFalse(grouped_outcomes(OUTCOMES.replace('(3)','(4)')));self.assertFalse(grouped_outcomes(OUTCOMES.replace('Có khả năng giao tiếp','|Có khả năng giao tiếp')))
 def test_outcome_scope_and_hold(self):
  rel='data/raw/uet/curricula/robot.md';h=self.put(rel,OUTCOMES);self.put('data/raw/uet/curricula/catalog.json',json.dumps({'records':[{'collection':'team_original_uploads','content_kind':'learning_outcomes','program_identifier':'ktrb','cohort_hint_unverified':'QH-2025 onward (filename hint only)','doc_id':'robot','content_path':rel,'content_sha256':h}]}))
  q='Chuẩn đầu ra của ngành Kỹ thuật Robot khóa QH-2025 gồm những gì?';r=sections(self.root,q,{})[0];self.assertIn('3 yêu cầu',r['answer']);self.assertNotIn('Không được trích',r['answer']);self.assertIsNone(sections(self.root,q.replace('2025','2024'),{}));self.assertIsNone(sections(self.root,q+' PLO1',{}));self.put('data/versioning/publication_holds.jsonl',json.dumps({'doc_id':'robot','content_sha256':h}));self.assertIsNone(sections(self.root,q,{}))
 def test_language(self):
  r=route(self.root,EN,{})[0];self.assertIn('bản sao công chứng',r['answer']);self.assertIn('24/09/2024',r['answer']);self.assertIn('Chưa xác minh',r['answer']);self.assertEqual(len(r['metadata']['advisor_sources']),2);self.assertIsNone(route(self.root,EN.replace('K69','K71'),{}));self.assertIsNone(route(self.root,EN+' K70',{}));self.assertIsNone(route(self.root,EN,{'kind':'student'}))
 def test_language_hold_and_change(self):
  self.put('data/versioning/publication_holds.jsonl',json.dumps({'doc_id':'advisor-uet-language-1011-notice-2023','content_sha256':'a'*64}));self.assertIsNone(route(self.root,EN,{}));self.put('data/versioning/publication_holds.jsonl','');self.put(NOTE,'{}');self.assertIsNone(route(self.root,EN,{}))
 def test_graduation_multi(self):
  def c(root,q):
   a,k=map(int,__import__('re').search(r'Điều (\d+) khoản (\d+)',q).groups());return {'answer':f'Tham chiếu\n\nĐiều {a}, khoản {k} — nội dung {a}.{k}', 'path':'test.md','sha256':'a'*64,'source_url':'https://example.invalid','articles':[{'article':a,'clause':k}]}
  with patch('advisor_release_counsel.pinned',side_effect=c):
   r=route(self.root,GRAD,{})[0];self.assertIn('Điều 46, khoản 1',r['answer']);self.assertIn('Điều 47, khoản 5',r['answer']);self.assertIn('Điều 47, khoản 7',r['answer']);self.assertIn('Lời khuyên',r['answer']);self.assertEqual(len(r['metadata']['articles']),3);self.assertIsNone(route(self.root,GRAD.replace('K69','K71'),{}))
  with patch('advisor_release_counsel.pinned',return_value=None):self.assertIsNone(route(self.root,GRAD,{}))
 def test_withdrawal_broad_not_narrow(self):
  q='Quy trình rút bớt học phần theo quy chế đào tạo UET? Cần chú ý những thời hạn và hậu quả nào?'
  full={'answer':'complete','path':'test.md','sha256':'a'*64,'source_url':'https://example.invalid'}
  with patch('advisor_tasks.pinned',return_value=full) as pin,patch('presentation.withdrawal_summary',return_value='2 tuần, 1 tuần, điểm F, Phòng Đào tạo'):
   r,c=withdrawal(q,norm(q),{},self.root,None,None);self.assertIn('điểm F',r['answer']);pin.assert_called_once_with(self.root,'Điều 23 QĐ 3626');self.assertEqual(c['topic'],'withdrawal')
  with patch('advisor_tasks.pinned',return_value=None):self.assertIn('chưa xác minh đủ',withdrawal(q,norm(q),{},self.root,None,None)[0]['answer'])
 def test_http_product_route_and_research_isolation(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from types import SimpleNamespace
  from conversation import add_conversation
  from test_quality_routes import Request
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:{'students':[]},_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')))
  def fallback(req):return {'answer':'fallback','routing':{'risk_tier':'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  add_conversation(s,fallback,Request,self.root);client=TestClient(s.app)
  def ask(q,engine='auto',**kw):return client.post('/api/advisor/chat',json={'question':q,'experience':'advisor','force_engine':engine,**kw}).json()
  self.assertEqual(ask(EN)['metadata']['advisor_intent'],'language_notice_reference');self.assertEqual(ask(EN,'lora')['answer'],'fallback')
  rel='data/raw/uet/curricula/robot.md';h=self.put(rel,OUTCOMES);self.put('data/raw/uet/curricula/catalog.json',json.dumps({'records':[{'collection':'team_original_uploads','content_kind':'learning_outcomes','program_identifier':'ktrb','cohort_hint_unverified':'QH-2025 onward (filename hint only)','doc_id':'robot','content_path':rel,'content_sha256':h}]}))
  self.assertEqual(ask('Chuẩn đầu ra của ngành Kỹ thuật Robot khóa QH-2025 gồm những gì?')['metadata']['advisor_intent'],'curriculum_outcomes_grouped_reference')
  def c(root,q):
   a,k=map(int,__import__('re').search(r'Điều (\d+) khoản (\d+)',q).groups());return {'answer':f'Tham chiếu\n\nĐiều {a}, khoản {k} — nội dung {a}.{k}', 'path':'test.md','sha256':'a'*64,'source_url':'https://example.invalid','articles':[{'article':a,'clause':k}]}
  with patch('advisor_release_counsel.pinned',side_effect=c):self.assertEqual(len(ask(GRAD)['metadata']['articles']),3)
if __name__=='__main__':unittest.main()
