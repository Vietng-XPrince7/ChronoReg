"""Restricted reviewed facts from official UET adjustment; not original signed decision."""
import hashlib,json,re
from pathlib import Path
from quality import norm
REL='data/advisor_sources/tuition_history/adjustment_2022_ug.json'
PIN='a25cb5cd2ba15900877b42efd7559c83c10b5c7053bc4c0037a8678895f73971'
DOC='uet-advisor-fee-adjustment-2022-undergraduate'

def adjusted_standard(root,cohort,question):
    # Never reinterpret historical, special-program, nationality, payment or combined queries.
    n=norm(question)
    if type(cohort) is not int or not 2018<=cohort<=2022:return None
    if re.search(r'\b(?:ban dau|truoc dieu chinh|truoc khi|truoc thang|thoi diem|du kien|tt 23|thong tu 23|clc|chat luong cao|dmktkt|dinh muc kinh te ky thuat|bang kep|nuoc ngoai|quoc tich|lao|campuchia|thac si|tien si|sau dai hoc|mien|giam|hoc bong|nop|dong khi nao|lich thu|so sanh|tinh tong|tong tien|bao nhieu tin chi|thu tuc)\b',n):return None
    if re.search(r'\b(?:ngay|thang) \d{1,2}\b',n):return None
    root=Path(root).resolve();p=root/REL;ledger=root/'data/versioning/publication_holds.jsonl'
    try:
        if p.resolve()!=p or not ledger.is_file():return None
        raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!=PIN:return None
        v=json.loads(raw)
        for line in ledger.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():continue
            h=json.loads(line);ident=norm(str(h.get('doc_id',''))+' '+str(h.get('source_path',''))+' '+str(h.get('content_path','')))
            if h.get('doc_id')==DOC or h.get('content_sha256')==PIN or REL in (h.get('source_path'),h.get('content_path')) or ('2022' in ident and 'hoc phi' in ident and 'dieu chinh' in ident):return None
        r=v['rates'];fmt=lambda x:f'{x:,}'.replace(',','.')
        answer=f"Dạ cô, định mức điều chỉnh cho năm học 2022–2023 đối với đại học hệ chính quy, CTĐT chuẩn (sinh viên Việt Nam, khóa QH-{cohort}):\n• {fmt(r['month'])} đồng/tháng theo định mức.\n• {fmt(r['academic_year_10_months'])} đồng/năm học (10 tháng).\n• {fmt(r['credit'])} đồng/tín chỉ; áp dụng cả học lần đầu, học lại, cải thiện điểm và tự chọn tự do.\nNguồn UET công bố 12/04/2023, Điều 1 và Điều 3, điều chỉnh mức áp dụng cả năm học. {v['qualification']}"
        return {'answer':answer,'year':2022,'path':REL,'sha256':digest,'source_url':v['source_url'],'table_kind':'tuition_rate','doc_id':DOC}
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None
