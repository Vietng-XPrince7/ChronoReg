"""Read-only contextual review planner. The local model may choose views, not
facts, actions, parameters or student identities. All substantive output is
computed by the existing scoped tools. Unknown scope returns clarification.
"""
import re,json,urllib.request
from semantic_planner import MODEL
from quality import norm
VIEWS={
 'summary':'Tóm tắt phương án hiện tại và phần còn thiếu',
 'priority':'Xác định việc nên làm trước và việc có thể hoãn',
 'feasibility':'Đánh giá phương án có khả thi không, điều kiện để thực hiện',
 'risks':'Chỉ ra hạn chế, rủi ro và những gì chưa được xác minh',
 'next_steps':'Đề xuất bước tiếp theo và cách theo dõi',
}
# Restrict model fallback to an explicit reference to an existing plan or work.
# No numeric parameters, course IDs, new constraints, public/private mutations.
REFERENT=re.compile(r'\b(?:ke hoach|phuong an|lo trinh|nhiem vu|noi dung|viec|buoi gap|de xuat) (?:nay|tren|vua roi|da lap|da de xuat|cua em|cua co)\b')
REVIEW=re.compile(r'\b(?:nhan xet|danh gia|phan bien|gop y|nhin nhan|suy nghi|thay|nghi|on|hop ly|hop voi|kha thi|phu hop|thuc te|diem yeu|rui ro|han che|uu tien|bat dau|buoc tiep|theo doi|tom tat|tong hop|can luu y|bo sot|can xac minh|luu y|chac chan|kiem tra)\b')
UNSAFE=re.compile(r'\b(?:doi|sua|them|bo|thay|tang|giam|rut gon|viet|soan|gui|cong khai|phe duyet|dang ky|quy che|hoc phi|hoc bong|diem chuan|mssv|sinh vien khac|lop khac|ngoai le|lich mo lop|truoc mon|sau mon|hoc ky|mon moi|ca lop|toan lop|khong can|bo qua|khong duoc|dung|khong nhac|khong neu|khong liet ke|khong tom tat|khong danh gia|khong phan bien|khong de cap|khong noi|chi noi|chi liet ke)\b')

def eligible(n):
    safe=re.sub(r'\bem thay (?=the nao\b|sao\b)', 'em nhan xet ', n)
    # A monitoring request is not an edit; keep actual edit verbs blocked.
    safe=re.sub(r'\btheo doi\b','',safe)
    return bool(len(n)<=240 and not re.search(r'\d',n) and not UNSAFE.search(safe) and REFERENT.search(n) and REVIEW.search(n))

def explicit_views(n):
    if not eligible(n):return []
    patterns={
      'summary':r'\b(?:tom tat|tong hop)\b',
      'priority':r'\b(?:uu tien|viec nao truoc|bat dau tu dau)\b',
      'feasibility':r'\b(?:kha thi|phu hop|hop ly|thuc te|lam duoc|co the thuc hien)\b',
      'risks':r'\b(?:rui ro|han che|diem yeu|can luu y|bo sot|can xac minh|chua chac chan|can kiem tra|chua ro|thieu can cu)\b',
      'next_steps':r'\b(?:buoc tiep|theo doi|lam gi tiep)\b',
    }
    return [k for k,v in patterns.items() if re.search(v,n)]

def checked(obj):
    if not isinstance(obj,dict) or set(obj)!={'views'} or not isinstance(obj['views'],list):raise ValueError('review schema')
    vals=obj['views']
    if not 1<=len(vals)<=3 or any(type(x) is not str or x not in VIEWS for x in vals) or len(set(vals))!=len(vals):raise ValueError('review scope')
    return vals

def infer(question):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k):return None
    schema={'type':'object','properties':{'views':{'type':'array','items':{'type':'string','enum':list(VIEWS)},'minItems':1,'maxItems':3}},'required':['views'],'additionalProperties':False}
    # Local-only request. No roster, prior raw answer or student identifier.
    body={'model':MODEL,'messages':[{'role':'system','content':'Chỉ chọn loại đánh giá kế hoạch đã có; không trả lời hay lập kế hoạch mới. '+json.dumps(VIEWS,ensure_ascii=False)},{'role':'user','content':question}],'format':schema,'stream':False,'think':False,'options':{'temperature':0,'num_predict':48,'num_ctx':1024,'num_gpu':0}}
    req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=30) as r:d=json.load(r)
    if d.get('done_reason')!='stop':raise ValueError('incomplete review plan')
    return checked(json.loads(d['message']['content']))

def plan(question,enabled=False):
    n=norm(question)
    if not eligible(n):return [],None
    views=explicit_views(n)
    if views:return views,'explicit_review'
    if re.search(r'\b(?:em thay the nao|em nghi sao|em nghi the nao|em thay sao)\b',n):
        return ['feasibility','risks'],'explicit_review'
    if enabled:
        try:return checked({'views':infer(question)}),'local_model_review'
        except (OSError,ValueError,TypeError,KeyError):return [],'review_unresolved'
    return [],'review_unresolved'
