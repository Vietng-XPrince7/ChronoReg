"""Deterministic review packet checks; no GPU or internet required."""
import csv
import hashlib
import json

import pytest

from src.lora.contracts import read_jsonl, write_jsonl
from src.lora.review_packet import generate_packet


def example(tmp_path):
    src = tmp_path/'data/raw/uet/markdown/2025/tuition.md'
    src.parent.mkdir(parents=True)
    quote = '| Chương trình đào tạo chuẩn, Khóa QH-2025 | 2.350.000đ |'
    prose = ('Quy định minh họa của trường trong năm học 2025-2026 chỉ sử dụng '
             'cho phép thử phát hiện thay đổi chứng cứ và nguồn trong module.')
    src.write_text('# Chính sách\n\n' + prose + '\n\n' + quote + '\n', encoding='utf-8')
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    doc_id = 'uet-demo-2025'
    doc = {'doc_id':doc_id, 'relative_path':'2025/tuition.md',
           'review_status':'verified_against_source', 'policy_qa_ready':True,
           'academic_year_verified':'2025-2026', 'content_sha256':sha}
    registry=tmp_path/'data/versioning/documents.jsonl'
    holds=tmp_path/'data/versioning/publication_holds.jsonl'
    write_jsonl(registry,[doc]); write_jsonl(holds,[])
    base={'doc_id':doc_id, 'as_of_year':2025, 'academic_year':'2025-2026',
          'review_status':'draft','source_file':'data/raw/uet/markdown/2025/tuition.md',
          'source_sha256':sha}
    prose_path=tmp_path/'prose.jsonl'
    table_path=tmp_path/'tables.jsonl'
    write_jsonl(prose_path,[dict(base,id='p1', question='Quy định chung về học phí là gì?',
                                answer=prose, evidence_quote=prose)])
    write_jsonl(table_path,[dict(base,id='t1', question='Mức học phí QH-2025 là bao nhiêu?',
                                answer='2.350.000đ', evidence_quote=quote,
                                table_column='Học phí (đồng/tháng)', table_section='Học phí',
                                table_row_label='Khóa QH-2025')])
    out=tmp_path/'packet.csv'
    manifest=tmp_path/'packet.json'
    return src, registry, holds, prose_path, table_path, out, manifest


def run(tmp_path, bench=None):
    _, registry, holds, prose, tables, out, manifest=example(tmp_path)
    r=generate_packet(tmp_path,prose,tables,registry,holds,out,manifest,bench)
    return r,out,manifest


def test_packets_are_pending_and_prioritized(tmp_path):
    r,out,manifest=run(tmp_path)
    assert r['draft_candidates']==2 and r['human_approved']==0
    assert r['years']['2025']==2 and not r['ready_for_training']
    assert r['priorities']=={'P0':0,'P1':1,'P2':1}
    with out.open(encoding='utf-8-sig', newline='') as f:
        rows=list(csv.DictReader(f))
    assert [x['priority'] for x in rows]==['P1','P2']
    assert all(x['human_decision'].startswith('PENDING') for x in rows)
    assert all(len(x['candidate_sha256'])==64 for x in rows)
    assert json.loads(manifest.read_text(encoding='utf-8'))['draft_candidates']==2


def test_sources_remain_unchanged(tmp_path):
    src,registry,holds,prose,tables,out,manifest=example(tmp_path)
    before=[p.read_bytes() for p in (src,registry,holds,prose,tables)]
    generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    assert [p.read_bytes() for p in (src,registry,holds,prose,tables)]==before


def test_existing_packet_not_overwritten(tmp_path):
    src,registry,holds,prose,tables,out,manifest=example(tmp_path)
    out.write_bytes(b'KEEP')
    with pytest.raises(FileExistsError):
        generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    assert out.read_bytes()==b'KEEP' and not manifest.exists()


def test_existing_manifest_prevents_csv_creation(tmp_path):
    src,registry,holds,prose,tables,out,manifest=example(tmp_path)
    manifest.write_text('KEEP',encoding='utf-8')
    with pytest.raises(FileExistsError):
        generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    assert not out.exists() and manifest.read_text()=='KEEP'


def test_mutated_source_refused_before_output(tmp_path):
    src,registry,holds,prose,tables,out,manifest=example(tmp_path)
    src.write_text(src.read_text(encoding='utf-8')+'altered', encoding='utf-8')
    with pytest.raises(ValueError,match='SHA mismatch'):
        generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    assert not out.exists() and not manifest.exists()


def test_publication_hold_blocks(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    row=read_jsonl(registry)[0]
    write_jsonl(holds,[{'doc_id':row['doc_id'],'content_sha256':row['content_sha256'],
                        'reason':'Review needed'}])
    with pytest.raises(ValueError,match='not released'):
        generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    assert not out.exists()


def test_duplicate_ids_fail(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    t=read_jsonl(tables)
    t[0]['id']='p1'
    write_jsonl(tables,t)
    with pytest.raises(ValueError,match='Duplicate candidate IDs'):
        generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)


def test_duplicate_question_is_priority_zero(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    t=read_jsonl(tables)
    t[0]['question']=read_jsonl(prose)[0]['question']
    write_jsonl(tables,t)
    report=generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    assert report['priorities']['P0']==2
    assert report['flags']['DUPLICATE_DRAFT_QUESTION']==2


def test_benchmark_overlap_is_flagged_without_copying_benchmark(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    b=tmp_path/'benchmark.jsonl'
    draft=read_jsonl(tables)[0]
    write_jsonl(b,[{'id':'eval1','question':draft['question'], 'gold_answer':'2.350.000đ',
                    'gold_doc_id':draft['doc_id'],'type':'historical','as_of_year':2025}])
    original=b.read_bytes()
    result=generate_packet(tmp_path,prose,tables,registry,holds,out,manifest,b)
    assert result['flags']['BENCHMARK_EXACT_QUESTION']==1
    assert result['priorities']['P0']==1
    assert result['benchmark_provided'] and not result['benchmark_leakage_clearance']
    assert b.read_bytes()==original
    assert 'gold_answer' not in out.read_text(encoding='utf-8-sig')


def test_csv_formula_escape(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    t=read_jsonl(tables)
    t[0]['table_section']='=HYPERLINK("https://fake.test")'
    write_jsonl(tables,t)
    generate_packet(tmp_path,prose,tables,registry,holds,out,manifest)
    with out.open(encoding='utf-8-sig', newline='') as f:
        rows=list(csv.DictReader(f))
    assert any(x['section'].startswith("'=") for x in rows)


def test_reject_output_alias_and_same_inputs(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    with pytest.raises(ValueError,match='Prose and table'):
        generate_packet(tmp_path,prose,prose,registry,holds,out,manifest)
    with pytest.raises(ValueError,match='Output must not replace'):
        generate_packet(tmp_path,prose,tables,registry,holds,prose,manifest)
    assert not out.exists()


def test_empty_benchmark_is_rejected(tmp_path):
    _,registry,holds,prose,tables,out,manifest=example(tmp_path)
    b=tmp_path/'benchmark.jsonl'; write_jsonl(b,[])
    with pytest.raises(ValueError,match='benchmark is empty'):
        generate_packet(tmp_path,prose,tables,registry,holds,out,manifest,b)
    assert not out.exists()
