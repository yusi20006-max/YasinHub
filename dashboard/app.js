const API = "";

// Theme toggle
const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
    themeToggle.onclick = () => {
        document.body.classList.toggle("dark");
    };
}

// Mobile menu toggle
const menuToggle = document.getElementById("menu-toggle");
const sidebar = document.getElementById("sidebar");
if (menuToggle && sidebar) {
    menuToggle.onclick = () => {
        sidebar.classList.toggle("open");
    };
}

// Connection Status Indicator
function updateConnectionStatus() {
    const statusEl = document.getElementById("connection-status");
    if (!statusEl) return;

    if (navigator.onLine) {
        statusEl.textContent = "🟢 آنلاین";
        statusEl.className = "status-online";
    } else {
        statusEl.textContent = "🔴 آفلاین (عدم اتصال به سرور)";
        statusEl.className = "status-offline";
    }
}

window.addEventListener("online", () => {
    updateConnectionStatus();
    refresh();
});

window.addEventListener("offline", () => {
    updateConnectionStatus();
    refresh();
});

// Helper to safely set text content of elements
function setSafeText(id, text) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
    }
}

// Helper to fetch JSON
async function getJSON(url) {
    if (!navigator.onLine) {
        return { _offline: true };
    }
    try {
        const res = await fetch(API + url);
        if (!res.ok) {
            return { _error: true };
        }
        return await res.json();
    } catch (e) {
        return { _error: true };
    }
}

// Load Dashboard summary metrics
async function loadDashboard() {
    const data = await getJSON("/api/dashboard");
    if (data._offline || data._error) {
        setSafeText("total-services", "آفلاین");
        setSafeText("success", "آفلاین");
        setSafeText("running", "آفلاین");
        setSafeText("failed", "آفلاین");
        setSafeText("unknown", "آفلاین");
        setSafeText("total-posts", "آفلاین");
        setSafeText("published", "آفلاین");
        setSafeText("pending", "آفلاین");
        return;
    }
    const d = data.dashboard || {};

    setSafeText("total-services", d.total_projects || 0);
    setSafeText("success", d.success || 0);
    setSafeText("running", d.running || 0);
    setSafeText("failed", d.failed || 0);
    setSafeText("unknown", d.unknown || 0);
    setSafeText("total-posts", d.total_posts || 0);
    setSafeText("published", d.published_posts || 0);
    setSafeText("pending", d.pending_posts || 0);
}

// Load Metrics (crash-safe)
async function loadMetrics() {
    const data = await getJSON("/api/metrics/yasinrelay");
    if (data._offline || data._error) {
        setSafeText("cpu", "آفلاین");
        setSafeText("memory", "آفلاین");
        setSafeText("uptime", "آفلاین");
        setSafeText("fetched", "آفلاین");
        setSafeText("metrics-published", "آفلاین");
        setSafeText("metrics-failed", "آفلاین");
        setSafeText("error-rate", "آفلاین");
        return;
    }
    const m = data.metrics || {};

    setSafeText("cpu", data.cpu || 0);
    setSafeText("memory", data.memory_mb || 0);
    setSafeText("uptime", data.uptime || 0);
    setSafeText("fetched", m.total_fetched_posts || 0);
    setSafeText("metrics-published", m.total_published_posts || 0);
    setSafeText("metrics-failed", m.total_failed_posts || 0);
    setSafeText("error-rate", m.error_rate_percent || 0);
}

