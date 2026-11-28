"""Independent regressions for the changed behavior; synthetic evidence only."""
import unittest
from types import SimpleNamespace
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from conversation import add_conversation, resolve, Context
from intelligence import dispatch
from adaptive_counsel import validated
from meeting_context import update_topics
from course_planning import make_plan
from schedule_optimizer import validate

class Upgrade(unittest.TestCase):
 def setUp(self):
  self.students=[{'student_id':'24000001','full_name':'Demo A','gpa_semester':1.4,'owed_credits':7,'drl':68}, {'student_id':'24000002','full_name':'Demo B','gpa_semester':3.5,'owed_credits':0,'drl':90}]
  self.roster={'students':self.students,'courses':[],'class_short':'K69-CNTT1','cohort':'QH-2024 (K69)'}
  class Request(BaseModel):
   question:str;force_engine:str|None=None;mssv:str|None=None
  def call(req):
   bundle={'category':'STUDENT_STATUS','student_id':req.mssv,'entities':{'mssv':req.mssv},'roster_obj':self.roster}
   p=dispatch(req.question,bundle,Path('.')) if req.mssv else None
   return {'answer':p['predicted_answer'] if p else 'public','metadata':p or {},'routing':{'risk_tier':'GREEN'}}
  s=SimpleNamespace(app=FastAPI(),_router=SimpleNamespace(route_decision=lambda q:SimpleNamespace(risk_tier='RED' if 'ngoại lệ' in q else 'GREEN')))
  add_conversation(s,call,Request);self.c=TestClient(s.app)
 def ask(self,q,token=None,sid=None,force=None):
  r=self.c.post('/api/advisor/chat',json={'question':q,'context_token':token,'mssv':sid,'force_engine':force});self.assertEqual(r.status_code,200);return r.json()
 def start(self):
  return self.ask('Nếu em này vừa đi làm vừa học, cô nên hỗ trợ thế nào?',sid='24000001')['context_token']
 def test_retains_hypothesis_and_answers_only_questions(self):
  t=self.start();r=self.ask('Trong buổi gặp đó cô nên hỏi gì?',t);self.assertIn('lịch ca',r['answer']);self.assertIn('giả định',r['answer']);self.assertNotIn('Hồ sơ demo:',r['answer']);self.assertNotIn('Việc cô có thể làm',r['answer']);self.assertNotIn('Demo B',r['answer'])
  r=self.ask('Chỉ cho cô 2 câu hỏi',r['context_token']);self.assertEqual(r['answer'].count('• '),2);self.assertIn('lịch ca',r['answer'])
 def test_explicit_same_student_keeps_context(self):
  r=self.ask('Chỉ cho cô 3 câu hỏi',self.start(),sid='24000001');self.assertIn('lịch ca',r['answer']);self.assertEqual(r['answer'].count('• '),3)
 def test_correction_removes_context(self):
  r=self.ask('Em ấy không còn đi làm nữa.',self.start());self.assertIn('đính chính',r['answer']);self.assertNotIn('lịch ca',r['answer']);r2=self.ask('Trong buổi gặp đó cô nên hỏi gì?',r['context_token']);self.assertNotIn('lịch ca',r2['answer'])
 def test_adds_new_context(self):
  r=self.ask('Nếu em ấy cũng mất gốc thì cô nên hỗ trợ thế nào?',self.start());self.assertIn('lịch ca',r['answer']);self.assertIn('kiến thức nền',r['answer']);self.assertNotIn('Hồ sơ demo:',r['answer'])
 def test_other_student_isolated(self):
  r=self.ask('Cô nên hỏi gì khi gặp riêng sinh viên này?',self.start(),sid='24000002');self.assertIn('Demo B',r['answer']);self.assertNotIn('lịch ca',r['answer']);self.assertNotIn('Demo A',r['answer'])
 def test_public_question_not_inherited(self):
  t=self.start();r=self.ask('Tóm tắt học phí năm 2025',t);self.assertEqual(r['answer'],'public');self.assertIsNone(r['context_token'])
 def test_fresh_tab_no_leak(self):
  self.assertEqual(self.ask('Trong buổi gặp đó cô nên hỏi gì?')['metadata']['engine_mode'],'CONTEXT_CLARIFICATION')
 def test_context_only_hypothesis_labels(self):
  topics,_=update_topics('Em này không đủ tiền và nhà xa');self.assertEqual(set(topics),{'finance','commute'});topics,_=update_topics('Em ấy không còn nhà xa',topics);self.assertEqual(topics,['finance'])
 def test_model_wrong_voice(self):
  ab={'roster_obj':self.roster,'student_id':'24000001'}
  for q in ['Em có thể hỏi sinh viên về điểm học kỳ thấp không?', 'Em có thể hỏi sinh viên có có tín chỉ nợ không?', 'Em có có khó khăn nào trong quá trình học không?']:
   self.assertIsNone(validated({'questions':[q],'action':'study'},'',ab))
  self.assertTrue(validated({'questions':['Em thấy khó nhất ở bước nào khi tự học ở nhà?'],'action':'study'},'',ab))
 def test_exact_beats_greedy(self):
  credits={f'ABC{i:04d}':n for i,n in enumerate([2,2,2,3,5,6])};deps={c:() for c in credits};table={c:(n,deps[c]) for c,n in credits.items()};rows=[(c,c,n) for c,n in credits.items()]
  stages,excluded=make_plan(rows,table,[],10);self.assertFalse(excluded);self.assertEqual(len(stages),2);self.assertTrue(validate({'rounds':[[r[0] for r in b] for b in stages],'round_count':len(stages)},credits,deps,10))
 def test_exact_keeps_unverified_and_cycles_excluded(self):
  table={'ABC0001':(2,()),'ABC0002':(2,('ABC0001',)),'ABC0003':(2,('ABC0004',)),'ABC0004':(2,('ABC0003',)),'ABC0005':(2,('ABC9999',))};rows=[(c,c,v[0]) for c,v in table.items()];stages,excluded=make_plan(rows,table,[],6)
  self.assertEqual([[x[0] for x in b] for b in stages],[['ABC0001'],['ABC0002']]);self.assertEqual(set(excluded),{'ABC0003','ABC0004','ABC0005'})
 def test_large_safe_fallback(self):
  table={f'ABC{i:04d}':(2,()) for i in range(13)};rows=[(c,c,v[0]) for c,v in table.items()];stages,excluded=make_plan(rows,table,[],6);self.assertFalse(excluded);self.assertEqual(sum(map(len,stages)),13);self.assertTrue(all(sum(x[2] for x in b)<=6 for b in stages))
if __name__=='__main__':unittest.main()
