"""Read scoped course credit tables; never interpret PLO matrix scores as credits."""
import json,re,hashlib,unicodedata
from pathlib import Path
from quality import norm
from advisor_source_precision import programs,public_result,src
from advisor_public_sections import read_source
CODE_PATTERN=r'(?:UET\.)?[A-Z]{2,3}\d{4}E?'
CODE=re.compile(r'(?<![\w.])'+CODE_PATTERN+r'(?!\w)',re.I)
ROW_NUMBER=re.compile(r'\d+\.?')

def ordinal(s):return bool(ROW_NUMBER.fullmatch(s))

def code_cell(s):
    return re.fullmatch(r'('+CODE_PATTERN+r')\s*([#*]{0,3})',s,re.I)
CATALOG='data/raw/uet/curricula/catalog.json'
PIN='96c0490ea017785a279905884a822a5059dbe56b4aa435efb6a91a19ff86dedb'

def cells(line):
    if not line.strip().startswith('|') or not line.strip().endswith('|'):return []
    return [' '.join(re.sub(r'\*|_|<br\s*/?>',' ',x.replace(r'\*','\ue000'),flags=re.I).replace('\ue000','*').split()) for x in line.strip()[1:-1].split('|')]

def read_rows(text,official):
    """Read only literal credit cells below a recognized, column-aligned header.
    Reassemble header fragments, not data. Unknown headers invalidate the layout.
    """
    lines=unicodedata.normalize('NFC',text).splitlines()
    active=not official;layout=None;headers=[];out=[];width=None;prereq_col=None
    def header_layout(parts):
        if not parts:return None
        # Every fragment must share its leading column positions. A separator
        # can have a different width in the original extracted markdown.
        if len({len(a) for a in parts})!=1:return None
        merged=[' '.join(a[j] for a in parts if a[j]).strip() for j in range(len(parts[0]))]
        squashed=[x.replace(' ','') for x in merged]
        if squashed[0] not in ('stt','sott'):return None
        if len(merged)>=3 and squashed[1].startswith(('mahocphanhocphan','mahocphantenhocphan')):
            if squashed[2] in ('sot','sotc','sotin','sotinchi'):return 'three'
            if squashed[2]=='sotinchislyth':return 'three_hours'
        if len(merged)<4:return None
        # Two corrupted header spellings observed in source: not a general fuzzy match.
        if squashed[1] not in ('mahocphan','masohocphan','mahhaocpn','amahocphn'):return None
        if not (squashed[2].startswith('hocphan') or squashed[2].startswith('tenhocphan') or squashed[2].startswith(('ghibangtiengviet','opghibangtiengviet','hchanopghibangtiengviet','ocpnghibangtiengviet','hopghibangtiengviet','hhocpnghibangtiengviet'))):return None
        if squashed[3] not in ('sotinchi','sotc','sot','sotin','sotinchislyth','soitnchi','ostinchi','oistnchi','stinchi','soitnchi','ostnchi','stnchi'):return None
        # Damaged tokens are allowed only as the observed pair.
        if squashed[1]=='mahhaocpn' and squashed[3] not in ('soitnchi','sotinchi','stinchi'):return None
        if squashed[1]=='amahocphn' and squashed[3]!='sotinchi':return None
        return 'four_hours' if squashed[3]=='sotinchislyth' else 'four'
    for i,line in enumerate(lines,1):
        if official and re.match(r'^##\s+',line):
            active=norm(line)=='noi dung chuong trinh dao tao';layout=None;headers=[];continue
        if not active:continue
        c=cells(line)
        if not c:
            if line.strip():
                layout=None;headers=[]
            continue
        n=[norm(x) for x in c]
        if any(re.search(r'\bplo\s*\d+',x) for x in n) or any('chuan dau ra' in x or 'ma tran' in x for x in n):
            layout=None;headers=[];continue
        if all(re.fullmatch(r'[: -]*',x) for x in c):continue
        if not ordinal(c[0]) and not (layout and not c[0] and len(c)>1 and code_cell(c[1])):
            # Header fragments occur with empty row-number column, STT, or Số TT.
            # Exclude continuation data and section totals from the header window.
            is_header=(n[0] in ('','stt','so tt') and not CODE.search(' '.join(c)) and not any(x.isdigit() for x in c[1:]) and (n[0] in ('stt','so tt') or (len(n)>=4 and (n[1].startswith(('ma','phan','hoc phan','oc pn','a')) or n[2].startswith(('hoc phan','ten hoc phan','ghi bang')) or n[3] in ('so','so tin','so i','tin chi','chi','tn','o','s tin','s tin chi','o i','s tn','s tn chi','so i','s tin chi') or (bool(headers) and all(not x for x in n[:4]) and any(x.startswith('ma hoc ph') for x in n[4:]))))))
            if is_header:
                layout=None
                headers=(headers+[n])[-3:]
                # Prefer the latest sufficient header, including complete single rows.
                for start in range(len(headers)-1,-1,-1):
                    candidate=header_layout(headers[start:])
                    if candidate:
                        layout=candidate;width=len(n)
                        parts=headers[start:]
                        last=' '.join(x[-1] for x in parts if x[-1]).replace(' ','')
                        prereq_col=width-1 if candidate=='four' and width>=5 and last in ('mahocphantienquyet','masohocphantienquyet','hocphantienquyet') else None
                        # Official HTML extracts can flatten a colspan: the label is at
                        # column 6, but the data follows the complete hour columns.
                        # Exact observed signature only; never use the last nonempty cell.
                        if official and candidate=='four' and width in (8,9):
                            h=[''.join(a[j] for a in parts if a[j]).replace(' ','') for j in range(width)]
                            if h[4] in ('sogiotinchi','sogiohoctap') and h[5] in ('mahocphantienquyet','masohocphantienquyet','hocphantienquyet') and not any(h[6:]):
                                prereq_col=width-1
                        break
            else:
                headers=[]
            continue
        headers=[]
        if not layout:continue
        # The first four columns are preserved in the observed sources, even
        # when extraction adds or drops a trailing empty cell. No shifted-value guessing.
        if layout in ('four','four_hours') and len(c)>=4:
            m=code_cell(c[1]);name=c[2];credit=c[3]
        elif layout in ('three','three_hours') and len(c)>=3:
            m=re.fullmatch(r'('+CODE_PATTERN+r')([#*]{0,3})\s+(.+)',c[1],re.I);name=m[3] if m else '';credit=c[2]
        else:continue
        rawcells=line.strip()[1:-1].split('|')
        credit_col=3 if layout.startswith('four') else 2
        raw_credit=rawcells[credit_col].strip()
        # Only strip a superscript tag if the entire cell is a single literal number.
        sup=re.fullmatch(r'<sup>\s*\*{0,2}(\d{1,2})\*{0,2}\s*</sup>',raw_credit,re.I)
        if sup:credit=sup[1]
        if layout.endswith('_hours'):
            pair=re.fullmatch(r'\s*\*{0,2}(\d{1,2})\*{0,2}\s*<br\s*/?>\s*\*{0,2}(\d{1,3})\*{0,2}\s*',raw_credit,re.I)
            if pair:credit=pair[1]
        if not m or not name or not re.fullmatch(r'\d{1,2}',credit) or not 1<=int(credit)<=30:continue
        record=dict(line=i,code=m[1].upper(),credits=int(credit),marker=m[2],layout=layout,name_excerpt=name)
        if prereq_col is not None and layout=='four' and len(c)==width and all(not x or re.fullmatch(r'\d+(?:[.,]\d+)?|[*-]+',x) for x in c[4:prereq_col]):
            cell=c[prereq_col]
            record['prerequisite_cell']=cell
            if not cell:record['prerequisite_status']='BLANK_NOT_PROOF_OF_NONE'
            elif norm(cell) in ('khong co','khong co hoc phan tien quyet','khong co mon tien quyet','khong yeu cau hoc phan tien quyet','khong ap dung','none','not applicable'):
                record['prerequisite_status']='EXPLICIT_NONE' if norm(cell) not in ('khong ap dung','not applicable') else 'NOT_APPLICABLE'
                record['prerequisite_codes']=[]
            elif re.fullmatch(CODE_PATTERN+r'(?:[ ,;]+(?:'+CODE_PATTERN+r'))*',cell,re.I):
                record['prerequisite_status']='LITERAL_CODES';record['prerequisite_codes']=[v.group().upper() for v in CODE.finditer(cell)]
            else:record['prerequisite_status']='UNRESOLVED_LITERAL'
        else:record['prerequisite_status']='HEADER_OR_ALIGNMENT_UNVERIFIED'
        out.append(record)
    return out

