"""Product-only NDJSON transport. No raw model tokens or chain of thought.
Existing chat handler runs exactly once; only completed, existing-gated answer is streamed.
"""
import asyncio, json, math
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from conversation import AdvisorChatRequest


def line(event, **data):
    return json.dumps({'event':event, **data}, ensure_ascii=False, separators=(',', ':'))+'\n'


def install_stream(app, handler, *, interval=0.035, heartbeat=2.0):
    @app.post('/api/advisor/chat/stream')
    async def stream(req: AdvisorChatRequest):
        async def events():
            yield line('processing')
            task=asyncio.create_task(run_in_threadpool(handler, req))
            try:
                while not task.done():
                    done,_=await asyncio.wait({task},timeout=heartbeat)
                    if not done:yield line('processing')
                result=task.result()
                if hasattr(result,'status_code') and result.status_code>=400:
                    yield line('error',message='Không thể xử lý yêu cầu.');return
                data=json.loads(result.body) if hasattr(result,'body') else result
                if not isinstance(data,dict) or not isinstance(data.get('answer'),str):
                    yield line('error',message='Phản hồi không hợp lệ.');return
                # Bound animation overhead even for long source excerpts.
                answer=data['answer']; size=max(12,math.ceil(len(answer)/45))
                for i in range(0,len(answer),size):
                    yield line('delta',text=answer[i:i+size])
                    if interval and i+size<len(answer):await asyncio.sleep(interval)
                # Context and provenance arrive once, after the complete text.
                yield line('done',data=data)
            except Exception:
                # Do not expose stack traces, secrets or student records in errors.
                yield line('error',message='Không thể hoàn tất câu trả lời.')
            finally:
                if not task.done():task.cancel()
        return StreamingResponse(events(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff'})

JS=r'''
    let advisorSending = false;
    async function readAdvisorStream(payload) {
      const res = await fetch('/api/advisor/chat/stream', {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload), cache:'no-store'
      });
      if (!res.ok || !res.body) throw new Error('HTTP ' + res.status);
      const reader = res.body.getReader(), decoder = new TextDecoder('utf-8', {fatal:true});
      let buffer = '', accumulated = '', completed = null, preview = null, cursor = null;
      function consume(raw) {
        if (!raw.trim()) return;
        const e = JSON.parse(raw);
        if (completed) throw new Error('Luồng trả lời không hợp lệ');
        if (e.event === 'processing') return;
        if (e.event === 'error') throw new Error(e.message || 'Không thể hoàn tất');
        if (e.event === 'delta' && typeof e.text === 'string') {
          if (!preview) {
            removeTypingSkeleton();
            preview = document.createElement('article'); preview.id='advisorStreamPreview'; preview.className='msg-ai';
            preview.setAttribute('aria-busy','true');
            const body=document.createElement('div'); body.className='ai-tier2';
            const text=document.createElement('span'); text.id='advisorStreamText';
            cursor=document.createElement('span'); cursor.textContent='▍'; cursor.setAttribute('aria-hidden','true');
            body.append(text,cursor); preview.append(body); document.getElementById('chatList').appendChild(preview);
          }
          accumulated += e.text;
          // Only the same escaped highlight markup permitted by the final renderer.
          preview.querySelector('#advisorStreamText').innerHTML=allowHighlightMarkup(accumulated);
          scrollToBottom(); return;
        }
        if (e.event === 'done' && e.data && e.data.answer === accumulated) { completed=e.data; return; }
        throw new Error('Luồng trả lời không hợp lệ');
      }
      try {
        while (true) {
          const part=await reader.read();
          buffer += decoder.decode(part.value || new Uint8Array(), {stream:!part.done});
          const lines=buffer.split('\n'); buffer=lines.pop(); lines.forEach(consume);
          if (part.done) break;
        }
        if (buffer.trim()) consume(buffer);
        if (!completed) throw new Error('Luồng trả lời bị gián đoạn');
        return completed;
      } finally {
        preview?.remove();
        try { await reader.cancel(); } catch (_) {}
        reader.releaseLock();
      }
    }
'''

def patch_page(html):
    anchor='async function handleSend(overrideMssv = null) {'
    # run_live has already installed bounded conversation behavior.
    if anchor not in html: return html  # non-product fixture page
    old="""const res = await fetch(autoMode ? '/api/advisor/chat' : '/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();"""
    new="""let data;
        if (autoMode && typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined') {
          data = await readAdvisorStream(payload);
        } else {
          const res = await fetch(autoMode ? '/api/advisor/chat' : '/api/chat', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
          });
          if (!res.ok) throw new Error('HTTP ' + res.status);
          data = await res.json();
        }"""
    tail="""appendErrorMessage('Lỗi kết nối server: ' + err.message);
      }
    }"""
    for marker in (anchor,old,tail,"if (!question) return;"):
        if html.count(marker)!=1: raise RuntimeError('Unsupported chat page layout')
    html=html.replace(anchor,JS+'\n    '+anchor,1)
    html=html.replace('if (!question) return;',"if (!question || advisorSending) return;\n      advisorSending = true;\n      document.getElementById('btnSend').disabled = true;",1)
    html=html.replace(old,new,1)
    html=html.replace(tail,"""appendErrorMessage('Lỗi kết nối server: ' + err.message);
      } finally {
        advisorSending = false;
        document.getElementById('btnSend').disabled = false;
      }
    }""",1)
    return html.replace('Đang chạy Pre-Check bảng điểm &amp; truy xuất mô hình...', 'Đang xử lý yêu cầu và đối chiếu dữ liệu…')
