#!/usr/bin/env python3
"""Read-only evidence and temporal eligibility gate for V8 candidate (never freezes)."""
import argparse,hashlib,json,sys
from pathlib import Path

ORIGINAL_SHA='333404a93e510ca580a19dc149c2f93587782eb6380def40626deaa05e1036e2'
RETRO={'BENCH_SUP_001':2025,'BENCH_SUP_002':2025,'BENCH_SUP_003':2025,
       'BENCH_SUP_004':2025,'BENCH_SUP_011':2025,'BENCH_SUP_021':2024}
V7_TEN={'BENCH_SUP_008','BENCH_SUP_012','BENCH_SUP_001','BENCH_SUP_002',
        'BENCH_SUP_003','BENCH_SUP_021','BENCH_TEM_001','BENCH_TEM_002',
        'BENCH_TEM_005','BENCH_TEM_006'}
CHANGES=V7_TEN|set(RETRO)
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def digest(r):return sha(json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8'))

def inspect(repo):
 repo=Path(repo)
 review=repo/'docs/benchmark_review_v8'
 manifest=json.loads((review/'MANIFEST.json').read_text(encoding='utf-8'))
 original_file=repo/'data/qa_benchmark/benchmark.jsonl'
 if sha(original_file.read_bytes())!=ORIGINAL_SHA or manifest['source_primary_sha256']!=ORIGINAL_SHA:
  raise ValueError('Primary benchmark changed; do not apply review candidate')
 if manifest['status']!='REVIEW_ONLY_PENDING_OWNER_REVIEW' or any(manifest[k] for k in ('owner_approved','benchmark_frozen','training_authorized')):
  raise ValueError('V8 is review-only; approval and release flags are forbidden')
 v7_file=repo/'docs/benchmark_review_v7/review_only/benchmark_candidate_90_NOT_FROZEN.jsonl'
 if sha(v7_file.read_bytes())!=manifest['source_v7_candidate_sha256']:
  raise ValueError('V7 parent candidate mismatch')
 original=read(original_file);candidate=read(review/'review_only/benchmark_candidate_90_NOT_FROZEN.jsonl')
 if len(original)!=90 or len(candidate)!=90 or [x['id'] for x in original]!=[x['id'] for x in candidate]:
  raise ValueError('Benchmark size, ordering or IDs changed')
 original_by={x['id']:x for x in original}
 if {x['id'] for x in candidate if digest(x)!=digest(original_by[x['id']])}!=CHANGES:
  raise ValueError('Unexpected benchmark candidate delta')
 for filename,spec in manifest['artifacts'].items():
  blob=(review/filename).read_bytes()
  if sha(blob)!=spec['sha256'] or len(read(review/filename))!=spec['rows']:
   raise ValueError('Artifact fingerprint/length mismatch: '+filename)
 v8_by={r['id']:r for r in candidate}
 for label,file,category,n in (
   ('active','valid_candidate_37_NOT_FROZEN.jsonl','active_rule',37),
   ('superseded','superseded_candidate_27_NOT_FROZEN.jsonl','superseded_rule',27),
   ('temporal','year_specific_candidate_26_NOT_FROZEN.jsonl','temporal_specific',26)):
  subset=read(review/'review_only'/file)
  if len(subset)!=n or {r['id'] for r in subset}!={r['id'] for r in candidate if r['category']==category}:
   raise ValueError(label+' split ID mismatch')
  if any(any(v8_by[r['id']].get(k)!=v for k,v in r.items()) for r in subset):
   raise ValueError(label+' split payload mismatch')
 for r in candidate:
  if r['id'] in RETRO:
   if (r['as_of_year']!=2026 or r['target_year']!=2026
       or r.get('retrospective_subject_year')!=RETRO[r['id']]
       or not r['question'].startswith('Nhìn lại từ năm 2026, ')):
    raise ValueError('Temporal fix missing for '+r['id'])
   if r['as_of_year']<=RETRO[r['id']]:raise ValueError('Future hindsight at historical checkpoint')
  else:
   v7=[x for x in read(v7_file) if x['id']==r['id']][0]
   if r['id']=='BENCH_SUP_012':
    old=dict(r);old.pop('supporting_sources',None)
    if old!=v7 or len(r.get('supporting_sources',[]))!=1:
     raise ValueError('Foreign tuition supporting-source update invalid')
   elif r!=v7:
    raise ValueError('Non-approved V7 difference at '+r['id'])
 delta=read(review/'review_only/proposed_delta_12_NOT_APPLIED.jsonl')
 if len(delta)!=12 or {r['id'] for r in delta}!=CHANGES or any(r['review_status']!='PENDING_OWNER_REVIEW' for r in delta):
  raise ValueError('All proposed corrections must remain pending')
 return {'status':'REVIEW_REQUIRED','rows':90,'changed_ids':len(CHANGES),
         'temporal_causality_fixed_in_preview':len(RETRO),
         'subject_years_preserved':True,'as_of_year_checkpoint_convention_pending_team_confirmation':True,
         'benchmark_frozen':False,'training_authorized':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True);a=p.parse_args()
 try:r=inspect(a.repo)
 except (OSError,ValueError,TypeError,KeyError,IndexError) as e:
  print('AUDIT_ERROR:',str(e),file=sys.stderr);return 3
 print(json.dumps(r,indent=2,ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
