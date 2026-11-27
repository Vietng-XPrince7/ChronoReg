"""Live workflow checks against the loaded demo; avoid printing student identifiers."""
import argparse,json,urllib.request,sys,html,re
from pathlib import Path
from course_planning import load_candidate,REL
from workflow import debt_rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args();base=f'http://127.0.0.1:{a.port}'
 def call(path,body=None):
  req=urllib.request.Request(base+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json; charset=utf-8'});return json.load(urllib.request.urlopen(req,timeout=450))
 roster=call('/api/class-roster');students=roster.get('students',[]);st=next((s for s in students if s.get('owed_credits',0)>0),None)
 if not st:raise SystemExit('Demo roster with owed credits required')
 sid=str(st.get('student_id') or st.get('mssv') or '')
 if not sid:raise SystemExit('Missing student id')
 cases=[('class_and_draft',{'question':'Lớp cô có em nào cần gặp riêng? Soạn thông báo cho lớp.'},lambda t,m: m.get('engine_mode')=='ADVISOR_WORKFLOW' and set(['screening','communication_draft'])<=set(m.get('workflow_tools',[])) and 'Dự thảo thông báo chung' in t and not any(str(s.get('student_id') or s.get('mssv') or '---') in t.split('Dự thảo thông báo chung',1)[1] for s in students)),('student_scenarios',{'question':'So sánh phương án học lại và soạn tin nhắn riêng cho em này','mssv':sid},lambda t,m: m.get('engine_mode')=='ADVISOR_WORKFLOW' and set(['credit_scenarios','communication_draft'])<=set(m.get('workflow_tools',[])) and 'tối đa 6 tín chỉ' in t and 'tối đa 12 tín chỉ' in t and sid in t and 'không tự gửi' in t),('custom_budget',{'question':'Lập phương án học lại tối đa 4 tín chỉ môn nợ','mssv':sid},lambda t,m: m.get('engine_mode')=='ADVISOR_WORKFLOW' and 'tối đa 4 tín chỉ' in t and 'tối đa 12 tín chỉ' not in t),('wrong_class',{'question':'Lớp K65 cần gặp riêng ai?'},lambda t,m: m.get('engine_mode')=='ADVISOR_WORKFLOW' and m.get('workflow_tools')==['scope_check'] and sid not in t)]
 # Verify actual prerequisite order on an applicable demo record, not just the tool label.
 root=Path(__file__).resolve().parents[2]
 table,reason=load_candidate(root,roster)
 if table is None:raise SystemExit('Prerequisite smoke requires scoped demo table: '+str(reason))
 pair=next((s for s in students if {'INT1008','INT2210'}<={r[0] for r in debt_rows(s,roster.get('courses') or [])[0]}),None)
 if pair is None:raise SystemExit('Prerequisite smoke needs a demo record with both INT1008 and INT2210 unresolved')
 pair_id=str(pair.get('student_id') or pair.get('mssv') or '')
 def check_dependency(t,m):
  if 'prerequisite_planning' not in m.get('workflow_tools',[]) or not any(x.get('source_path')==REL for x in m.get('advisor_sources',[])):return False
  # Explicitly ask for a single 12-credit scenario. No co-enrollment of a prerequisite and its dependent.
  stages=re.findall(r'Đợt (\d+): ([A-Z0-9, ]+) — (\d+) tín chỉ',t)
  order={};completed={str(g.get('ma_mon')) for g in pair.get('bang_diem',[]) if g.get('dat') is True}-{str(g.get('ma_mon')) for g in pair.get('bang_diem',[]) if g.get('dat') is False}
  for i,codes,credit in stages:
   cs=[c.strip() for c in codes.split(',')]
   if len(set(cs))!=len(cs) or any(c not in table or c in order or not set(table[c][1])<=completed for c in cs):return False
   if int(credit)!=sum(table[c][0] for c in cs) or int(credit)>12:return False
   order.update({c:int(i) for c in cs});completed.update(cs)
  return 'INT1008' in order and 'INT2210' in order and order['INT1008']<order['INT2210'] and 'bảng chưa duyệt' in t
 cases.append(('prerequisite_order',{'question':'Lập phương án học lại tối đa 12 tín chỉ môn nợ','mssv':pair_id},check_dependency))
 def report_check(t,m,personal=False):
  rep=m.get('advisor_report') or {};report=rep.get('text','');actions=rep.get('actions') or []
  if rep.get('draft') is not True or 'advisor_report' not in m.get('workflow_tools',[]) or not actions:return False
  if any(not all(x.get(k) for k in ('owner','action','completion_check','checkpoint')) for x in actions):return False
  if personal:return rep.get('scope')=='individual_private' and sid in report and not any(str(s.get('student_id') or s.get('mssv') or '---') in report for s in students if str(s.get('student_id') or s.get('mssv'))!=sid)
  return rep.get('scope')=='class_aggregate' and not any(str(s.get('student_id') or s.get('mssv') or '---') in report for s in students)
 cases.extend([('class_report',{'question':'Lập báo cáo tư vấn cho lớp cô và kế hoạch hành động'},report_check),('student_report',{'question':'Lập phiếu tư vấn cho em này và kế hoạch hành động','mssv':sid},lambda t,m:report_check(t,m,True))])
 passed=0
 for name,body,check in cases:
  r=call('/api/chat',{**body,'force_engine':'auto'});m=r.get('metadata') or {};t=html.unescape(re.sub(r'</?mark>','',r.get('answer','')));ok=bool(check(t,m));passed+=ok;print('PASS' if ok else 'REVIEW',name,m.get('engine_mode'),m.get('workflow_tools'),flush=True)
 print(f'WORKFLOW_PROBE: {passed}/{len(cases)} checks');return 0 if passed==len(cases) else 1
if __name__=='__main__':sys.exit(main())
