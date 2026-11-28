"""Product-only raw-source reference fallback. Exact excerpts, never approval.
The existing reviewed retrieval, decision gates, and research routes take precedence.
"""
from pathlib import Path
from collections import Counter
import hashlib,re,threading,json,math
from dataclasses import replace
from knowledge import Index,norm,tokens,requested_period,matches_period
from advisor_evidence import fresh_ledger
from quality_routes import response
from advisor_source_precision import eligible as scope_eligible

PERSONAL=re.compile(r'\b(?:mssv|ma sinh vien|\d{8}|ho so cua|ban ay|em ay|ban nay|em nay|sinh vien nay|sinh vien do|ca lop|toan lop|trong lop|lop cua|lop minh|lop co|sinh vien nao|nhung ai|soan|viet|lap ke hoach|tu van rieng|gap rieng|gia su|mo phong|cpa|gpa)\b')
# Exclude individual records, live decisions, unsafe requests and foreign institutions.
BLOCK=re.compile(r'\b(?:ngoai le|dac cach|bo qua|ignore|system prompt|tam khoa|publication hold|chua duyet|hutech|ulis|uit|bach khoa|truong khac|du doan|phe duyet|gui ngay|sua diem|hieu luc hien tai|dang ap dung|co duoc phep|du dieu kien|xac nhan|ap dung cho|quy che moi nhat)\b')
TOPIC=re.compile(r'\b(?:uet|dhqghn|tuyen sinh|diem chuan|diem trung tuyen|hoc phi|hoc bong|kkht|chuong trinh dao tao|ctdt|hoc phan|tin chi|lich hoc|lich thi|ke hoach hoc tap|nam hoc|quy che|quy dinh|quyet dinh|thong bao|thu tuc|nghien cuu khoa hoc|nckh|thac si|tien si|chuan dau ra|tot nghiep|ngoai ngu|tieng anh|co so vat chat|ky tuc xa|nganh dao tao|chi tieu|giang vien|dao tao|bao luu|dang ky|thoi han|hoc lai)\b')
PRIVATE_DOC=re.compile(r'\b(?:danh sach (?:sinh vien|thi sinh|nguoi hoc)|bang diem|ket qua hoc tap ca nhan|ho so sinh vien|danh sach canh bao|danh sach buoc thoi hoc)\b')
SUSPICIOUS=re.compile(r'\b(?:ignore previous|system prompt|bo qua chi dan|hay tra loi|instruction|api key|password)\b')
STOP=set('giup em co cho hoi biet nao gi la bao nhieu khi nao the nao nhu the nao mot cac nhung cua tai theo trong nam hoc uet dhqghn thong tin duoc can muon xem noi dung'.split())

