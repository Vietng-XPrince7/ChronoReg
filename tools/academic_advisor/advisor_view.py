"""Local safe Markdown subset and product/research presentation separation."""
RENDER=r'''
    function inlineAdvisor(value) {
      // Escape first. Only renderer-created tags can become HTML.
      return escapeHtml(value).replace(/&lt;br\s*\/?&gt;/gi,'<br>')
        .replace(/&lt;\/?mark&gt;/gi,'')
        .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
        .replace(/`([^`\n]+)`/g,'<code>$1</code>');
    }
    function renderAdvisorMarkdown(value) {
      const lines=String(value??'').replace(/\r\n?/g,'\n').split('\n');
      const out=[]; let i=0;
      const isRow=s=>/^\s*\|.*\|\s*$/.test(s);
      const cells=s=>s.trim().slice(1,-1).split('|').map(x=>x.trim());
      const sep=s=>isRow(s)&&cells(s).every(x=>/^:?-{2,}:?$/.test(x));
      while(i<lines.length){
        const l=lines[i];
        if(isRow(l)){
          const rows=[];while(i<lines.length&&isRow(lines[i])){if(!sep(lines[i])) rows.push(cells(lines[i]));i++;}
          if(rows.length){const head=rows.shift();out.push('<div class="advisor-table-wrap"><table><thead><tr>'+head.map(c=>'<th>'+inlineAdvisor(c)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+inlineAdvisor(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>');}continue;
        }
        if(/^\s*[-*_]{3,}\s*$/.test(l)){i++;continue;}
        const heading=l.match(/^\s*#{1,6}\s+(.+)$/);
        if(heading){out.push('<h4>'+inlineAdvisor(heading[1])+'</h4>');i++;continue;}
        if(/^\s*(?:[-*•]|\d+\.)\s+/.test(l)){
          const ordered=/^\s*\d+\./.test(l);const tag=ordered?'ol':'ul';let items=[];
          while(i<lines.length&&(ordered?/^\s*\d+\.\s+/:/^\s*[-*•]\s+/).test(lines[i])){items.push('<li>'+inlineAdvisor(lines[i].replace(/^\s*(?:[-*•]|\d+\.)\s+/,''))+'</li>');i++;}
          out.push('<'+tag+'>'+items.join('')+'</'+tag+'>');continue;
        }
        if(l.trim())out.push('<p>'+inlineAdvisor(l)+'</p>');i++;
      }
      return out.join('');
    }
    function advisorSource(m) {
      let label='',url='';
      if (m.source_path && ['SOURCE_TABLE','SOURCE_CLAUSE','ADVISOR_EVIDENCE'].includes(m.engine_mode)) {
        label=['SOURCE_CLAUSE','ADVISOR_EVIDENCE'].includes(m.engine_mode)?(m.doc_title||'Điều khoản đối chiếu'):(m.effective_year?'Bảng nguồn năm '+m.effective_year:'Bảng nguồn đối chiếu');
        if(typeof m.source_url==='string'&&/^https?:\/\//i.test(m.source_url))url=m.source_url;
      } else if (Array.isArray(m.workflow_tools)&&m.workflow_tools.some(x=>['screening','student_signals','course_history','scope_check','credit_scenarios'].includes(x))) {
        label=m.roster_provenance === 'sample_roster' ? 'Hồ sơ mẫu và công cụ học vụ' : 'Hồ sơ đang mở và công cụ học vụ';
      } else if(m.engine_mode==='ADVISOR_SIMULATION')label='Mô phỏng từ dữ kiện giả định';
      if(!label)return '';
      return '<span><strong>Căn cứ:</strong> '+(url?'<a href="'+escapeHtml(url)+'" target="_blank" rel="noopener noreferrer">'+escapeHtml(label)+'</a>':escapeHtml(label))+'</span>' + (typeof m.advisor_evidence==='string' && m.advisor_evidence ? '<details class="advisor-evidence"><summary>Xem toàn bộ đoạn nguồn</summary><p>'+escapeHtml(m.advisor_evidence)+'</p></details>' : '');
    }
'''
STYLE='''
    .advisor-answer .ai-tier1,.advisor-answer .xray-details,.advisor-answer .compare-trigger,.advisor-answer .cmp-box{display:none!important}
    .advisor-answer .ai-tier3:has(.ai-provenance:empty){display:none}
    .advisor-answer .ai-tier2{white-space:normal;line-height:1.7;overflow-wrap:anywhere;font-size:14px}
    .advisor-answer .ai-tier2 p{margin:0 0 .65em;white-space:pre-wrap}
    .advisor-answer .ai-tier2 h4{font-size:15px;margin:1em 0 .5em}
    .advisor-answer .ai-tier2 ul,.advisor-answer .ai-tier2 ol{margin:.5em 0;padding-left:1.6em}
    .advisor-answer .ai-tier2 li{margin:.2em 0}
    .advisor-table-wrap{overflow-x:auto;margin:.7em 0}
    .advisor-table-wrap table{border-collapse:collapse;width:100%;font-size:13px}
    .advisor-table-wrap th,.advisor-table-wrap td{padding:8px;border:1px solid #bfc8cc;text-align:left;vertical-align:top}
    .advisor-table-wrap th{font-weight:600}
    .advisor-evidence{margin-top:.4em;max-width:100%;white-space:normal}
    .advisor-evidence p{overflow-wrap:anywhere;line-height:1.6}
    .advisor-answer .ai-tier2 p:last-child{margin-bottom:0}
'''
def patch_advisor_view(html):
    replacements=[
      ('function allowHighlightMarkup(str) {',RENDER+'\n    function allowHighlightMarkup(str) {'),
      ('const payload = { question, force_engine: currentEngineMode };',"const payload = { question, force_engine: currentEngineMode, ...(autoMode ? {experience:'advisor'} : {}) };"),
      ("card.className = 'msg-ai';","const product = currentEngineMode === 'auto';\n      card.className = product ? 'msg-ai advisor-answer' : 'msg-ai';\n      if(product) provenanceHtml = advisorSource(m);"),
      ("${allowHighlightMarkup(data.answer || '')}","${product ? renderAdvisorMarkdown(data.answer || '') : allowHighlightMarkup(data.answer || '')}"),
      ("preview.className='msg-ai';","preview.className='msg-ai advisor-answer';"),
      ("const text=document.createElement('span'); text.id='advisorStreamText';","const text=document.createElement('div'); text.id='advisorStreamText';"),
      ("innerHTML=allowHighlightMarkup(accumulated);","innerHTML=renderAdvisorMarkdown(accumulated);"),
      (">Auto Router</button>",">Trợ lý cố vấn</button>"),
    ]
    # Fixture pages may not contain the live chat layout.
    if 'async function handleSend(overrideMssv = null)' not in html:return html
    for a,b in replacements:
        if html.count(a)!=1:raise RuntimeError('Unsupported advisor view marker: '+a[:50])
        html=html.replace(a,b,1)
    html=html.replace('</style>',STYLE+'\n</style>',1)
    # A true session reset, not just deleting visible text. Disallow during stream.
    anchor="function setEngineMode(mode) {"
    html=html.replace(anchor,"function newAdvisorConversation() {\n      if(advisorSending) return;\n      advisorContextToken=null;advisorTurnSequence++;\n      document.getElementById('chatList').replaceChildren();\n      document.getElementById('promptInput').focus();\n    }\n    "+anchor,1)
    html=html.replace('function setEngineMode(mode) {','function setEngineMode(mode) {\n      if(advisorSending) return;',1)
    html=html.replace('<div class="topbar-controls">','<div class="topbar-controls"><button type="button" class="btn-outline" onclick="newAdvisorConversation()" title="Xóa ngữ cảnh phiên hiện tại">Chat mới</button>',1)
    html=html.replace('role="group" aria-label="Chọn mô hình"','role="group" aria-label="Chế độ cố vấn hoặc nghiên cứu"',1)
    return html