def catalog(root):
    b=(Path(root)/CATALOG).read_bytes()
    if PIN not in (hashlib.sha256(b).hexdigest(),hashlib.sha256(b.replace(b'\r\n',b'\n')).hexdigest()):raise ValueError('catalog changed; review required')
    return json.loads(b.decode('utf-8-sig'))

def eligible(r,cy):
    if r.get('collection')=='official_uet_extractions' and r.get('content_kind')=='curriculum':
        a,b=r.get('cohort_from'),r.get('cohort_to');return type(a) is int and a<=cy and (b is None or type(b) is int and cy<=b)
    if r.get('collection')!='team_original_uploads' or r.get('content_kind')!='curriculum_content':return False
    hint=r.get('cohort_hint_unverified') or '';ys=list(map(int,re.findall(r'20\d{2}',hint)))
    return (len(ys)==2 and ys[0]<=cy<=ys[1]) or (len(ys)==1 and (cy>=ys[0] if 'onward' in hint else cy==ys[0]))

def excluded(r,ex):
    return any(any(e.get(k) and e.get(k)==r.get(v) for k,v in [('doc_id','doc_id'),('source_path','content_path'),('source_sha256','content_sha256')]) for e in ex)

def query(q):
    from reference_knowledge import safe_public
    n=norm(q)
    if not safe_public(q) or not re.search(r'\b(?:ctdt|chuong trinh dao tao|nganh)\b',n):return None
    if re.search(r'\b(?:cua toi|cua em|cua minh|cua co|lop|neu|so sanh|doi chieu|tien quyet|bat buoc|tu chon|hoc lai|hoc phi|hoc bong|hoc ky|con thieu|con no|da tich luy|tot nghiep|clc|nhat ban|dieu kien|tinh giup|tinh tong|tinh tien|va|hoac|quy che|thay the|tuong duong|chuyen doi|hoc vu|mien|ngoai le)\b',n.replace('mang may tinh va truyen thong du lieu','mang may tinh truyen thong du lieu').replace('thiet ke cong nghiep va do hoa','thiet ke cong nghiep do hoa').replace('ky thuat dieu khien va tu dong hoa','ky thuat dieu khien tu dong hoa').replace('khoa hoc va ky thuat du lieu','khoa hoc ky thuat du lieu')):return None
    if not re.search(r'\b(?:bao nhieu tin chi|may tin chi|so tin chi|tin chi la bao nhieu)\b',n):return None
    codes={x.group().upper() for x in CODE.finditer(q)}
    ys=set(map(int,re.findall(r'\b(?:qh\s+|khoa\s+)(20\d{2})\b',n)))|{1955+int(k) for k in re.findall(r'\bk(6[4-9]|7[01])\b',n)}
    if len(codes)!=1 or len(ys)!=1:return None
    cy=next(iter(ys)); all_years=set(map(int,re.findall(r'\b20\d{2}\b',n)))
    # No additional year, including a different academic year.
    if not 2019<=cy<=2026 or all_years-{cy}:return None
    wanted=programs(q)
    if len(wanted)!=1:return None
    return next(iter(wanted)),cy,next(iter(codes))