// Load Services
async function loadServices() {
    const servicesData = await getJSON("/api/services");
    const statusData = await getJSON("/api/status");

    const body = document.getElementById("services-body");
    if (!body) return;

    if (servicesData._offline || servicesData._error || statusData._offline || statusData._error) {
        body.innerHTML = `<tr><td colspan="3" style="text-align: center; color: red; font-weight: bold;">عدم اتصال به سرور (آفلاین)</td></tr>`;
        return;
    }

    const reports = statusData.projects || [];
    body.innerHTML = "";

    const services = servicesData.services || [];

    // Dynamically populate log-service select once
    const select = document.getElementById("log-service");
    if (select && select.dataset.populated !== "true") {
        select.innerHTML = "";
        services.forEach(service => {
            const opt = document.createElement("option");
            opt.value = service.name;
            opt.textContent = service.name;
            select.appendChild(opt);
        });
        select.dataset.populated = "true";
        if (services.length > 0) {
            select.value = services[0].name;
            loadLogs();
        }
    }

    services.forEach(service => {
        const report = reports.find(x => x.name === service.name);

        let state = "UNKNOWN";
        let color = "gray";
        let uptime = "-";

        if (report) {
            state = report.status || "UNKNOWN";
            uptime = report.last_run || "-";

            if (state === "RUNNING") {
                color = "green";
            } else if (state === "SUCCESS") {
                color = "blue";
            } else if (state === "FAILED") {
                color = "red";
            } else if (state === "STALE") {
                color = "orange";
            } else if (state === "IDLE") {
                color = "purple";
            }
        }

        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${service.name}</td>
            <td style="color:${color}">
                ${state}
                <br>
                <small>uptime: ${uptime}</small>
            </td>
            <td>
                <button onclick="control('${service.name}','start')">▶</button>
                <button onclick="control('${service.name}','restart')">🔄</button>
                <button onclick="control('${service.name}','stop')">⛔</button>
            </td>
        `;
        body.appendChild(row);
    });
}

// Control service start/restart/stop
async function control(service, action) {
    if (!navigator.onLine) {
        alert("خطا: شما آفلاین هستید و امکان کنترل سرویس‌ها وجود ندارد.");
        return;
    }
    await fetch(`/api/control/${service}/${action}`, {
        method: "POST"
    });
    // Immediately refresh the dashboard states
    await refresh();
}

// Load events log list
async function loadEvents() {
    const data = await getJSON("/api/events");
    const box = document.getElementById("events");
    if (!box) return;

    if (data._offline || data._error) {
        box.innerHTML = `<div style="padding: 20px; text-align: center; color: red; font-weight: bold;">خطا در دریافت رویدادها (آفلاین)</div>`;
        return;
    }

    box.innerHTML = "";

    const events = data.events || [];
    if (events.length === 0) {
        const item = document.createElement("div");
        item.style.padding = "20px";
        item.style.textAlign = "center";
        item.style.color = "#888";
        item.style.fontSize = "0.95em";
        item.textContent = "هیچ رویدادی ثبت نشده است.";
        box.appendChild(item);
        return;
    }

    events.slice(0, 10).forEach(e => {
        let color = "#777";

        if (e.type === "PublishingCompleted") {
            color = "green";
        } else if (e.type === "AIProcessingCompleted") {
            color = "blue";
        } else if (e.type === "DuplicateDetected") {
            color = "orange";
        } else if (e.type === "ERROR") {
            color = "red";
        } else if (e.type === "ProcessingStarted") {
            color = "gray";
        }

        const item = document.createElement("div");
        const isDark = document.body.classList.contains("dark");

        item.style.borderRight = `5px solid ${color}`;
        item.style.padding = "12px";
        item.style.margin = "8px";
        item.style.background = isDark ? "#111827" : "#fff";
        item.style.color = isDark ? "#eee" : "#222";
        item.style.borderRadius = "8px";
        item.style.boxShadow = "0 2px 4px rgba(0,0,0,0.05)";
        item.style.direction = "rtl";

        let timestamp_str = e.timestamp ? `<span style="float: left; font-size: 0.85em; color: #888;">${e.timestamp}</span>` : "";
        let severity_str = e.severity ? ` <span style="font-size: 0.8em; padding: 2px 6px; border-radius: 4px; background: ${isDark ? '#1e293b' : '#f1f5f9'}; color: ${isDark ? '#cbd5e1' : '#475569'}; margin-right: 5px;">${e.severity}</span>` : "";

        item.innerHTML = `
            <div style="overflow: hidden; margin-bottom: 5px;">
                <b style="color:${color}; font-size: 1.1em;">${e.type}</b>
                ${severity_str}
                ${timestamp_str}
            </div>
            <small style="color: ${isDark ? '#94a3b8' : '#4b5563'}; font-weight: bold;">سرویس: ${e.service}</small>
            <p style="margin: 8px 0 0 0; font-size: 0.95em; line-height: 1.4;">${e.message}</p>
        `;
        box.appendChild(item);
    });
}

// Helper to escape HTML to prevent XSS
function escapeHTML(str) {
    return str.replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#039;");
}

// Load logs of selected service with filtering and highlighting
async function loadLogs() {
    const select = document.getElementById("log-service");
    if (!select || !select.value) return;

    const service = select.value;
    const filterInput = document.getElementById("log-filter");
    const filterVal = filterInput ? filterInput.value.trim() : "";

    let url = `/api/logs/${service}?lines=50`;
    if (filterVal) {
        url += `&filter=${encodeURIComponent(filterVal)}`;
    }

    const data = await getJSON(url);
    const logsPre = document.getElementById("logs");
    if (logsPre) {
        if (data._offline || data._error) {
            logsPre.innerHTML = '<span style="color: #f87171; font-weight: bold;">خطا در اتصال به سرور و دریافت لاگ‌ها (آفلاین)</span>';
            return;
        }
        const lines = data.lines || [];
        if (lines.length === 0) {
            logsPre.innerHTML = '<span style="color: #888; font-style: italic;">لاگی برای نمایش وجود ندارد یا فایل لاگ خالی است.</span>';
            return;
        }

        // Escape HTML and highlight ERROR/WARNING lines
        const formattedLines = lines.map(line => {
            const escaped = escapeHTML(line);
            const lowerLine = escaped.toLowerCase();

            if (lowerLine.includes("error")) {
                return `<span style="color: #f87171; font-weight: bold;">${escaped}</span>`;
            } else if (lowerLine.includes("warning")) {
                return `<span style="color: #fbbf24; font-weight: bold;">${escaped}</span>`;
            } else if (lowerLine.includes("success") || lowerLine.includes("completed")) {
                return `<span style="color: #34d399;">${escaped}</span>`;
            }
            return escaped;
        });

        logsPre.innerHTML = formattedLines.join("\n");
    }
}

// Bind log controls
const logServiceSelect = document.getElementById("log-service");
if (logServiceSelect) {
    logServiceSelect.addEventListener("change", loadLogs);
}

const logFilterInput = document.getElementById("log-filter");
if (logFilterInput) {
    logFilterInput.addEventListener("input", loadLogs);
}

// Realtime log updates implementation (checks every 2 seconds)
setInterval(() => {
    const realtimeCheck = document.getElementById("realtime-logs");
    if (realtimeCheck && realtimeCheck.checked) {
        loadLogs();
    }
}, 2000);

// Global refresh function
async function refresh() {
    try {
        updateConnectionStatus();
        await loadDashboard();
        await loadServices();
        await loadMetrics();
        await loadEvents();
        await loadLogs();
    } catch (e) {
        // Safe fail
    }
}

// Initial fetch
refresh();

// Set auto refresh every 15 seconds
setInterval(refresh, 15000);

// Register Service Worker
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/dashboard/sw.js", { scope: "/dashboard/" })
            .then(reg => {
                console.log("ServiceWorker registered successfully with scope: ", reg.scope);
            })
            .catch(err => {
                console.error("ServiceWorker registration failed: ", err);
            });
    });
}
