"""HTTP source-clause checks (development regression, not a research benchmark)."""
import argparse,json,re
from pathlib import Path
from smoke_live import request
CASES=[
 ('Quy trình rút bớt học phần?',23,['2 tuần','1 tuần','Phòng Đào tạo']),
 ('Xin bảo lưu kết quả học tập như thế nào?',36,['2,0','01 học kỳ','2 tuần']),
 ('Tiêu chí cảnh báo học vụ UET?',44,['1,20','1,40','1,60','1,80','24 tín chỉ','50%','17/02/2023','nhắc nhở']),
 ('Điều kiện học vượt 24 tín chỉ?',21,['2/3','3/2','18 tín chỉ','không thể kết luận']),
 ('Điều kiện tốt nghiệp?',46,['2,00','2,50']),
 ('Điều kiện chuyển ngành?',28,['năm học thứ nhất','2,50']),
 ('Xếp loại học lực?',45,['3,60','3,20','2,50','2,00']),
 ('Quy trình xin bảo lưu kết quả học tập hoặc rút bớt học phần?',23,['Điều 23','Điều 36','2 tuần']),
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--output',type=Path,required=True);a=p.parse_args();h=request(a.url+'/api/health');assert h['all_models_ready'] and h['base_model']=='chronoreg-base:7b' and h['lora_model']=='chronoreg-lora:7b' and not h['peft_v3']['ready'],h
 fail=0;a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('w',encoding='utf-8') as f:
  for q,n,values in CASES:
   try:
    r=request(a.url+'/api/chat',{'question':q});m=r['metadata'];answer=re.sub('<[^>]*>','',r.get('answer',''));ok=m.get('inference_source')=='deterministic_source_clause' and m.get('effective_year')==2022 and len(m.get('sha256') or '')==64 and len(m.get('pdf_sha256') or '')==64 and n in [x['article'] for x in m.get('articles',[])] and all(v in answer for v in values);row={'question':q,'expected':values,'pass':ok,'response':r}
   except Exception as e:ok=False;row={'question':q,'pass':False,'error':str(e)}
   f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();print('PASS' if ok else 'FAIL',q,'\n',row.get('response',{}).get('answer',row.get('error')),flush=True);fail+=not ok
 print(f'REGULATION_PROBE: {len(CASES)-fail}/{len(CASES)} PASS',flush=True)
 if fail:raise SystemExit(1)
if __name__=='__main__':main()
