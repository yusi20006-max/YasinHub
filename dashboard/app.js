console.log('YASIN DASHBOARD LOADED');
const API = "";


// Theme

document
.getElementById("theme-toggle")
.onclick = () => {
    document.body.classList.toggle("dark");
};


// Mobile menu

const menu = document.getElementById("menu-toggle");
const sidebar = document.getElementById("sidebar");

if(menu && sidebar){
    menu.onclick = () => {
        sidebar.classList.toggle("open");
    };
}



async function getJSON(url){

    try {

        const res = await fetch(API + url);
        return await res.json();

    } catch(e){

        return {};

    }

}



// Dashboard cards


console.log("YASIN DEBUG START");

async function loadDashboard(){

    
console.log("CALLING DASHBOARD API");

const data = await getJSON("/api/dashboard");


console.log("DASHBOARD RESPONSE:", data);

document.body.insertAdjacentHTML(
    "afterbegin",
    "<pre id='debug-box' style='background:#222;color:#0f0;padding:10px'>"
    + JSON.stringify(data,null,2)
    + "</pre>"
);

 console.log("DASHBOARD API:", data);

    const d = data.dashboard || {};


    document.getElementById("total-services").textContent =
        d.total_projects || 0;

    document.getElementById("success").textContent =
        d.success || 0;

    document.getElementById("running").textContent =
        d.running || 0;

    document.getElementById("failed").textContent =
        d.failed || 0;

    document.getElementById("unknown").textContent =
        d.unknown || 0;

    document.getElementById("total-posts").textContent =
        d.total_posts || 0;

    document.getElementById("published").textContent =
        d.published_posts || 0;

    document.getElementById("pending").textContent =
        d.pending_posts || 0;

}



// Metrics

async function loadMetrics(){

    const data =
    await getJSON("/api/metrics/yasinrelay");


    document.getElementById("cpu").textContent =
        data.cpu || 0;


    document.getElementById("memory").textContent =
        data.memory_mb || 0;


    document.getElementById("uptime").textContent =
        data.uptime || 0;


    const m = data.metrics || {};


    document.getElementById("fetched").textContent =
        m.total_fetched_posts || 0;


    document.getElementById("metrics-published").textContent =
        m.total_published_posts || 0;


    document.getElementById("metrics-failed").textContent =
        m.total_failed_posts || 0;


    document.getElementById("error-rate").textContent =
        m.error_rate_percent || 0;

}



// Services


async function loadServices(){

    const servicesData =
        await getJSON("/api/services");

    const statusData =
        await getJSON("/api/status");


    const reports =
        statusData.projects || [];


    const body =
        document.getElementById("services-body");


    body.innerHTML = "";


    (servicesData.services || [])
    .forEach(service=>{


        let report =
            reports.find(
                x => x.name === service.name
            );


        let state = "UNKNOWN";
        let color = "gray";
        let uptime = "-";


        if(report){

            state =
                report.status || "UNKNOWN";


            uptime =
                report.last_run || "-";


            if(state === "RUNNING"){
                color = "green";
            }

            else if(state === "SUCCESS"){
                color = "blue";
            }

            else if(state === "FAILED"){
                color = "red";
            }

        }


        const row =
            document.createElement("tr");


        row.innerHTML = `

        <td>
        ${service.name}
        </td>


        <td style="color:${color}">
        ${state}
        <br>
        <small>
        uptime: ${uptime}
        </small>
        </td>


        <td>

        <button onclick="control('${service.name}','start')">
        ▶
        </button>


        <button onclick="control('${service.name}','restart')">
        🔄
        </button>


        <button onclick="control('${service.name}','stop')">
        ⛔
        </button>

        </td>

        `;


        body.appendChild(row);


    });


}



async function control(service, action){


    await fetch(
    `/api/control/${service}/${action}`,
    {
        method:"POST"
    });


    loadDashboard();

}





// Events

async function loadEvents(){

    const data =
    await getJSON("/api/events");


    const box =
    document.getElementById("events");

    console.log("EVENT DATA:", data);



    box.innerHTML = "";

    box.innerHTML += "<pre style='background:#111;color:#0f0;padding:10px'>EVENT COUNT: "
        + (data.events || []).length
        + "</pre>";


    (data.events || [])
    .slice(0,10)
    .forEach(e=>{


        let color = "#777";


        if(e.type === "PublishingCompleted"){
            color = "green";
        }

        else if(e.type === "AIProcessingCompleted"){
            color = "blue";
        }

        else if(e.type === "DuplicateDetected"){
            color = "orange";
        }

        else if(e.type === "ERROR"){
            color = "red";
        }


        else if(e.type === "ProcessingStarted"){
            color = "gray";
        }


        box.innerHTML += `

        <div style="
            border-right:5px solid ${color};
            padding:10px;
            margin:8px;
        ">

        <b style="color:${color}">
        ${e.type}
        </b>

        <br>

        <small>
        ${e.service}
        </small>

        <p>
        ${e.message}
        </p>

        </div>

        `;


    });


}



// Logs

async function loadLogs(){

    const service =
    document.getElementById(
    "log-service"
    ).value;


    const data =
    await getJSON(
    `/api/logs/${service}?lines=30`
    );


    document
    .getElementById("logs")
    .textContent =
    (data.lines || [])
    .join("\n");


}




async function refresh(){

    try {

        console.log("refresh start");

        await loadDashboard();
        console.log("dashboard ok");

        await loadServices();
        console.log("services ok");

        await loadMetrics();
        console.log("metrics ok");

        await loadEvents();
        console.log("events ok");

        await loadLogs();
        console.log("logs ok");

    } catch(e) {

        console.error("Dashboard error:", e);

    }

}



refresh();


// auto refresh

setInterval(
refresh,
15000
);
