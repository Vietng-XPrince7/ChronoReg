"""Live product generation checks. Human review still required for semantic completeness."""
import argparse,html,json,re,urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--base',default='http://127.0.0.1:8765');a=p.parse_args()
    def req(path,body=None):
        r=urllib.request.Request(a.base+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json; charset=utf-8'})
        with urllib.request.urlopen(r,timeout=700) as f:return json.load(f)
    status=req('/api/knowledge/status');print('INDEX:',json.dumps(status,ensure_ascii=False),flush=True)
    if status.get('product_version')!='12.0':raise SystemExit('Wrong server version')
    students=req('/api/class-roster').get('students',[])
    if not students:raise SystemExit('Missing roster')
    s=next((x for x in students if x.get('owed_credits',0)>0),students[0]);sid=str(s.get('student_id') or s.get('mssv'))
    def narrative(r):
        m=r.get('metadata',{});return m.get('presentation_mode')=='LORA_ADVISOR_PRIORITY' and m.get('model_name')=='chronoreg-lora:7b' and m.get('advisor_priority',{}).get('selected_by')=='lora' and bool(m.get('advisor_evidence'))
    cases=[('withdrawal',{'question':'Quy trình rút bớt học phần?'},lambda r,t:narrative(r) and all(x in t for x in ['2 tuần','1 tuần','được trả lại học phí','điểm F','18 tín chỉ','khoản 1 Điều 21','Phòng Đào tạo','giấy báo']) and 'Điều 23' in r['metadata']['advisor_evidence']),('student',{'question':'Hãy nhận định tình hình học tập và tư vấn roadmap cá nhân cho sinh viên này. Giảng viên nên làm gì trước?','mssv':sid},lambda r,t:narrative(r) and bool(r['metadata'].get('roadmap')) and sid in t and 'CPA độc lập' in t),('conflict',{'question':'Thông báo hoạt động nghiên cứu khoa học cấp Viện TTNT năm học 2025-2026 có nội dung gì?'},lambda r,t:'15/02/2026' in t and '25/02/2026' in t and bool(r['metadata'].get('advisor_evidence')) and r['metadata'].get('presentation_mode')=='SOURCE_CONFLICT_SUMMARY'),('admissions',{'question':'Điểm chuẩn ngành Khoa học máy tính UET năm 2024?'},lambda r,t:'27,58' in t and r['metadata'].get('engine_mode')=='SOURCE_TABLE')]
    passed=0
    with a.output.open('w',encoding='utf-8') as f:
        for key,body,check in cases:
            try:
                r=req('/api/chat',{**body,'force_engine':'auto'});t=html.unescape(re.sub(r'</?mark>','',r.get('answer','')));ok=bool(check(r,t))
            except Exception as e:r={'error':str(e)};t=str(e);ok=False
            m=r.get('metadata',{});f.write(json.dumps({'probe':key,'pass':ok,'response':r},ensure_ascii=False)+'\n');f.flush();passed+=int(ok);print(('PASS' if ok else 'REVIEW'),key,m.get('presentation_mode'),m.get('model_name'),'attempts:',m.get('narrative_attempts'),'diagnostics:',m.get('narrative_diagnostics'),'\n',t,flush=True)
    print(f'NARRATIVE_PROBE: {passed}/{len(cases)} checks; review actual advice and scope',flush=True)
    return 0 if passed==len(cases) else 1
if __name__=='__main__':raise SystemExit(main())