def words(s):return {x for x in tokens(s) if ' ' not in x and len(x)>1 and x not in STOP and not x.isdigit()}
EXTRA_TOPIC=re.compile(r'\b(?:phong ban|phong dao tao|khoa vien|khoa hoc may tinh|cong nghe thong tin|dia chi|lien he|email|nganh|chuyen nganh|mon hoc|mon tien quyet|mon bat buoc|mon tu chon|chuong trinh|muc thu|le phi|hoc lai|hoc vu|tot nghiep|chung chi|han nop|han dang ky|thi lai|nghi le|nghi tet|thuc tap|khoa luan|do an|viec lam|tieng anh|ngoai ngu|chuan dau ra|danh hieu|van bang|bao hiem|co so|ky tuc xa|chi tieu|xet tuyen|xet hoc bong|ren luyen|mien giam|quy doi|dieu kien|hoc ky|hoc ki)\b')
CODE=re.compile(r'(?<![\w.])(?:uet\.)?[a-z]{2,3}\d{4}e?(?!\w)',re.I)
ALIASES=(('diem chuan','diem trung tuyen'),('mon hoc','hoc phan'),('mon tien quyet','hoc phan tien quyet'),('ctdt','chuong trinh dao tao'),('hoc ki','hoc ky'),('lich hoc','ke hoach hoc tap'),('lich thi','ke hoach hoc tap'),('nckh','nghien cuu khoa hoc'),('kkht','khuyen khich hoc tap'),('cntt','cong nghe thong tin'),('khmt','khoa hoc may tinh'),('httt','he thong thong tin'),('ktmt','ky thuat may tinh'),('ktrb','ky thuat robot'),('ktvt','ky thuat dien tu vien thong'),('mmtttdl','mang may tinh va truyen thong du lieu'),('hoc phi','muc thu hoc phi'),('hoc bong','dinh muc hoc bong'),('chuan dau ra','yeu cau dau ra'),('so tin chi','tong so tin chi'))
CURRIC=re.compile(r'\b(?:chuong trinh dao tao|ctdt|hoc phan|mon hoc|tin chi|tien quyet|chuan dau ra|khoa luan|do an)\b')
QUERY_STOP=set('co em toi minh giup xem tra tim cho xin liet ke danh sach tat ca day du tong hop so sanh khac nhau nhu the nao co gi bao nhieu nao cac nhung nay do cua ve duoc biet muon hay la va trong theo nam hoc khoa uet dhqghn'.split())
def safe_public(q):
    n=norm(q)
    # Preserve the privacy and consequential-decision gate. A course code is
    # also a legitimate standalone public query.
    return 5<=len(q)<=700 and not PERSONAL.search(n) and not BLOCK.search(re.sub(r'\b(?:xac nhan nhap hoc)\b','nhap hoc',n)) and bool(TOPIC.search(n) or EXTRA_TOPIC.search(n) or CODE.search(n))
def variants(q):
    n=norm(q);out=[q]
    for a,b in ALIASES:
        for src,dst in ((a,b),(b,a)):
            if re.search(r'\b'+re.escape(src)+r'\b',n):
                v=re.sub(r'\b'+re.escape(src)+r'\b',dst,n)
                if v not in out:out.append(v)
    return out[:8]
def terms_for(q):
    return {x for x in re.findall(r'[a-z0-9]+',norm(q)) if len(x)>1 and x not in QUERY_STOP and not x.isdigit() and not re.fullmatch(r'k\d{2}',x)}
def cohort_request(q):
    n=norm(q)
    m=re.search(r'\b(?:qh[- ]?|khoa\s+)(20\d{2})\b',n)
    if m:return int(m[1])
    m=re.search(r'\bk(6[7-9]|7[01])\b',n)
    return int(m[1])+1955 if m else None

def cohort_candidate(c,cy):
    if cy is None:return True
    if '/curricula/' not in c.path:return False
    if c.cohort_from is not None:
        return c.cohort_from<=cy and (c.cohort_to is None or cy<=c.cohort_to)
    # Only a search hint. The output explicitly distinguishes it from verified scope.
    name=norm(Path(c.path).stem).replace('_','-')
    m=re.search(r'(20\d{2})-(?:to-)?(20\d{2})',name)
    if m:return int(m[1])<=cy<=int(m[2])
    m=re.search(r'(20\d{2})-(?:tro-?di|plus|onward)',name)
    if m:return cy>=int(m[1])
    return bool(re.search(r'(?<!\d)'+str(cy)+r'(?!\d)',name))


def safe_excerpt(c):
    # Never return personal-list documents, embedded instructions, or active HTML.
    name=norm(c.path.replace('_',' ').replace('-',' ')+' '+c.heading)
    if PRIVATE_DOC.search(name) or SUSPICIOUS.search(norm(c.text)):return None
    if re.search(r'(?i)\b(?:mssv|mã sinh viên|số cccd|số cmnd)\b.{0,35}\b\d{8,12}\b',c.text):return None
    if re.search(r'(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b',c.text):return None
    text=c.text.strip()
    if not 30<=len(text)<=2500 or text.startswith('---') or re.match(r'(?i)^(?:retrieval_eligible|review_status|doc_id|content_sha256|source_url):',text):return None
    # Preserve data and Markdown structure; neutralize HTML rather than execute it.
    text=re.sub(r'<br\s*/?>',' / ',text,flags=re.I).replace('<','&lt;').replace('>','&gt;')
    return text

