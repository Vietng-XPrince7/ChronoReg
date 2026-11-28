"""Auto product boundary: reject unqualified excerpt dumps, normalize display text.
Research routes and original evidence bytes are deliberately untouched.
"""
import html,re,unicodedata
from quality import norm
from quality_routes import response, pinned, source_response

RAW_MODES={'KNOWLEDGE_EXCERPTS','LORA_KNOWLEDGE_ACCESS','SLM_KNOWLEDGE_ACCESS','GEMINI_KNOWLEDGE_ACCESS'}
RAW_ENGINES={'deterministic_corpus_reference','knowledge_excerpts','local_slm_knowledge','gemini_public_knowledge'}

def clean_answer(text):
    # Decode nested entities, never render resulting HTML. Only known presentation
    # markers are removed; unknown markup is rejected by the caller.
    for _ in range(3):
        t=html.unescape(text)
        if t==text:break
        text=t
    text=re.sub(r'</?mark\s*>','',text,flags=re.I)
    text=re.sub(r'<br\s*/?>','\n',text,flags=re.I)
    text=unicodedata.normalize('NFC',text).replace('\xa0',' ')
    return ''.join(c for c in text if c in '\n\t' or unicodedata.category(c) not in ('Cf','Cc')).strip()

def finalize(r,question):
    m=r.get('metadata') or {}; routing=r.get('routing') or {}
    if routing.get('risk_tier')=='RED':return r
    a=r.get('answer'); reason=None
    if not isinstance(a,str) or not a.strip():reason='empty_answer'
    elif m.get('inference_source') in RAW_ENGINES or m.get('engine_mode') in RAW_MODES or re.search(r'(?im)^\s*\*{0,2}Nguồn\s+\d+\s*:',a):reason='unqualified_excerpt'
    else:
        a=clean_answer(a)
        if re.search(r'<\s*/?\s*[A-Za-z][^>]*>|<!--|&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z]+);',a) or any(unicodedata.category(c)=='Co' or c=='\ufffd' for c in a):reason='unsafe_or_corrupt_text'
    # Comparisons must address every explicitly named policy family. This is a
    # coverage check, not proof of correctness or support for individual claims.
    if not reason and m.get('engine_mode')!='CONTEXT_CLARIFICATION':
        topics=policy_topics(question); ans_topics=policy_topics(a)
        n=norm(question)
        if len(topics)>1 and contains(n,'phan biet|so sanh|khac nhau|khac .*the nao|lien quan gi') and not topics.issubset(ans_topics):reason='incomplete_multi_topic'
        if topics=={'graduation'} and 'scholarship' in ans_topics and 'graduation' not in ans_topics:reason='wrong_topic'
    if reason:
        out=response('Dạ cô, em chưa tổng hợp được câu trả lời đủ căn cứ cho câu hỏi này. Em không đưa các đoạn tài liệu rời rạc hoặc chưa rõ phạm vi thay cho câu trả lời.','quality_gate_unresolved')
        out.update(question=question,context_token=None)
        out['routing']['risk_tier']=routing.get('risk_tier','GREEN')
        out['metadata'].update(advisor_experience=True,quality_gate='REJECTED',quality_gate_reason=reason,quality_qualified=False)
        return out
    r['answer']=re.sub(r'^Dạ cô, (Nếu|Với|Học bổng|Mức xét|Quy định)\b',lambda m:'Dạ cô, '+m[1][0].lower()+m[1][1:],a)
    r.setdefault('metadata',{})['quality_gate']='DISPLAY_CHECKED_NOT_SEMANTIC_APPROVAL'
    return r

# Intent families, not whole-sentence patterns. Do not rewrite original question,
# signed context, identifiers or numeric values. Only public tool dispatch below.
def contains(n,p):return bool(re.search(r'\b(?:'+p+r')\b',n))

def policy_topics(q):
    n=norm(q); topics=set()
    if contains(n,'tot nghiep|ra truong|(?:xet |cong nhan )?cap bang dai hoc|ha bang|ha hang|giam hang bang|giam hang|bang (?:loai )?(?:gioi|xuat sac|kha|trung binh)'):topics.add('graduation')
    if contains(n,'rut (?:bot )?(?:mon|hoc phan)|bo (?:bot )?(?:mot |1 )?(?:mon|hoc phan)|huy (?:mon|hoc phan)'):topics.add('withdrawal')
    if contains(n,'bao luu ket qua|xin bao luu|nghi hoc tam thoi|tam dung (?:viec )?hoc|tam nghi hoc'):topics.add('leave')
    if contains(n,'canh bao hoc vu|canh bao hoc tap|canh bao ket qua hoc tap|canh bao.*nhac nho|nhac nho.*canh bao|buoc thoi hoc'):topics.add('warning')
    if contains(n,'hoc lai|hoc cai thien|cai thien diem|thi lai|(?:mon|hoc phan).*?(?:nhan|diem|bi) f'):topics.add('retake')
    if contains(n,'hoc vuot|gioi han tin chi|khoi luong (?:hoc (?:duoc )?)?dang ky|dang ky(?: hoc)? (?:toi da|toi thieu)|dang ky bao nhieu (?:tc|tin chi)'):topics.add('load')
    if contains(n,'hoc bong|kkht'):topics.add('scholarship')
    if contains(n,'hoc phi|dinh muc thu|(?:nop|dong|mat|hoan|tra lai|tra) (?:tien|phi)(?: hoc lai| da dong)?'):topics.add('tuition')
    if contains(n,'tuyen sinh|diem chuan|diem trung tuyen|nhap hoc'):topics.add('admissions')
    return topics

