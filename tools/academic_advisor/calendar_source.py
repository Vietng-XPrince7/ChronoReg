"""Conservative source retrieval for semester start. No date inference from file names."""
import re, json, hashlib
from datetime import date
from pathlib import Path
from quality import norm,clean
from knowledge import Index

SEM={'main_1':r'\b(?:hoc )?ky(?: chinh)? (?:1|i|thu nhat)\b','main_2':r'\b(?:hoc )?ky(?: chinh)? (?:2|ii|thu hai)\b','summer':r'\b(?:hoc )?ky (?:phu|he)\b'}
DATE=re.compile(r'(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?!\d)')
TOPIC=re.compile(r'\b(?:ke hoach (?:hoc tap|dao tao|nam hoc)|lich (?:hoc tap|dao tao|nam hoc))\b')

PACK_MANIFEST_SHA = '4c5d43cc133b0d079651f8c5ba5ca8507db64c0a922df4b9572951178d697288'
PACK_DIR = 'data/advisor_sources/calendar'

# Narrow evidence review, NOT a release of the original held documents.
# Exact quality-hold records observed on GitHub main (blob 72ca25983f96526a04fd300996c2ad3b43ce4668).
# Only the six semester intervals, visually checked on pages 1–2 of the pinned
# operator-supplied PDFs, qualify. The original Markdown, all weekly rows,
# and other uses remain held. Changed/unknown holds are never overridden.
INTERVAL_REVIEW = {
    'uet-2024-ke-hoach-hoc-tap-2024-ad259a29a6': {
        'period':'2024-2025',
        'hold': {
            'doc_id':'uet-2024-ke-hoach-hoc-tap-2024-ad259a29a6',
            'content_sha256':'5bf42a976f874c31e242f888042816d43b8ccb8a868c56176db4e7a99199332a',
            'evidence_reference':'https://uet.edu.vn/wp-content/uploads/2024/08/K%E1%BA%BF-ho%E1%BA%A1ch-h%E1%BB%8Dc-t%E1%BA%ADp-n%C4%83m-h%E1%BB%8Dc-2024-2025.pdf',
            'reason':'quality_hold: Official 2024-2025 schedule, header columns are malformed in extracted Markdown'},
        'intervals':{'main_1':('2024-09-04','2025-01-19'),'main_2':('2025-02-03','2025-07-06'),'summer':('2025-07-07','2025-08-31')}},
    'uet-2025-ke-hoach-hoc-tap-2025-1372cdf5f4': {
        'period':'2025-2026',
        'hold': {
            'doc_id':'uet-2025-ke-hoach-hoc-tap-2025-1372cdf5f4',
            'content_sha256':'f5633676482f4f547bad5faee2b3faabb5a24601c31f013e5990aadb9941c5b1',
            'evidence_reference':'https://fet.uet.vnu.edu.vn/wp-content/uploads/2025/08/Ke-hoach-hoc-tap-2025-2026-2.pdf',
            'reason':'quality_hold: Official PDF verified, extracted cells shifted in initial weeks'},
        'intervals':{'main_1':('2025-09-03','2026-02-08'),'main_2':('2026-02-23','2026-07-05'),'summer':('2026-07-06','2026-08-31')}}
}


REVIEW_2022 = {'period': '2022-2023', 'hold': {'doc_id': 'uet-2022-ke-hoach-hoc-tap-2022-7f683bf6cb', 'content_sha256': 'ab398b7e6b150da001d8d97b683658ce8127598676004dd0594a9101cdf103f8', 'evidence_reference': 'https://uet.vnu.edu.vn/wp-content/uploads/2022/07/K%E1%BA%BF-ho%E1%BA%A1ch-h%E1%BB%8Dc-t%E1%BA%ADp-n%C4%83m-h%E1%BB%8Dc-2022_2023.pdf', 'reason': 'quality_hold: Calendar PDF verified, multi-column extraction requires table QA'}, 'intervals': {'main_1': ('2022-08-22', '2023-01-15'), 'main_2': ('2023-01-30', '2023-07-02'), 'summer': ('2023-07-03', '2023-08-27')}}
PACK_2022_SHA = '686a4ae950fa7535c171c5b4b252ee25bc844136efb100c3e0dfee2b749fd48c'