def lookup(root,q):
    parsed=query(q)
    if not parsed:return None
    program,cy,code=parsed;cat=catalog(root);ex=cat.get('owner_excluded_documents',[])
    if not isinstance(ex,list) or any(not isinstance(e,dict) for e in ex):raise ValueError('excluded ledger')
    rows=[r for r in cat['records'] if r.get('program_identifier')==program and eligible(r,cy) and not excluded(r,ex)]
    data=[];missing=[];sources=[]
    for r in rows:
        rel=r['content_path'];label=r.get('edition') or Path(rel).stem
        try:t,sha=read_source(root,rel,r['content_sha256'],r['doc_id'])
        except (OSError,ValueError,KeyError,TypeError):missing.append(label+' (nguồn chưa đủ điều kiện đọc)');continue
        found=[v for v in read_rows(t,r['collection']=='official_uet_extractions') if v['code']==code]
        if not found:missing.append(label+' (chưa tìm thấy dòng tín chỉ rõ ràng)');continue
        # No merge between editions; retain contradictions within each edition.
        amounts=sorted({v['credits'] for v in found});source=src(rel,sha);source.update(source_url=r.get('source_url'),source_lines=[v['line'] for v in found]);sources.append(source)
        data.append((label,amounts,found))
    if not data:return None
    lines=[f'trong bản CTĐT lưu trữ của ngành được hỏi, khóa QH-{cy}, mã **{code}**:']
    for label,amounts,found in data:
        lines.append('- '+label+': '+', '.join(f'**{a} tín chỉ**' for a in amounts)+' (dòng '+', '.join(str(x['line']) for x in found)+').')
        if len(amounts)>1:lines.append('  Nguồn ghi các giá trị khác nhau; chưa xác định được giá trị áp dụng.')
        if any(x['marker'] for x in found):lines.append('  Mã học phần có ký hiệu chú thích trong bảng; cần xem điều kiện đi kèm.')
    if len(rows)>1:lines.append('Các bản lưu có phạm vi khóa chồng lấn; chưa xác nhận văn bản thay thế hoặc hiệu lực của từng bản.')
    if len({a for _,amounts,_ in data for a in amounts})>1:lines.append('Các phiên bản không thống nhất; không tự chọn một định mức.')
    if missing:lines.append('Chưa đối chiếu được các phiên bản còn lại: '+'; '.join(missing)+'.')
    lines.append('Đây là số tín chỉ ghi trong đúng cột của bản lưu; phạm vi khóa theo catalog, chưa xác minh độc lập hiệu lực hoặc điều kiện áp dụng cá nhân.')
    return public_result('\n'.join(lines),sources,'course_credit_reference')


