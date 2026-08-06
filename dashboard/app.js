const STATUS_API="http://127.0.0.1:8000/api/status";
const DASHBOARD_API="http://127.0.0.1:8000/api/dashboard";

async function load(){

const status=await fetch(STATUS_API).then(r=>r.json());
const dash=await fetch(DASHBOARD_API).then(r=>r.json());

const s=dash.dashboard;

document.getElementById("summary").innerHTML=`
<div class="card">پروژه‌ها<br>${s.total_projects}</div>
<div class="card">موفق<br>${s.success}</div>
<div class="card">درحال اجرا<br>${s.running}</div>
<div class="card">کل پست‌ها<br>${s.total_posts}</div>
<div class="card">منتشر شده<br>${s.published_posts}</div>
<div class="card">Pending<br>${s.pending_posts}</div>
`;

const body=document.getElementById("table-body");
body.innerHTML="";

status.projects.forEach(p=>{

const cls=p.status.toLowerCase();

body.innerHTML+=`
<tr class="${cls}">
<td>${p.name}</td>
<td>${p.status}</td>
<td>${p.last_run??"-"}</td>
<td>${p.metrics.total_fetched_posts??0}</td>
<td>${p.metrics.total_published_posts??0}</td>
<td>${p.db_stats.pending_posts??0}</td>
<td>${p.db_stats.total_posts??0}</td>
</tr>
`;

});

}

load();
setInterval(load,5000);

const btn=document.getElementById("theme-toggle");

btn.onclick=()=>{

document.body.classList.toggle("dark");

localStorage.theme=document.body.classList.contains("dark")
?"dark":"light";

};

if(localStorage.theme==="dark"){
document.body.classList.add("dark");
}