def scoped(q):
    n=norm(q)
    if contains(n,'mssv|ma sinh vien|bang diem|ho so|ca lop|toan lop|lop minh|em ay|ban ay|sinh vien nay|hutech|ulis|uit|bach khoa|truong khac|thac si|tien si|5115|3079|thong tu|nghi dinh|quy che moi|quy che cu|ngoai le|dac cach|bo qua|ignore|gia su|du dieu kien tot nghiep khong|co du dieu kien|da du dieu kien') or re.search(r'\b\d{8}\b',n):return None
    years={1955+int(k) for k in re.findall(r'\bk(\d{2})\b',n)}|{int(y) for y in re.findall(r'\b(?:qh|khoa(?: tuyen sinh)?) (20\d{2})\b',n)}
    if len(years)>1 or not years.issubset({2022,2023,2024,2025}) or set(map(int,re.findall(r'\b20\d{2}\b',n)))-years:return None
    return ('Với khóa QH-'+str(next(iter(years))) if years else 'Nếu thuộc khóa tuyển sinh 2022–2025')+' và áp dụng QĐ 3626'

def get(root,a,k=None):
    from advisor_evidence import fresh_ledger,blocked_qd
    if blocked_qd(fresh_ledger(root)):return None
    return pinned(root,f'Điều {a}'+(f' khoản {k}' if k else '')+' QĐ 3626')

