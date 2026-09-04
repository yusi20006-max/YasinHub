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
  const normalized=normalizeStatus(status);
  const actions=ACTIONS.filter(a=>allowed(a,normalized));
  return `<div class="service-controls" data-service-controls="${escapeAttr(service)}" data-service-status="${normalized}">${actions.map(a=>buttonHtml(service,a)).join("")}<span class="service-feedback" role="status" aria-live="polite"></span></div>`;
}
async function callLifecycle(service,action){
  try{
    const response=await fetch(`/api/control/${encodeURIComponent(service)}/${encodeURIComponent(action)}`,{method:"POST",headers:{Accept:"application/json","Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({source:"pwa",action})});
    let data=null;try{data=await response.json();}catch(_){ }
    return {ok:Boolean(response.ok&&data&&data.success===true),status:response.status,data,message:data&&(data.error||data.message)||response.statusText||"request failed"};
  }catch(error){return {ok:false,status:null,data:null,message:error?.message||"network error"};}
}
function setFeedback(container,message,error=false){
  const feedback=container.querySelector(".service-feedback");
  if(!feedback)return;
  feedback.textContent=message||"";
  feedback.className="service-feedback"+(error?" control-error":" control-ok");
}
function formatAuthoritativeResult(action,data){
  const parts=[`${LABELS[action]} تأیید شد`];
  if(data&&data.status) parts.push(`state=${data.status}`);
  if(data&&data.pid!=null) parts.push(`pid=${data.pid}`);
  return parts.join(" · ");
}
async function refreshOverview(){document.getElementById("refresh-btn")?.click();}
async function handleAction(button){
  const service=button.getAttribute("data-service"),action=button.getAttribute("data-service-action");
  if(!service||!ACTIONS.includes(action))return;
  const confirmMessage=button.getAttribute("data-confirm");
  if(confirmMessage&&!window.confirm(confirmMessage))return;
  const container=button.closest(".service-controls");if(!container)return;
  if(container.getAttribute("data-lifecycle-pending")==="1")return;
  container.setAttribute("data-lifecycle-pending","1");
  container.querySelectorAll("button").forEach(b=>b.disabled=true);
  setFeedback(container,`${LABELS[action]} ${service}…`);
  const result=await callLifecycle(service,action);
  container.removeAttribute("data-lifecycle-pending");
  if(!result.ok){setFeedback(container,(result.status===403?"دسترسی رد شد: ":"کنترل ناموفق: ")+result.message,true);await refreshOverview();return;}
  setFeedback(container,formatAuthoritativeResult(action,result.data));
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
    const status=getRowStatus(row);
    const normalized=normalizeStatus(status);
    const existing=row.querySelector("[data-service-controls]");
    if(existing){
      if(existing.getAttribute("data-service-status")===normalized)return;
      existing.outerHTML=buildControls(service,normalized);
      return;
    }
    const td=document.createElement("td");td.dataset.label="کنترل";td.innerHTML=buildControls(service,normalized);row.appendChild(td);
  });
}
function injectGlassTheme(){
  if(document.getElementById("yg-service-controls-style"))return;
  const style=document.createElement("style");
  style.id="yg-service-controls-style";
  style.textContent=`.service-controls{display:flex!important;align-items:center!important;justify-content:flex-start!important;gap:5px!important;min-width:180px}.service-action{border:1px solid transparent!important;border-radius:8px!important;padding:5px 9px!important;min-height:34px!important;font-size:.7rem!important;font-weight:700!important;color:#fff!important;cursor:pointer!important;box-shadow:0 4px 14px rgba(0,0,0,.22)!important}.service-action-primary{background:linear-gradient(135deg,rgba(37,99,235,.9),rgba(124,58,237,.9))!important;border-color:rgba(129,140,248,.42)!important}.service-action-danger{background:linear-gradient(135deg,rgba(220,38,38,.9),rgba(190,24,93,.9))!important;border-color:rgba(251,113,133,.38)!important}.service-action:hover{transform:translateY(-1px);filter:brightness(1.08)}.service-action:disabled{opacity:.45;cursor:not-allowed;transform:none}.service-feedback{font-size:.62rem!important;color:var(--yg-muted)!important}.service-feedback.control-ok{color:#67e8f9!important}.service-feedback.control-error{color:#fda4af!important}`;
  document.head.appendChild(style);
}
function wireDelegation(){document.addEventListener("click",event=>{const button=event.target.closest("button[data-service-action]");if(!button)return;event.preventDefault();handleAction(button);});}
function init(){injectGlassTheme();wireDelegation();const observer=new MutationObserver(()=>decorateServices());observer.observe(document.getElementById("content")||document.body,{childList:true,subtree:true});decorateServices();}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
