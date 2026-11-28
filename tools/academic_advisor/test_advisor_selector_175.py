import unittest,json
from unittest.mock import MagicMock,patch
from advisor_evidence import Passage,select_local,sentence_spans
from advisor_composer import compose,clarify

class SelectorTests(unittest.TestCase):
 def setUp(self):
  self.text='Điểm bộ phận được công bố theo quy định. Sinh viên chỉ được dự thi khi đáp ứng đủ điều kiện và đã nộp học phí.'
  self.p=Passage(self.text,'Điều thử nghiệm','p','h','','',38,1)
 def test_sentence_contract(self):
  self.assertEqual(len(sentence_spans(self.text)),2)
  self.assertEqual(len(sentence_spans('1. Điểm đạt từ 5.0 trở lên.')),1)
  fake=MagicMock();fake.__enter__.return_value=fake
  with patch('advisor_evidence.urllib.request.build_opener') as opener:
   opener.return_value.open.return_value=fake
   def run(obj):
    fake.read.return_value=json.dumps({'done_reason':'stop','message':{'content':json.dumps(obj)}})
    return select_local('Điều kiện?', [self.p])
   self.assertEqual(run({'id':'P1','sentence':2}),(self.p,sentence_spans(self.text)[1]))
   request=opener.return_value.open.call_args.args[0];payload=json.loads(request.data)
   self.assertEqual(payload['options']['num_predict'],40)
   self.assertNotIn('focus',payload['format']['properties'])
   self.assertEqual(run({'id':'P1','sentence':0}),(self.p,None))
   for obj in [{'id':'P2','sentence':1},{'id':'NONE','sentence':0},{'id':'P1','sentence':3},{'id':'P1','sentence':True},{'id':'P1','sentence':1,'answer':'fake'}]:self.assertIsNone(run(obj))
 def test_complete_sentence_and_conditions(self):
  r=compose('Điều kiện?',self.p,sentence_spans(self.text)[1]);self.assertTrue(r.startswith('Dạ cô, Sinh viên chỉ'));self.assertIn(self.text,r)
  self.assertIn(self.text,compose('?',self.p,'không có học phí'))
 def test_version(self):
  self.assertIn('K71',clarify('Theo QĐ 3626, khoản 1 Điều 37 áp dụng cho sinh viên K71 không?',{}))
  self.assertIn('K66',clarify('Theo QĐ 3626 áp dụng cho K66?',{}))
  self.assertIsNone(clarify('Theo QĐ 3626 áp dụng cho K69?',{}))
  self.assertIsNone(clarify('Trích nguyên văn khoản 1 Điều 37 QĐ 3626',{}))
 def test_no_second_generator_for_explicit_public_edition(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from types import SimpleNamespace
  from tempfile import TemporaryDirectory
  from pathlib import Path
  from conversation import add_conversation
  from test_quality_routes import Request
  with TemporaryDirectory() as temp:
   server=SimpleNamespace(app=FastAPI(),_get_active_roster=lambda:{},_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='GREEN')),_semantic_pilot=True)
   dispatch=MagicMock(return_value={'answer':'research result','metadata':{},'routing':{'risk_tier':'GREEN'}})
   add_conversation(server,dispatch,Request,Path(temp));client=TestClient(server.app)
   q='Theo QĐ 3626, trọng số điểm kết thúc học phần tối thiểu là bao nhiêu?'
   with patch('advisor_evidence.retrieve',return_value=None),patch('advisor_agent.route',return_value=None),patch('semantic_product.route',return_value=None),patch('quality_routes.route',return_value=None):
    r=client.post('/api/advisor/chat',json={'question':q,'experience':'advisor'}).json();self.assertIn('chưa xác minh',r['answer']);dispatch.assert_not_called()
    self.assertEqual(client.post('/api/advisor/chat',json={'question':q}).json()['answer'],'research result');dispatch.assert_called_once()
if __name__=='__main__':unittest.main()
