#!/usr/bin/env python3
"""Read-only integrity and coverage audit for exactly seven UET curricular programmes.

Verifies bytes/metadata/structure, *not* human source approval or semantic truth.
No third-party dependencies.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from collections import Counter
from pathlib import Path

SLUGS={
 'space-engineering','civil-engineering','industrial-graphic-design',
 'agricultural-technology','biotechnology','artificial-intelligence','data-science'
}
EXPECTED={
 'space-engineering':{'QH-2022-to-2024','QH-2025','QH-2026-plus'},
 'civil-engineering':{'QH-2022-to-2024','QH-2025','QH-2026-plus'},
 'industrial-graphic-design':{'QH-2024','QH-2025-plus'},
 'agricultural-technology':{'QH-2022-to-2024','QH-2025-plus'},
 'biotechnology':{'opening-proposal','QH-2025-plus'},
 'artificial-intelligence':{'QH-2022-to-2024-original','QH-2022-to-2024-updated','QH-2025-plus'},
 'data-science':{'opening-proposal','QH-2025-plus'}
}

def digest(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def frontmatter(md:str)->dict:
 if not md.startswith('---\n'):
  raise ValueError('FRONTMATTER_MISSING')
 end=md.find('\n---\n',4)
 if end<0:raise ValueError('FRONTMATTER_UNCLOSED')
 text=md[4:end]; out={}
 for line in text.splitlines():
  if ': ' not in line:continue
  k,v=line.split(': ',1)
  if k in {'doc_id','program_slug','program_name_vi','edition','degree','source_index_url'}:
   out[k]=json.loads(v) if v.startswith('"') else v
  if k in {'cohort_from','cohort_to','reported_total_credits'}:
   out[k]=None if v=='null' else int(v)
  if k=='retrieval_eligible':out[k]=(v=='true')
  if k=='source_pages':out[k]=json.loads(v)
 return out

def audit(root:Path, expect_clean:bool=False)->dict:
 root=Path(root)
 base=root/'data/raw/uet/curricula';mdroot=root/'data/raw/uet/markdown/curricula'
 manifest=load(base/'manifest.json'); checks=load(base/'source_checksums.json')
 errors=[];warnings=[];rows=[]
 filtered=[r for r in manifest['records'] if r['program_slug'] in SLUGS]
 if len(filtered)!=17:errors.append(['COUNT_17_EXPECTED',len(filtered)])
 if len({r['doc_id'] for r in filtered})!=len(filtered):errors.append(['DUPLICATE_DOC_ID'])
 for slug,wanted in EXPECTED.items():
  found={r['edition_label'] for r in filtered if r['program_slug']==slug}
  if found!=wanted:errors.append(['EDITION_COVERAGE_MISMATCH',slug,sorted(found),sorted(wanted)])
 for r in filtered:
  key=r['doc_id'];mdfile=mdroot/(key+'.md');cardfile=mdroot/'source_cards'/(key+'.md');item={'doc_id':key,'program':r['program_slug'],'edition':r['edition_label']}
  if not mdfile.is_file() or not cardfile.is_file():
   errors.append(['MD_OR_SOURCE_CARD_MISSING',key]);rows.append(item);continue
  raw=mdfile.read_bytes();s=raw.decode('utf-8');card=cardfile.read_text(encoding='utf-8')
  item['sha256']=digest(raw);item['bytes']=len(raw)
  entry=checks.get(key)
  if not entry or entry.get('sha256_markdown')!=item['sha256']:
   errors.append(['MD_CHECKSUM_MISMATCH',key])
  try:fm=frontmatter(s)
  except Exception as e:errors.append(['INVALID_FRONTMATTER',key,str(e)]);fm={}
  for left,right in [('doc_id','doc_id'),('program_slug','program_slug'),('edition','edition_label'),('program_name_vi','program_name_vi'),('cohort_from','cohort_from'),('cohort_to','cohort_to'),('degree','degree'),('reported_total_credits','reported_total_credits'),('source_index_url','source_index_url'),('retrieval_eligible','retrieval_eligible'),('source_pages','source_pages')]:
   if fm.get(left)!=r.get(right):errors.append(['FRONTMATTER_MANIFEST_MISMATCH',key,left])
  if r['retrieval_eligible'] is not False:errors.append(['UNAPPROVED_RETRIEVAL_ENABLED',key])
  if '## Nội dung chương trình đào tạo' not in s:errors.append(['CONTENT_SECTION_MISSING',key])
  if len(re.findall(r'^\|.+\|$',s,flags=re.M))<50:errors.append(['INSUFFICIENT_TABLE_ROWS',key])
  if r['edition_label'] not in card or f'../{key}.md' not in card:
   if expect_clean:errors.append(['CARD_DOES_NOT_LINK_MD',key])
  if expect_clean and ('chưa trích xuất toàn bộ bảng học phần' in card or 'để trích xuất học phần' in card):
   errors.append(['STALE_SOURCE_CARD_STATUS',key])
  if expect_clean and r['review_status']!='metadata_reviewed; course_table_extracted; human_review_pending':
   errors.append(['STALE_EXTRACTION_STATUS',key])
  if any(t in s for t in ('### Bài viết liên quan','Bài trước','Bài tiếp theo')):
   if expect_clean:errors.append(['WEB_CHROME_IN_MD',key])
   else:warnings.append(['WEB_CHROME_IN_MD',key])
  body=s.split('## Nội dung chương trình đào tạo',1)[-1]
  if str(r['reported_total_credits']) not in body:
   warnings.append(['TOTAL_CREDITS_NOT_LOCATED_IN_BODY',key])
  if r['curriculum_status']=='opening_proposal' and (r['cohort_from'] is not None or r['cohort_to'] is not None):
   errors.append(['PROPOSAL_INCORRECTLY_ASSIGNED_TO_COHORT',key])
  item['md_sha_match']=bool(entry and entry.get('sha256_markdown')==item['sha256'])
  item['retrieval_eligible']=r['retrieval_eligible'];rows.append(item)
 if sum(r['curriculum_status']=='curriculum' for r in filtered)!=15:errors.append(['EXPECTED_15_CURRICULA'])
 if sum(r['curriculum_status']=='opening_proposal' for r in filtered)!=2:errors.append(['EXPECTED_2_PROPOSALS'])
 # Unrelated programmes must not be changed; apply_data.py separately checks source bytes.
 return {
  'status':'PASS_SOURCE_BYTES_AND_STRUCTURE_NOT_HUMAN_APPROVAL' if not errors else 'BLOCKED',
  'seven_programs':len({r['program_slug'] for r in filtered}),
  'source_records':len(filtered),'curriculum_versions':sum(r['curriculum_status']=='curriculum' for r in filtered),
  'opening_proposals':sum(r['curriculum_status']=='opening_proposal' for r in filtered),
  'source_sha_match':sum(x.get('md_sha_match',False) for x in rows),
  'retrieval_eligible_count':sum(bool(r['retrieval_eligible']) for r in filtered),
  'errors':errors,'warnings':warnings,
  'external_content_review':'PENDING: checksum only proves local bytes; site text and effectivity require human review',
  'rows':rows,
 }

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path('.'));p.add_argument('--expect-clean',action='store_true');p.add_argument('--out',type=Path);a=p.parse_args()
 x=audit(a.repo,a.expect_clean)
 if a.out:
  a.out.parent.mkdir(parents=True,exist_ok=True)
  a.out.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in x.items() if k!='rows'},indent=2,ensure_ascii=False))
 sys.exit(0 if not x['errors'] else 2)
