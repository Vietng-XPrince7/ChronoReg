"""Deterministic hypothetical credit-weighted GPA tool. No roster inference.
Only an explicit scenario with labeled inputs is accepted, not an eligibility ruling.
"""
from decimal import Decimal, ROUND_HALF_UP
import re
from quality import norm

NUM=r'([+-]?\d{1,3}(?:[.,]\d{1,2})?)(?!\d|[.,]\d)'
FIELDS={
 'cpa':r'\b(?:cpa|gpa tích lũy|điểm trung bình tích lũy|điểm trung bình chung tích lũy)\s*(?:hiện tại|ban đầu)?\s*[:=]?\s*'+NUM,
 'earned':r'\b(?:đã tích lũy|tín chỉ tích lũy|tín chỉ đã tích lũy|số tín chỉ hiện tại)\s*[:=]?\s*'+NUM+r'(?:\s*tín chỉ)?',
 'new':r'\b(?:học thêm|tích lũy thêm|tín chỉ mới|số tín chỉ mới)\s*[:=]?\s*'+NUM+r'(?:\s*tín chỉ)?',
 'gpa':r'\b(?:gpa(?: kỳ tới| học kỳ tới| mới| kỳ mới| học kỳ mới| dự kiến)|điểm trung bình kỳ tới)\s*[:=]?\s*'+NUM,
}
GOAL=r'\b(?:mục tiêu cpa|cpa mục tiêu|cpa mong muốn|mục tiêu gpa tích lũy|gpa tích lũy mục tiêu|gpa tích lũy mong muốn)\s*[:=]?\s*'+NUM
TRIGGER=re.compile(r'\b(?:gia su|mo phong|what if|neu)\b')
EXAMPLE='Giả sử CPA hiện tại 2,50; đã tích lũy 60 tín chỉ; học thêm 15 tín chỉ; GPA kỳ tới 3,50. Tính CPA mới.'
GOAL_EXAMPLE='Mô phỏng CPA hiện tại 2,50; đã tích lũy 60 tín chỉ; học thêm 15 tín chỉ; CPA mục tiêu 2,80.'

def format_d(x,places=2):
    return str(x.quantize(Decimal('1').scaleb(-places),rounding=ROUND_HALF_UP)).replace('.',',')

