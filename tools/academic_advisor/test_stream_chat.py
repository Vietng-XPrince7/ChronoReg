import json,time,unittest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from stream_chat import install_stream

class StreamTests(unittest.TestCase):
 def test_exact_text_context_and_heartbeat(self):
  app=FastAPI(); calls=[]
  answer='Tiếng Việt: <mark>đối chiếu</mark> 27 tín chỉ.\n'+'🙂 Nội dung kiểm tra. '*100
  def handler(req):
   calls.append(req.model_dump());time.sleep(.025)
   return JSONResponse({'answer':answer,'context_token':'signed-token','metadata':{'source':'test'},'routing':{'risk_tier':'GREEN'}})
  install_stream(app,handler,interval=0,heartbeat=.005)
  r=TestClient(app).post('/api/advisor/chat/stream',json={'question':'kiểm tra','context_token':'prior','mssv':'24000001'})
  self.assertEqual(r.status_code,200);self.assertIn('application/x-ndjson',r.headers['content-type']);self.assertEqual(r.headers['cache-control'],'no-store')
  events=[json.loads(x) for x in r.text.splitlines()];self.assertEqual(events[0]['event'],'processing');self.assertGreaterEqual(sum(e['event']=='processing' for e in events),2)
  self.assertEqual(''.join(e['text'] for e in events if e['event']=='delta'),answer);self.assertEqual(events[-1]['data']['context_token'],'signed-token');self.assertEqual(len(calls),1);self.assertEqual(calls[0]['context_token'],'prior')
  self.assertLessEqual(sum(e['event']=='delta' for e in events),45)
 def test_error_and_input_validation(self):
  app=FastAPI(); calls=[]
  def handler(req):calls.append(req);raise RuntimeError('PRIVATE_SECRET')
  install_stream(app,handler,interval=0);c=TestClient(app)
  self.assertEqual(c.post('/api/advisor/chat/stream',json={'question':''}).status_code,422);self.assertEqual(calls,[])
  r=c.post('/api/advisor/chat/stream',json={'question':'test'});e=[json.loads(x) for x in r.text.splitlines()];self.assertEqual(e[-1]['event'],'error');self.assertNotIn('PRIVATE_SECRET',r.text);self.assertFalse(any(x['event']=='delta' for x in e))
 def test_http_failure_not_rendered(self):
  app=FastAPI();install_stream(app,lambda req:JSONResponse(status_code=503,content={'answer':'should not render'}),interval=0)
  r=TestClient(app).post('/api/advisor/chat/stream',json={'question':'test'});self.assertNotIn('should not render',r.text);self.assertEqual(json.loads(r.text.splitlines()[-1])['event'],'error')
if __name__=='__main__':unittest.main()
