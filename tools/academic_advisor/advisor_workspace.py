"""Local, explicit-confirmation advisor action tracking. No model calls or official decisions."""
import hashlib, json, os, sqlite3, secrets
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from contextlib import closing
from urllib.parse import urlsplit
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Literal
from workflow import screening

GOALS={'graduation':'Hỗ trợ tốt nghiệp đúng hạn','improvement':'Cải thiện kết quả học tập','daily':'Ưu tiên hỗ trợ trước mắt'}
STATES=('todo','doing','blocked','done')

def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(obj):return hashlib.sha256(canonical(obj).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def scope_for(roster):
    if not roster.get('students') or not (roster.get('class_short') or roster.get('class_id')):raise ValueError('Chưa có hồ sơ lớp hợp lệ.')
    # Deliberately isolate snapshots (including regenerated demos with reused IDs).
    return digest(roster)

def proposal(roster,goal,days,today=None):
    if goal not in GOALS or type(days) is not int or not 1<=days<=90:raise ValueError('Mục tiêu hoặc thời gian không hợp lệ.')
    today=today or date.today();scope=scope_for(roster);groups,dups=screening(roster['students']);tasks=[]
    def add(key,title,owner,criterion,offset,priority=2,sid=None):
        tasks.append(dict(key=key,title=title,owner=owner,criterion=criterion,due=(today+timedelta(days=min(days,offset))).isoformat(),priority=priority,student_id=sid))
    add('refresh','Đối chiếu hồ sơ kỳ hiện tại','Cố vấn','Xác minh ngày cập nhật, GPA tích lũy độc lập và lịch sử học vụ; ghi rõ dữ liệu còn thiếu.',1,1)
    if dups or groups[3] or any(x[3] for tier in (1,2) for x in groups[tier]):add('repair','Rà dữ liệu thiếu hoặc trùng','Cố vấn','Đối chiếu từng trường thiếu hoặc mã trùng; không suy diễn giá trị còn thiếu.',2,1)
    for rank,(sid,name,flags,missing) in enumerate(groups[1]):
        add('meet:'+sid,'Gặp riêng sinh viên '+sid,'Cố vấn và sinh viên','Xác nhận nhu cầu, bảng điểm mới và thống nhất một bước hỗ trợ; không kết luận cảnh báo từ sàng lọc.',2+rank,1,sid)
        if goal!='daily':add('path:'+sid,'Đối chiếu phương án học tập '+sid,'Cố vấn và sinh viên','Rà môn nợ, CTĐT đúng khóa, tiên quyết và lịch mở lớp; ghi phương án đã xác nhận.',5+rank,2,sid)
    if groups[2]:add('support','Trao đổi với nhóm cần hỗ trợ','Cố vấn','Rà '+str(len(groups[2]))+' hồ sơ có tín hiệu khác; ghi nhu cầu và bước hỗ trợ riêng.',5,2)
    if goal=='graduation':add('graduation','Rà điều kiện tốt nghiệp toàn lớp','Cố vấn','Đối chiếu từng hồ sơ: tín chỉ bắt buộc, chuẩn đầu ra, thời gian đào tạo và quy chế đúng khóa; không dự báo khi thiếu dữ liệu.',max(1,days-2),2)
    if goal=='improvement':
        add('course','Phối hợp giảng viên bộ môn','Cố vấn và giảng viên','Rà học phần khó từ bảng điểm mới; thống nhất hoạt động hỗ trợ phù hợp.',min(7,days),2)
        add('midterm','Đặt mốc đánh giá kết quả học tập','Cố vấn','Thống nhất mốc giữa kỳ thực tế; đối chiếu GPA học kỳ và tín chỉ nợ khi có dữ liệu mới.',max(1,days-1),2)
    add('review','Đánh giá tiến độ và điều chỉnh kế hoạch','Cố vấn','Rà công việc đã hoàn thành, trở ngại còn mở và mốc tiếp theo.',days,3)
    tasks.sort(key=lambda t:(t['priority'],t['due']))
    return dict(scope=scope,goal=goal,label=GOALS[goal],days=days,as_of=today.isoformat(),class_label=str(roster.get('class_short') or roster.get('class_id')),semester=str(roster.get('semester') or 'chưa xác định'),counts={str(i):len(groups[i]) for i in range(1,5)},duplicates=dups,tasks=tasks,draft=True,disclaimer='Mốc do cố vấn chọn, không phải hạn của trường. Hồ sơ demo chưa chứng minh tình trạng học vụ hay tốt nghiệp.')

def storage_path(root):
    base=Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home()/'.local'/'share'
    return base/'ChronoReg'/'advisor-workspace'/digest(str(Path(root).resolve()))[:20]/'workspace.sqlite3'

class Store:
    def __init__(self,path):self.path=Path(path)
    def db(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript('''CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,scope TEXT NOT NULL,goal TEXT NOT NULL,created TEXT NOT NULL,body TEXT NOT NULL,UNIQUE(scope,goal));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES plans(id),body TEXT NOT NULL,status TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',review TEXT,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),status TEXT NOT NULL,note TEXT NOT NULL,review TEXT,revision INTEGER NOT NULL,at TEXT NOT NULL);''')
        return c
    def save(self,p):
        pid=digest([p['scope'],p['goal']]);stamp=now()
        with closing(self.db()) as c,c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM plans WHERE id=?',(pid,)).fetchone():return pid,False
            c.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(pid,p['scope'],p['goal'],stamp,canonical({k:v for k,v in p.items() if k!='tasks'})))
            for t in p['tasks']:
                tid=digest([pid,t['key']]);c.execute('INSERT INTO tasks(id,plan_id,body,status,updated) VALUES(?,?,?,?,?)',(tid,pid,canonical(t),'todo',stamp))
        return pid,True
    def list(self,scope):
        out=[]
        with closing(self.db()) as c:
            for p in c.execute('SELECT * FROM plans WHERE scope=? ORDER BY created,id',(scope,)):
                d=json.loads(p['body']);d.update(id=p['id'],draft=False,created=p['created']);d['tasks']=[]
                for t in c.execute('SELECT * FROM tasks WHERE plan_id=? ORDER BY rowid',(p['id'],)):
                    d['tasks'].append({**json.loads(t['body']),**{k:t[k] for k in ('id','status','revision','note','review','updated')},'history':[dict(e) for e in c.execute('SELECT status,note,review,revision,at FROM events WHERE task_id=? ORDER BY revision DESC LIMIT 20',(t['id'],))]})
                d['completed']=sum(t['status']=='done' for t in d['tasks']);d['total']=len(d['tasks']);out.append(d)
            archived=c.execute('SELECT COUNT(*) FROM plans WHERE scope<>?',(scope,)).fetchone()[0]
        return {'plans':out,'other_snapshot_plan_count':archived}
    def update(self,scope,tid,revision,status,note,review):
        if status not in STATES or type(revision) is not int or revision<0 or len(note)>1000:raise ValueError('Trạng thái hoặc ghi chú không hợp lệ.')
        note=note.strip()
        if status in ('done','blocked') and not note:raise ValueError('Cần ghi kết quả hoặc trở ngại trước khi lưu.')
        if review is not None:
            try:
                if date.fromisoformat(review).isoformat()!=review:raise ValueError('Noncanonical date')
            except ValueError:raise ValueError('Mốc theo dõi phải là ngày hợp lệ.')
        stamp=now()
        with closing(self.db()) as c,c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT t.revision FROM tasks t JOIN plans p ON p.id=t.plan_id WHERE t.id=? AND p.scope=?',(tid,scope)).fetchone()
            if not r:raise KeyError('Không tìm thấy công việc trong hồ sơ hiện tại.')
            if r['revision']!=revision:raise RuntimeError('Công việc đã thay đổi; tải lại trước khi lưu.')
            c.execute('UPDATE tasks SET status=?,note=?,review=?,revision=?,updated=? WHERE id=?',(status,note,review,revision+1,stamp,tid))
            c.execute('INSERT INTO events(task_id,status,note,review,revision,at) VALUES(?,?,?,?,?,?)',(tid,status,note,review,revision+1,stamp))
        return revision+1

class PlanRequest(BaseModel):
    goal:Literal['graduation','improvement','daily'];days:int=Field(ge=1,le=90);scope:str=Field(min_length=64,max_length=64)
class ConfirmRequest(PlanRequest):
    confirmation:Literal[True];as_of:str;preview_hash:str=Field(min_length=64,max_length=64)
class UpdateRequest(BaseModel):
    scope:str=Field(min_length=64,max_length=64);task_id:str=Field(min_length=64,max_length=64);revision:int=Field(ge=0);status:Literal['todo','doing','blocked','done'];note:str=Field(default='',max_length=1000);review:str|None=None

def install_workspace(app,roster_loader,root,*,path=None):
    store=Store(path or storage_path(root));token=secrets.token_urlsafe(32)
    def guard(req,write=False,*,page_navigation=False):
        if req.url.hostname not in ('localhost','127.0.0.1','::1'):raise HTTPException(403,'Chỉ hỗ trợ địa chỉ loopback.')
        origin=req.headers.get('origin')
        if origin and origin!=str(req.base_url).rstrip('/'):raise HTTPException(403,'Nguồn yêu cầu không hợp lệ.')
        if req.headers.get('sec-fetch-site')=='cross-site':
            # A top-level document navigation (e.g. link from a chat) is safe:
            # no writes, no cross-origin reads, and framing is denied below.
            # Never grant this exception to any API, fetch, or iframe request.
            navigation=(page_navigation and req.method=='GET' and not origin
                        and req.headers.get('sec-fetch-mode')=='navigate'
                        and req.headers.get('sec-fetch-dest')=='document')
            if not navigation:raise HTTPException(403,'Yêu cầu khác trang bị từ chối.')
        if write and not secrets.compare_digest(req.headers.get('x-advisor-workspace',''),token):raise HTTPException(403,'Thiếu xác nhận phiên làm việc.')
    def current(expected=None):
        r=roster_loader()
        try:s=scope_for(r)
        except ValueError as e:raise HTTPException(409,str(e)) from e
        if expected is not None and expected!=s:raise HTTPException(409,'Hồ sơ đã thay đổi. Tải lại trang; không áp dụng kế hoạch cũ.')
        return r,s
    def response(data):return JSONResponse(data,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    @app.get('/advisor/workspace')
    def page(req:Request):
        guard(req,page_navigation=True);return HTMLResponse(PAGE.replace('__WORKSPACE_TOKEN__',token),headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"})
    @app.get('/api/advisor/workspace')
    def state(req:Request):
        guard(req,True);r,s=current();return response({'scope':s,'class_label':r.get('class_short') or r.get('class_id'),'semester':r.get('semester'),**store.list(s)})
    @app.post('/api/advisor/workspace/preview')
    def preview(req:Request,body:PlanRequest):
        guard(req,True);r,s=current(body.scope);p=proposal(r,body.goal,body.days);return response({**p,'preview_hash':digest(p)})
    @app.post('/api/advisor/workspace/confirm')
    def confirm(req:Request,body:ConfirmRequest):
        guard(req,True);r,s=current(body.scope);p=proposal(r,body.goal,body.days)
        if body.as_of!=p['as_of'] or body.preview_hash!=digest(p):raise HTTPException(409,'Bản nháp đã thay đổi; xem lại trước khi xác nhận.')
        pid,created=store.save(p);return response({'id':pid,'created':created,**store.list(s)})
    @app.post('/api/advisor/workspace/update')
    def update(req:Request,body:UpdateRequest):
        guard(req,True);_,s=current(body.scope)
        try:v=store.update(s,body.task_id,body.revision,body.status,body.note,body.review)
        except ValueError as e:raise HTTPException(422,str(e)) from e
        except KeyError as e:raise HTTPException(404,'Không tìm thấy công việc trong hồ sơ hiện tại.') from e
        except RuntimeError as e:raise HTTPException(409,str(e)) from e
        return response({'revision':v,**store.list(s)})
    return store

PAGE='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ChronoReg | Công việc cố vấn</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f9;color:#18283a;font:15px/1.5 system-ui,sans-serif}header{background:#172c45;color:white;padding:18px 24px}header a{color:#dbeafe}main{max-width:1080px;margin:auto;padding:24px}h1{font-size:26px;margin:12px 0}h2{font-size:19px}p{margin:8px 0}.panel{background:white;border:1px solid #d8e0ea;padding:18px;margin:16px 0;border-radius:8px}.task{border-top:1px solid #e2e8f0;padding:14px 0}.muted{color:#536479;font-size:13px}.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}button,select,input,textarea{font:inherit;padding:8px 10px;border:1px solid #b6c5d5;border-radius:5px;background:white;color:#172c45}button{background:#214b76;color:white;cursor:pointer}button:disabled{opacity:.5;cursor:wait}textarea{display:block;width:100%;margin:8px 0;min-height:65px}progress{width:100%;height:14px}#notice{color:#9b341c;white-space:pre-wrap}label{display:inline-flex;align-items:center;gap:6px}.tag{font-size:12px;color:#375477}a{color:inherit}
</style><header><a href="/">← Trợ lý học tập</a> &nbsp; / &nbsp; Công việc cố vấn</header><main><h1>Kế hoạch hỗ trợ sinh viên</h1><p id="scope" class="muted"></p><p>Chỉ lưu trên máy này. Nguồn hồ sơ: dữ liệu mẫu. Không thay thế quyết định học vụ. Không nhập thông tin nhạy cảm vào ghi chú; không tự gửi tin nhắn.</p><div id="notice" role="status"></div><section class="panel"><h2>Tạo kế hoạch đề xuất</h2><div class="controls"><label>Mục tiêu <select id="goal"><option value="graduation">Tốt nghiệp đúng hạn</option><option value="improvement">Cải thiện học tập</option><option value="daily">Ưu tiên hỗ trợ</option></select></label><label>Khoảng thời gian (ngày) <input id="days" type="number" min="1" max="90" value="14"></label><button id="preview">Xem đề xuất</button></div><div id="draft"></div></section><section id="plans"></section><p class="muted">Mỗi mục tiêu có một kế hoạch trên mỗi ảnh chụp hồ sơ. Khi dữ liệu đổi, kế hoạch cũ được cách ly; chưa hỗ trợ chuyển kế hoạch sang hồ sơ mới.</p></main><script>
const token='__WORKSPACE_TOKEN__', base='/api/advisor/workspace';let scope=null;const $=id=>document.getElementById(id);const el=(tag,text,parent,cls)=>{const x=document.createElement(tag);if(text!==null)x.textContent=text;if(cls)x.className=cls;if(parent)parent.append(x);return x};
async function api(suffix='',body){const r=await fetch(base+suffix,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Advisor-Workspace':token},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Dữ liệu không hợp lệ.');return d}
async function act(button,fn){button.disabled=true;$('notice').textContent='';try{await fn()}catch(e){$('notice').textContent=e.message}finally{button.disabled=false}}
function taskSummary(t,root){el('strong',t.title,root);el('p','Phụ trách: '+t.owner+' · Mốc đề xuất: '+t.due,root,'muted');el('p',t.criterion,root)}
function render(d){const root=$('plans');root.replaceChildren();if(d.other_snapshot_plan_count)el('p',d.other_snapshot_plan_count+' kế hoạch thuộc ảnh chụp hồ sơ khác đang được cách ly.',root,'muted');if(!d.plans.length)el('p','Chưa có kế hoạch đã xác nhận.',root);for(const p of d.plans){const panel=el('article',null,root,'panel');el('h2',p.label,panel);el('p',p.completed+'/'+p.total+' công việc do cố vấn xác nhận hoàn thành',panel);const bar=el('progress',null,panel);bar.max=p.total;bar.value=p.completed;for(const t of p.tasks){const task=el('div',null,panel,'task');taskSummary(t,task);if(t.status!=='done'&&t.due<new Date().toLocaleDateString('sv-SE'))el('p','Đã qua mốc đề xuất — rà lại kế hoạch.',task,'tag');const controls=el('div',null,task,'controls');const lab=el('label','Trạng thái ',controls);const select=el('select',null,lab);for(const [v,label] of Object.entries({todo:'Chưa làm',doing:'Đang làm',blocked:'Có trở ngại',done:'Hoàn thành'})){const o=el('option',label,select);o.value=v}select.value=t.status;const dl=el('label','Mốc gặp lại ',controls);const review=el('input',null,dl);review.type='date';review.value=t.review||'';const note=el('textarea',null,task);note.value=t.note;note.maxLength=1000;note.placeholder='Kết quả hoặc trở ngại (bắt buộc khi hoàn thành/bị chặn)';note.setAttribute('aria-label','Ghi nhận công việc');const save=el('button','Lưu cập nhật',task);save.onclick=()=>act(save,async()=>{await api('/update',{scope,task_id:t.id,revision:t.revision,status:select.value,note:note.value,review:review.value||null});await load();$('notice').textContent='Đã lưu cập nhật.'});if(t.history.length){const details=el('details',null,task);el('summary','Lịch sử cập nhật (tối đa 20 lần gần nhất)',details);for(const h of t.history){el('p',h.at+' · '+({todo:'Chưa làm',doing:'Đang làm',blocked:'Có trở ngại',done:'Hoàn thành'}[h.status]||h.status)+' — '+(h.note||'Không có ghi chú'),details,'muted')}}}}}
async function load(){const d=await api();scope=d.scope;$('scope').textContent='Lớp '+d.class_label+' · '+(d.semester||'Kỳ chưa xác định');render(d)}
$('preview').onclick=()=>act($('preview'),async()=>{const goal=$('goal').value,days=Number($('days').value);const d=await api('/preview',{scope,goal,days});const root=$('draft');root.replaceChildren();el('h2',d.label+' — bản nháp',root);el('p',d.disclaimer,root,'muted');el('p',d.tasks.length+' công việc đề xuất; chưa lưu.',root);for(const t of d.tasks)taskSummary(t,el('div',null,root,'task'));const confirm=el('button','Xác nhận lưu kế hoạch',root);confirm.onclick=()=>act(confirm,async()=>{const r=await api('/confirm',{scope:d.scope,goal:d.goal,days:d.days,as_of:d.as_of,preview_hash:d.preview_hash,confirmation:true});root.replaceChildren();await load();$('notice').textContent=r.created?'Đã lưu kế hoạch.':'Đã có kế hoạch cho mục tiêu này; giữ nguyên tiến độ.'})});load().catch(e=>$('notice').textContent=e.message);
</script></html>'''