def inspect_uploaded_calendar(root,period,semester):
    """Return a reason for every failed evidence gate. Never bypass holds or hash checks."""
    root=Path(root).resolve(); base=root/('data/advisor_sources/calendar_2022' if period=='2022-2023' else PACK_DIR); manifest=base/'manifest.json'
    pin=PACK_2022_SHA if period=='2022-2023' else PACK_MANIFEST_SHA
    reviews={**INTERVAL_REVIEW,REVIEW_2022['hold']['doc_id']:REVIEW_2022} if period=='2022-2023' else INTERVAL_REVIEW
    hold=root/'data/versioning/publication_holds.jsonl'
    def result(code,**kw):return {'status':code,'period':period,'semester':semester,'hits':[],**kw}
    if semester not in SEM:return result('INVALID_SEMESTER')
    if not manifest.is_file():return result('PACK_MANIFEST_MISSING',expected_path=PACK_DIR+'/manifest.json')
    if not hold.is_file():return result('HOLD_LEDGER_MISSING')
    try:
        raw=manifest.read_bytes(); actual=hashlib.sha256(raw).hexdigest()
        if actual!=pin:return result('MANIFEST_HASH_MISMATCH',actual_sha256=actual,expected_sha256=pin)
        record=next((v for v in json.loads(raw)['sources'] if v['period']==period),None)
        if not record:return result('PERIOD_NOT_IN_PACK')
        pdf=base/record['pdf']; md=base/record['markdown']
        if any(p.resolve()!=p for p in (manifest,pdf,md)):return result('UNEXPECTED_RESOLVED_PATH')
        for p in (pdf,md):
            if not p.is_file():return result('PACK_FILE_MISSING',expected_path=p.relative_to(root).as_posix())
        pdf_sha=hashlib.sha256(pdf.read_bytes()).hexdigest(); md_raw=md.read_bytes(); sha=hashlib.sha256(md_raw).hexdigest()
        if pdf_sha!=record['pdf_sha256']:return result('PDF_HASH_MISMATCH',actual_sha256=pdf_sha,expected_sha256=record['pdf_sha256'])
        if sha!=record['markdown_sha256']:return result('MARKDOWN_HASH_MISMATCH',actual_sha256=sha,expected_sha256=record['markdown_sha256'])
        try:holds=[json.loads(x) for x in hold.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
        except (OSError,ValueError):return result('HOLD_LEDGER_UNREADABLE')
        rel=md.relative_to(root).as_posix(); pdfrel=pdf.relative_to(root).as_posix()
        retained=[]
        for h in holds:
            if not isinstance(h,dict):return result('HOLD_LEDGER_INVALID_RECORD')
            ident=norm(str(h.get('doc_id',''))+' '+str(h.get('source_path',''))+' '+str(h.get('content_path','')))
            if h.get('content_sha256') in (pdf_sha,sha) or h.get('doc_id')==record['doc_id'] or rel in (h.get('source_path'),h.get('content_path')) or pdfrel in (h.get('source_path'),h.get('content_path')):
                return result('EXACT_PUBLICATION_HOLD',hold_doc_id=h.get('doc_id'))
            if re.search(r'\b(?:ke hoach hoc tap|calendar|lich hoc tap)\b',ident) and any(y in ident for y in period.split('-')):
                reviewed=reviews.get(h.get('doc_id'))
                # The old extraction defect is independent of the new, separately
                # pinned interval-only evidence. Do not ignore exact holds, changed
                # reasons/hashes, or other related records.
                if reviewed and h==reviewed['hold'] and record.get('review_scope')=='semester_interval_only':
                    if reviewed['period']==period:retained.append(h['doc_id'])
                    continue
                return result('POSSIBLE_RELATED_PUBLICATION_HOLD',hold_doc_id=h.get('doc_id'),hold_source_path=h.get('source_path') or h.get('content_path'))
        text=md_raw.decode('utf-8').split('## Bản trích xuất toàn văn')[0]
        matches=[]
        for line in text.splitlines():
            if not re.match(SEM[semester],norm(line)):continue
            dates=list(DATE.finditer(line))
            if len(dates)!=2:continue
            start,end=[date(int(m[3]),int(m[2]),int(m[1])) for m in dates]
            if not start<end or not all(str(d.year) in period.split('-') for d in (start,end)):continue
            reviewed=next((v for v in reviews.values() if v['period']==period),None)
            if not reviewed or (start.isoformat(),end.isoformat())!=reviewed['intervals'][semester]:
                return result('INTERVAL_REVIEW_MISMATCH')
            matches.append({'date':start.isoformat(),'excerpt':line.strip()+' (khoảng thời gian học kỳ, không phải ngày học chuyên môn từng khóa)','source_path':rel,'source_url':record['source_url'],'sha256':sha,'pdf_sha256':pdf_sha,'doc_id':record['doc_id'],'scope':record['scope'][semester],'qualification':record['qualification'],'source_status':'operator_installed_calendar_evidence','review_scope':'semester_interval_only','retained_quality_hold_ids':retained})
        if len(matches)!=1:return result('INTERVAL_NOT_UNIQUE',match_count=len(matches))
        return {'status':'READY','period':period,'semester':semester,'hits':matches,'review_scope':'semester_interval_only','retained_quality_hold_ids':retained}
    except (OSError,ValueError,KeyError,TypeError) as e:return result('PACK_READ_ERROR',error_type=type(e).__name__)

def uploaded_calendar(root,period,semester):
    return inspect_uploaded_calendar(root,period,semester)['hits']

def pack_status(root):
    periods=('2024-2025','2025-2026')
    if (Path(root)/'data/advisor_sources/calendar_2022/manifest.json').is_file():periods=('2022-2023',)+periods
    return [{k:v for k,v in inspect_uploaded_calendar(root,p,s).items() if k!='hits'} for p in periods for s in SEM]

def lookup_start(root,period,semester,index=None):
    if semester not in SEM or not re.fullmatch(r'20\d{2}-20\d{2}',period or ''):return []
    a,b=map(int,period.split('-'))
    if b!=a+1:return []
    # The index verifies reviewed chunk/hash eligibility and publication holds.
    # Refuse operation if the hold manifest is unavailable.
    if index is None:
        if not (Path(root)/'data/versioning/publication_holds.jsonl').is_file():return []
        index=Index(root)
    if index.errors:return []
    hits={}
    for c in index.chunks:
        if c.status!='reviewed' or not c.temporal_verified or tuple(c.years)!=(a,b):continue
        title=norm(c.path+' '+c.heading)
        if not TOPIC.search(title) or re.search(r'\b(?:sau dai hoc|thac si|tien si|tuyen sinh|nghien cuu khoa hoc)\b',title):continue
        for line in c.text.splitlines():
            # Formal semester interval in a reviewed source is not a teaching-week row.
            heading=re.fullmatch(r'\s*(?:#{1,6}\s+)?((?:\*{1,2})?HỌC\s+KỲ\s+(?:I{1,2}|[12]|PHỤ)(?:\*{1,2})?\s*\(\s*\d{1,2}[./-]\d{1,2}[./-]20\d{2}\s*[^\w\d\s]+\s*\d{1,2}[./-]\d{1,2}[./-]20\d{2}\s*\)(?:\*{1,2})?)\s*',line,re.I)
            if heading:
                txt=clean(heading[1]); nn=norm(txt); ds=list(DATE.finditer(txt))
                if len(ds)==2 and re.match(SEM[semester],nn) and sum(bool(re.search(p,nn)) for p in SEM.values())==1 and not re.search(r'\b(?:dang ky|lich thi|hoc chuyen mon|rut bot|nop)\b',nn):
                    try: start,end=[date(int(m[3]),int(m[2]),int(m[1])) for m in ds]
                    except ValueError:continue
                    if start.year in (a,b) and end.year in (a,b) and start<end and (end-start).days<=300:
                        key=(c.path,start.isoformat(),txt);hits[key]={'date':start.isoformat(),'excerpt':txt+' (khoảng thời gian học kỳ; không đồng nghĩa ngày bắt đầu học chuyên môn từng khóa)','source_path':c.path,'source_url':c.url,'sha256':c.sha,'doc_id':c.doc_id,'scope':c.heading}
                continue
            text=clean(line);n=norm(text)
            if not re.search(SEM[semester],n) or not re.search(r'\b(?:bat dau|tu ngay|ngay bat dau)\b',n):continue
            if re.search(r'\b(?:dang ky|rut bot|lich thi|ngay thi|ky thi|kiem tra|nop|hoc bong|thuc tap|do an)\b',n):continue
            # Only one semester mentioned; a row with multiple semester columns is ambiguous.
            if sum(bool(re.search(p,n)) for p in SEM.values())!=1:continue
            dates=list(DATE.finditer(text))
            if len(dates)!=1:continue
            d,m,y=map(int,dates[0].groups())
            try:val=date(y,m,d)
            except ValueError:continue
            if y not in (a,b):continue
            key=(c.path, val.isoformat(), text)
            hits[key]={'date':val.isoformat(),'excerpt':text,'source_path':c.path,'source_url':c.url,'sha256':c.sha,'doc_id':c.doc_id,'scope':c.heading}
    return list(hits.values())[:10] or uploaded_calendar(root,period,semester)