def public_policy(root,q,prior):
    n=norm(q); topics=policy_topics(q); scope=scoped(q)
    if contains(n,'bo qua quy dinh|bo qua dieu kien|ignore rules') and contains(n,'xac nhan|phe duyet|cong nhan'):
        return response('Dạ cô, em không thể xác nhận đủ điều kiện học vụ khi chưa đáp ứng quy định hoặc chưa đủ hồ sơ. Cần đối chiếu các điều kiện thực tế với Phòng Đào tạo.','unsafe_eligibility_request'),{}
    if 'graduation' in topics and re.search(r'\b(?:qh|khoa(?: tuyen sinh)?) 20(?:2[6-9]|[3-9]\d)\b|\bk(?:7[1-9]|[89]\d)\b',n) and not scope:
        return response('Dạ cô, em chưa xác minh được quy chế tốt nghiệp dành cho khóa được hỏi. Em không áp dụng quy định của khóa khác để xác nhận điều kiện.','graduation_scope_unverified'),{}
    if not scope or contains(n,'dieu [0-9]+|khoan [0-9]+|hieu luc|hien nay|tuong duong|chuyen doi|tam khoa|chua duyet|chua phe duyet|system prompt'):return None
    instruments=re.findall(r'\b(?:qd|quyet dinh) (\d+)\b',n)
    if any(x!='3626' for x in instruments):return None
    if prior and prior.get('kind') in ('student','advisor_mission','advisor_task','semantic_task','advisor_experience_cpa'):return None
    if contains(n,'bo qua quy dinh'):return None
    def out(text,c,tag):
        r=source_response('Dạ cô, '+scope+':\n\n'+text+'\n\nCần đối chiếu quy chế và thông báo UET áp dụng đúng khóa; không phải quyết định học vụ cá nhân.',tag,c)
        r['metadata']['advisor_intent']=tag
        return r,{}
    # Known compound intents: treat the narrower task as the primary one only
    # if the secondary topic is its consequence, not an independent question.
    if 'withdrawal' in topics and topics <= {'withdrawal','tuition'} and not contains(n,'so sanh|phan biet|hoc phi hoc lai|bao nhieu tien'):
        # Prefer the established typed withdrawal route: it signs cohort and
        # semester state for follow-ups, and answers narrow deadlines directly.
        from advisor_tasks import withdrawal, state as withdrawal_state
        from quality_routes import cohort
        existing=withdrawal(q,n,prior,root,None,None)
        if existing is not None:return existing
        old=prior if prior.get('kind')=='advisor_agent' and prior.get('topic')=='withdrawal' else {}
        cy=cohort(n,old.get('cohort'))
        if cy is not None and not 2022<=cy<=2025:return None
        periods=set(re.findall(r'\b(?:ky|ki) (phu|he|chinh)\b',n))
        periods={'phu' if x=='he' else x for x in periods}
        if len(periods)>1:return None
        sem=next(iter(periods),old.get('semester','chinh'))
        if cy is not None:scope='Với khóa QH-'+str(cy)+' và áp dụng QĐ 3626'
        from presentation import withdrawal_summary
        c=get(root,23)
        if c:
            t=withdrawal_summary('rút học phần',c['answer'])
            if t:
                if contains(n,'sau han|qua han') and 'tuition' in topics:t='Nếu đã quá hạn rút học phần, không được hoàn học phí. '+t
                elif sem=='phu' and 'tuition' in topics and contains(n,'het (?:tuan dau|tuan thu nhat|1 tuan|mot tuan)|qua (?:tuan dau|1 tuan|mot tuan)'):t='Nếu đã hết 1 tuần kể từ đầu học kỳ phụ thì đã quá hạn rút học phần theo Điều 23. Học phần vẫn trong phiếu đăng ký; tự ý không học sẽ nhận điểm F và không được trả lại học phí.'
                elif contains(n,'ky phu|ki phu') and contains(n,'han|bao lau'):t='Hạn rút học phần kỳ phụ là 1 tuần kể từ đầu kỳ. '+t
                r,_=out(t,c,'withdrawal_general')
                return r,withdrawal_state('withdrawal',cohort=cy,semester=sem)
    if topics=={'leave','warning'} and contains(n,'khac|phan biet|so sanh') and contains(n,'buoc thoi hoc'):
        cs=[get(root,36,3),get(root,44,2)]
        if all(cs) and all(x in norm(cs[0]['answer']) for x in ('bao luu','hoc tiep','2 tuan')) and all(x in norm(cs[1]['answer']) for x in ('buoc thoi hoc','khong dang ky hoc 2 hoc ky','het han nghi hoc tam thoi')):
            c=dict(cs[0]);c['articles']=[a for item in cs for a in item['articles']];c['answer']='\n\n'.join(item['answer'] for item in cs)
            return out('**Nghỉ học tạm thời:** sinh viên được phép tạm dừng học và bảo lưu kết quả theo các trường hợp tại khoản 3 Điều 36; có thể xin học tiếp, gửi đơn chậm nhất 2 tuần trước khi hết hạn nghỉ.\n\n**Buộc thôi học:** là xử lý học vụ theo khoản 2 Điều 44 khi thuộc trường hợp quy định, chẳng hạn vượt giới hạn cảnh báo, vượt thời gian đào tạo hoặc không đăng ký học 2 học kỳ liên tiếp. Hết thời hạn nghỉ tạm thời mà không xin học lại cũng là một trường hợp buộc thôi học. Hai hình thức không đồng nhất; cần đối chiếu quyết định và hồ sơ cụ thể.',c,'leave_warning_comparison')
    if topics=={'leave'} or topics=={'leave','retake'} and contains(n,'hoc lai|hoc tiep|tro lai'):
        c=get(root,36,3)
        if c and all(x in norm(c['answer']) for x in ('ly do ca nhan','toi thieu 01 hoc ky','tich luy','2 tuan','hoc tiep')):
            t='Xin nghỉ học tạm thời vì lý do cá nhân: cần đã học ít nhất một học kỳ, không thuộc diện xem xét buộc thôi học hoặc kỷ luật, và CPA tối thiểu 2,0. Thời gian nghỉ vì lý do cá nhân tính vào thời gian đào tạo tối đa. Khi muốn học tiếp, gửi đơn đề nghị thủ trưởng đơn vị đào tạo chậm nhất 2 tuần trước khi hết hạn nghỉ. Các trường hợp được điều động, ốm đau, thai sản hoặc tai nạn có điều kiện riêng; cần đối chiếu khoản 3 Điều 36.'
            return out(t,c,'leave_general')
    if 'graduation' in topics and topics <= {'graduation','retake','tuition'} and contains(n,'ha bang|ha hang|giam hang|giam loai|ky luat canh cao') and ('tuition' not in topics or contains(n,'tranh|mien ha|giup|khong bi ha') and not contains(n,'bao nhieu|don gia|so sanh|tinh tien')):
        from presentation import graduation_summary
        c=get(root,47,7)
        if c:
            t=graduation_summary(q,c['answer'])
            if t:
                if contains(n,'bang (?:loai )?(?:kha|trung binh)') and not contains(n,'bang (?:loai )?(?:gioi|xuat sac)|so sanh|phan biet'):
                    t='Không bị hạ hạng theo khoản 7 Điều 47 chỉ vì học lại vượt 5% nếu kết quả toàn khóa là hạng Khá hoặc Trung bình. Điều khoản này áp dụng cho hạng Giỏi hoặc Xuất sắc. '+t
                elif re.search(r'\b(?:dung|bang|bang dung)\s*5\s*%', q.casefold().replace('đ','d')) or re.search(r'\b(?:dung|bang|bang dung) 5\b',n):
                    if re.search(r'(?<!\d)5\s*%',q) and not contains(n,'hon 5|vuot 5|tren 5|vuot qua 5'):t='Đúng 5% không vượt ngưỡng 5%; riêng tiêu chí tín chỉ học lại chưa làm hạ hạng. '+t
                if 'tuition' in topics:t='Không. Việc nộp học phí học lại không phải tiêu chí để tránh hạ hạng trong khoản 7 Điều 47; điều khoản xét số tín chỉ phải học lại và kỷ luật. '+t
                if contains(n,'thi lai') and contains(n,'hoc lai'):t='Điều khoản tính khối lượng học phần phải học lại, không quy định mọi lần thi lại đều là học lại. Cần đối chiếu cách ghi nhận từng học phần. '+t
                return out(t,c,'graduation_penalty_general')
    if topics=={'graduation'} and contains(n,'can|dieu kien|tieu chi|yeu cau|dap ung') and not contains(n,'xuat sac|gioi|kha|xep loai|hang|ha bang|bao nhieu tin chi|bao nhieu diem|duoc khong|khong du tin chi'):
        from advisor_release_counsel import graduation_conditions
        canonical='Điều kiện tốt nghiệp '+('K'+str(int(re.search(r'QH-(\d+)',scope)[1])-1955) if 'QH-' in scope else '')
        result=graduation_conditions(root,canonical)
        if result and isinstance(result[0],dict) and contains(n,'chung chi') and contains(n,'ngoai ngu|tieng anh') and result[0].get('metadata',{}).get('engine_mode')=='SOURCE_CLAUSE':
            result[0]['answer']+='\n\n**Về chứng chỉ:** điều khoản yêu cầu đạt trình độ ngoại ngữ; chỉ từ điều khoản này không thể kết luận mọi sinh viên bắt buộc phải có một chứng chỉ riêng. Cần đối chiếu hướng dẫn công nhận chuẩn ngoại ngữ của đúng ngành và khóa.'
        return result
    if topics=={'retake'} and contains(n,'cai thien|khong dat|diem f|nhan f|bi f|diem cu|bat buoc|tu chon') and not contains(n,'lo trinh|ke hoach|tinh cpa|tinh gpa|bao nhieu tin chi|con no|con lai'):
        cs=[get(root,21,k) for k in (4,5)]
        if all(cs) and all(x in norm(cs[0]['answer']) for x in ('bat buoc','diem f','tu chon')) and all(x in norm(cs[1]['answer']) for x in ('diem d d','diem hoc phan cu bi huy bo','cai thien')):
            c=dict(cs[0]);c['articles']=[a for s in cs for a in s['articles']];c['answer']='\n\n'.join(s['answer'] for s in cs)
            if contains(n,'tu chon') and contains(n,'nhan f|diem f|bi f') and contains(n,'thay|doi|chon mon khac'):
                return out('Có. Với học phần tự chọn có điều kiện bị F, sinh viên có thể học lại hoặc chọn học phần khác cùng khối kiến thức để thay thế (khoản 4 Điều 21). Không áp dụng cách thay thế này cho học phần bắt buộc.',c,'retake_general')
            return out('**Học lại:** môn bắt buộc bị F phải học lại; môn tự chọn có điều kiện bị F có thể học lại hoặc chọn môn khác cùng khối kiến thức để thay thế.\n\n**Học cải thiện:** môn đạt D hoặc D+ có thể học lại (hoặc đổi môn tự chọn có điều kiện). Điểm cũ bị hủy khi đăng ký cải thiện được chấp nhận và thay bằng điểm cải thiện. Căn cứ khoản 4 và 5 Điều 21.',c,'retake_general')
    if topics=={'warning','graduation'} and contains(n,'phan biet|so sanh|khac nhau') and contains(n,'canh bao'):
        cs=[get(root,44,1),get(root,47,5),get(root,47,7)]
        if all(cs):
            c=dict(cs[0]);c['articles']=[a for item in cs for a in item['articles']];c['answer']='\n\n'.join(item['answer'] for item in cs)
            return out('Cảnh báo học vụ là việc theo dõi kết quả học tập trong từng kỳ và có thể dẫn đến xử lý học vụ; xếp loại tốt nghiệp là xác định hạng văn bằng theo CPA toàn khóa và các điều kiện hạ hạng. Không được dùng mức xếp loại văn bằng để xác định cảnh báo. Theo thông báo UET được lưu về đợt xử lý HKII 2022–2023, CPA theo năm học dùng xét cảnh báo; GPA kỳ và tín chỉ không đạt dùng xét nhắc nhở, cần kiểm tra thông báo của kỳ hiện tại. Căn cứ Điều 44 và Điều 47.',c,'warning_graduation_comparison')
    if topics=={'warning'} and contains(n,'canh bao') and contains(n,'nhac nho') and not contains(n,'buoc thoi hoc'):
        c=get(root,44,1)
        if c and c.get('notice_url') and all(v in norm(c['answer']) for v in ('de xet canh bao','de xet nhac nho','cpa theo nam thu')):
            from advisor_evidence import fresh_ledger
            if not any(h.get('source_url')==c['notice_url'] or 'tieu-chi-xet-canh-bao' in str(h.get('doc_id','')) for h in fresh_ledger(root)):
                r,_=out('Không giống nhau. Theo thông báo UET ngày 17/02/2023, áp dụng từ đợt xử lý học vụ HKII 2022–2023, CPA theo năm thứ dùng xét cảnh báo học vụ (điểm a khoản 1 Điều 44); GPA học kỳ và tín chỉ không đạt/nợ đọng dùng xét nhắc nhở (điểm b, c). Cần đối chiếu thông báo của kỳ đang xét.',c,'warning_comparison')
                r['metadata']['advisor_sources'].append({'source_url':c['notice_url'],'source_label':'Thông báo UET 17/02/2023'})
                return r,{}
    if topics=={'warning'} and contains(n,'canh bao') and contains(n,'buoc thoi hoc'):
        cs=[get(root,44,k) for k in (1,2)]
        if all(cs):
            c=dict(cs[0]);c['articles']=[a for s in cs for a in s['articles']];c['answer']='\n\n'.join(s['answer'] for s in cs)
            return out('Cảnh báo học vụ không đồng nghĩa với buộc thôi học. Cảnh báo là xử lý kết quả học tập theo kỳ; việc buộc thôi học có điều kiện riêng, trong đó có vượt giới hạn số lần cảnh báo. Không tự kết luận một sinh viên phải thôi học chỉ vì có một cảnh báo.\n\n'+cs[0]['answer']+'\n\n'+cs[1]['answer'],c,'warning_comparison')
    if topics=={'load'} and not re.search(r'\b(?:gpa|cpa|diem trung binh)\b',n):
        c=get(root,21,1)
        if c and contains(n,'ky phu|ki phu|ky he|ki he') and not contains(n,'ky chinh|ki chinh|so sanh|phan biet'):
            return out('Đối với học kỳ phụ, khoản 1 Điều 21 giao thủ trưởng đơn vị đào tạo quy định khối lượng đăng ký. Chưa có thông báo UET của kỳ phụ cụ thể để xác nhận số tín chỉ tối đa; không áp dụng trần kỳ chính thay thế.',c,'credit_load_general')
        if c:return out('Không thể xác nhận mức 24 tín chỉ chỉ từ GPA hoặc CPA. Khối lượng đăng ký phải đối chiếu tải chuẩn, loại học kỳ và tình trạng học vụ.\n\n'+c['answer'],c,'credit_load_general')
    return None


