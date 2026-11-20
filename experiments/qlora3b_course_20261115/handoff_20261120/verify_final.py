#!/usr/bin/env python3
"""Read-only reproducibility audit for ChronoReg's 2026-11-20 classroom QLoRA results.

Does not verify legal policy effectivity or grant owner/human review approval.
Input: original owner's pre-normalization repository ZIP and real 45-GPU-result ZIP.
"""
import argparse,csv,hashlib,json,re,zipfile,collections
from pathlib import Path

def sha(v): return hashlib.sha256(v).hexdigest()
def jj(v): return json.loads(v.decode('utf-8-sig'))
def lines(v): return [jj(x) for x in v.splitlines() if x.strip()]
def check(ok,msg):
    if not ok: raise AssertionError(msg)

def audit(repo_zip,run_zip,output):
    output.mkdir(parents=True,exist_ok=True)
    zh=hashlib.sha256(repo_zip.read_bytes()).hexdigest();rh=hashlib.sha256(run_zip.read_bytes()).hexdigest()
    expected_repo='fde3fabf8dc1894975f628676b439ee400a72ad46011949d3c38727a07dd3d46'
    expected_run='89c386afa124888469f715098a663b2206ea3fdeab9cc5421ba0389931469938'
    check(zh==expected_repo,'Unexpected historical repository snapshot SHA')
    check(rh==expected_run,'Unexpected GPU results ZIP SHA')
    with zipfile.ZipFile(repo_zip) as z, zipfile.ZipFile(run_zip) as g:
        check(z.testzip() is None and g.testzip() is None, 'Bad ZIP member CRC')
        root='ChronoReg-main/experiments/qlora3b_course_20261115/'
        entry=lambda rel: z.read(root+rel)
        manifest=jj(entry('COURSE_MANIFEST.json'))
        mismatches=[]
        for rel,h in manifest['files_sha256'].items():
            actual=sha(entry(rel))
            if h!=actual:mismatches.append({'file':rel,'recorded':h,'actual':actual})
        known={'file':'reproduction/test_course_runner.py','recorded':'a70241b1bbba140fe9f4ad8db0d97da6a88bfbe313e5f14afc17520ac56079ad','actual':'bc24b30f7fdbaa3344f867b9094af5592f3b82d387d498709d617aab4012715a'}
        check(mismatches == [known],f'Manifest has NEW unexpected difference: {mismatches}')
        train_raw=entry('training/course_train_200.jsonl')
        train=lines(train_raw)
        check(len(train)==200,'Course train count != 200')
        check(sha(train_raw)=='1e7f8dffa8425e6a441f651bb320935bd4e1e32a69933ac5073e85a55d71851e','Train SHA mismatch')
        counts=dict(sorted(collections.Counter(int(r['as_of_year']) for r in train).items()))
        check(counts=={2022:40,2023:37,2024:36,2025:49,2026:38},'Course year counts differ')
        qa_err=[];n_course_code=0
        for r in train:
            f='ChronoReg-main/'+r['source_file']
            raw=z.read(f)
            if sha(raw)!=r['source_sha256_recorded'] or r['evidence_quote'] not in raw.decode('utf-8'):
                qa_err.append({'id':r['id'],'issue':'SOURCE_SHA_OR_QUOTE'})
            if r['independent_review_verified'] is not False or r['effective_year_verified'] is not False:
                qa_err.append({'id':r['id'],'issue':'UNEXPECTED_REVIEW_FLAG'})
            if r['topic']=='curriculum_course_credits':
                n_course_code+=1
                cells=[x.strip() for x in r['evidence_quote'].split('|') if x.strip()]
                a=re.search(r'\b(?:UET\.)?[A-Z]{2,4}\d{4}\b',r['answer'])
                q=re.search(r'\b(?:UET\.)?[A-Z]{2,4}\d{4}\b',r['question'])
                credits=re.search(r'(\d+)\s*tín\s*chỉ\b',r['answer'],re.I)
                if not all((a,q,credits)) or len(cells)<4 or a.group()!=q.group() or cells[1]!=a.group() or cells[3]!=credits.group(1):
                    qa_err.append({'id':r['id'],'issue':'COURSE_CODE_OR_CREDIT_COLUMN'})
        check(n_course_code==64 and not qa_err,f'Train QA source or column errors: {qa_err[:3]}')
        chain=[];prev=None
        for year in range(2022,2027):
            s=jj(entry(f'checkpoints/year-{year}/course_stage.json'))
            w=sha(entry(f'checkpoints/year-{year}/adapter_model.safetensors'))
            check(s['year']==year and s['adapter_sha256']==w,'Checkpoint sha/year wrong')
            check(s['previous_adapter_sha256']==prev,'Checkpoint chain wrong')
            chain.append({'year':year,'rows':s['rows'],'sha256':w,'train_loss':s['loss']})
            prev=w
        check(jj(entry('checkpoints/five_stage_completion.json'))['last_adapter_sha256']==prev,'Completion checkpoint mismatch')
        bench_raw=z.read('ChronoReg-main/data/qa_benchmark/benchmark.jsonl')
        check(sha(bench_raw)=='47497e6bea518c95fa9c3b674fc63ccf022cc625e73da056c3e87bc63a70596f','Benchmark SHA mismatch')
        bench=lines(bench_raw);check(len(bench)==90 and len({b['id'] for b in bench})==90,'Benchmark rows invalid')
        pred_raw=entry('evaluation/predictions.jsonl')
        check(sha(pred_raw)==manifest['files_sha256']['evaluation/predictions.jsonl'],'Prediction SHA mismatch')
        pred=lines(pred_raw);check(len(pred)==450,'Expected 450 baseline predictions')
        byid={b['id']:b for b in bench}
        check(len({(r['checkpoint_year'],r['id']) for r in pred})==450,'Prediction keys duplicate')
        def f1(gold,pred):
            g=collections.Counter(re.findall(r'\w+',gold.lower()))
            p=collections.Counter(re.findall(r'\w+',pred.lower()))
            common=sum((g&p).values());total=sum(g.values())+sum(p.values())
            return round(2*common/total,4) if total else 0.
        f1errs=[];by_year=collections.defaultdict(list)
        for r in pred:
            b=byid[r['id']]
            if r['question']!=b['question'] or r['gold_answer']!=b['gold_answer'] or int(r['as_of_year'])!=int(b['as_of_year']):
                raise AssertionError('Benchmark-question mismatch in 450 eval')
            score=f1(r['gold_answer'],r['prediction'])
            if abs(score-float(r['token_f1_proxy']))>0.00001:f1errs.append(r['id'])
            by_year[int(r['checkpoint_year'])].append(score)
        check(not f1errs,'Stored 450 TokenF1 does not recompute')
        check({y:len(v) for y,v in by_year.items()}=={y:90 for y in range(2022,2027)},'Missing per-year benchmark prediction')
        means={str(y):round(sum(v)/len(v),4) for y,v in sorted(by_year.items())}
        train_q={re.sub(r'\s+',' ',r['question'].strip().lower()) for r in train}
        check(len(train_q.intersection({re.sub(r'\s+',' ',r['question'].strip().lower()) for r in bench}))==0,'Exact benchmark/train question collision')
        source_shas={r['source_sha256_recorded'] for r in train}
        doc_overlap=sum(b['source_sha256'] in source_shas for b in bench)
        check(doc_overlap==49,'Benchmark document overlap changed')
        probe_raw=g.read('PROBE_25_CASES.jsonl');run_manifest=jj(g.read('RETENTION_RUN_MANIFEST.json'))
        probes=lines(probe_raw);out=lines(g.read('RETENTION_45_PREDICTIONS.jsonl'))
        canonical_probe_sha=sha((json.dumps(probes,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
        check(canonical_probe_sha==run_manifest['probe_cases_sha256'],'Canonical probe digest invalid')
        check(len(probes)==25 and len(out)==45,'Retention count changed')
        train_by_id={r['id']:r for r in train}
        probe_by_id={p['id']:p for p in probes}
        for p in probes:
            t=train_by_id[p['id']]
            for k in ('question','answer','source_file','evidence_quote','as_of_year'):
                check(p[k]==t[k],f'Probe differs from train: {p["id"]} {k}')
        keyset={(x['checkpoint_year'],x['id']) for x in out}
        check(len(keyset)==45 and all(x['id'] in probe_by_id for x in out),'Retention keys invalid')
        needed={(int(p['as_of_year']),p['id']) for p in probes}
        needed.update({(2026,p['id']) for p in probes})
        check(keyset==needed,'Retention missing paired checkpoint')
        check({str(x['year']):x['sha256'] for x in chain}==run_manifest['course_adapter_sha256'],'Retention uses wrong checkpoint hashes')
        report={'scope':'COURSE_MODE_EXPERIMENT_NOT_OFFICIAL_POLICY_RELEASE',
        'original_repo_zip_sha256':zh,'retention_zip_sha256':rh,'manifest_entries_verified':len(manifest['files_sha256']),
        'historical_manifest_discrepancy':known,'unexpected_manifest_discrepancies':[],
        'train_qa_rows':len(train),'train_year_distribution':counts,'qa_source_sha_and_quote_pass':len(train),
        'qa_course_code_credit_column_checked':n_course_code,'qa_independent_review_approved_count':0,
        'adapters':chain,'benchmark_rows':len(bench),'benchmark_document_overlap_with_course_train':doc_overlap,
        'benchmark_exact_question_overlap':0,'benchmark_generated_predictions':len(pred),
        'benchmark_token_f1_proxy_by_checkpoint':means,
        'retention_train_cases':len(probes),'retention_model_predictions':len(out),
        'retention_scoring':'Reproduce with analyze_retention.py in prior adjudication package',
        'confidence_note':'Computational reproducibility only. Official source effectivity, semantic leakage, and human approval are not verified.'}
        (output/'VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('PASS',json.dumps({k:report[k] for k in ('manifest_entries_verified','qa_source_sha_and_quote_pass','qa_course_code_credit_column_checked','benchmark_generated_predictions','retention_model_predictions')},ensure_ascii=False))
        return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-zip',type=Path,required=True);p.add_argument('--retention-zip',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.repo_zip,a.retention_zip,a.out)
