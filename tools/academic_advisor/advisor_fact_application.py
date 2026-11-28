"""Bounded application of public policy to supplied hypothetical facts.
Numeric slots preserve decimal separators; no roster lookup or personal approval.
"""
import re,unicodedata
from decimal import Decimal
from quality import norm
from advisor_quality_gate import contains, scoped, get
from quality_routes import source_response


def numeric_slots(q):
    # Preserve decimal punctuation before the general lexical normalizer.
    t=unicodedata.normalize('NFKD',q.lower().replace('đ','d'))
    t=''.join(c for c in t if not unicodedata.combining(c))
    patterns={'cpa':r'\b(?:cpa|gpa tich luy|diem trung binh (?:chung )?tich luy)', 'gpa':r'\b(?:gpa (?:hoc )?ky(?: truoc| nay)?|diem trung binh (?:chung )?hoc ky)'}
    out={}
    for key,p in patterns.items():
        values=re.findall(p+r'\s*(?:la\s*|[:=]\s*)?(\d+(?:[.,]\d+)?)(?!\d|[.,]\d)',t)
        vals={Decimal(v.replace(',','.')) for v in values}
        if len(vals)==1 and 0<=next(iter(vals))<=4:out[key]=next(iter(vals))
    return out


def fmt(x):return format(x,'f').replace('.',',')


