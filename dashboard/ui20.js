/* YasinHub UI 2.0 progressive enhancement: Persian chrome + table tools. */
const TEXT = new Map([
  ["Online","آنلاین"],["Offline","آفلاین"],["Idle","آماده"],["Live","زنده"],["Updated","به‌روزرسانی"],
  ["Refreshing…","در حال به‌روزرسانی…"],["Loading…","در حال بارگذاری…"],["Overview / System Status","نمای کلی سامانه"],
  ["Executions","اجراها"],["Execution Detail","جزئیات اجرا"],["Fleets","ناوها"],["Fleet Detail","جزئیات ناو"],["Events","رویدادها"],
  ["Refresh","به‌روزرسانی"],["Yasin Programs","برنامه‌های یاسین"],["Current program status from the observer backend.","وضعیت فعلی برنامه‌ها از Observer"],
  ["Projects","پروژه‌ها"],["Running","در حال اجرا"],["Success","موفق"],["Failed","ناموفق"],["Unknown","نامشخص"],
  ["Last run:","آخرین اجرا:"],["Result:","نتیجه:"],["success","موفق"],["not successful","ناموفق"],["RUNNING / ACTIVE","در حال اجرا / فعال"],
  ["Live observer surface. Backend remains authoritative for lifecycle.","این صفحه فقط مشاهده‌گر است؛ مرجع چرخه عمر، Backend است."],
  ["No executions yet.","هنوز اجرایی ثبت نشده است."],["No fleets yet.","هنوز ناوی ثبت نشده است."],["No execution events.","رویدادی ثبت نشده است."],
  ["Execution","اجرا"],["Task","وظیفه"],["Status","وضعیت"],["Agent","عامل"],["Created","ایجاد"],["Error","خطا"],
  ["Worker","کارگر"],["Role","نقش"],["Session","نشست"],["Progress","پیشرفت"],["Breakdown","تفکیک وضعیت"],["Controls","کنترل‌ها"]
]);

function translate(root=document.body){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT); const nodes=[];
  while(walker.nextNode()) nodes.push(walker.currentNode);
  for(const n of nodes){const v=n.nodeValue.trim(); if(TEXT.has(v)) n.nodeValue=n.nodeValue.replace(v,TEXT.get(v));}
  for(const el of root.querySelectorAll("[title],[aria-label],[placeholder]")){for(const a of ["title","aria-label","placeholder"]){const v=el.getAttribute(a); if(v&&TEXT.has(v)) el.setAttribute(a,TEXT.get(v));}}
}
function enhanceTables(root=document){
  for(const table of root.querySelectorAll("table.data-table")){
    if(table.dataset.ui20) continue; table.dataset.ui20="1";
    const wrap=table.closest(".table-wrap")||table.parentElement; if(!wrap) continue;
    const bar=document.createElement("div"); bar.className="table-toolbar"; bar.innerHTML='<input class="table-search" type="search" placeholder="جستجو در جدول…" aria-label="جستجو در جدول"><select class="table-filter" aria-label="فیلتر وضعیت"><option value="">همه وضعیت‌ها</option><option value="running">در حال اجرا</option><option value="succeeded">موفق</option><option value="failed">ناموفق</option><option value="queued">در صف</option><option value="paused">متوقف</option></select><button type="button" class="btn-ghost table-reset">پاک‌کردن</button>';
    wrap.parentElement.insertBefore(bar,wrap);
    const search=bar.querySelector(".table-search"), filter=bar.querySelector(".table-filter");
    const apply=()=>{const q=search.value.toLowerCase(),f=filter.value; for(const row of table.querySelectorAll("tbody tr")){const text=row.textContent.toLowerCase(), badge=row.querySelector(".badge"), s=badge?.className.match(/status-([a-z-]+)/)?.[1]||""; row.hidden=!!((q&&!text.includes(q))||(f&&s!==f));}};
    search.addEventListener("input",apply); filter.addEventListener("change",apply); bar.querySelector(".table-reset").addEventListener("click",()=>{search.value="";filter.value="";apply();});
  }
}
function polish(){translate();enhanceTables(); const title=document.getElementById("page-title"); if(title&&TEXT.has(title.textContent.trim())) title.textContent=TEXT.get(title.textContent.trim()); const conn=document.getElementById("connection-status"); if(conn&&TEXT.has(conn.textContent.trim())) conn.textContent=TEXT.get(conn.textContent.trim());}
const observer=new MutationObserver(()=>polish());
observer.observe(document.body,{subtree:true,childList:true,characterData:true});
window.addEventListener("DOMContentLoaded",polish); polish();
