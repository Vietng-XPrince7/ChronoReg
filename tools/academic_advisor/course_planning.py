"""Provisional dependency-aware planning from the pinned team CNTT table.
Not approved policy evidence, never an official registration or graduation plan.
Only exact demo program/cohort match; no automatic equivalent-course mapping.
"""
from collections import defaultdict
from pathlib import Path
import hashlib,json,re
from quality import norm,clean
from schedule_optimizer import optimize_rounds, validate

REL='data/raw/uet/curricula/tuan_2022_2026/original/noi_dung_cua_chuong_trinh_dao_tao_cntt_2022_2024.md'
SHA='46f225e304b2eab9da55eae289de37f6853ac1b70d27a4067994f79a92055fec'
DOC='uet-tuan-noi-dung-cua-chuong-trinh-dao-tao-cntt-2022-2024-46f225e3'
CODE=r'[A-Z]{3}\d{4}'

class CandidateTable(dict):
    """Provenance is attached only by a successful source loader."""
    def __init__(self, rows, evidence):
        super().__init__(rows)
        self.evidence = dict(evidence)


def candidate_source(table):
    if isinstance(table, CandidateTable):
        return dict(table.evidence)
    return {'source_path':REL,'sha256':SHA,'source_url':None,'status':'unreviewed'}


def candidate_label(table):
    return ('CTĐT có dòng tín chỉ/tiên quyết đã đối chiếu' if candidate_source(table).get('status')=='reviewed_scoped' else 'CTĐT tham khảo chưa duyệt')


def parse_rows(text):
    candidates=defaultdict(set)
    for line in text.splitlines():
        if not line.startswith('|') or not line.endswith('|'):continue
        cells=[clean(x) for x in line[1:-1].split('|')]
        if len(cells)!=8:continue
        num,code,name,credit,_,_,_,deps=cells
        if not re.fullmatch(r'\d{1,3}',num) or not re.fullmatch(CODE,code) or not re.fullmatch(r'\d{1,2}',credit) or not 1<=int(credit)<=30:continue
        # Reject ambiguous strings instead of extracting arbitrary codes from a damaged row.
        if deps and not re.fullmatch(CODE+r'(?:[ ,;]+'+CODE+r')*',deps):continue
        pres=tuple(sorted(set(re.findall(CODE,deps))))
        if code in pres:continue
        candidates[code].add((int(credit),pres))
    return {code:next(iter(v)) for code,v in candidates.items() if len(v)==1}

def load_candidate(root,roster):
    root=Path(root).resolve()
    if norm(str(roster.get('major','')))!='cong nghe thong tin':return None,'chưa có bảng tiên quyết khớp chính xác ngành demo'
    cohort=re.findall(r'\bQH[- ]?(20\d{2})\b',str(roster.get('cohort','')),re.I)
    if len(set(cohort))!=1 or int(cohort[0]) not in (2022,2023,2024):return None,'chưa có bảng tham khảo khớp khóa tuyển sinh'
    try:
        holds=root/'data/versioning/publication_holds.jsonl';catalog=root/'data/raw/uet/curricula/catalog.json';p=root/REL
        for x in (holds,catalog,p):x.resolve().relative_to(root)
        raw=p.read_bytes();digest=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest();raw_hash=hashlib.sha256(raw).hexdigest()
        if digest!=SHA:return None,'bảng tiên quyết thay đổi, cần rà soát lại'
        records=json.loads(catalog.read_text(encoding='utf-8-sig'))['records']
        matches=[r for r in records if r.get('content_path')==REL]
        if len(matches)!=1 or matches[0].get('doc_id')!=DOC or matches[0].get('content_sha256')!=SHA or matches[0].get('program_identifier')!='cntt':return None,'catalog không khớp bảng tham khảo'
        for line in holds.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():continue
            hold=json.loads(line)
            if hold.get('doc_id')==DOC or hold.get('content_sha256') in (SHA,raw_hash) or hold.get('content_path')==REL or hold.get('source_path')==REL:return None,'bảng tiên quyết đang tạm khóa'
        # The separate review pack contains the official factual columns, including
        # rows damaged in OCR. The archive/catalog/hold checks above remain mandatory.
        from reviewed_sources import PACK,PIN,curriculum_table
        if (root/PACK).is_file():
            try:
                rec,rows=curriculum_table(root,int(cohort[0]))
                return CandidateTable(rows,{'source_path':PACK,'sha256':PIN,'source_url':rec['source_url'],'review_id':rec['id'],'review_scope':rec['review_scope'],'status':'reviewed_scoped'}),None
            except (OSError,ValueError,KeyError,TypeError):return None,'gói đối chiếu CTĐT thay đổi hoặc nguồn đang tạm khóa'
        table=parse_rows(raw.decode('utf-8-sig'))
        if not table:return None,'không đọc được bảng tiên quyết'
        return table,None
    except (OSError,ValueError,KeyError,TypeError):return None,'thiếu bảng tiên quyết hoặc hồ sơ kiểm soát phiên bản'