def aliases(root,q,prior):
    """Dispatch alternate phrasings into existing verified structured readers.
    No changes to the user text, dates, cohort, code, or research routing.
    """
    if prior and prior.get('kind') not in ('public_year','policy_clause'):return None
    n=norm(q)
    admin=administrative_reference(root,q,prior)
    if admin:return admin
    combined=combined_public(root,q,prior)
    if combined:return combined
    if contains(n,'mssv|ma sinh vien|ho so cua|ca lop|toan lop|em ay|ban ay|ngoai le|dac cach|hutech|uit|bach khoa|truong khac|bo qua|ignore|gia su|so sanh') or re.search(r'\b\d{8}\b',n):return None
    from advisor_source_precision import programs,academic_year
    if 'scholarship' in policy_topics(q):
        result=scholarship_policy(root,q)
        if result:return result
    from advisor_public_sections import outcomes_v2,grouped_outcomes,catalog_rows,read_source,parse_plo,public_result,src,postgraduate,org
    from reference_knowledge import cohort_request
    # Keep exact dates and codes in the original question. Use only named
    # aliases when a single program and cohort are resolved.
    cy=cohort_request(q); wanted=programs(q)
    if not wanted and contains(n,'nganh robot'):wanted={'ktrb'}
    if len(wanted)==1 and cy in range(2022,2027) and contains(n,'cdr|chuan dau ra|plo') and not contains(n,'hoc phi|hoc bong|tot nghiep|hieu luc|ap dung|chung chi cua'):
        canonical=q
        canonical=re.sub(r'(?i)\bCDR\b','chuẩn đầu ra',canonical)
        canonical=re.sub(r'(?i)\bngành Robot\b','ngành Kỹ thuật Robot',canonical)
        if contains(n,'ngoai ngu|tieng anh'):
            rows=catalog_rows(root,canonical,'team_original_uploads','learning_outcomes')
            if len(rows)==1:
                r=rows[0];rel=r['content_path'];t,sha=read_source(root,rel,r['content_sha256'],r['doc_id'])
                groups=grouped_outcomes(t);plos=parse_plo(t) if not groups else []
                vals=[v for _,items in groups for v in items] if groups else [v for _,v in plos]
                matched=[v for v in vals if contains(norm(v),'ngoai ngu|tieng anh')]
                if matched:return public_result(f'bản chuẩn đầu ra lưu trữ có nhãn QH-{cy} ghi yêu cầu ngoại ngữ:\n\n'+'\n'.join('- '+v for v in matched)+'\n\nCần xác minh hiệu lực theo đúng ngành và khóa; không đồng nghĩa chứng chỉ cá nhân đã được công nhận.',[dict(src(rel,sha),source_url=r.get('source_url'))],'outcome_language_reference')
        else:
            out=outcomes_v2(root,canonical)
            if out:return out
    if len(wanted)==1 and cy in range(2022,2027) and contains(n,'ctdt|chuong trinh (?:dao tao|ttnt|khmt|cntt|ktrb)|nganh') and not contains(n,'hoc phi|hoc bong|hoc lai|tot nghiep|tuong duong|thay the|duoc dang ky|so sanh|quy che|ngoai le|hieu luc') and set(map(int,re.findall(r'\b20\d{2}\b',n)))<={cy} and {1955+int(k) for k in re.findall(r'\bk(\d{2})\b',n)}<={cy}:
        from advisor_course_reference import CODE,relation_lookup
        codes=set(x.group().upper() for x in CODE.finditer(q))
        if len(codes)==1:
            code=next(iter(codes));program=next(iter(wanted));scope='CTĐT ngành '+__import__('advisor_source_precision').PROGRAMS[program][0]+f' QH-{cy}'
            if contains(n,'hoc mon nao truoc|hoc truoc|tien quyet'):return relation_lookup(root,f'Học phần {code} có môn tiên quyết nào trong {scope}?')
            if contains(n,'la mon gi|mon hoc gi|ten mon|ten hoc phan'):return relation_lookup(root,f'Học phần {code} có mã gì trong {scope}?')
    if contains(n,'thpt') and re.search(r'\bcn\d{1,2}\b',n) and contains(n,'lay may diem|lay bao nhieu diem|lay diem bao nhieu') and not contains(n,'nguong|du doan|xet tuyen thang|hoc bong'):
        from admission_multiyear import route
        return route('Điểm chuẩn '+q,root)
    if cy in range(2022,2026) and contains(n,'chung chi|vstep|ielts|toefl') and contains(n,'ngoai ngu|vstep|ielts|toefl') and contains(n,'nop|cap nhat') and not contains(n,'thac si|tien si|tuyen sinh'):
        from advisor_release_counsel import language
        result=language(root,f'UET QH-{cy} nộp chứng chỉ ngoại ngữ công nhận chuẩn đầu ra')
        if result:
            if contains(n,'online|truc tuyen'):result[0]['answer']='Dạ cô, em chưa xác minh được kênh nộp online hiện tại. Không nên dùng biểu mẫu đầu khóa đã hết hạn.\n\n'+result[0]['answer']
            return result
    if contains(n,'tuyen sinh sau dai hoc') and academic_year(q)==2026 and contains(n,'may bac|bao nhieu bac|gom nhung bac'):
        return postgraduate(root,'Tổng quan tuyển sinh sau đại học UET năm 2026 gồm những gì?')
    if academic_year(q) in (2022,2024,2025) and contains(n,'lich hoc|ke hoach nam hoc|ke hoach hoc tap') and not contains(n,'dang ky|lich thi|nghi le|tuan|hoc phan') and not cy:
        from advisor_source_precision import route as precision
        y=academic_year(q); sem='học kỳ II' if contains(n,'ky 2|ki 2|ky ii|ki ii') else 'học kỳ I' if contains(n,'ky 1|ki 1|ky i|ki i') else 'các kỳ'
        return precision(root,f'Lịch học {sem} năm học {y}-{y+1}',{})
    return None


