"""Small live smoke: year carryover, student carryover, isolation and GPA naming."""
import argparse,json,urllib.request
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--base',default='http://127.0.0.1:8765');a=p.parse_args()
 def call(path,payload=None):
  req=urllib.request.Request(a.base+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=330) as f:return json.load(f)
 status=call('/api/knowledge/status');print('INDEX:',json.dumps(status,ensure_ascii=False),flush=True)
 if status.get('product_version')!='12.0':raise SystemExit('Wrong server version')
 roster=call('/api/class-roster'); students=roster.get('students',[])
 if not students:raise SystemExit('No student roster')
 sid=str(students[0].get('student_id') or students[0].get('mssv'))
 def ask(q,**kw):return call('/api/advisor/chat',{'question':q,'force_engine':'auto',**kw})
 results=[]
 def record(key,r,ok):
  # Do not persist the signed context token in logs.
  results.append({'probe':key,'pass':bool(ok),'response':{k:v for k,v in r.items() if k!='context_token'}});print('PASS' if ok else 'FAIL',key,r.get('context_resolution',{}),flush=True)
 try:
  r=ask('Điểm chuẩn ngành Khoa học máy tính UET năm 2024?');t=r.get('context_token');record('year_seed',r,bool(t) and '27,58' in r.get('answer',''))
  r=ask('Còn năm 2025 thì sao?',context_token=t);record('year_followup',r,r.get('context_resolution',{}).get('kind')=='year_followup' and r.get('metadata',{}).get('effective_year')==2025)
  r=ask('Hãy tư vấn lộ trình học tập cho sinh viên này',mssv=sid);t=r.get('context_token');record('student_seed',r,bool(t) and sid in r.get('answer',''))
  r=ask('Em này cần ưu tiên điều gì trong lộ trình?',context_token=t);record('student_followup',r,r.get('context_resolution',{}).get('kind')=='student_followup' and sid in r.get('answer',''))
  r=ask('Em này cần ưu tiên gì trong lộ trình?');record('independent_tab',r,r.get('metadata',{}).get('engine_mode')=='CONTEXT_CLARIFICATION' and not r.get('context_token'))
  r=ask('Giả sử GPA tích lũy hiện tại 2,50; đã tích lũy 60 tín chỉ; học thêm 15 tín chỉ; GPA kỳ tới 3,50. Tính GPA tích lũy mới.',context_token=t);record('gpa_alias_and_new_scope',r,r.get('metadata',{}).get('simulation',{}).get('projected_cpa')=='2.70' and not r.get('context_token'))
 except Exception as e:results.append({'probe':'runtime','pass':False,'error':str(e)});print('FAIL runtime',e,flush=True)
 with a.output.open('w',encoding='utf8') as f:
  for row in results:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 count=sum(row['pass'] for row in results);print(f'CONVERSATION_PROBE: {count}/6 PASS',flush=True);return int(count!=6 or len(results)!=6)
if __name__=='__main__':raise SystemExit(main())