def route(root,q,prior):
    if prior:return None
    n=norm(q);scope=scoped(q)
    if contains(n,'mssv|ma sinh vien|ho so|bang diem|ca lop|toan lop|em ay|ban ay|sinh vien nay|hutech|ulis|uit|bach khoa|truong khac|ngoai le|dac cach|bo qua|ignore|system prompt|tam khoa|chua duyet|hien nay|moi nhat|chua xac minh') or re.search(r'\b\d{8}\b',n):return None
    from advisor_public_sections import public_result,src,catalog_rows,read_source,parse_plo,grouped_outcomes
    from advisor_source_precision import academic_year,programs,PROGRAMS
    from advisor_quality_gate import administrative_reference
    def out(body,cs,tag):
        c=dict(cs[0]);c['articles']=[a for x in cs for a in x.get('articles',[])];c['answer']='\n\n'.join(x['answer'] for x in cs)
        r=source_response('Dạ cô, '+scope+':\n\n'+body+'\n\nĐây là đối chiếu các dữ kiện giả định, không phải quyết định học vụ cá nhân.',tag,c)
        r['metadata']['advisor_intent']=tag
        return r,{}
    slots=numeric_slots(q)
    instruments=re.findall(r'\b(?:qd|quyet dinh) (\d+)\b',n)
    if scope and all(x=='3626' for x in instruments):
        # A disciplinary ground is independent of the retake-credit ground.
        if 'cpa' in slots and contains(n,'tot nghiep|bang gioi|bang xuat sac|hang gioi|hang xuat sac|hang tot nghiep') and contains(n,'bi canh cao ky luat|bi ky luat (?:tu muc )?canh cao|bi canh cao|ky luat canh cao') and not contains(n,'khong bi|chua bi|neu khong|gia dinh khong|duoc xoa|hoc lai|thi lai|bao luu|hoc bong'):
            cs=[get(root,47,5),get(root,47,7)]
            if all(cs) and all(v in norm(cs[0]['answer']) for v in ('3 60','3 20','2 50','3 59','4 00')) and all(v in norm(cs[1]['answer']) for v in ('canh cao','ha mot hang','xuat sac hoac gioi')):
                cpa=slots['cpa']
                if Decimal('3.60')<=cpa<=4:before,after='Xuất sắc','Giỏi'
                elif Decimal('3.20')<=cpa<=Decimal('3.59'):before,after='Giỏi','Khá'
                else:return None
                return out(f'Không giữ được hạng {before} nếu đã bị kỷ luật cảnh cáo trong thời gian học. CPA {fmt(cpa)} tương ứng hạng {before} trước khi xét hạ hạng; theo khoản 5 và 7 Điều 47, bị hạ một hạng xuống **{after}** nếu đáp ứng các điều kiện tốt nghiệp khác. Không cần biết số tín chỉ học lại để xác định riêng căn cứ kỷ luật này.',cs,'rank_discipline_application')
        if 'gpa' in slots and contains(n,'18 tin chi|18 tc') and contains(n,'ky chinh|ki chinh') and contains(n,'cpa|tich luy') and not contains(n,'ky phu|ki phu|ky he|ki he|hoc bong|tot nghiep|so sanh'):
            cs=[get(root,21,1),get(root,23,1)]
            if all(cs) and all(v in norm(cs[1]['answer']) for v in ('hoc ky duoi 2 00','18 tin chi')) and '3 2' in norm(cs[0]['answer']):
                g=slots['gpa'];c=slots.get('cpa')
                lead=f'GPA học kỳ trước {fmt(g)} không dưới 2,00, nên không kích hoạt riêng trần 18 tín chỉ theo khoản 1(c) Điều 23.' if g>=2 else f'GPA học kỳ trước {fmt(g)} dưới 2,00, nên nếu chưa thuộc diện buộc thôi học thì giới hạn kỳ chính là 18 tín chỉ theo khoản 1(c) Điều 23.'
                return out(lead+(f' CPA {fmt(c)} là chỉ số khác; ' if c is not None else ' CPA là chỉ số khác; ')+'không thể khẳng định trần 18 tín chỉ chỉ từ CPA. Vẫn phải đối chiếu tải chuẩn tối đa 1,5 lần và tình trạng học vụ theo Điều 21.',cs,'credit_load_fact_application')
        if 'cpa' in slots and contains(n,'bao luu|nghi hoc tam thoi|tam dung hoc') and contains(n,'ly do ca nhan|viec rieng|ly do rieng') and not contains(n,'tai nan|thai san|om dau|quan su|dieu dong|hoc bong|tot nghiep|so sanh'):
            c=get(root,36,3)
            if c and all(v in norm(c['answer']) for v in ('toi thieu 01 hoc ky','tich luy toi thieu 2 0','ly do ca nhan')):
                v=slots['cpa'];lead=f'CPA {fmt(v)} '+('chưa đáp ứng' if v<2 else 'đáp ứng riêng')+' ngưỡng CPA tối thiểu 2,0 để xin nghỉ học tạm thời vì lý do cá nhân.'
                return out(lead+' Khoản 3 Điều 36 còn yêu cầu đã học ít nhất một học kỳ và không thuộc diện xem xét buộc thôi học hoặc kỷ luật. Thỏa mãn ngưỡng CPA không đồng nghĩa được duyệt bảo lưu.',[c],'leave_cpa_application')
        if contains(n,'tai nan') and contains(n,'nghi|tam dung|bao luu') and contains(n,'thoi gian dao tao toi da|thoi gian toi da') and not contains(n,'ly do ca nhan|viec rieng|so sanh|hoc bong|tot nghiep'):
            c=get(root,36,3)
            if c and all(v in norm(c['answer']) for v in ('tai nan phai dieu tri','khong tinh vao thoi gian toi da','co so kham benh')):
                return out('Không tính vào thời gian đào tạo tối đa nếu thuộc trường hợp tai nạn phải điều trị dài ngày và có chứng nhận của cơ sở khám chữa bệnh có thẩm quyền. Căn cứ điểm c khoản 3 Điều 36 và phần quy định thời gian nghỉ cho các trường hợp a, b, c.',[c],'leave_exception_application')
    # Compare separate, verified source scopes; do not merge cohort metadata.
    if academic_year(q)==2026 and contains(n,'thac si') and contains(n,'tien si') and contains(n,'tuyen sinh|du tuyen') and contains(n,'ngoai ngu|tieng anh|chung chi') and contains(n,'khac|so sanh|toi thieu') and not contains(n,'nuoc ngoai|mien|quy doi|ielts|toefl|vstep|hoc phi|le phi|online') and set(re.findall(r'\b20\d{2}\b',n))=={'2026'}:
        from advisor_public_sections import PG,PINS
        t,sha=read_source(root,PG,PINS[PG],git=True);t=' '.join(t.replace('\\.','.').split());m=re.search(r'I\. TUYỂN SINH BẬC THẠC SĨ',t);p=re.search(r'II\. TUYỂN SINH BẬC TIẾN SĨ',t)
        if not m or not p or m.start()>=p.start():return None
        ms=norm(t[m.end():p.start()]);ph=norm(t[p.end():]);
        if 'tieng anh tu bac 3 tro len' in ms and 'chung chi ngoai ngu dat trinh do tuong duong bac 4 tro len' in ph and 'trong thoi han 2 nam' in ms and 'trong thoi han 2 nam' in ph:
            return public_result('theo thông báo tuyển sinh UET 2026, nếu sử dụng chứng chỉ thuộc danh mục được chấp nhận: **Thạc sĩ:** tiếng Anh từ bậc 3/6 trở lên. **Tiến sĩ (công dân Việt Nam):** ngoại ngữ tương đương bậc 4/6 trở lên. Chứng chỉ phải trong thời hạn 2 năm tính từ ngày thi đến ngày đăng ký dự tuyển. Đây là so sánh yêu cầu chứng chỉ, không phải toàn bộ các hình thức minh chứng hoặc xác nhận đủ điều kiện.',[src(PG,sha)],'postgraduate_language_comparison')
    years={int(y) for y in re.findall(r'\b(?:qh|khoa) (20\d{2})\b',n)}|{1955+int(k) for k in re.findall(r'\bk(\d{2})\b',n)}
    if len(years)==2 and years.issubset(range(2022,2027)) and set(map(int,re.findall(r'\b20\d{2}\b',n))).issubset(years) and contains(n,'chuan dau ra|cdr|plo') and contains(n,'cach trinh bay|cau truc|so sanh|khac nhau') and not contains(n,'hieu luc|tuong duong|ap dung|ngoai ngu|hoc phi|hoc bong|tot nghiep|tien quyet|chung chi'):
        wanted=programs(q) or ({'ktrb'} if contains(n,'nganh robot') else set())
        if len(wanted)!=1:return None
        program=PROGRAMS[next(iter(wanted))][0]; parts=[];sources=[]
        for y in sorted(years):
            rows=catalog_rows(root,f'{program} QH-{y}','team_original_uploads','learning_outcomes')
            if len(rows)!=1:return None
            row=rows[0];rel=row['content_path'];t,sha=read_source(root,rel,row['content_sha256'],row['doc_id']);plos=parse_plo(t)
            if plos:label=f'{len(plos)} yêu cầu có nhãn PLO riêng ({plos[0][0]} đến {plos[-1][0]} trong bản đọc được)'
            else:
                groups=grouped_outcomes(t)
                if not groups:return None
                label=f'{sum(len(v) for _,v in groups)} yêu cầu theo {len(groups)} nhóm: '+', '.join(k for k,_ in groups)+'; phần mô tả không gắn nhãn PLO riêng'
            parts.append(f'- QH-{y}: {label}.');sources.append(src(rel,sha))
        return public_result('đối chiếu cách trình bày chuẩn đầu ra của hai bản lưu:\n\n'+'\n'.join(parts)+'\n\nĐây là so sánh cấu trúc văn bản; không suy ra hai chương trình tương đương hoặc yêu cầu bị loại bỏ. Phạm vi theo nhãn bản lưu.',sources,'outcomes_version_comparison')
    if contains(n,'uet|dai hoc cong nghe|qh 2026|k71') and contains(n,'nop minh chung') and contains(n,'xet tuyen') and contains(n,'han|ngay nao|khi nao') and contains(n,'truc tuyen|online') and not contains(n,'gia han|qua han|tre han|thac si|tien si|hoc phi') and (set(re.findall(r'\b20\d{2}\b',n))=={'2026'} or years=={2026}) and not (years-{2026}):
        r=administrative_reference(root,'Quy trình xác nhận nhập học UET 2026?',{})
        if r and '03/09/2026' in r[0]['answer']:
            r[0]['answer']='Dạ cô, theo thông báo cập nhật UET cho tân sinh viên QH-2026, hạn nộp minh chứng xét tuyển trực tuyến là **03/09/2026** (đợt từ 15/08 đến 03/09/2026), qua StudentHub. Đây là mốc lịch sử, không xác nhận gia hạn hoặc cổng còn mở.'
            return r
    return None