def relation_query(q):
    """Explicit single-course public lookup; keep compound/advisory questions elsewhere."""
    from reference_knowledge import safe_public
    n=norm(q)
    if not safe_public(q):return None
    if re.search(r'\b(?:cua toi|cua em|cua minh|cua co|lop|neu|so sanh|doi chieu|tuong duong|thay the|hoc lai|hoc phi|hoc bong|hoc ky|con thieu|da tich luy|tot nghiep|clc|nhat ban|du dieu kien|duoc dang ky|tinh tong|tinh tien|quy che|mien|ngoai le|lo trinh|gpa|cpa)\b',n):return None
    # Require an explicit scope separated from the target. Avoid matching a program name inside a course name.
    m=re.search(r'\b(?:hoc phan|mon hoc|mon)\s+(.+?)(?=\s+(?:co bao nhieu tin chi|bao nhieu tin chi|may tin chi|co may tin chi|co so tin chi|co ma gi|ma la gi|la ma gi|ma hoc phan la gi|co mon tien quyet|co hoc phan tien quyet|co dieu kien tien quyet|can hoc truoc|can hoc mon nao truoc|tien quyet la gi|tien quyet nao|tien quyet|la bao nhieu|thuoc nganh|trong ctdt|trong chuong trinh dao tao|nganh|khoa|qh)\b|$)',n)
    if not m:return None
    target=m[1].strip()
    # If the target captured an unrelated phrase, no route. A course name is never reconstructed from a truncated source.
    if not target or len(target)>140 or re.search(r'\b(?:nao|gi|bao nhieu|tien quyet|tin chi|dang ky|va mon|hoac mon)\b',target):return None
    scope=n[:m.start(1)]+ ' '+n[m.end(1):]
    if not re.search(r'\b(?:nganh|ctdt|chuong trinh dao tao)\b',scope):return None
    wanted=programs(scope)
    ys=set(map(int,re.findall(r'\b(?:qh\s+|khoa\s+)(20\d{2})\b',scope)))|{1955+int(k) for k in re.findall(r'\bk(6[4-9]|7[01])\b',scope)}
    if len(wanted)!=1 or len(ys)!=1:return None
    cy=next(iter(ys))
    if not 2019<=cy<=2026 or set(map(int,re.findall(r'\b20\d{2}\b',scope)))-{cy}:return None
    intents=[]
    if re.search(r'\b(?:bao nhieu tin chi|may tin chi|so tin chi|tin chi la bao nhieu)\b',scope):intents.append('credits')
    if re.search(r'\b(?:tien quyet|can hoc truoc|can hoc mon nao truoc)\b',scope):intents.append('prerequisite')
    if re.search(r'\b(?:ma gi|ma la gi|ma hoc phan la gi|la ma gi)\b',scope):intents.append('code')
    if not intents:return None
    # Multiple explicitly requested course properties are supported, not multiple courses.
    codes={x.group().upper() for x in CODE.finditer(q)}
    if len(codes)>1:return None
    code=next(iter(codes),None)
    if code and norm(code)!=target:return None
    if code is None and len(target.split())<2:return None
    return next(iter(wanted)),cy,code,target,intents

