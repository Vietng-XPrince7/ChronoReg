import unittest,tempfile,re,copy,sqlite3
from contextlib import closing
from pathlib import Path
from datetime import date
from fastapi import FastAPI
from fastapi.testclient import TestClient
from advisor_workspace import install_workspace,proposal,scope_for,Store,digest

class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test.sqlite3'
  self.roster={'class_short':'K69-DEMO','semester':'2025.1','students':[{'student_id':'24000001','gpa_semester':1.1,'owed_credits':11,'drl':65},{'student_id':'24000002','gpa_semester':1.4,'owed_credits':7,'drl':69},{'student_id':'24000003','gpa_semester':3.1,'owed_credits':0,'drl':90},{'student_id':'24000004','gpa_semester':3.1,'owed_credits':0,'drl':None}]}
  self.make_client()
 def make_client(self):
  app=FastAPI();self.store=install_workspace(app,lambda:self.roster,Path(self.tmp.name),path=self.path);self.c=TestClient(app,base_url='http://127.0.0.1:8765');page=self.c.get('/advisor/workspace');self.assertEqual(page.status_code,200);self.headers={'X-Advisor-Workspace':re.search(r"const token='([^']+)'",page.text)[1]};self.scope=scope_for(self.roster)
 def get(self):return self.c.get('/api/advisor/workspace',headers=self.headers)
 def post(self,suffix,body):return self.c.post('/api/advisor/workspace/'+suffix,json={'scope':self.scope,**body},headers=self.headers)
 def preview(self,goal='graduation',days=14):
  r=self.post('preview',{'goal':goal,'days':days});self.assertEqual(r.status_code,200,r.text);return r.json()
 def confirm(self,p):return self.post('confirm',{k:p[k] for k in ('goal','days','as_of','preview_hash')}|{'confirmation':True})
 def saved(self):
  r=self.confirm(self.preview());self.assertEqual(r.status_code,200,r.text);return r.json()['plans'][0]
 def update(self,t,**kw):return self.post('update',{'task_id':t['id'],'revision':t['revision'],'status':'doing','note':'','review':None,**kw})
 def test_preview_no_write(self):
  p=self.preview();self.assertTrue(p['draft']);self.assertFalse(self.path.exists());self.assertEqual(self.get().json()['plans'],[])
 def test_goal_and_boundaries(self):
  for g in ('graduation','improvement','daily'):
   p=proposal(self.roster,g,3,date(2026,11,27));self.assertEqual({t['student_id'] for t in p['tasks'] if t['student_id']},{'24000001','24000002'});self.assertTrue(all('2026-11-27'<t['due']<='2026-11-30' for t in p['tasks']));self.assertEqual('graduation' in [t['key'] for t in p['tasks']],g=='graduation');self.assertEqual('midterm' in [t['key'] for t in p['tasks']],g=='improvement')
  self.assertEqual(self.post('preview',{'goal':'daily','days':0}).status_code,422)
 def test_confirm_once_and_tamper(self):
  p=self.preview();bad={**p,'preview_hash':'0'*64};self.assertEqual(self.confirm(bad).status_code,409)
  r=self.confirm(p);self.assertTrue(r.json()['created']);r=self.confirm(p);self.assertFalse(r.json()['created']);self.assertEqual(len(r.json()['plans']),1)
 def test_persistence_and_event(self):
  t=self.saved()['tasks'][0];r=self.update(t,status='done',note='Đã đối chiếu hồ sơ',review='2026-12-01');self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['plans'][0]['completed'],1)
  self.make_client();p=self.get().json()['plans'][0];self.assertEqual(p['completed'],1);self.assertEqual(p['tasks'][0]['review'],'2026-12-01');self.assertEqual(p['tasks'][0]['note'],'Đã đối chiếu hồ sơ');self.assertEqual(p['tasks'][0]['history'][0]['status'],'done')
  with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
 def test_reject_stale_or_invalid(self):
  t=self.saved()['tasks'][0];self.assertEqual(self.update(t,status='done').status_code,422);self.assertEqual(self.update(t,status='blocked').status_code,422);self.assertEqual(self.update(t,review='2026-02-30').status_code,422);self.assertEqual(self.update(t).status_code,200);self.assertEqual(self.update(t).status_code,409)
 def test_snapshot_isolation(self):
  t=self.saved()['tasks'][0];self.roster['students'][0]['owed_credits']=5;self.assertEqual(self.update(t).status_code,409);self.scope=scope_for(self.roster);self.assertEqual(self.update(t).status_code,404);r=self.get().json();self.assertEqual(r['plans'],[]);self.assertEqual(r['other_snapshot_plan_count'],1)
 def test_guard(self):
  self.assertEqual(self.c.get('/api/advisor/workspace').status_code,403);self.assertEqual(self.c.get('/api/advisor/workspace',headers={**self.headers,'Origin':'https://bad.example'}).status_code,403);self.assertEqual(self.c.get('/advisor/workspace',headers={'Host':'bad.example'}).status_code,403)
 def test_external_top_level_navigation(self):
  nav={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document','Sec-Fetch-User':'?1'}
  r=self.c.get('/advisor/workspace',headers=nav);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.headers['X-Frame-Options'],'DENY');self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy']);self.assertEqual(r.headers['Cache-Control'],'no-store')
  self.assertEqual(self.c.get('/advisor/workspace',headers={**nav,'Sec-Fetch-Dest':'iframe'}).status_code,403)
  self.assertEqual(self.c.get('/advisor/workspace',headers={**nav,'Sec-Fetch-Mode':'cors'}).status_code,403)
  self.assertEqual(self.c.get('/advisor/workspace',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
  self.assertEqual(self.c.get('/advisor/workspace',headers={**nav,'Origin':'https://bad.example'}).status_code,403)
  self.assertEqual(self.c.get('/advisor/workspace',headers={**nav,'Host':'bad.example'}).status_code,403)
 def test_cross_site_api_still_blocked(self):
  nav={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'}
  self.assertEqual(self.c.get('/api/advisor/workspace',headers={**self.headers,**nav}).status_code,403)
  p=self.preview();body={k:p[k] for k in ('goal','days','as_of','preview_hash','scope')}|{'confirmation':True}
  self.assertEqual(self.c.post('/api/advisor/workspace/confirm',json=body,headers={**self.headers,**nav}).status_code,403)
  self.assertEqual(self.c.post('/api/advisor/workspace/confirm',json=body).status_code,403)
  self.assertEqual(self.get().json()['plans'],[])
 def test_same_origin_browser_requests(self):
  headers={**self.headers,'Sec-Fetch-Site':'same-origin','Sec-Fetch-Mode':'cors','Sec-Fetch-Dest':'empty'}
  self.assertEqual(self.c.get('/api/advisor/workspace',headers=headers).status_code,200)
  self.assertEqual(self.c.post('/api/advisor/workspace/preview',headers={**headers,'Origin':'http://127.0.0.1:8765'},json={'scope':self.scope,'goal':'daily','days':14}).status_code,200)
 def test_no_students(self):
  self.roster['students']=[];self.assertEqual(self.get().status_code,409)
 def test_duplicate_ids_and_missing_fields(self):
  self.roster['students'].append(copy.deepcopy(self.roster['students'][0]));self.scope=scope_for(self.roster);p=self.preview();self.assertEqual(p['duplicates'],2);self.assertNotIn('24000001',{t['student_id'] for t in p['tasks']});self.assertIn('repair',[t['key'] for t in p['tasks']])
if __name__=='__main__':unittest.main()