def simulate(question):
    q=norm(question)
    if not TRIGGER.search(q) or not re.search(r'\b(?:cpa|gpa tich luy|diem trung binh (?:chung )?tich luy)\b',q):return None
    # Only handle explicit calculations, not mixed administrative/eligibility queries.
    if re.search(r'\b(?:hoc bong|hoc phi|du dieu kien|tot nghiep|canh bao|buoc thoi hoc|chuyen nganh|bao luu|rut hoc phan|hoc vuot|ngoai le|hoc lai|cai thien diem|thay diem|thay the|khong dat|khong qua mon)\b',q):return None
    def incomplete(reason):
        return {'answer':reason+'\n\nĐể mô phỏng, thầy/cô có thể nhập:\n'+EXAMPLE+'\nHoặc: '+GOAL_EXAMPLE+'\nChỉ dùng CPA tích lũy độc lập và số tín chỉ thực sự được tính vào CPA, không dùng GPA học kỳ thay CPA.', 'status':'needs_inputs','inputs':{}}
    # Goal phrase contains CPA too: remove it before parsing current CPA.
    goals=re.findall(GOAL,question,re.I); rest=re.sub(GOAL,'',question,flags=re.I)
    # Natural sentence forms: CPA X with N credits; next semester M credits at GPA Y.
    alternatives={
        'earned': r'\b(?:cpa|gpa tích lũy|điểm trung bình tích lũy|điểm trung bình chung tích lũy)\s*(?:hiện tại|ban đầu)?\s*[:=]?\s*[+-]?\d{1,3}(?:[.,]\d{1,2})?\s+(?:với|trên)\s+'+NUM+r'\s*(?:tín chỉ|tc)\b',
        'new': r'\b(?:kỳ tới|học kỳ tới|kỳ sau|học kỳ sau|kỳ mới)\s+(?:học|tích lũy)\s+'+NUM+r'\s*(?:tín chỉ|tc)\b',
        'gpa': r'\b(?:kỳ tới|học kỳ tới|kỳ sau|học kỳ sau|kỳ mới)\s+(?:học|tích lũy)\s+[+-]?\d{1,3}(?:[.,]\d{1,2})?\s*(?:tín chỉ|tc)\s+(?:và\s+)?(?:đạt|có)\s+gpa\s*[:=]?\s*'+NUM,
    }
    values={}
    for key,pattern in FIELDS.items():
        matches=re.findall(pattern,rest,re.I)
        if key in alternatives:matches+=re.findall(alternatives[key],rest,re.I)
        if len(matches)>1:return incomplete('Có nhiều giá trị cho cùng một trường. Hãy nhập một kịch bản tại một thời điểm.')
        if matches:values[key]=Decimal(matches[0].replace(',','.'))
    if len(goals)>1:return incomplete('Có nhiều CPA mục tiêu; vui lòng chọn một mục tiêu.')
    if goals:values['goal']=Decimal(goals[0].replace(',','.'))
    if not {'cpa','earned','new'}.issubset(values) or not ('gpa' in values or 'goal' in values):return incomplete('Chưa đủ giả định để tính CPA mới hoặc GPA cần đạt.')
    if 'gpa' in values and 'goal' in values:return incomplete('Hãy chọn tính CPA mới từ GPA dự kiến hoặc tính GPA cần đạt từ CPA mục tiêu, không nhập cả hai.')
    if any(not 0<=values[k]<=4 for k in ('cpa','gpa','goal') if k in values):return incomplete('CPA và GPA phải nằm trong thang 0–4.')
    if any(values[k]!=values[k].to_integral_value() or not 1<=values[k]<=500 for k in ('earned','new')):return incomplete('Số tín chỉ cần là số nguyên dương, trong phạm vi 1–500.')
    c,n,m=values['cpa'],values['earned'],values['new'];total=n+m
    out={'inputs':{k:str(v) for k,v in values.items()},'status':'calculated'}
    lead=f'Với giả định GPA tích lũy (CPA) hiện tại {format_d(c)}, {int(n)} tín chỉ đã tính vào CPA và {int(m)} tín chỉ mới:'
    if 'gpa' in values:
        g=values['gpa'];result=(c*n+g*m)/total;out['projected_cpa']=str(result)
        calculation=f'GPA tích lũy (CPA) dự kiến = ({format_d(c)} × {int(n)} + {format_d(g)} × {int(m)}) / {int(total)} = {format_d(result)}.'
        advice='Đề xuất cho cố vấn: dùng kết quả để thảo luận mục tiêu kỳ tới; đối chiếu từng học phần và giới hạn đăng ký trước khi chốt kế hoạch.'
    else:
        g=values['goal'];result=(g*total-c*n)/m;out['required_gpa']=str(result)
        calculation=f'GPA học kỳ cần đạt = ({format_d(g)} × {int(total)} − {format_d(c)} × {int(n)}) / {int(m)} = {format_d(result)}.'
        if result>4:advice='Mục tiêu này không đạt được trong kịch bản đã nhập vì GPA cần thiết vượt thang 4. Cần điều chỉnh mục tiêu hoặc phân bổ lộ trình qua nhiều kỳ.'
        elif result<=0:advice='Trong mô hình giả định này, mục tiêu không đòi hỏi GPA dương ở kỳ mới. Tuy nhiên, vẫn phải đạt yêu cầu học tập thực tế.'
        else:advice='Đề xuất cho cố vấn: thảo luận mục tiêu này với sinh viên, xem xét độ khó và lịch mở lớp của các học phần; không coi đây là kết quả đảm bảo.'
    out['answer']=lead+'\n\n'+calculation+'\n\n'+advice+'\n\nGiả định mọi tín chỉ mới đều được tính vào CPA theo trọng số tín chỉ, không thay thế điểm học lại, không loại trừ học phần và không xét quy tắc làm tròn riêng của trường. Đây là mô phỏng, không phải xác nhận học vụ.'
    return out
