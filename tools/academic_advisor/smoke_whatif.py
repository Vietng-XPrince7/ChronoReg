"""Quick live check; no model inference needed for supported hypothetical calculations."""
import argparse,json,urllib.request
from pathlib import Path
from decimal import Decimal
from whatif import EXAMPLE,GOAL_EXAMPLE

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--base',default='http://127.0.0.1:8765');a=p.parse_args()
    def request(path,body=None):
        req=urllib.request.Request(a.base+path,data=json.dumps(body,ensure_ascii=False).encode('utf8') if body is not None else None,headers={'Content-Type':'application/json; charset=utf-8'})
        with urllib.request.urlopen(req,timeout=60) as f:return json.load(f)
    status=request('/api/knowledge/status');print('INDEX:',json.dumps(status,ensure_ascii=False));
    if status.get('product_version')!='12.0':raise SystemExit('Wrong server version')
    cases=[('projection',EXAMPLE,lambda r:Decimal(r['projected_cpa'])==Decimal('2.70')),('goal',GOAL_EXAMPLE,lambda r:Decimal(r['required_gpa'])==4),('unreachable',GOAL_EXAMPLE.replace('2,80','3,20'),lambda r:Decimal(r['required_gpa'])>4 and 'vượt thang 4' in r['answer']),('missing','Mô phỏng CPA nếu GPA hiện tại 2,5 và học thêm 15 tín chỉ',lambda r:r['status']=='needs_inputs')]
    passed=0
    with a.output.open('w',encoding='utf8') as f:
        for key,q,check in cases:
            try:
                r=request('/api/chat',{'question':q,'force_engine':'auto'});m=r.get('metadata',{});ok=m.get('engine_mode')=='ADVISOR_SIMULATION' and m.get('inference_source')=='deterministic_calculator' and bool(check(m['simulation']))
            except Exception as e:r={'error':str(e)};ok=False
            passed+=int(ok);print(('PASS' if ok else 'FAIL'),key,'\n',r.get('answer',r),flush=True);f.write(json.dumps({'probe':key,'pass':ok,'response':r},ensure_ascii=False)+'\n');f.flush()
    print(f'WHATIF_PROBE: {passed}/{len(cases)} PASS');return int(passed!=len(cases))
if __name__=='__main__':raise SystemExit(main())