def name_matches(name,target):
    # Compare literal normalized name words, not fuzzy similarity. A prefix or suffix
    # is a candidate, not proof of an exact bilingual name: report any ambiguity.
    n=norm(name)
    return n==target or n.startswith(target+' ') or n.endswith(' '+target)

def relation_lookup(root,q):
    parsed=relation_query(q)
    if not parsed:return None
    program,cy,code,target,intents=parsed;cat=catalog(root);ex=cat.get('owner_excluded_documents',[])
    if not isinstance(ex,list) or any(not isinstance(e,dict) for e in ex):raise ValueError('excluded ledger')
    docs=[];missing=[];sources=[]
    for r in cat['records']:
        if r.get('program_identifier')!=program or not eligible(r,cy) or excluded(r,ex):continue
        rel=r['content_path'];label=r.get('edition') or Path(rel).stem
        try:t,h=read_source(root,rel,r['content_sha256'],r['doc_id'])
        except (OSError,ValueError,KeyError,TypeError):missing.append(label+' (nguồn chưa đủ điều kiện đọc)');continue
        rows=read_rows(t,r['collection']=='official_uet_extractions')
        found=[v for v in rows if (v['code']==code if code else name_matches(v['name_excerpt'],target))]
        if not found:missing.append(label+' (chưa tìm thấy dòng phù hợp)');continue
        docs.append((label,found,rows,rel,h,r.get('source_url')))
    if not docs:return None
    # Do not select an arbitrary course if several codes match the provided name.
    allcodes=sorted({v['code'] for _,found,*_ in docs for v in found})
    if len(allcodes)>12:return None
    out=[f'theo các bản CTĐT lưu trữ của ngành được hỏi, khóa QH-{cy}:']
    if len(docs)>1:out.append('Các bản lưu có phạm vi khóa chồng lấn; chưa xác nhận hiệu lực thay thế.')
    if len(allcodes)>1:out.append('Tên hỏi khớp nhiều mã học phần; dưới đây là các ứng viên, chưa tự chọn một mã hoặc coi chúng tương đương.')
    for label,found,rows,rel,h,url in docs:
        out.append('\n**'+label+'**')
        cited=set()
        for v in found:
            cited.add(v['line']);line=f"- **{v['code']}** — {v['name_excerpt']}"
            if 'credits' in intents:line+=f" — **{v['credits']} tín chỉ**"
            out.append(line+f" (dòng {v['line']}).")
            if 'prerequisite' in intents:
                status=v.get('prerequisite_status')
                if status=='LITERAL_CODES':
                    out.append('  Ô tiên quyết ghi: **'+v['prerequisite_cell']+'**.')
                    for pc in v.get('prerequisite_codes',[]):
                        matches=[p for p in rows if p['code']==pc]
                        names=sorted({p['name_excerpt'] for p in matches})
                        if names:
                            out.append('  '+pc+': '+' / '.join(names)+'.');cited.update(p['line'] for p in matches)
                        else:out.append('  '+pc+': chưa tìm thấy dòng tên môn trong cùng bản CTĐT.')
                elif status in ('EXPLICIT_NONE','NOT_APPLICABLE'):out.append('  Ô tiên quyết ghi rõ: **'+v['prerequisite_cell']+'**; không thêm mã học phần tiên quyết từ bảng này.')
                elif status=='BLANK_NOT_PROOF_OF_NONE':out.append('  Bảng không liệt kê học phần tiên quyết ở dòng này. Ô trống có thể là không yêu cầu; không mặc định là lỗi dữ liệu hay xác nhận đủ điều kiện đăng ký.')
                elif status=='UNRESOLVED_LITERAL':out.append('  Ô tiên quyết ghi '+v.get('prerequisite_cell','')+'; mã hoặc nội dung chưa phân giải, không tự điền.')
                else:out.append('  Chưa xác nhận được cột tiên quyết trong bảng này.')
        source=src(rel,h);source.update(source_url=url,source_lines=sorted(cited));sources.append(source)
    if missing:out.append('Chưa đối chiếu được các bản còn lại: '+'; '.join(missing)+'.')
    out.append('Thông tin theo bản lưu, không phải xác nhận đủ điều kiện đăng ký học. Các phiên bản và dòng khác nhau được giữ riêng.')
    return public_result('\n'.join(out),sources,'course_relation_reference')


