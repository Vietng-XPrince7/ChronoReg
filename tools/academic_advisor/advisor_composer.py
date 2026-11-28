"""Conservative extractive answer composition. No model-authored factual claims.
A focus is an exact source substring; preserve the whole paragraph and all qualifiers.
"""
import re
from quality import norm


def compose(question, passage, focus=None):
    text=passage.text
    # Only select whole word spans; no invented wording, negation or numbers.
    if not isinstance(focus,str) or not 12<=len(focus)<=950 or focus not in text or text.count(focus)!=1:
        focus=None
    if focus:
        pos=text.index(focus); end=pos+len(focus)
        if (pos and text[pos-1].isalnum() and focus[0].isalnum()) or (end<len(text) and text[end].isalnum() and focus[-1].isalnum()) or re.search(r'[<>|`*#]',focus):focus=None
    if focus:
        pos=text.index(focus)
        # Do not emphasize a fragment detached from a nearby negation or bound.
        before=norm(text[max(0,pos-65):pos]); f=norm(focus)
        if re.search(r'\b(?:khong|chua|chi|khong duoi|khong qua|toi thieu|toi da|it nhat|nhieu nhat|tu|duoi|tren)$',before):focus=None
        elif not re.search(r'[a-z]',f):focus=None
    # A short answer is an exact extract, never a paraphrase. Keep the
    # complete verified passage immediately visible to preserve exceptions.
    label=passage.title
    if focus:
        # A full negative predicate or bounded quantitative phrase can be placed
        # first, but no synthesized yes/no or reinterpretation of comparators.
        # A complete sentence can answer directly; leave the whole original
        # clause visible below if the preceding sentences contain qualifications.
        if focus==text:
            return 'Dạ cô, theo '+label+':\n\n'+text
        if re.search(r'[.!?]$',focus) and (pos==0 or re.search(r'[.!?]\s+$',text[:pos])):
            return 'Dạ cô, '+focus+'\n\n**Căn cứ: '+label+'**\n\n'+text
        highlighted=text.replace(focus,'**'+focus+'**',1)
        result='Dạ cô, theo '+label+':\n\n'+highlighted
        # Only lead with a literal bounded or negative predicate. No new
        # yes/no assertion; the entire source remains part of the answer.
        f=norm(focus)
        if len(focus)<=150 and focus[-1] not in ',;:' and re.search(r'\b(?:khong duoi|khong qua|toi thieu|toi da|it nhat|khong dung|khong duoc|khong phai)\b',f):
            result='Dạ cô, nội dung cần lưu ý là **'+focus+'**\n\n**Căn cứ: '+label+'**\n\n'+text
    else:
        result='Dạ cô, '+label+' ghi:\n\n'+text
    return result



# Independent, conservative lexical relevance check. It is NOT entailment.
# This check never introduces facts or changes the selected document/paragraph.
_FOCUS_STOP=set("theo qd quyet dinh quy che dieu khoan sinh vien hoc tap co em gi nao nhu the nao bao nhieu bao lau khi nao hay cua va la cho trong den duoc can phai ve mot cac nhung neu thi nay do ay tren duoi tu ra tai voi bi khong da se dang hien tai".split())

def _words(text):
    return [x for x in norm(text).split() if len(x)>1 and x not in _FOCUS_STOP and not x.isdigit()]

def assess_focus(question, spans, proposed):
    """Return (decision, literal span). Reject ambiguity instead of promoting
    a merely authentic sentence. Preserve the complete verified clause later.
    """
    if not spans:return ('no_focus',None)
    n=norm(question)
    # Multi-condition requests must preserve the whole provision, not imply
    # that a single selected sentence is the entire list of conditions.
    if re.search(r'\b(?:nhung dieu kien|cac dieu kien|tat ca|liet ke|day du|nguyen van|so sanh|giai thich)\b',n):return ('whole_clause',None)
    q=set(_words(question)); vocab=[set(_words(x)) for x in spans]
    if len(q)<2:return ('no_focus',None)
    # Distinctive question terms carry greater weight than common terms in
    # the passage. Also reward contiguous normalized phrase matches.
    weights={w:1+2*(sum(w in v for v in vocab)==1) for w in q}
    qseq=_words(question);pairs=set(zip(qseq,qseq[1:]))
    scores=[]
    for j,span in enumerate(spans):
        seq=_words(span); hits=q&vocab[j]; pairhits=pairs&set(zip(seq,seq[1:]))
        score=sum(weights[w] for w in hits)+2*len(pairhits)
        scores.append((score,len(hits),j))
    ordered=sorted(scores,reverse=True);best=ordered[0]; runner=ordered[1][0] if len(ordered)>1 else 0
    if best[1]<2 or best[0]<4 or best[0]-runner<max(2,best[0]*.18):return ('ambiguous_focus',None)
    span=spans[best[2]]
    # A paragraph fragment or a reference depending on another paragraph is
    # not a standalone answer. Use it only in-place, with the entire clause.
    if not re.search(r'[.!?]$',span) or re.search(r'^\s*(?:[a-zđ]\)|[-•])',span,re.I):return ('context_only',span)
    if proposed!=span:return ('selector_disagrees',span)
    return ('agreed_focus',span)