def scholarship_policy(root,q):
    from advisor_public_sections import read_source,public_result,src
    from advisor_source_precision import academic_year
    n=norm(q); topics=policy_topics(q); y=academic_year(q)
    if y!=2026 or topics-{'scholarship'} or contains(n,'bao nhieu tien|so tien|dinh muc|dong thang|hoc bong ngoai ngan sach|hoc bong tai tro|ho so|cua toi|cua em|hoc bong nao dang mo|hoc bong chinh phu'):return None
    if not contains(n,'dieu kien|tieu chi|ren luyen|hieu luc|thay the|tu ky nao|tu hoc ky nao|ap dung|xet muc|xet loai|xet cap'):return None
    rel='data/raw/uet/markdown/2026/Quy_dinh_xet_hoc_bong_kkht_2026.md'
    t,sha=read_source(root,rel,'b98ee5d4a7cf1b9e5ba307a7d9a227b626be3820',git=True)
    nn=norm(t)
    anchors=('diem ren luyen dat loai tot tro len','diem trung binh chung hoc ky va diem ren luyen deu dat loai xuat sac','hoan thanh it nhat 15 tin chi','muc thap hon giua ket qua hoc tap va ket qua ren luyen','ap dung tu hoc ky i nam hoc 2026 2027','hoc ky ii nam hoc 2025 2026','khong bi ky luat tu muc khien trach tro len','thay the cho cac van ban duoc ban hanh truoc do')
    if not all(v in nn for v in anchors):return None
    if contains(n,'hieu luc|thay the|tu ky nao|tu hoc ky nao'):
        answer='Quy định KKHT ban hành kèm QĐ 1931/QĐ-ĐHCN ngày 07/08/2026 có hiệu lực từ ngày ký; áp dụng từ học kỳ I năm học 2026–2027 (xét kết quả học tập học kỳ II năm học 2025–2026), thay thế các văn bản trước đó. Căn cứ Điều 9.'
    else:
        # Compare ordinal categories rather than matching the word "xuất sắc".
        academic=re.findall(r'\b(?:hoc tap|gpa|diem hoc) (?:dat )?(?:loai )?(kha|gioi|xuat sac)\b',n)
        conduct=re.findall(r'\bren luyen (?:chi |dat )?(?:loai )?(kha|tot|xuat sac)\b',n)
        if contains(n,'xet (?:hang|loai|muc) (?:gi|nao)|duoc (?:hang|loai|muc) (?:gi|nao)') and len(set(academic))==len(set(conduct))==1 and not contains(n,'khong|so sanh|hoac'):
            ac={'kha':0,'gioi':1,'xuat sac':2};co={'kha':0,'tot':1,'xuat sac':2};levels=['Khá','Giỏi','Xuất sắc'];conduct_labels=['Khá','Tốt','Xuất sắc']
            i,j=ac[academic[0]],co[conduct[0]]
            if min(i,j)==0 and 'diem ren luyen deu dat loai kha' not in nn:return None
            lead=f'Mức xét là {levels[min(i,j)]} nếu đáp ứng các điều kiện chung: học tập {levels[i]}, rèn luyện {conduct_labels[j]}; lấy mức thấp hơn theo Điều 8. Không bảo đảm được cấp học bổng.'
        elif contains(n,'gioi') and not contains(n,'xuat sac'):
            lead='Học bổng loại Giỏi yêu cầu kết quả học tập học kỳ từ loại Giỏi trở lên và điểm rèn luyện từ loại Tốt trở lên.'
        elif contains(n,'xuat sac'):
            lead='Học bổng loại Xuất sắc yêu cầu kết quả học tập học kỳ và điểm rèn luyện đều đạt loại Xuất sắc.'
        else:
            lead='Mức xét học bổng được xác định theo mức thấp hơn giữa kết quả học tập và rèn luyện (Điều 8). Ví dụ, nếu học tập đạt loại Xuất sắc nhưng rèn luyện chỉ đạt loại Tốt thì mức xét là Giỏi.'
        answer=lead+'\n\nĐiều kiện chung: sinh viên đại học chính quy trong thời gian đào tạo chuẩn, học tập và rèn luyện từ Khá trở lên, không bị kỷ luật từ mức khiển trách trong kỳ xét; hoàn thành ít nhất 15 tín chỉ (trường hợp học kỳ cuối và trường hợp đặc biệt theo Điều 7). Số suất còn phụ thuộc nguồn kinh phí và thứ tự xét. Đây là điều kiện/mức xét, không bảo đảm được cấp học bổng. Căn cứ Điều 4, 5, 7, 8, áp dụng từ HKI 2026–2027 theo Điều 9.'
    return public_result(answer,[src(rel,sha)],'scholarship_criteria_reference')