def verified_bytes(index,c,holds):
    """Re-read exact bytes and fresh hold ledger. A raw read is not official review."""
    try:
        root=index.root;p=(root/c.path).resolve();p.relative_to(root)
        raw=p.read_bytes();body=raw.decode('utf-8-sig');sha=hashlib.sha256(raw).hexdigest();canon=hashlib.sha256(body.replace('\r\n','\n').encode()).hexdigest()
        if sha!=c.sha:return False
        if any(h['content_sha256'] in (sha,canon) or (c.doc_id and h['doc_id']==c.doc_id) or c.path in (h.get('source_path'),h.get('content_path')) for h in holds):return False
        # A held alias can have a different newline representation. The reference
        # index tracks the canonical hashes of all aliases that were held.
        if canon in getattr(index,'reference_held_canonical',set()):return False
        return True
    except (OSError,ValueError,KeyError,TypeError,UnicodeError):return False

def clean_reference_text(value):
    import unicodedata
    return unicodedata.normalize('NFC', value.replace('\ufeff','').replace('\u00ad','').replace('\u200b',''))


def normalize_reference_index(index):
    from collections import Counter, defaultdict
    from dataclasses import replace
    index.chunks = [replace(c,text=clean_reference_text(c.text),heading=clean_reference_text(c.heading)) for c in index.chunks]
    index.postings=defaultdict(dict);index.lengths=[]
    for i,c in enumerate(index.chunks):
        tf=Counter(tokens(c.heading+' '+c.path.replace('_',' ').replace('-',' ')+' '+c.text))
        index.lengths.append(sum(tf.values()))
        for w,n in tf.items():index.postings[w][i]=n
    index.avg=sum(index.lengths)/max(1,len(index.lengths)) or 1
    return index

