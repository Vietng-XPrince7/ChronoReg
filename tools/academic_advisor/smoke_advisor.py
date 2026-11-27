"""Live checks against v8 only; no model training, roster regeneration or network scrape."""
import argparse, json, re, html, urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--base',default='http://127.0.0.1:8765');a=p.parse_args()
    def req(path,body=None):
        r=urllib.request.Request(a.base+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json; charset=utf-8'})
        with urllib.request.urlopen(r,timeout=330) as f:return json.load(f)
    status=req('/api/knowledge/status');print('INDEX:',json.dumps(status,ensure_ascii=False),flush=True)
    if status.get('product_version')!='12.0':raise SystemExit('Wrong server version; stop older server')
    roster=req('/api/class-roster');students=roster.get('students',[])
    if not students:raise SystemExit('Roster missing; cannot test scoped advisor')
    target=next((s for s in students if s.get('owed_credits',0)>0),students[0]);sid=str(target.get('student_id') or target.get('mssv'))
    cases=[('admissions',{'question':'Điểm chuẩn ngành Khoa học máy tính UET năm 2024?'},lambda r,t:'27,58' in t and r['metadata']['engine_mode']=='SOURCE_TABLE'),('conflict',{'question':'Thông báo hoạt động nghiên cứu khoa học cấp Viện TTNT năm học 2025-2026 có nội dung gì?'},lambda r,t:'15/02/2026' in t and '25/02/2026' in t and all('2024' not in x['path'] for x in r['metadata'].get('knowledge_sources',[]))),('roadmap',{'question':'Hãy tư vấn và vẽ roadmap học tập cá nhân cho sinh viên này','mssv':sid},lambda r,t:r['metadata']['engine_mode']=='ADVISOR_PLAN' and len(r['metadata']['roadmap'])>=3 and sid in t),('class',{'question':'Liệt kê những em trong lớp mình cần hỗ trợ học vụ và đề xuất lộ trình cho lớp'},lambda r,t:r['metadata']['engine_mode']=='ADVISOR_PLAN' and bool(r['metadata']['roadmap'])),('overload',{'question':'Sinh viên này có được học vượt 24 tín chỉ không?','mssv':sid},lambda r,t:'Không xác nhận được phép' in (t+r['metadata'].get('advisor_evidence','')) and r['metadata']['engine_mode']=='ADVISOR_PLAN'),('curriculum',{'question':'Học phần Vật lý chất rắn EPN2062 ngành Vật lý kỹ thuật QH-2022 có bao nhiêu tín chỉ?'},lambda r,t:bool(re.search(r'\b3\s*tín chỉ',t)) and r['metadata']['engine_mode']=='LORA_KNOWLEDGE_ACCESS')]
    passed=0
    with a.output.open('w',encoding='utf-8') as f:
        for key,body,check in cases:
            try:
                r=req('/api/chat',{**body,'force_engine':'auto'});t=html.unescape(re.sub(r'</?mark>','',r.get('answer','')));ok=bool(check(r,t))
            except Exception as e:r={'error':str(e)};t=str(e);ok=False
            # Output contains demo roster identifiers; retain locally or redact before sharing outside project.
            f.write(json.dumps({'probe':key,'pass':ok,'response':r},ensure_ascii=False)+'\n');f.flush();passed+=int(ok);print(('PASS' if ok else 'FAIL'),key,'\n',t,flush=True)
    print(f'ADVISOR_PROBE: {passed}/{len(cases)} PASS',flush=True)
    return 0 if passed==len(cases) else 1
if __name__=='__main__':raise SystemExit(main())
