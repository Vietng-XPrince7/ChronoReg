"""Focused HTTP regression: no model calls expected for supported table queries."""
import argparse,json,re
from pathlib import Path
from smoke_live import request
LONG='Mức học bổng khuyến khích học tập loại xuất sắc của nhóm Đối với lớp chất lượng cao thuộc ngành Công nghệ thông tin; Các khóa từ QH-2021 trở về trước tại UET năm học 2023-2024 là bao nhiêu?'

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    h=request(a.url+'/api/health');assert h['all_models_ready'] and h['base_model']=='chronoreg-base:7b' and h['lora_model']=='chronoreg-lora:7b' and not h['peft_v3']['ready'],h
    cases=[(LONG,'2.070.000'),('Mức học bổng xuất sắc lớp CLC CNTT khóa QH-2021 năm học 2023-2024?','2.070.000'),('Mức học bổng giỏi lớp chất lượng cao ngành Công nghệ thông tin khóa QH-2023 năm học 2023-2024?','3.800.000')]
    failed=0;a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',encoding='utf-8') as f:
        for q,amount in cases:
            try:
                r=request(a.url+'/api/chat',{'question':q,'force_engine':'chrono_rag'});m=r['metadata'];answer=re.sub('<[^>]*>','',r.get('answer','')); ok=(m.get('inference_source')=='deterministic_source_table' and m.get('row_count')==1 and m.get('effective_year')==2023 and len(m.get('sha256') or '')==64 and amount+' đồng/tháng' in answer and not any('Pre-Check' in x for x in r['routing'].get('detected_signals',[])));row={'question':q,'expected':amount,'pass':ok,'response':r}
            except Exception as e:ok=False;row={'question':q,'pass':False,'error':str(e)}
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();print('PASS' if ok else 'FAIL',q,'\n',row.get('response',{}).get('answer',row.get('error')),flush=True);failed+=not ok
    print(f'SCOPE_PROBE: {len(cases)-failed}/{len(cases)} PASS',flush=True)
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
