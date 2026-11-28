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
 def test_graduation_natural_language(self):
  source={'answer':'Tham chiếu\n\nĐiều 46, khoản 1 — Điều kiện tốt nghiệp:\n1. Tích lũy đủ số tín chỉ; CPA; ngoại ngữ; thời gian đào tạo.', 'path':'test.md','sha256':'a'*64,'source_url':'https://example.invalid','articles':[{'article':46,'clause':1}]}
  qs=['tôi cần tốt nghiệp điều kiện là gì','Điều kiện tốt nghiệp?','Muốn tốt nghiệp cần đáp ứng những yêu cầu gì?','Sinh viên UET K69 cần đáp ứng điều kiện gì để tốt nghiệp?','muon tot nghiep can lam gi']
  with patch('advisor_release_counsel.pinned',return_value=source) as pin:
   for q in qs:
    with self.subTest(q=q):
     r,ctx=route(self.root,q,{});self.assertEqual(r['metadata']['engine_mode'],'SOURCE_CLAUSE');self.assertIn('Điều 46, khoản 1',r['answer']);self.assertIn('chưa xác nhận cá nhân',r['answer']);self.assertEqual(ctx,{})
   self.assertIn('2022–2025',route(self.root,qs[0],{})[0]['answer']);self.assertIn('QH-2024',route(self.root,qs[3],{})[0]['answer']);self.assertIn('Điều 46',route(self.root,qs[0],{'kind':'public_year','question':'Điểm chuẩn 2024'})[0]['answer'])
   pin.assert_called_with(self.root,'Điều 46 khoản 1 QĐ 3626')
 def test_graduation_natural_language_scope(self):
  with patch('advisor_release_counsel.pinned') as pin:
   for q in ['Điều kiện tốt nghiệp K71?','Điều kiện tốt nghiệp khóa 2021?','Điều kiện tốt nghiệp K69 K70?']:
    r,_=route(self.root,q,{});self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertNotIn('2,00',r['answer'])
   for q in ['Tôi có đủ điều kiện tốt nghiệp không?','Tôi có đủ điều kiện tốt nghiệp?','Tôi cần bao nhiêu tín chỉ để tốt nghiệp?','Điều kiện tốt nghiệp thạc sĩ?','Điều kiện tốt nghiệp HUTECH?','Điều kiện tốt nghiệp của sinh viên 24000001?','Điều kiện tốt nghiệp và học phí?']:
    self.assertIsNone(route(self.root,q,{}),q)
   pin.assert_not_called()
  with patch('advisor_release_counsel.pinned',return_value=None):
   self.assertIn('chưa xác minh',route(self.root,'tôi cần tốt nghiệp điều kiện là gì',{})[0]['answer'])
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
  with patch('advisor_release_counsel.pinned',side_effect=c):
   self.assertEqual(len(ask(GRAD)['metadata']['articles']),3)
   r=ask('tôi cần tốt nghiệp điều kiện là gì');self.assertEqual(r['metadata']['articles'],[{'article':46,'clause':1}]);self.assertIn('2022–2025',r['answer']);self.assertEqual(ask('tôi cần tốt nghiệp điều kiện là gì','lora')['answer'],'fallback')
 def test_rank_natural_intents(self):
  from advisor_release_counsel import graduation_rank
  answers={
   (46,1):'Điều 46, khoản 1: đủ tín chỉ, chuẩn ngoại ngữ, thời gian đào tạo, giáo dục thể chất.',
   (47,5):'Điều 47, khoản 5: a) Xuất sắc: Điểm trung bình chung tích lũy từ 3,60 đến 4,00\nb) Giỏi: Điểm trung bình chung tích lũy từ 3,20 đến 3,59\nc) Khá: Điểm trung bình chung tích lũy từ 2,50 đến 3,19\nd) Trung bình: Điểm trung bình chung tích lũy từ 2,00 đến 2,49.',
   (47,7):'Điều 47, khoản 7: Hạng xuất sắc hoặc giỏi bị hạ nếu học lại vượt quá 5% hoặc bị kỷ luật từ mức cảnh cáo trở lên.'}
  def c(root,q):
   a,k=map(int,__import__('re').search(r'Điều (\d+) khoản (\d+)',q).groups());return {'answer':answers[a,k], 'path':'test.md','sha256':'a'*64,'source_url':'https://example.invalid','articles':[{'article':a,'clause':k}]}
  questions=['cách để tốt nghiệp loại xuât sắc là gì','làm sao để ra trường bằng xuất sắc','muon tot nghiep xuat sac thi can lam gi','Tốt nghiệp xuất sắc cần CPA bao nhiêu?','Điểm trung bình tích lũy để tốt nghiệp xuất sắc là bao nhiêu?','Bằng giỏi cần bao nhiêu điểm?','Xếp loại tốt nghiệp gồm các mức nào?','Tốt nghiệp xuất sắc K69 cần gì?','cách tốt nghiệp loại suat sac']
  with patch('advisor_release_counsel.pinned',side_effect=c):
   for q in questions:
    with self.subTest(q=q):
     r,_=route(self.root,q,{});self.assertEqual(r['metadata']['engine_mode'],'SOURCE_CLAUSE');self.assertIn('5%',r['answer']);self.assertIn('Điều 46',r['answer']);self.assertEqual(len(r['metadata']['articles']),3)
     if 'giỏi' not in q and 'Xếp loại' not in q:self.assertIn('3,60',r['answer']);self.assertNotIn('2,00–2,49',r['answer'])
   for q in ['Tốt nghiệp xuất sắc K71 cần gì?','Tốt nghiệp xuất sắc năm 2026?','Tốt nghiệp xuất sắc K69 K70?']:
    r,_=route(self.root,q,{});self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertNotIn('3,60',r['answer'])
   for q in ['Học bổng loại xuất sắc cần gì?','Tốt nghiệp xuất sắc và học bổng?', 'Tốt nghiệp xuất sắc HUTECH?', 'Tốt nghiệp loại giỏi nếu học lại 2 môn?', 'Tôi có CPA 3,4 tốt nghiệp xuất sắc được không?', 'Sinh viên 24000001 tốt nghiệp xuất sắc?', 'Tốt nghiệp thạc sĩ xuất sắc?']:
    self.assertIsNone(graduation_rank(self.root,q),q)
  with patch('advisor_release_counsel.pinned',return_value=None):
   r,_=route(self.root,questions[0],{});self.assertEqual(r['metadata']['engine_mode'],'CONTEXT_CLARIFICATION');self.assertNotIn('3,60',r['answer'])
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from types import SimpleNamespace
  from conversation import add_conversation
  from test_quality_routes import Request
  s=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:{'students':[]},_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')))
  def fallback(req):return {'answer':'fallback','routing':{'risk_tier':'GREEN'},'metadata':{'engine_mode':'KNOWLEDGE_EXCERPTS'}}
  add_conversation(s,fallback,Request,self.root);client=TestClient(s.app)
  with patch('advisor_release_counsel.pinned',side_effect=c):
   for engine in ['auto','lora','rag']:
    r=client.post('/api/advisor/chat',json={'question':questions[0],'experience':'advisor','force_engine':engine}).json()
    if engine=='auto':self.assertIn('3,60',r['answer'])
    else:self.assertEqual(r['answer'],'fallback')
if __name__=='__main__':unittest.main()
