import json, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from runtime_v5 import install
from quality import SYSTEM
ROOT=Path(os.environ['CHRONOREG_TEST_REPO'])
class Response:
 def __init__(self,answer='27,58 điểm',reason='stop'): self.answer=answer;self.reason=reason
 def raise_for_status(self): pass
 def json(self): return {'message':{'content':self.answer},'done_reason':self.reason}
class Backend:
 def __init__(self): self.lora_model='lora';self.base_model='base';self.ollama_url='http://local';self.payload=None;self.response=Response()
 def _make_client(self,*a,**k):return self,False
 def post(self,url,json,timeout):self.payload=json;return self.response
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.backend=Backend();self.calls=[]
  def original(q,mode,advisor_bundle=None):self.calls.append((q,mode,advisor_bundle));return {'old':True}
  self.server=SimpleNamespace(llm_backend=self.backend,_run_rag_engine=original,_build_metadata=lambda *a,**k:{'original':True})
  install(self.server,ROOT)
 def test_table_dispatch(self):
  # Explicitly isolate source lookup from the hold ledger in local fixture tests.
  p=ROOT/'data/versioning/publication_holds.jsonl';self.assertTrue(p.is_file())
  pred=self.server._run_rag_engine('điểm chuẩn các ngành 2026','chrono_rag');self.assertEqual(pred['inference_source'],'deterministic_source_table');self.assertEqual(len(self.calls),0)
  meta=self.server._build_metadata([],1,pred=pred);self.assertEqual(meta['row_count'],20);self.assertEqual(len(meta['sha256']),64);self.assertIsNone(meta['model_name'])
 def test_scholarship_dispatch(self):
  pred=self.server._run_rag_engine('Mức học bổng xuất sắc CLC CNTT QH-2021 năm học 2023-2024?', 'chrono_rag');self.assertEqual(pred['inference_source'],'deterministic_source_table');self.assertIn('2.070.000 đồng/tháng',pred['predicted_answer']);self.assertEqual(len(self.calls),0)
  meta=self.server._build_metadata([],1,pred=pred);self.assertEqual(len(meta['sha256']),64);self.assertIsNone(meta['model_name'])
 def test_scholarship_hold(self):
  from scholarship import lookup_rates
  q='Mức học bổng xuất sắc CLC CNTT QH-2021 năm học 2023-2024?';v=lookup_rates(ROOT,q);hold=ROOT/'data/versioning/publication_holds.jsonl';read=Path.read_text
  def fake(p,*a,**k):return json.dumps({'content_sha256':v['normalized_sha256']}) if p==hold else read(p,*a,**k)
  with patch.object(Path,'read_text',fake):self.assertTrue(self.server._run_rag_engine(q,'chrono_rag')['old'])
 def test_other_routes_unchanged(self):
  for mode,ab in [('naive_rag',{}),('chrono_rag',{'roster_context':'x'})]:self.assertTrue(self.server._run_rag_engine('điểm chuẩn các ngành 2026',mode,ab)['old'])
 def test_prompt_and_guard(self):
  self.backend._call_ollama('lora','Năm học được hỏi: 2024-2025.\nCâu hỏi?');self.assertEqual(self.backend.payload['messages'][0]['content'],SYSTEM)
  prompt='Dưới đây là các đoạn văn bản quy định chính thức:\n\n27,58 điểm\n\nCâu hỏi của sinh viên: Điểm chuẩn 2024?'
  self.assertEqual(self.backend._call_ollama('base',prompt),'27,58 điểm');self.assertEqual(self.backend.payload['options']['num_predict'],768)
  self.backend.response=Response('26,85 điểm');self.assertRaises(RuntimeError,self.backend._call_ollama,'base',prompt)
  self.backend.response=Response('27,58 điểm','length');self.assertRaises(RuntimeError,self.backend._call_ollama,'base',prompt)
 def test_publication_hold(self):
  from quality import lookup
  v=lookup(ROOT,'điểm chuẩn các ngành 2026');hold=ROOT/'data/versioning/publication_holds.jsonl';old=hold.read_bytes()
  # Mock read, do not modify repository data.
  read=Path.read_text
  def fake(p,*a,**k):return json.dumps({'content_sha256':v['sha256']}) if p==hold else read(p,*a,**k)
  with patch.object(Path,'read_text',fake):self.assertTrue(self.server._run_rag_engine('điểm chuẩn các ngành 2026','chrono_rag')['old'])
  self.assertEqual(hold.read_bytes(),old)
if __name__=='__main__':unittest.main()