def graph_query(q):
    """Explicit public prerequisite-chain or reverse lookup, scope before target."""
    from reference_knowledge import safe_public
    n=norm(q)
    if not safe_public(q) or re.search(r'\b(?:cua toi|cua em|cua minh|cua ban|cua co|lop|neu|so sanh|tuong duong|thay the|hoc phi|hoc bong|hoc ky|du dieu kien|duoc dang ky|gpa|cpa|mien|ngoai le|clc|nhat ban|da hoc|da qua|da dat|con no|quy che)\b',n):return None
    # One course, explicit scope, no arbitrary free-text query rewrite.
    m=re.fullmatch(r'(.+?)\s+(?:hay\s+)?(?:liet ke\s+|cho biet\s+)?chuoi tien quyet cua (?:hoc phan|mon hoc|mon)\s+(.+)',n)
    mode='chain'
    if not m:
        m=re.fullmatch(r'(.+?)\s+(?:hoc phan|mon hoc|mon)\s+(.+?)\s+la (?:hoc phan |mon )?tien quyet cua (?:nhung |cac )?(?:hoc phan|mon hoc|mon) nao',n)
        mode='reverse'
    if not m:return None
    scope,target=m[1],m[2].strip()
    if not re.search(r'\b(?:ctdt|chuong trinh dao tao)\b',scope):return None
    if re.search(r'\b(?:va mon|hoac|bao nhieu|nao|tinh|dang ky|tien quyet|tin chi)\b',target):return None
    wanted=programs(scope)
    ys=set(map(int,re.findall(r'\b(?:qh\s+|khoa\s+)(20\d{2})\b',scope)))|{1955+int(k) for k in re.findall(r'\bk(6[4-9]|7[01])\b',scope)}
    if len(wanted)!=1 or len(ys)!=1:return None
    cy=next(iter(ys))
    if not 2019<=cy<=2026 or set(map(int,re.findall(r'\b20\d{2}\b',n)))-{cy}:return None
    codes={x.group().upper() for x in CODE.finditer(q)}
    if len(codes)>1:return None
    code=next(iter(codes),None)
    if code and norm(code)!=target:return None
    if not code and (len(target.split())<2 or len(target)>140):return None
    return next(iter(wanted)),cy,code,target,mode


def graph_data(rows):
    """Keep each document separate; no equivalence, no AND/OR inference."""
    by={}
    for row in rows:by.setdefault(row['code'],[]).append(row)
    edges={};issues={}
    for code,rs in by.items():
        known={'LITERAL_CODES','EXPLICIT_NONE','NOT_APPLICABLE'}
        variants={tuple(sorted(set(r.get('prerequisite_codes',[])))) for r in rs if r.get('prerequisite_status') in known and (r.get('prerequisite_codes') or r.get('prerequisite_status')!='LITERAL_CODES')}
        unknown=[r for r in rs if r.get('prerequisite_status') not in known or (r.get('prerequisite_status')=='LITERAL_CODES' and not r.get('prerequisite_codes'))]
        # Explicit no-requirement is a valid terminal node. A blank is not a
        # broken row; only a limit on interpreting completeness of this graph.
        if len(variants)>1 or (variants and unknown):issues[code]='Các dòng ghi khác nhau hoặc có ô chưa xác nhận; không tự hợp nhất.'
        elif unknown:
            issues[code]='Bảng không liệt kê hoặc chưa xác nhận tiên quyết; không mặc định là lỗi hay suy ra đủ điều kiện.'
        if len(variants)==1 and not unknown:edges[code]=next(iter(variants))
    return by,edges,issues


