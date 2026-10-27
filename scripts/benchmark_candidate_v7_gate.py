#!/usr/bin/env python3
"""Read-only check of V7 benchmark candidate against canonical file and source hashes."""
import argparse
from pathlib import Path
import hashlib
import json
import sys

EXPECTED='333404a93e510ca580a19dc149c2f93587782eb6380def40626deaa05e1036e2'
CHANGE={'BENCH_SUP_008','BENCH_SUP_012','BENCH_SUP_001','BENCH_SUP_002','BENCH_SUP_003','BENCH_SUP_021','BENCH_TEM_001','BENCH_TEM_002','BENCH_TEM_005','BENCH_TEM_006'}

def sha(b):return hashlib.sha256(b).hexdigest()
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def digest(rec):return sha(json.dumps(rec,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
def verify(root):
 review=root/'docs/benchmark_review_v7'
 m=json.loads((review/'MANIFEST.json').read_text(encoding='utf-8'))
 original=root/'data/qa_benchmark/benchmark.jsonl'
 if sha(original.read_bytes())!=EXPECTED:raise ValueError('Canonical SHA mismatch')
 if m['source_primary_sha256']!=EXPECTED or m['status']!='REVIEW_ONLY_NOT_FROZEN_NOT_FOR_MODEL_EVALUATION':
  raise ValueError('Unexpected manifest status or source hash')
 current={r['id']:r for r in rows(original)}
 candidate={r['id']:r for r in rows(review/m['candidate_files']['primary']['file'])}
 if len(candidate)!=90 or len(current)!=90 or candidate.keys()!=current.keys():raise ValueError('Invalid candidate IDs')
 original_hash=m['original_record_sha256_by_id']
 if set(original_hash)!=set(current) or any(original_hash[i]!=digest(r) for i,r in current.items()):
  raise ValueError('Original record fingerprints diverged')
 changed={i for i in candidate if digest(candidate[i])!=digest(current[i])}
 if changed!=CHANGE:raise ValueError('Unexpected candidate changes: '+str(changed.symmetric_difference(CHANGE)))
 for spec in m['candidate_files'].values():
  p=review/spec['file']
  rr=rows(p)
  if sha(p.read_bytes())!=spec['sha256'] or len(rr)!=spec['rows']:raise ValueError('Candidate file changed: '+str(p))
 split_sets=[]
 for k in ['active','superseded','temporal']:
  rr=rows(review/m['candidate_files'][k]['file'])
  split_sets.append({r['id'] for r in rr})
  for r in rr:
   if any(candidate[r['id']].get(key)!=value for key,value in r.items()):raise ValueError('Split/content mismatch')
 if len(set.union(*split_sets))!=90 or any(split_sets[i].intersection(split_sets[j]) for i,j in [(0,1),(1,2),(0,2)]):
  raise ValueError('Split partition error')
 delta=rows(review/'review_only/proposed_delta_10.jsonl')
 if len(delta)!=10 or {r['id'] for r in delta}!=CHANGE or not all(r['decision']=='PENDING_OWNER_REVIEW' for r in delta):
  raise ValueError('Unexpected approval metadata')
 if m['benchmark_frozen'] or m['training_authorized'] or m['owner_approved']:
  raise ValueError('Unsafe release flag')
 return {'status':'REVIEW_REQUIRED','primary_sha256':EXPECTED,'benchmark_rows':90,'changed_ids':sorted(CHANGE),'changed_count':10,'split_counts':[len(s) for s in split_sets], 'owner_approved':False,'benchmark_frozen':False,'training_authorized':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);a=p.parse_args()
 try:r=verify(a.repo.resolve())
 except (OSError,KeyError,TypeError,ValueError,IndexError) as e:
  print('AUDIT_ERROR:',str(e),file=sys.stderr);return 3
 print(json.dumps(r,ensure_ascii=False,indent=2));return 2
if __name__=='__main__':sys.exit(main())