def combined_public(root,q,prior):
    """Compose public rule families only from separately verified evidence.
    Do not attach private records, inherit unrelated context, or guess dates.
    """
    if prior or not 5<=len(q)<=700:return None
    n=norm(q);topics=policy_topics(q)
    if contains(n,'mssv|ma sinh vien|ho so|bang diem|ca lop|toan lop|em ay|ban ay|truong khac|hutech|ulis|uit|bach khoa|ngoai le|dac cach|bo qua|ignore|du dieu kien|tinh tien|bao nhieu tien|gia su|neu toi|neu em|cua toi|cua em|xac nhan|phe duyet|du doan|quy che moi|quy che cu|thong tu|nghi dinh') or re.search(r'\b\d{8}\b',n):return None
    from advisor_public_sections import read_source,public_result,src,PG,PINS
    from advisor_source_precision import academic_year
    from reference_knowledge import cohort_request
    cy=cohort_request(q);year=academic_year(q)
    if topics in ({'scholarship','graduation'},{'scholarship','load'},{'tuition','retake','graduation'}) and contains(n,'phan biet|so sanh|khac|lien quan|can kiem tra|dieu kien|tieu chi'):
        scope=scoped(q)
        # A cohort and academic year are different dimensions. No unverified
        # substitution if the question explicitly specifies other versions.
        if not scope:return None
        needed=[];parts=[]
        if 'graduation' in topics:
            cs=[get(root,46,1),get(root,47,5),get(root,47,7)]
            if not all(cs):return None
            if not all(x in norm(cs[1]['answer']) for x in ('3 60','4 00')) or '5%' not in cs[2]['answer']:return None
            needed+=cs
            if 'tuition' in topics:
                parts.append('**Hạ hạng tốt nghiệp:** khoản 7 Điều 47 QĐ 3626 xét khối lượng học phần phải học lại vượt quá 5% tổng tín chỉ chương trình, hoặc kỷ luật từ mức cảnh cáo, đối với hạng Giỏi/Xuất sắc. Số tiền học phí đã đóng không phải tiêu chí hạ hạng trong điều khoản này.')
            else:
                parts.append('**Tốt nghiệp:** theo Điều 46 và Điều 47 QĐ 3626, sinh viên phải đủ tín chỉ, CPA tối thiểu theo chương trình, chuẩn ngoại ngữ, các học phần điều kiện, thời gian đào tạo và các yêu cầu còn lại. Hạng Xuất sắc dựa trên CPA toàn khóa 3,60–4,00; hạng Giỏi hoặc Xuất sắc có thể bị hạ một hạng nếu tín chỉ phải học lại vượt 5% hoặc bị kỷ luật từ mức cảnh cáo trở lên.')
        if 'load' in topics:
            cs=[get(root,21,1),get(root,23,1)]
            if not all(cs) or not all(x in norm(cs[0]['answer']) for x in ('3 2','18 tin chi','hoc ky phu')):return None
            needed+=cs;parts.append('**Đăng ký học vượt:** Điều 21 QĐ 3626 giới hạn khối lượng kỳ chính theo tải chuẩn bình quân (tối đa 1,5 lần, có ngoại lệ học kỳ cuối và các học phần không tính vào giới hạn); Điều 23 quy định trần 18 tín chỉ kỳ chính nếu GPA kỳ dưới 2,00 và chưa bị buộc thôi học. Kỳ phụ do thủ trưởng đơn vị đào tạo quy định. Không thể mặc định mọi sinh viên được đăng ký 24 tín chỉ.')
        sources=[dict(src(c['path'],c['sha256']),source_url=c['source_url']) for c in needed]
        if 'scholarship' in topics:
            # Explicitly label the scholarship edition, not the graduation cohort.
            s=scholarship_policy(root,'Điều kiện xét học bổng KKHT năm học 2026-2027')
            if not s:return None
            sources+=s[0]['metadata']['advisor_sources']
            parts.append('**Học bổng KKHT (QĐ 1931, áp dụng từ HKI 2026–2027):** xét kết quả học tập học kỳ và rèn luyện; loại Xuất sắc cần cả hai đạt Xuất sắc. Điều kiện chung gồm thời gian đào tạo chuẩn, không bị kỷ luật từ mức khiển trách trong kỳ xét và hoàn thành ít nhất 15 tín chỉ, có quy định riêng cho kỳ cuối/trường hợp đặc biệt. Còn phụ thuộc kinh phí và thứ tự xét. Không đồng nhất với CPA toàn khóa hoặc quyền đăng ký học vượt.')
        if 'tuition' in topics:
            parts.append('**Học phí học lại:** là nghĩa vụ tài chính riêng, phụ thuộc năm học, khóa và chương trình. Chưa có đủ ba dữ kiện để tra đơn giá; không suy ra hạ hạng từ số tiền. Để tính tỷ lệ học lại cần tổng tín chỉ CTĐT và số tín chỉ phải học lại.')
        unique=list({s['source_path']:s for s in sources}.values())
        if not unique:return None
        return public_result(scope+' (phần quy chế đào tạo):\n\n'+'\n\n'.join(parts)+'\n\nCần đối chiếu từng văn bản với đúng kỳ xét và hồ sơ; không kết luận quyền lợi cá nhân.',unique,'multi_policy_composition')
    if year==2026 and contains(n,'tuyen sinh|du tuyen') and contains(n,'cao hoc|thac si') and contains(n,'dieu kien|yeu cau|can gi') and not contains(n,'tien si|online|le phi|hoc phi|chi tieu|han nop|dang ky|chung chi|ngoai ngu'):
        t,sha=read_source(root,PG,PINS[PG],git=True);t=t.replace('\\.','.');m=re.search(r'I\. TUYỂN SINH BẬC THẠC SĨ',t);p=re.search(r'II\. TUYỂN SINH BẬC TIẾN SĨ',t)
        if not m or not p or m.start()>=p.start():return None
        a=norm(t[m.end():p.start()]);anchors=('hang tot nghiep tu kha tro len hoac co cong bo khoa hoc','tieng anh tu bac 3 tro len','khong chap nhan chung chi thi online','hoan thanh hoc phan bo sung truoc khi du tuyen','co du suc khoe de hoc tap')
        if not all(x in a for x in anchors):return None
        return public_result('theo thông báo tuyển sinh thạc sĩ UET 2026, các nhóm điều kiện chính gồm:\n\n- Tốt nghiệp hoặc đủ điều kiện công nhận tốt nghiệp đại học trở lên ngành phù hợp; hạng Khá trở lên hoặc có công bố khoa học liên quan.\n- Hoàn thành học phần bổ sung nếu Hội đồng tuyển sinh yêu cầu; văn bằng nước ngoài cần được công nhận theo quy định.\n- Tiếng Anh từ bậc 3/6, có minh chứng thuộc các loại được thông báo chấp nhận; chứng chỉ phải trong thời hạn 2 năm tính từ ngày thi đến ngày đăng ký, không chấp nhận chứng chỉ thi online.\n- Lý lịch rõ ràng, không trong thời gian thi hành kỷ luật từ cảnh cáo hoặc án hình sự, đủ sức khỏe, khai hồ sơ và nộp lệ phí đúng hạn.\n\nĐối chiếu ngành phù hợp ở Phụ lục 4 và minh chứng ngoại ngữ ở Phụ lục 1, 2. Đây là điều kiện thạc sĩ, không dùng cho tiến sĩ.',[src(PG,sha)],'postgraduate_conditions_reference')
    if year in (2022,2024,2025) and contains(n,'ke hoach nam hoc|ke hoach hoc tap|lich hoc tap') and contains(n,'moc|tong quan|cac ky|thoi gian') and not contains(n,'dang ky|thi|nghi le|tuan|chuyen mon|ngay hoc|hoc phan'):
        if cy and cy>year:return None
        from calendar_source import inspect_uploaded_calendar,SEM
        rows=[]
        for sem in SEM:
            got=inspect_uploaded_calendar(root,f'{year}-{year+1}',sem)
            if got.get('status')!='READY' or len(got['hits'])!=1:return None
            rows+=got['hits']
        return public_result(f'các khoảng học kỳ trong kế hoạch năm học {year}–{year+1}:\n\n'+'\n'.join('- '+r['excerpt'] for r in rows)+'\n\nChỉ xác nhận khoảng học kỳ đã được đối chiếu; chưa đủ căn cứ xác định lịch chuyên môn hoặc mốc đăng ký riêng '+(f'của khóa QH-{cy}.' if cy else 'của từng khóa.'),list({r['source_path']:src(r['source_path'],r['sha256']) for r in rows}.values()),'calendar_interval_overview')
    if year==2023 and cy is None and contains(n,'lich|ke hoach|moc') and contains(n,'dang ky hoc phan|dang ky mon|dang ky hoc') and not contains(n,'tuyen sinh|nguyen vong|nhap hoc|thi|hoc bong'):
        rel='data/raw/uet/markdown/2023/Ke_hoach_hoc_tap_2023.md';t,sha=read_source(root,rel,'713492f4455a13a41344970765e3b9d5df6b968b',git=True)
        rows=[]
        for line in t.splitlines():
            if not line.startswith('|'):continue
            cells=line.strip().strip('|').split('|')
            dates=re.findall(r'\b\d{2}/\d{2}/20\d{2}\b','|'.join(cells[:2]))
            if len(dates)!=2:continue # merged weekly rows cannot be attributed safely
            last=norm(line.rstrip().rstrip('|').split('|')[-1]).replace('dangky','dang ky').replace('dang kyhoc','dang ky hoc')
            label=None
            if 'sv dang ky hoc hkii' in last:label='Sinh viên đăng ký học kỳ II'
            elif 'sv dang ky hoc hoc ky phu' in last:label='Thông báo thời khóa biểu và đăng ký học kỳ phụ'
            elif 'sv dang ky hoc hki nam hoc 2024 2025' in last:label='Sinh viên đăng ký học kỳ I năm học 2024–2025'
            elif 'thong bao ket qua dang ky mon' in last:label='Thông báo kết quả đăng ký môn học'
            if label:rows.append((dates,label))
        if not rows:return None
        return public_result('các mốc đăng ký học phần đọc được từ dòng tuần rõ ràng trong kế hoạch 2023–2024:\n\n'+'\n'.join(f'- {d[0]}–{d[1]}: {label}.' for d,label in rows)+'\n\nĐây là khoảng tuần theo kế hoạch, không phải giờ mở/đóng cổng. Các dòng gộp nhiều tuần không được tự gán ngày; cần đối chiếu thông báo đăng ký từng kỳ.',[src(rel,sha)],'calendar_registration_reference')
    return None