def make_plan(rows,table,history,cap,*,first_course=None):
    """Each stage assumes all courses in previous stages are passed.
    An unobserved prerequisite is never assumed satisfied. No automatic substitution.
    """
    outcomes=defaultdict(set)
    for g in history:
        code=str(g.get('ma_mon','')).upper();v=g.get('dat')
        if re.fullmatch(CODE,code) and isinstance(v,bool):outcomes[code].add(v)
    completed={c for c,values in outcomes.items() if values=={True}}
    pending={};excluded={}
    for code,name,credit in rows:
        if code in completed:excluded[code]='hồ sơ đã có lần đạt, cần đối chiếu trước khi học lại';continue
        if code not in table:excluded[code]='không có dòng khớp mã trong bảng tham khảo';continue
        if table[code][0]!=credit:excluded[code]='số tín chỉ giữa hồ sơ demo và bảng tham khảo khác nhau';continue
        if credit>cap:excluded[code]='vượt mức tín chỉ giả định';continue
        pending[code]=(code,name,credit)
    # Compute the reachable subset first. A missing external prerequisite or a
    # cycle must never be treated as fulfilled just to optimize the remaining plan.
    reachable=set(completed)
    while True:
        new={c for c in pending if c not in reachable and set(table[c][1])<=reachable}
        if not new:break
        reachable.update(new)
    # Keep the existing public return contract. For small feasible graphs, the
    # exact BFS minimizes rounds; large graphs use the original safe heuristic.
    schedulable={c:row for c,row in pending.items() if c in reachable and c not in completed}
    if first_course is not None and (first_course not in schedulable or len(schedulable)>12):raise ValueError('first-stage constraint not solvable with verified small graph')
    if 0<len(schedulable)<=12 and type(cap) is int and cap>0:
        credits={c:row[2] for c,row in schedulable.items()}
        deps={c:table[c][1] for c in schedulable}
        solution=optimize_rounds(credits,deps,cap,satisfied=completed,first_course=first_course)
        if not validate(solution,credits,deps,cap,completed) or (first_course is not None and first_course not in solution['rounds'][0]):raise RuntimeError('Invalid exact schedule')
        stages=[[pending[c] for c in batch] for batch in solution['rounds']]
        for c in schedulable:pending.pop(c);completed.add(c)
    else:stages=[]
    while pending:
        ready=[c for c in pending if set(table[c][1])<=completed]
        if not ready:break
        # Prioritize courses which unlock other pending courses; stable order.
        ready.sort(key=lambda c:(-sum(c in table[x][1] for x in pending),-pending[c][2],c))
        stage=[];used=0
        for c in ready:
            row=pending[c]
            if used+row[2]<=cap:stage.append(row);used+=row[2]
        if not stage:break
        stages.append(stage)
        for code,_,_ in stage:completed.add(code);pending.pop(code)
    for c in sorted(pending):
        missing=sorted(set(table[c][1])-completed)
        excluded[c]='chưa xác nhận hoàn thành tiên quyết: '+', '.join(missing)
    return stages,excluded

def dependency_lines(rows,table,history,cap):
    stages,excluded=make_plan(rows,table,history,cap)
    lines=[]
    for i,b in enumerate(stages,1):lines.append(f'  Đợt {i}: '+', '.join(r[0] for r in b)+f' — {sum(r[2] for r in b)} tín chỉ.')
    if not stages:lines.append('  Chưa có học phần đủ điều kiện giả định để xếp đợt.')
    if excluded:lines+=['  Chưa xếp (cô cần xác minh):']+[f'  • {c}: {reason}.' for c,reason in sorted(excluded.items())]
    return lines
