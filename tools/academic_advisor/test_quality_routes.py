import unittest, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from quality_routes import route
from conversation import add_conversation
from knowledge import Index

# Synthetic source text: do not certify real UET provisions with this fixture.
RANK_SOURCE={'path':'test.md','sha256':'fixture','source_url':'https://example.invalid','answer':'Điều 47, khoản 7 — Xếp hạng\nSinh viên đạt hạng xuất sắc hoặc giỏi bị hạ một hạng nếu bị kỷ luật từ mức cảnh cáo trở lên hoặc tổng số tín chỉ của các học phần phải học lại vượt quá 5% tổng số tín chỉ quy định cho toàn chương trình.'}
LOAD_SOURCE={'path':'test.md','sha256':'fixture','source_url':'https://example.invalid','answer':'Điểm trung bình chung học kỳ dưới 2,00 được đăng ký không quá 18 tín chỉ. 3/2 khối lượng trung bình.'}
class Request(BaseModel):
 question:str; force_engine:str|None=None; mssv:str|None=None
class Routes(unittest.TestCase):
 def setUp(self):
  self.roster={'class_short':'K69-CNTT1','cohort':'QH-2024 (K69)','semester':'2025.1','students':[{'student_id':'24000001','bang_diem':[{'ma_mon':c,'dat':False} for c in ('ABC0001','ABC0002','ABC0003')]},{'student_id':'24000002','bang_diem':[{'ma_mon':'ABC0001','dat':False},{'ma_mon':'ABC0002','dat':False},{'ma_mon':'ABC0003','dat':True}]}], 'courses':[{'ma_mon':c,'so_tin_chi':3} for c in ('ABC0001','ABC0002','ABC0003')]}
  self.root=Path('.')
 def go(self,q,old=None,sid=None):return route(q,old or {},sid,None,self.roster,self.root)
 def test_rank_followup_cohort_hold(self):
  with patch('quality_routes.lookup_regulation',return_value=RANK_SOURCE):
   r,ctx=self.go('Thi lại hai môn có phải bằng sẽ bị hạ không?');self.assertIn('phân biệt thi lại',r['answer']);self.assertEqual(ctx['topic'],'rank')
   r,ctx=self.go('Nếu đúng bằng 5% thì sao?',ctx);self.assertIn('không thỏa điều kiện',r['answer'])
   r,ctx=self.go('Còn khóa tuyển sinh 2026 thì sao?',ctx);self.assertIn('chưa có điều khoản',r['answer']);self.assertNotIn('5%',r['answer'])
  with patch('quality_routes.lookup_regulation',side_effect=ValueError('held')):
   r,_=self.go('Thi lại có bị hạ bằng không?');self.assertNotIn('5%',r['answer']);self.assertIn('chưa có điều khoản',r['answer'])
 def test_credit_correction(self):
  with patch('quality_routes.lookup_regulation',return_value=LOAD_SOURCE):
   r,c=self.go('GPA học kỳ 1,99 có nên đăng ký 18 tín chỉ không?');self.assertEqual(c['gpa'],1.99);self.assertIn('không phải mức nên',r['answer'])
   r,c=self.go('À, GPA đó là tích lũy.',c);self.assertNotIn('gpa',c);self.assertIn('không thay cho',r['answer'])
   r,c=self.go('Nếu kỳ phụ thì dùng ngưỡng đó không?',c);self.assertIn('kỳ phụ',r['answer']);self.assertEqual(c['gpa_kind'],'cumulative')
 def test_plan_changes_budget(self):
  table={'ABC0001':(3,()),'ABC0002':(3,('ABC0001',)),'ABC0003':(3,())}
  with patch('quality_routes.load_candidate',return_value=(table,None)):
   r,c=self.go('Mỗi đợt học lại 3 tín chỉ, tối ưu số đợt.',{'kind':'student','mssv':'24000001'});self.assertEqual(c['rounds'],3);self.assertIn('Tối thiểu',r['answer'])
   r,c=self.go('Đổi thành 6 tín chỉ mỗi đợt.',c);self.assertEqual(c['rounds'],2);self.assertIn('3 → 2',r['answer']);self.assertNotIn('24000002',r['answer'])
   r,c=self.go('Đổi thành 9 tín chỉ mỗi đợt của lớp K70.',c);self.assertEqual(c,{});self.assertIn('chọn đúng',r['answer'])
 def test_tied_leaders_and_cause(self):
  r,c=self.go('Môn nào có nhiều người chưa thấy lần đạt nhất?');self.assertIn('ABC0001',r['answer']);self.assertIn('ABC0002',r['answer']);self.assertNotIn('ABC0003',r['answer'])
  r,_=self.go('Có kết luận được giảng viên môn đó dạy kém không?',c);self.assertIn('không thể suy ra',r['answer'])
 def test_fresh_scope_and_hold(self):
  self.assertEqual(self.go('Bạn ấy đang nợ mấy tín chỉ?')[0]['metadata']['advisor_intent'],'scope_clarification')
  self.assertEqual(self.go('Trích điều khoản văn bản đang tạm khóa để tư vấn chính thức.')[0]['metadata']['advisor_intent'],'publication_hold')
  self.assertIsNone(self.go('Điểm chuẩn UET năm 2024?'))
 def test_api_research_and_context_isolation(self):
  calls=[]
  def original(req):calls.append(req.question);return {'answer':'original','routing':{'risk_tier':'RED' if 'ngoại lệ' in req.question else 'GREEN'},'metadata':{}}
  s=SimpleNamespace(app=FastAPI(),_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')),_get_active_roster=lambda:self.roster)
  add_conversation(s,original,Request,self.root);client=TestClient(s.app)
  def ask(q,**kw):return client.post('/api/advisor/chat',json={'question':q,**kw}).json()
  with patch('quality_routes.lookup_regulation',return_value=RANK_SOURCE):
   r=ask('Thi lại có bị hạ bằng không?');t=r['context_token'];self.assertTrue(t)
   self.assertIn('không thỏa',ask('Nếu đúng bằng 5% thì sao?',context_token=t)['answer'])
   self.assertEqual(ask('Nếu đúng bằng 5% thì sao?')['metadata']['advisor_intent'],'context_clarification')
   self.assertEqual(ask('Nếu đúng bằng 5% thì sao?',context_token=t+'x')['metadata']['advisor_intent'],'context_clarification')
   self.assertEqual(ask('Thi lại có bị hạ bằng không?',force_engine='continual_lora')['answer'],'original')
   self.assertEqual(ask('Xin ngoại lệ thi lại có bị hạ bằng không?',context_token=t)['routing']['risk_tier'],'RED')
 def test_no_technical_readme(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'data/raw/uet/markdown/2025';p.mkdir(parents=True)
   (p/'README.md').write_text('Học lại tín chỉ dữ liệu kỹ thuật nội bộ.',encoding='utf8');(p/'notice.md').write_text('Học lại tín chỉ theo thông báo đào tạo.',encoding='utf8')
   ix=Index(root);self.assertEqual(ix.stats()['metadata_only'],1);self.assertTrue(all(c.path.endswith('notice.md') for c in ix.search('Học lại tín chỉ')))
 def test_no_unrelated_conflict_notice(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'data/raw/uet/markdown/2025';p.mkdir(parents=True)
   (p/'notice.md').write_text('Hai mốc khác nhau về đăng ký học phần. Không tự quyết định mốc nào thay thế mốc nào.',encoding='utf8')
   ix=Index(root);self.assertFalse(ix.search('Giải thích đăng ký học phần'));self.assertTrue(ix.search('Hạn đăng ký học phần'))
if __name__=='__main__':unittest.main()