def administrative_reference(root,q,prior):
    """Curated summaries of public UET notices; no claims of current legal effect."""
    from pathlib import Path
    from advisor_public_sections import read_source,public_result,src
    from advisor_evidence import fresh_ledger
    n=norm(q)
    if prior or contains(n,'mssv|ma sinh vien|ho so cua|ca lop|em ay|ban ay|truong khac|hutech|ulis|uit|bach khoa|ngoai le|dac cach|bo qua|ignore|so sanh|thac si|tien si|gia su|gia han|qua han|tre han|so tien|bao nhieu tien|mat khau|da xac nhan|chua xac nhan') or re.search(r'\b\d{8}\b',n):return None
    # Avoid attributing the UET notes to another institution or a different year.
    years=set(re.findall(r'\b20\d{2}\b',n));cohorts=set(re.findall(r'\bk(\d{2})\b',n))
    if contains(n,'phong dao tao') and contains(n,'chuc nang|nhiem vu|lam gi|phu trach') and not contains(n,'nhap hoc|hoc phi|hoc bong|tot nghiep|lien he|email|dien thoai|dia chi|truong phong|hien nay|hien tai|moi nhat') and (not years or years=={'2017'}) and not cohorts:
        key='uet-training-office-2017-archive'
    elif contains(n,'nhap hoc') and contains(n,'xac nhan|quy trinh|thu tuc|cac buoc|can lam gi') and (years=={'2026'} or years=={'2026','2027'} or not years and cohorts=={'71'}) and (not cohorts or cohorts=={'71'}) and not contains(n,'hoc bong|hoc phi|mien giam|tot nghiep|hien nay|hien tai|moi nhat|duoc khong'):
        key='uet-enrollment-qh2026'
    else:return None
    rel='tools/academic_advisor/advisor_administration_notes.json'
    import json
    t,digest=read_source(root,rel,'76d21ed13cd95157f9b8bf5e650eeb7f36b4bad5d5b7e8a386213f629a8557f8',key)
    data=json.loads(t);row=next(x for x in data['records'] if x['id']==key)
    if any(h.get('source_url') in row['source_urls'] or h.get('doc_id')==key for h in fresh_ledger(root)):return None
    sources=[dict(src(rel,digest),source_url=u,doc_id=key,source_label='Tóm tắt nguồn công khai UET',reference_status='historical_reference') for u in row['source_urls']]
    return public_result(row['answer'],sources,'administrative_public_reference')
