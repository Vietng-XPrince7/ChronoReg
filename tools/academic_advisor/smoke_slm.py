"""Live release gate. Real model use is counted separately from deterministic tools."""
import argparse,json,urllib.request,sys,re,html

def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args();base=f'http://127.0.0.1:{a.port}'
 def get(path,data=None):
  req=urllib.request.Request(base+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers={'Content-Type':'application/json; charset=utf-8'});return json.load(urllib.request.urlopen(req,timeout=450))
 status=get('/api/knowledge/status');print('INDEX:',json.dumps(status,ensure_ascii=False),flush=True)
 if status.get('deployment_profile')!='local-slm' or status.get('product_version')!='15.0':raise SystemExit('Expected v15 local-slm, not offline fallback or older server')
 cases=[('graduation',{'question':'tôi bị trượt 1 môn có bị hạ bằng k'},lambda x,m:'5%' in x and 'Giỏi' in x and 'Không nhất thiết' in x),('withdrawal',{'question':'Cô cần hướng dẫn sinh viên rút học phần như thế nào?'},lambda x,m:'2 tuần' in x and '1 tuần' in x),('curriculum',{'question':'Học phần EPN2062 trong chương trình Kỹ thuật vật lý QH-2022 có bao nhiêu tín chỉ?'},lambda x,m:'EPN2062' in x and '3 tín chỉ' in x and m.get('engine_mode')=='SOURCE_COURSE_ROW'),('whatif',{'question':'Giả sử GPA tích lũy hiện tại 2,50; đã tích lũy 60 tín chỉ; học thêm 15 tín chỉ; GPA kỳ tới 3,50. Tính GPA tích lũy mới.'},lambda x,m:'2,70' in x and m.get('engine_mode')=='ADVISOR_SIMULATION')]
 roster=get('/api/class-roster');students=roster.get('students',[])
 if not students:raise SystemExit('Demo roster missing')
 student=next((s for s in students if s.get('owed_credits',0)>0),students[0]);sid=str(student.get('student_id') or student.get('mssv') or '')
 if not sid:raise SystemExit('Demo roster student ID missing')
 cases.append(('student',{'question':'Cô nên hỗ trợ sinh viên này như thế nào? Lập lộ trình học tập cá nhân.','mssv':sid},lambda x,m:m.get('engine_mode')=='ADVISOR_PLAN' and len(m.get('roadmap',[]))>=3 and sid in x))
 cases.append(('general_knowledge',{'question':'Thí sinh dự tuyển thạc sĩ UET đợt 1 năm 2024 cần năng lực tiếng Anh tối thiểu nào?'},lambda x,m:bool(re.search(r'\bbậc\s*3\b',x,re.I)) and m.get('engine_mode')=='SLM_KNOWLEDGE_ACCESS'))
 passed=0;natural=0;priority=0
 for name,q,check in cases:
  r=get('/api/chat',{**q,'force_engine':'auto'});m=r.get('metadata',{});text=html.unescape(re.sub(r'</?mark>','',r.get('answer','')));ok=check(text,m);passed+=ok;src=m.get('inference_source');natural+=src in ('local_slm_advisor','local_slm_knowledge');priority+=src=='local_slm_priority';print('PASS' if ok else 'REVIEW',name,m.get('engine_mode'),src,m.get('model_name'),'presentation:',m.get('presentation_mode'),'diagnostics:',m.get('narrative_diagnostics',[]),m.get('knowledge_diagnostics',[]),flush=True);print(text,flush=True)
 print(f'SLM_PROBE: {passed}/{len(cases)} checks; natural_model_responses={natural}; model_priority_responses={priority}; manual wording review required',flush=True)
 return 0 if passed==len(cases) and natural>=2 else 1
if __name__=='__main__':sys.exit(main())