def compose_evidence(passage, spans, decision):
    """Display the source once. Only promote a complete sentence when the
    selector and independent lexical check agree; preserve every other span.
    The untouched original clause is also retained in response metadata.
    """
    status,focus=decision
    if not spans or ' '.join(spans)!=passage.text:
        spans=[passage.text];focus=None;status='whole_clause'
    label=passage.title
    # Keep all legal list labels in original order; break into readable lines
    # only when a contiguous a), b), ... sequence can be identified.
    def readable(x):
        marks=list(re.finditer(r'(?<!\S)([a-zđ])\)\s+',x))
        if len(marks)>=2 and marks[0][1]=='a' and [m[1] for m in marks] == list('abcdeghiklmnopqrstu')[:len(marks)]:
            x=re.sub(r'(?<!\S)([a-zđ])\)\s+',r'\n\1) ',x).strip()
            x='\n'.join(line.rstrip() for line in x.splitlines())
        return x
    if status=='agreed_focus' and focus in spans and len(spans)>1 and spans.count(focus)==1 and not re.search(r'^\s*(?:truong hop (?:nay|tren|do)|cac doi tuong tren|ngoai ra|tuy nhien|dong thoi)\b',norm(focus)):
        others=[readable(x) for x in spans if x!=focus]
        return 'Dạ cô, '+re.sub(r'^\d{1,2}\.\s+','',focus)+'\n\n**Căn cứ: '+label+'**\n\n**Nội dung còn lại của khoản để đối chiếu:**\n\n'+'\n\n'.join(others)
    # Disagreement: never lead with the rejected model selection. Highlight
    # only in the original context, so all conditions remain visible.
    parts=[('**'+x+'**' if x==focus and len(x)<500 else readable(x)) for x in spans]
    return 'Dạ cô, theo '+label+':\n\n'+'\n\n'.join(parts)

def clarify(question, prior):
    """Only unambiguous missing-scope patterns; never guess a source."""
    n=norm(question)
    if not prior:
        from advisor_mission import mission_review_request
        from mission_intent import eligible
        if mission_review_request(n) or eligible(n):
            return 'Dạ cô, phiên này chưa có phương án để đối chiếu. Cô muốn em xem lại kế hoạch nào?'
    if not prior and re.fullmatch(r'(?:the|vay|con)?\s*(?:neu )?(?:diem (?:danh gia )?bo phan|tuong duong) (?:la |bang )?\d+(?: \d+)?(?: thi sao)?',n):
        return 'Dạ cô, cô muốn đối chiếu điều kiện nào trong quy chế với dữ kiện này?'
    # A named edition plus an unverified cohort is not an article lookup.
    # Do not pretend the applicability of a provision has been established.
    explicit_qd='3626' in n or (prior.get('kind')=='advisor_agent' and prior.get('topic')=='evidence_article')
    if explicit_qd and re.search(r'\b(?:ap dung|hieu luc|con hieu luc|con dung|xac nhan)\b',n):
        cohorts=re.findall(r'\bk(\d{2})\b',n)
        years=re.findall(r'\bqh (20\d{2})\b',n)
        if len(cohorts)+len(years)==1:
            year=int(years[0]) if years else 1955+int(cohorts[0])
            if not 2022<=year<=2025:
                label='K'+cohorts[0] if cohorts else 'QH-'+years[0]
                return 'Dạ cô, em chưa có căn cứ xác nhận QĐ 3626 áp dụng cho khóa '+label+'. Cần đối chiếu văn bản có hiệu lực đối với khóa đó; không mặc định dùng quy chế của khóa khác.'
    if re.fullmatch(r'(?:con|the|vay|trich|xem|doc)?\s*khoan \d{1,2}(?: thi sao| quy dinh gi)?',n) and not (prior.get('kind')=='advisor_agent' and prior.get('topic')=='evidence_article'):
        return 'Dạ cô, cô muốn xem khoản đó thuộc điều nào, trong văn bản nào?'
    if re.search(r'\bhoc bong\b',n) and re.search(r'\b(?:ho so|giay to|dang ky|nop don)\b',n) and not re.search(r'\b(?:khuyen khich hoc tap|tai tro|chinh sach|ten hoc bong|hoc bong [a-z0-9]+(?: [a-z0-9]+)? (?:nam|cua|do))\b',n):
        return 'Dạ cô, cô muốn tra hồ sơ của loại học bổng nào? Ví dụ học bổng khuyến khích học tập hay học bổng do một đơn vị tài trợ. Em cần xác định đúng chương trình trước khi đối chiếu giấy tờ.'
    if re.search(r'\b(?:nghien cuu khoa hoc|nckh)\b',n) and re.search(r'\b(?:han dang ky|han nop|cham nhat)\b',n) and not re.search(r'\b(?:khoa|vien|cap truong|toan truong|cap dhqghn|cap don vi)\b',n.replace('nghien cuu khoa hoc','nckh')):
        return 'Dạ cô, cô muốn tra hạn đăng ký của toàn trường hay của một khoa/viện cụ thể? Các đơn vị có thể có thông báo riêng; em chưa thể xác định một hạn chung từ nguồn hiện có.'
    return None
