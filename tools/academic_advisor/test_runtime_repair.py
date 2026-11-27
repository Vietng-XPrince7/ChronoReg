import json,tempfile,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import httpx
import local_slm as m

class RuntimeRepairTests(unittest.TestCase):
 def setUp(self):
  # Runtime detection is a test input, never a property of the host machine.
  # Any unexpected model download is a test failure, not a 1.12 GB transfer.
  self.enterContext(patch.object(m,'find_ollama',return_value=None))
  self.enterContext(patch.object(m,'download',side_effect=AssertionError('Unexpected model download in unit test')))

 def test_code_integrity_signed_and_unsigned(self):
  for code in (-1058471934,0xc0e90002):
   with self.assertRaises(m.RuntimeBlocked):m.check_exit(code,'runtime.log')
  with self.assertRaisesRegex(RuntimeError,'0x00000001'):m.check_exit(1,'runtime.log')
 def test_automatic_fallback(self):
  @contextmanager
  def blocked(cache):
   raise m.RuntimeBlocked('blocked')
   yield
  @contextmanager
  def available(cache,model):
   self.assertEqual(model,cache/m.MODEL_FILE)
   yield 'http://127.0.0.1:11434/ollama'
  with tempfile.TemporaryDirectory() as d,patch.object(m,'llama_server',blocked),patch.object(m,'ollama_server',available),patch.object(m,'download',return_value=Path(d)/m.MODEL_FILE) as dl:
   with m.server(Path(d)) as url:self.assertTrue(url.endswith('/ollama'))
   self.assertEqual(dl.call_args.args[2],m.MODEL_SHA)
 def test_not_fallback_on_application_exception(self):
  @contextmanager
  def healthy(cache):yield 'http://127.0.0.1:1234'
  with tempfile.TemporaryDirectory() as d,patch.object(m,'llama_server',healthy),patch.object(m,'ollama_server') as fallback:
   for error in (m.RuntimeBlocked('inside app'), PermissionError('inside app')):
    with self.assertRaises(type(error)) as caught:
     with m.server(Path(d)):raise error
    self.assertIs(caught.exception,error)
   fallback.assert_not_called()
 def test_preferred_ollama_application_error_no_llama_fallback(self):
  @contextmanager
  def healthy(cache,model):yield 'http://127.0.0.1:11434/ollama'
  with tempfile.TemporaryDirectory() as d,patch.object(m,'find_ollama',return_value='ollama'),patch.object(m,'download',return_value=Path(d)/m.MODEL_FILE) as dl,patch.object(m,'ollama_server',healthy),patch.object(m,'llama_server') as fallback:
   for error in (m.RuntimeBlocked('inside app'), PermissionError('inside app')):
    with self.assertRaises(type(error)) as caught:
     with m.server(Path(d)):raise error
    self.assertIs(caught.exception,error)
   fallback.assert_not_called()
   self.assertEqual(dl.call_count,2)
 def test_ollama_request_cpu_local_schema(self):
  schema={'type':'object'}
  def handler(req):
   self.assertEqual(str(req.url),'http://127.0.0.1:11434/api/chat');p=json.loads(req.content)
   self.assertEqual(p['model'],m.OLLAMA_TAG);self.assertEqual(p['format'],schema);self.assertEqual(p['options']['num_gpu'],0);self.assertFalse(p['stream'])
   return httpx.Response(200,json={'done':True,'done_reason':'stop','message':{'content':'{}'}})
  c=m.LocalClient('http://127.0.0.1:11434/ollama',httpx.MockTransport(handler))
  self.assertEqual(c.post('',{'messages':[{'role':'system','content':'test'}],'format':schema},2).json()['done_reason'],'stop')
 def test_missing_ollama(self):
  with patch.object(m,'find_ollama',return_value=None):
   with self.assertRaisesRegex(RuntimeError,'not installed'):
    with m.ollama_server(Path('.'),Path(m.MODEL_FILE)):pass

if __name__=='__main__':unittest.main()
