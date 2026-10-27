#!/usr/bin/env python3
"""Deterministic read-only check of benchmark and independent review annotations.

This tool reports freeze readiness. It can NEVER freeze or approve a benchmark.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

EXPECTED_BENCHMARK_SHA256 = "333404a93e510ca580a19dc149c2f93587782eb6380def40626deaa05e1036e2"
EXPECTED_COUNTS = {"valid": 37, "superseded": 27, "year_specific": 26}

def read_jsonl(path):
    result = []
    for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{num}: {exc}") from exc
    return result

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check(repo, review_dir):
    failures = []
    base = repo / "data/qa_benchmark"
    primary = base / "benchmark.jsonl"
    if not primary.is_file():
        raise ValueError("Primary benchmark missing")
    current = fingerprint(primary)
    if current != EXPECTED_BENCHMARK_SHA256:
        failures.append("PRIMARY_HASH_CHANGED_REQUIRES_NEW_EVIDENCE_AUDIT")
    rows = read_jsonl(primary)
    ids = [r["id"] for r in rows]
    if len(rows) != 90 or len(set(ids)) != 90:
        failures.append("PRIMARY_90_IDS_NOT_UNIQUE")
    by_id = {r["id"]: r for r in rows}
    def logical(r):
        return (r.get("ground_truth_answer",r.get("gold_answer")), r.get("target_year",r.get("as_of_year")),r.get("source_doc_id",r.get("gold_doc_id")))
    for r in rows:
        if (r.get("ground_truth_answer") != r.get("gold_answer")
            or r.get("source_doc_id") != r.get("gold_doc_id")
            or r.get("target_year") != r.get("as_of_year")):
            failures.append("PRIMARY_INTERNAL_ALIAS_CONFLICT")
            break
    split_ids=set()
    for label,n in EXPECTED_COUNTS.items():
        p=base / (label + ".jsonl")
        if not p.is_file():
            failures.append("MISSING_SPLIT_"+label)
            continue
        sub=read_jsonl(p)
        if len(sub)!=n or len({x['id'] for x in sub})!=n:
            failures.append("INVALID_SPLIT_"+label)
        for x in sub:
            if x['id'] not in by_id or logical(x)!=logical(by_id[x['id']]) or any(x.get(k)!=by_id[x['id']].get(k) for k in ('question','category','topic','key_facts','source_sha256','source_clause','outdated_trap_answer')):
                failures.append("SPLIT_CONTENT_DRIFT_"+label)
                break
            split_ids.add(x['id'])
    if split_ids!=set(ids):
        failures.append("SPLIT_ID_COVERAGE_DRIFT")
    candidate_file=review_dir / "correction_review_42.csv"
    temporal_file=review_dir / "benchmark_temporal_registry_90.csv"
    version_file=review_dir / "source_registry_24.csv"
    for p in (candidate_file,temporal_file,version_file):
        if not p.is_file():
            raise ValueError(f"Missing review file {p}")
    corrections=read_csv(candidate_file)
    original_corrections_path=repo/'docs/benchmark_corrections_review_20261027.csv'
    if original_corrections_path.is_file():
        original_corrections={r['id']:r for r in read_csv(original_corrections_path)}
    else:
        original_corrections={}
        failures.append('REPOSITORY_CORRECTION_REVIEW_MISSING')
    temporal=read_csv(temporal_file)
    sources=read_csv(version_file)
    if len(corrections)!=42 or len({r['benchmark_id'] for r in corrections})!=42:
        failures.append("CORRECTION_COUNT_OR_IDS_INVALID")
    for r in corrections:
        id=r['benchmark_id']
        if (id not in by_id or r['primary_gold_answer_sha256']!=hashlib.sha256(by_id[id]['gold_answer'].encode('utf-8')).hexdigest() or r['primary_question_sha256']!=hashlib.sha256(by_id[id]['question'].encode('utf-8')).hexdigest()):
            failures.append("CORRECTION_GOLD_HASH_OR_ID_DRIFT")
        if id not in original_corrections or (id in by_id and (original_corrections[id]['new_question']!=by_id[id]['question'] or original_corrections[id]['corrected_gold']!=by_id[id]['gold_answer'])):
            failures.append('CORRECTION_PROPOSAL_NOT_ALIGNED_WITH_PRIMARY')
        if r['owner_acceptance']!='ACCEPT' or r['reviewer_confirmation']!='CONFIRMED':
            failures.append("42_CORRECTION_OWNER_AND_REVIEW_SIGNOFF_PENDING")
            break
    if len(temporal)!=90 or {r['benchmark_id'] for r in temporal}!=set(ids):
        failures.append("TEMPORAL_REGISTRY_NOT_ALIGNED")
    for r in temporal:
        if (r['benchmark_id'] not in by_id or r['answer_fingerprint']!=hashlib.sha256(by_id[r['benchmark_id']]['gold_answer'].encode('utf-8')).hexdigest() or r['source_sha256'] != by_id[r['benchmark_id']]['source_sha256'] or str(r['target_year'])!=str(by_id[r['benchmark_id']]['target_year'])):
            failures.append("TEMPORAL_REGISTRY_CONTENT_DRIFT")
            break
    for r in temporal:
        if (r['source_version_effectivity_verified']!='YES' or r['fact_owner_approved']!='YES'):
            failures.append("90_SOURCE_EFFECTIVITY_OR_FACT_SIGNOFF_PENDING")
            break
    if len(sources)!=24 or sum(int(r['item_count']) for r in sources)!=90:
        failures.append("SOURCE_REGISTRY_COUNT_INVALID")
    for doc_id in {r['source_doc_id'] for r in rows}:
        match=[x for x in sources if x['doc_id']==doc_id]
        original=[x for x in rows if x['source_doc_id']==doc_id]
        if len(match)!=1 or int(match[0]['item_count'])!=len(original) or match[0]['source_sha256']!=original[0]['source_sha256']:
            failures.append('DOCUMENT_REGISTRY_SOURCE_DRIFT')
            break
    for r in sources:
        if r['item_count']!='0' and (not r['temporal_authentication'].startswith('VERIFIED') or not r['official_source_url']):
            failures.append("SOURCE_REGISTRY_UNVERIFIED")
            break
    # These four source conflicts must be resolved by explicitly modifying and reviewing the canonical benchmark.
    if current == EXPECTED_BENCHMARK_SHA256:
        failures.append("FOUR_RETROSPECTIVE_TUITION_QUESTIONS_UNRESOLVED_IN_PRIMARY")
        failures.append("2026_PLAN_ORIGINAL_PDF_LINEAGE_UNVERIFIED")
    # This gate is read-only: no file mutation and no approval token generation.
    return {'status': 'REVIEW_REQUIRED', 'benchmark_sha256':current,
            'primary_rows':len(rows),'review_corrections':len(corrections),
            'temporal_rows':len(temporal),'source_registry_rows':len(sources),
            'blocking_reasons':sorted(set(failures)),
            'benchmark_frozen':False,'training_authorized':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True,type=Path)
    parser.add_argument('--review-dir',required=True,type=Path)
    args=parser.parse_args()
    try:
        report=check(args.repo,args.review_dir)
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('PRECHECK_ERROR:',str(e),file=sys.stderr)
        return 1
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 2 if report['blocking_reasons'] else 0
if __name__=='__main__':
    sys.exit(main())