class ReferenceLibrary:
    def __init__(self,root):
        self.root=Path(root).resolve();self.index=None;self.lock=threading.RLock();self.comparison={};self._catalog_hash=None
    def get(self):
        with self.lock:
            # Refresh policy metadata even for a warm index. Rebuild only when the
            # catalog changes; source bytes and publication holds are checked below.
            catalog=self.root/'data/raw/uet/curricula/catalog.json'
            raw=catalog.read_bytes() if catalog.is_file() else b''
            fingerprint=hashlib.sha256(raw).hexdigest()
            cat=json.loads(raw.decode('utf-8-sig')) if raw else {}
            exclusions=set();program_map={}
            for r in cat.get('records',[]):
                if r.get('content_path'):program_map[r['content_path']]=r.get('program_identifier','')
            for r in cat.get('owner_excluded_documents',[]):
                for key in ('source_path','doc_id','source_sha256','content_sha256'):
                    if r.get(key):exclusions.add(r[key])
            p=self.root/'tools/academic_advisor/reference_comparison.json'
            d=json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
            comparison={r['path']:r for r in d.get('files',[]) if isinstance(r,dict) and r.get('path')}
            if self.index is None or fingerprint!=self._catalog_hash:
                fresh_ledger(self.root)
                self.index=normalize_reference_index(Index(self.root,include_pending=True))
                self._catalog_hash=fingerprint
            self._catalog_exclusions=exclusions;self.program_map=program_map;self.comparison=comparison
            return self.index
    def report(self):
        with self.lock:return self._report()
    def _report(self):
        ix=self.get();holds=fresh_ledger(ix.root);usable=Counter();all_chunks=Counter();by_sha={};byte_checks={}
        for c in ix.chunks:
            all_chunks[c.path]+=1
            key=(c.path,c.sha,c.doc_id)
            if key not in byte_checks:byte_checks[key]=verified_bytes(ix,c,holds)
            if safe_excerpt(c) and byte_checks[key] and not self.omitted(c):
                usable[c.path]+=1;by_sha[c.sha]=c.path
        excluded_paths={c.path for c in ix.chunks if c.doc_id and c.doc_id in self._catalog_exclusions}
        rows=[]
        for r in ix.inventory:
            path=r['path'];count=usable[path];alias=by_sha.get(r.get('sha256'))
            status='searchable_reference' if count else 'duplicate_reference' if alias and r['status'] not in ('held','metadata_only') else r['status'] if r['status'] in ('held','metadata_only') else 'no_safe_excerpt_or_duplicate'
            comp=self.comparison.get(path,{})
            if path in self._catalog_exclusions or r.get('sha256') in self._catalog_exclusions or path in excluded_paths:
                status='owner_excluded';count=0;alias=None
            if comp.get('sha256')==r.get('sha256') and r['status'] not in ('held','metadata_only'):
                if comp.get('status')=='OWNER_EXCLUDED_LEGACY_COPY':status='owner_excluded';count=0
                elif comp.get('status')=='DUPLICATE_BODY_MATCH':status='duplicate_reference';count=0;alias=comp.get('canonical_path')
            rows.append({**r,'indexed_chunks':all_chunks[path],'safe_reference_chunks':count,'access':status,'alias_of':alias if status=='duplicate_reference' else None})
        raw_ext=Counter(p.suffix.lower() or '(none)' for p in (ix.root/'data/raw/uet').rglob('*') if p.is_file())
        return {'raw_extension_counts':dict(raw_ext),'schema':'chronoreg-advisor-reference-coverage-v1','scope':'data/raw/uet Markdown and catalog paths plus existing QD3626 text; not PDF-only or external sources','inventory_count':len(rows),'chunk_count':len(ix.chunks),'reviewed_chunks':sum(c.status=='reviewed' for c in ix.chunks),'pending_reference_chunks':sum(c.status=='review_pending' for c in ix.chunks),'access_counts':dict(Counter(r['access'] for r in rows)),'inventory_status_counts':dict(Counter(r['status'] for r in rows)),'errors':ix.errors,'files':rows,'official_review_changed':False,'research_corpus_changed':False,'semantic_accuracy_verified':False}
    def review_record(self,c):
        r=self.comparison.get(c.path,{})
        return r if r.get('sha256')==c.sha else {}
    def omitted(self,c):
        r=self.review_record(c)
        return (r.get('status') in ('OWNER_EXCLUDED_LEGACY_COPY','DUPLICATE_BODY_MATCH') or c.path in self._catalog_exclusions or c.doc_id in self._catalog_exclusions or c.sha in self._catalog_exclusions or Path(c.path).stem in self._catalog_exclusions)
    def route(self,q,prior=None):
        with self.lock:return self._route(q,prior)
    def _route(self,q,prior=None):
        if not safe_public(q):return None
        # Do not reinterpret a personal continuation as a public search.
        if prior and prior.get('kind') in ('student','advisor_mission','advisor_task','semantic_task','advisor_agent') and not re.search(r'\b(?:uet|dhqghn|nam 20\d{2}|qh[- ]?20\d{2}|tuyen sinh)\b',norm(q)):return None
        try:
            ix=self.get();holds=fresh_ledger(ix.root);n=norm(q);cy=cohort_request(q)
            iscurr=bool(CURRIC.search(n) or CODE.search(n)) and not re.search(r'\b(?:hoc phi|hoc bong|ha hang|xep loai tot nghiep|quy che)\b',n)
            if not iscurr:cy=None
            searchq=q
            if cy is not None:
                searchq=re.sub(r'(?i)\b(?:qh[- ]?|khóa\s+|khoa\s+)20\d{2}\b|\bk(?:6[7-9]|7[01])\b',' ',q)
            years,academic=requested_period(searchq);vs=variants(searchq);ts=[terms_for(v) for v in vs];codes=set(CODE.findall(n));pool={}
            # The original search keeps its year, regulation and unit restrictions.
            # Larger per-document budget is confined to this product reference path.
            for v in vs:
                for rank,c in enumerate(ix.search(v,k=80,per_path_limit=12)):
                    if cy is not None and not cohort_candidate(c,cy):continue
                    if self.omitted(c) or not scope_eligible(c,q,self.program_map):continue
                    t=safe_excerpt(c)
                    if not t:continue
                    body=terms_for(c.text);head=terms_for(c.heading+' '+c.path.replace('_',' ').replace('-',' '));combined=body|head
                    if codes and not codes.issubset({x.group().lower() for x in CODE.finditer(c.text)}):continue
                    if not any(vt and len(vt&body)>=min(2,len(vt)) and len(vt&combined)/len(vt)>=.48 for vt in ts) and not codes:continue
                    # Use lexical coverage and reciprocal rank, not a fabricated probability.
                    score=max((len(vt&body)*2+len(vt&combined))/max(1,len(vt)) for vt in ts)+2/(1+rank/5)
                    key=(c.path,c.text);old=pool.get(key)
                    if old is None or score>old[0]:pool[key]=(score,c,t)
            if not pool:return None
            ranked=sorted(pool.values(),key=lambda x:-x[0]);best=ranked[0][0];chosen=[];seen=set();counts=Counter();checks={}
            def add(item):
                score,c,t=item;key=norm(t)
                if key in seen or counts[c.path]>=2 or len(chosen)>=5:return False
                identity=(c.path,c.sha,c.doc_id)
                if identity not in checks:checks[identity]=verified_bytes(ix,c,holds)
                if not checks[identity]:return False
                if sum(len(x[1]) for x in chosen)+len(t)>5500:return False
                chosen.append((c,t));seen.add(key);counts[c.path]+=1;return True
            # Preserve a distinct candidate for each explicitly requested year.
            if len(years)>1:
                for y in sorted(years):
                    for item in ranked:
                        if matches_period(item[1],{y},False) and add(item):break
            for item in ranked:
                if item[0]<best*.60:continue
                add(item)
                if len(chosen)>=3:break
            if not chosen:return None
            lines=['Dạ cô, em tìm được các đoạn liên quan trong kho dữ liệu UET. Đây là trích dẫn tham khảo, không tự xác nhận hiệu lực hoặc điều kiện áp dụng.'];sources=[]
            if len(years)>1:
                missing=sorted(y for y in years if not any(matches_period(c,{y},False) for c,t in chosen))
                if missing:lines.append('Chưa tìm thấy nguồn đủ liên quan cho năm '+', '.join(map(str,missing))+'.')
            if cy is not None:lines.append(f'Đang tìm theo khóa QH-{cy}; phạm vi của tài liệu chưa xác minh chỉ là gợi ý, không phải kết luận áp dụng.')
            for i,(c,t) in enumerate(chosen,1):
                heading=re.sub(r'[<>\r\n]',' ',c.heading.strip())[:150] or Path(c.path).name
                lines+=['',f'**Nguồn {i}: {heading}**',t,'',f'Tệp: `{c.path}`']
                url=c.url;rec=self.review_record(c)
                if not url and rec.get('candidate_url'):url=rec['candidate_url']
                url=url if url and re.fullmatch(r'https://(?:[a-z0-9.-]+\.)?(?:vnu\.edu\.vn|uet\.edu\.vn)(?:/[^\s<>]*)?',url,re.I) else None
                if url:lines.append(('Nguồn đối chiếu ứng viên: ' if rec.get('candidate_url')==url and not c.url else 'Nguồn: ')+url)
                lines.append('Trạng thái: '+('đã rà soát đoạn nguồn' if c.status=='reviewed' else 'tài liệu tham khảo, chưa xác minh đầy đủ'))
                sources.append({'source_path':c.path,'sha256':c.sha,'source_url':url,'review_status':c.status,'comparison_status':rec.get('status'),'candidate_match_fraction':rec.get('candidate_match_fraction')})
            if years:lines+=['','Năm trong đường dẫn chỉ là dấu hiệu tìm kiếm; không tự suy ra thời điểm hiệu lực từ tên tệp.']
            r=response('\n'.join(lines),'corpus_reference',['reference_search'],sources);r['metadata'].update(engine_mode='ADVISOR_EVIDENCE',inference_source='deterministic_corpus_reference',source_label='Tra cứu tài liệu UET (tham khảo)',quality_qualified=False,reference_only=True,source_path=chosen[0][0].path,sha256=chosen[0][0].sha,advisor_evidence='\n\n'.join(t for _,t in chosen),reference_candidate_count=len(pool),reference_passage_count=len(chosen))
            return r,{}
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,AttributeError):return None