def chain_data(rows,target,mode='chain'):
    by,edges,issues=graph_data(rows);links=[];warnings=[];seen=set();active=set();cited=set()
    def visit(code):
        if code in active:
            warnings.append((code,'Phát hiện vòng lặp trong dữ liệu; dừng mở rộng.'));return
        if code in seen:return
        seen.add(code)
        if code not in by:warnings.append((code,'Mã được dẫn chiếu nhưng chưa tìm thấy trong cùng CTĐT.'));return
        cited.update(r['line'] for r in by[code])
        if code in issues:warnings.append((code,issues[code]));return
        active.add(code)
        for dep in edges.get(code,()):
            links.append((dep,code));visit(dep)
        active.remove(code)
    if mode=='chain':visit(target)
    else:
        # Direct reverse lookup only. Never call this a complete list with partial data.
        cited.update(r['line'] for r in by.get(target,[]))
        for code,ds in edges.items():
            if target in ds:links.append((target,code));cited.update(r['line'] for r in by[code])
        for code in sorted(issues):
            if any(target in r.get('prerequisite_codes',[]) for r in by[code]):
                warnings.append((code,issues[code]));cited.update(r['line'] for r in by[code])
        if issues:warnings.append((target,'Một số ô tiên quyết của CTĐT còn trống/chưa xác nhận; danh sách không bảo đảm đầy đủ.'))
    return links,warnings,sorted(cited)


def graph_lookup(root,q):
    parsed=graph_query(q)
    if not parsed:return None
    program,cy,code,target,mode=parsed;cat=catalog(root);ex=cat.get('owner_excluded_documents',[])
    if not isinstance(ex,list) or any(not isinstance(e,dict) for e in ex):raise ValueError('excluded ledger')
    out=[f'đối chiếu các bản CTĐT của ngành được hỏi, khóa QH-{cy}. Quan hệ dưới đây chỉ là các mã ghi trong bảng, không suy ra điều kiện AND/OR hoặc đủ điều kiện đăng ký.'];sources=[];missing=[]
    docs=[]
    for r in cat['records']:
        if r.get('program_identifier')!=program or not eligible(r,cy) or excluded(r,ex):continue
        rel=r['content_path'];label=r.get('edition') or Path(rel).stem
        try:t,h=read_source(root,rel,r['content_sha256'],r['doc_id'])
        except (OSError,ValueError,KeyError,TypeError):missing.append(label+' (nguồn chưa đủ điều kiện đọc)');continue
        rows=read_rows(t,r['collection']=='official_uet_extractions')
        found=sorted({v['code'] for v in rows if (v['code']==code if code else name_matches(v['name_excerpt'],target))})
        if not found:missing.append(label+' (chưa tìm thấy học phần)');continue
        docs.append((r,rel,label,h,rows,found))
    if not docs:return None
    allcodes={c for *_,found in docs for c in found}
    if len(allcodes)>8:return None
    if len(allcodes)>1:out.append('Tên hỏi có nhiều mã ứng viên; tách riêng, không coi chúng là môn tương đương.')
    if len(docs)>1:out.append('Các bản lưu có phạm vi khóa chồng lấn; chưa xác nhận bản nào có hiệu lực thay thế bản nào.')
    for r,rel,label,h,rows,found in docs:
        out.append('\n**'+label+'**');cited=set();by,_,_=graph_data(rows)
        for c in found:
            links,warnings,lines=chain_data(rows,c,mode);cited.update(lines)
            def label_for(k):
                names=sorted({v['name_excerpt'] for v in by.get(k,[])})
                return k+(' — '+' / '.join(names) if names else '')
            out.append('Học phần: **'+label_for(c)+'**')
            if not links:
                if mode=='chain' and by.get(c) and all(v.get('prerequisite_status') in ('EXPLICIT_NONE','NOT_APPLICABLE') for v in by[c]):out.append('Bảng ghi rõ không có hoặc không áp dụng học phần tiên quyết cho học phần này.')
                else:out.append('Chưa có quan hệ xác định được theo yêu cầu trong bản này.')
            for dep,dst in links[:50]:out.append('- '+label_for(dep)+' → '+label_for(dst))
            if len(links)>50:out.append('Còn '+str(len(links)-50)+' quan hệ; cần thu hẹp phạm vi.')
            for k,msg in warnings[:20]:out.append('- Lưu ý '+k+': '+msg)
            if len(warnings)>20:out.append('Còn các ô chưa xác nhận khác.')
        s=src(rel,h);s.update(source_url=r.get('source_url'),source_lines=sorted(cited));sources.append(s)
    if missing:out.append('Các bản chưa đối chiếu được: '+'; '.join(missing)+'.')
    out.append('Không sử dụng kết quả này để tự động xác nhận đăng ký, miễn môn hoặc công nhận tương đương.')
    return public_result('\n'.join(out),sources,'course_prerequisite_graph')


def route(root,q,prior):
    if prior:return None
    try:return graph_lookup(root,q) or lookup(root,q) or relation_lookup(root,q)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError):return None
