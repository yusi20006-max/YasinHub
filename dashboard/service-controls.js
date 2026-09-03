/** YasinHub PWA service lifecycle controls + glass mobile UI. */
const ACTIONS = ["start", "stop", "restart"];
const LABELS = { start: "شروع", stop: "توقف", restart: "راه‌اندازی مجدد" };

function escapeAttr(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function normalizeStatus(value){
  const s=String(value||"").trim().toLowerCase();
  if(s.includes("running")||s.includes("در حال اجرا")||s.includes("فعال")) return "running";
  if(s.includes("starting")||s.includes("شروع")) return "starting";
  if(s.includes("restarting")||s.includes("راه‌اندازی")) return "restarting";
  if(s.includes("paused")||s.includes("مکث")) return "paused";
  if(s.includes("failed")||s.includes("ناموفق")||s.includes("خطا")) return "failed";
  if(s.includes("idle")||s.includes("stopped")||s.includes("متوقف")) return "idle";
  return "unknown";
}
function allowed(action,status){
  const s=normalizeStatus(status);
  if(action==="start") return !["running","starting","restarting"].includes(s);
  if(action==="stop"||action==="restart") return ["running","starting","restarting","paused"].includes(s);
  return false;
}
function getRowStatus(row){
  const badge=row.querySelector('td[data-label="Status"] .badge');
  if(badge){
    const cls=[...badge.classList].find(c=>c.startsWith("status-"));
    if(cls) return normalizeStatus(cls.slice(7));
  }
  return normalizeStatus(row.querySelector('td[data-label="Status"]')?.textContent);
}
function buttonHtml(service,action){
  const danger=action==="stop";
  const confirm=action==="stop"||action==="restart"?` data-confirm="${escapeAttr(`${LABELS[action]} ${service}؟`)}"`:"";
  return `<button type="button" class="service-action ${danger?"service-action-danger":"service-action-primary"}" data-service-action="${action}" data-service="${escapeAttr(service)}"${confirm}>${LABELS[action]}</button>`;
}
function buildControls(service,status){
  const actions=ACTIONS.filter(a=>allowed(a,status));
  return `<div class="service-controls" data-service-controls="${escapeAttr(service)}" data-service-status="${escapeAttr(status)}">${actions.map(a=>buttonHtml(service,a)).join("")}<span class="service-feedback" role="status" aria-live="polite"></span></div>`;
}
async function callLifecycle(service,action){
  try{
    const response=await fetch(`/api/control/${encodeURIComponent(service)}/${encodeURIComponent(action)}`,{method:"POST",headers:{Accept:"application/json","Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({source:"pwa",action})});
    let data=null;try{data=await response.json();}catch(_){ }
    return {ok:response.ok&&data&&data.success!==false,status:response.status,data,message:data&&(data.error||data.message)||response.statusText||"request failed"};
  }catch(error){return {ok:false,status:null,data:null,message:error?.message||"network error"};}
}
function setFeedback(container,message,error=false){
  const feedback=container.querySelector(".service-feedback");
  if(!feedback)return;
  feedback.textContent=message||"";
  feedback.className="service-feedback"+(error?" control-error":" control-ok");
}
async function refreshOverview(){document.getElementById("refresh-btn")?.click();}
async function handleAction(button){
  const service=button.getAttribute("data-service"),action=button.getAttribute("data-service-action");
  if(!service||!ACTIONS.includes(action))return;
  const confirmMessage=button.getAttribute("data-confirm");
  if(confirmMessage&&!window.confirm(confirmMessage))return;
  const container=button.closest(".service-controls");if(!container)return;
  container.querySelectorAll("button").forEach(b=>b.disabled=true);
  setFeedback(container,`${LABELS[action]} ${service}…`);
  const result=await callLifecycle(service,action);
  if(!result.ok){setFeedback(container,(result.status===403?"دسترسی رد شد: ":"کنترل ناموفق: ")+result.message,true);await refreshOverview();return;}
  setFeedback(container,`${LABELS[action]} با موفقیت درخواست شد`);
  await refreshOverview();
}
function decorateServices(){
  const table=document.querySelector('table[aria-label="Services status"]');
  if(!table)return;
  table.classList.add("service-table");
  const header=table.querySelector("thead tr");
  if(header&&!header.querySelector("[data-service-actions-header]")){
    const th=document.createElement("th");th.textContent="کنترل";th.dataset.serviceActionsHeader="1";header.appendChild(th);
  }
  table.querySelectorAll("tbody tr").forEach(row=>{
    const service=row.querySelector('td[data-label="Service"] strong')?.textContent?.trim();
    if(!service)return;
    const existing=row.querySelector("[data-service-controls]");
    if(existing){
      const status=getRowStatus(row);existing.outerHTML=buildControls(service,status);return;
    }
    const td=document.createElement("td");td.dataset.label="کنترل";td.innerHTML=buildControls(service,getRowStatus(row));row.appendChild(td);
  });
}
function injectGlassTheme(){
  if(document.getElementById("yasin-glass-theme"))return;
  const style=document.createElement("style");style.id="yasin-glass-theme";style.textContent=`
:root{--yg-bg:#03040a;--yg-panel:rgba(10,12,24,.72);--yg-panel2:rgba(17,20,39,.78);--yg-border:rgba(96,110,255,.28);--yg-blue:#38bdf8;--yg-purple:#8b5cf6;--yg-text:#eef2ff;--yg-muted:#9aa5c4;--yg-danger:#fb7185}
html,body{background:radial-gradient(circle at 15% 0%,rgba(56,189,248,.12),transparent 32%),radial-gradient(circle at 85% 10%,rgba(139,92,246,.16),transparent 35%),#03040a!important;color:var(--yg-text)!important}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(120deg,rgba(56,189,248,.025),rgba(139,92,246,.04));z-index:-1}
.app-header{background:rgba(5,7,15,.78)!important;border-bottom:1px solid var(--yg-border)!important;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 8px 32px rgba(0,0,0,.3)}
.sidebar{background:rgba(5,7,15,.72)!important;border-inline-end:1px solid var(--yg-border);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
.main{width:100%;max-width:none!important;padding:12px 14px 28px!important}
.page-heading{margin-bottom:8px!important}.page-heading h2{font-size:1.1rem!important;color:#fff}.meta-row{margin-bottom:8px!important;font-size:.72rem!important}
.overview-cards{grid-template-columns:repeat(5,minmax(0,1fr))!important;gap:7px!important;margin-bottom:10px!important}.card{background:var(--yg-panel)!important;border:1px solid var(--yg-border)!important;border-radius:14px!important;padding:9px 10px!important;box-shadow:0 8px 28px rgba(0,0,0,.25)!important;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}.card h3{font-size:.65rem!important;margin-bottom:2px!important}.card .metric{font-size:1.15rem!important;color:var(--yg-blue)!important}
.service-status{width:100%!important}.section-heading{margin-bottom:6px!important}.section-heading .hint{display:none}.table-wrap{width:100%!important;background:var(--yg-panel)!important;border:1px solid var(--yg-border)!important;border-radius:16px!important;box-shadow:0 14px 45px rgba(0,0,0,.34)!important;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
.service-table{font-size:.78rem!important}.service-table th,.service-table td{padding:8px 9px!important;border-bottom:1px solid rgba(148,163,184,.12)!important}.service-table th{background:rgba(20,24,45,.72)!important;color:#aab6d7!important;font-size:.65rem!important}.service-table tbody tr:hover td{background:rgba(56,189,248,.045)!important}.service-table .badge{font-size:.64rem!important;padding:3px 7px!important}.service-table td[data-label="Message"]{max-width:260px}.service-table td[data-label="Last run"]{font-size:.68rem!important;color:var(--yg-muted)!important}
.service-controls{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:5px!important;min-width:180px}.service-action{border:1px solid transparent!important;border-radius:8px!important;padding:5px 9px!important;min-height:34px!important;font-size:.7rem!important;font-weight:700!important;color:#fff!important;cursor:pointer!important;box-shadow:0 4px 14px rgba(0,0,0,.22)!important}.service-action-primary{background:linear-gradient(135deg,rgba(37,99,235,.9),rgba(124,58,237,.9))!important;border-color:rgba(129,140,248,.42)!important}.service-action-danger{background:linear-gradient(135deg,rgba(220,38,38,.9),rgba(190,24,93,.9))!important;border-color:rgba(251,113,133,.38)!important}.service-action:hover{transform:translateY(-1px);filter:brightness(1.08)}.service-action:disabled{opacity:.45;cursor:not-allowed;transform:none}.service-feedback{font-size:.62rem!important;color:var(--yg-muted)!important}.service-feedback.control-ok{color:#67e8f9!important}.service-feedback.control-error{color:#fda4af!important}
.state{background:var(--yg-panel)!important;border-color:var(--yg-border)!important}.hint{color:var(--yg-muted)!important}.content{min-height:0!important}.nav-footnote{color:#6f7b9d!important}.connection-status{font-size:.7rem!important}
@media(max-width:800px){
  .app-header{padding:7px 10px!important}.header-meta{gap:5px!important}.brand{gap:6px!important}.brand h1{font-size:1rem!important}.main{padding:8px!important}.page-heading{margin-bottom:5px!important}.overview-cards{grid-template-columns:repeat(5,minmax(55px,1fr))!important;gap:5px!important}.card{padding:7px 5px!important;border-radius:11px!important}.card h3{font-size:.52rem!important}.card .metric{font-size:1rem!important}.table-wrap{overflow-x:auto!important}.service-table{min-width:640px!important}.service-table th,.service-table td{padding:7px 7px!important}.service-table td[data-label="Message"]{max-width:180px}.service-controls{min-width:170px}.service-action{min-height:36px!important;padding:5px 8px!important}.sidebar{inset:48px auto 0 0!important;width:225px!important}.nav-backdrop.visible{inset:48px 0 0!important}
}
@media(min-width:801px){.main{padding-inline:16px!important}.service-table th,.service-table td{padding:7px 9px!important}}
`;
  document.head.appendChild(style);
}
function wireDelegation(){document.addEventListener("click",event=>{const button=event.target.closest("button[data-service-action]");if(!button)return;event.preventDefault();handleAction(button);});}
function init(){injectGlassTheme();wireDelegation();const observer=new MutationObserver(()=>decorateServices());observer.observe(document.getElementById("content")||document.body,{childList:true,subtree:true});decorateServices();}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
