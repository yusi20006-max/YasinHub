const API="http://127.0.0.1:8000/api/status";


async function load(){

    const res = await fetch(API);
    const data = await res.json();

    const app=document.getElementById("app");

    app.innerHTML="";


    data.projects.forEach(p=>{

        let cls="unknown";

        if(p.status==="SUCCESS")
            cls="success";

        if(p.status==="FAILED")
            cls="failed";


        app.innerHTML += `

        <div class="card ${cls}">

        <h2>${p.name}</h2>

        <p>
        وضعیت:
        <b>${p.status}</b>
        </p>

        <p>${p.message}</p>


        <div class="metric">
        <span>آخرین اجرا</span>
        <span>${p.last_run ?? "-"}</span>
        </div>


        <div class="metric">
        <span>دریافت</span>
        <span>${p.metrics.total_fetched_posts ?? 0}</span>
        </div>


        <div class="metric">
        <span>انتشار</span>
        <span>${p.metrics.total_published_posts ?? 0}</span>
        </div>


        <div class="metric">
        <span>کل دیتابیس</span>
        <span>${p.db_stats.total_posts ?? 0}</span>
        </div>


        </div>

        `;

    });


}


load();

setInterval(load,5000);

