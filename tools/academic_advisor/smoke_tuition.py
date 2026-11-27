"""HTTP regression against the pinned source-table overlay; no LLM needed."""
import argparse,json,re
from pathlib import Path
from smoke_live import request
CASES=[
 ('Mức học phí CTĐT chuẩn khóa QH-2023 năm học 2026-2027?',2026,['3.600.000','974.000','đồng/tháng','đồng/tín chỉ']),
 ('Mức học phí CTĐT chuẩn khóa QH-2024 năm học 2024-2025?',2024,['32.000.000','869.000','đồng/1 năm học']),
 ('Mức học phí CTĐT chuẩn khóa QH-2022 ngành Công nghệ Nông nghiệp năm học 2025-2026?',2025,['2.000.000','545.000','816.000']),
 ('Mức học phí CLC theo Thông tư 23 khóa QH-2022 năm học 2024-2025?',2024,['35.000.000','800.000']),
 ('Mức học phí CTĐT theo ĐMKTKT khóa QH-2024 năm học 2026-2027?',2026,['4.400.000','1.188.000']),
 ('Mức học phí thạc sĩ khóa QH-2024 năm học 2026-2027?',2026,['3.700.000','1.221.000']),
 ('Mức học phí thạc sĩ khóa QH-2025 năm học 2025-2026?',2025,['248/QĐ-ĐHCN','1.144.000']),
 ('Mức học bổng xuất sắc lớp CLC CNTT khóa QH-2021 năm học 2023-2024?',2023,['2.070.000 đồng/tháng'])]
def main():
 p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--output',type=Path,required=True);a=p.parse_args();h=request(a.url+'/api/health');assert h['all_models_ready'] and h['base_model']=='chronoreg-base:7b' and h['lora_model']=='chronoreg-lora:7b' and not h['peft_v3']['ready'],h
 fail=0;a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('w',encoding='utf-8') as f:
  for q,y,values in CASES:
   try:
    r=request(a.url+'/api/chat',{'question':q,'force_engine':'chrono_rag'});m=r['metadata'];answer=re.sub('<[^>]*>','',r.get('answer',''));ok=m.get('inference_source')=='deterministic_source_table' and m.get('effective_year')==y and len(m.get('sha256') or '')==64 and all(v in answer for v in values);row={'question':q,'expected':values,'pass':ok,'response':r}
   except Exception as e:ok=False;row={'question':q,'pass':False,'error':str(e)}
   f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();print('PASS' if ok else 'FAIL',q,'\n',row.get('response',{}).get('answer',row.get('error')),flush=True);fail+=not ok
 print(f'TUITION_PROBE: {len(CASES)-fail}/{len(CASES)} PASS',flush=True)
 if fail:raise SystemExit(1)
if __name__=='__main__':main()
