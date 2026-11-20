// ==========================================================================
// PaveSentry: Real-Time Delhi NCT Pavement Intelligence & Maintenance Predictor
// ==========================================================================
let currentView = "landing";
let currentUser = {
    name: "Executive Engineer",
    role: "Executive Engineer - Delhi PWD",
    email: "engineer@pwd.delhi.gov.in"
};

let map, geojsonLayer;
let chartRisk, chartCondition;
let currentGeojson = null;
let allScheduledSegments = [];
let currentFilter = "all";
let searchTerm = "";
let mapInitialized = false;

// Currency & INR Formatting Helper
function formatINR(amount) {
    if (amount == null || isNaN(amount)) return "₹0";
    const abs = Math.abs(amount);
    if (abs >= 10000000) {
        return `₹${(amount / 10000000).toFixed(2)} Cr`;
    } else if (abs >= 100000) {
        return `₹${(amount / 100000).toFixed(2)} L`;
    } else {
        return `₹${Math.round(amount).toLocaleString("en-IN")}`;
    }
}

// ==========================================================================
// Theme Management: Light / Dark Mode System
// ==========================================================================
function initTheme() {
    const urlParams = window.location.search ? new URLSearchParams(window.location.search) : null;
    const urlTheme = urlParams ? urlParams.get("theme") : null;
    const savedTheme = localStorage.getItem("pavesentry_theme");
    const systemPrefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initialTheme = urlTheme || savedTheme || (systemPrefersDark ? "dark" : "light");
    applyTheme(initialTheme);
}

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    if (document.body) {
        document.body.setAttribute("data-theme", theme);
    }
    localStorage.setItem("pavesentry_theme", theme);

    // Update all theme toggle button icons
    const toggleBtns = document.querySelectorAll(".btn-theme-toggle");
    toggleBtns.forEach(btn => {
        if (theme === "dark") {
            btn.innerHTML = '<i class="fa-solid fa-sun" style="color:#f59e0b;"></i>';
            btn.setAttribute("title", "Switch to Light Mode");
        } else {
            btn.innerHTML = '<i class="fa-solid fa-moon" style="color:#64748b;"></i>';
            btn.setAttribute("title", "Switch to Dark Mode");
        }
    });

    updateChartsForTheme(theme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const newTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(newTheme);
}

function updateChartsForTheme(theme) {
    if (typeof Chart !== "undefined") {
        const isDark = theme === "dark";
        Chart.defaults.color = isDark ? "#94a3b8" : "#64748b";
        Chart.defaults.borderColor = isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.06)";
        const chartsToUpdate = [
            chartRisk,
            chartCondition,
            window.chartScenariosInstance,
            window.chartDecayInstance,
            window.chartFleetOscilloscopeInstance
        ];
        chartsToUpdate.forEach(c => {
            if (c && typeof c.update === "function") {
                c.update();
            }
        });
    }
}

// Window global bindings
window.toggleTheme = toggleTheme;
window.applyTheme = applyTheme;
window.initTheme = initTheme;

// Run immediately to eliminate any flash of white
initTheme();

// ==========================================================================
// SPA Router: navigateTo('landing' | 'auth' | 'workspace')
// ==========================================================================
function navigateTo(viewName) {
    currentView = viewName;
    window.location.hash = viewName;

    document.querySelectorAll(".app-view").forEach(el => el.classList.remove("active-view"));

    const targetEl = document.getElementById(`view-${viewName}`);
    if (targetEl) {
        targetEl.classList.add("active-view");
    }

    window.scrollTo({ top: 0, behavior: "smooth" });

    if (viewName === "workspace") {
        if (!mapInitialized) {
            initMap();
            initCharts();
            loadDashboardStats();
            loadDelhiWeather();
            loadMapGeoJSON();
            loadNetworkCostOfInaction();
            mapInitialized = true;
        }
        
        // Ensure Leaflet recalculates dimensions after CSS display transition settles
        setTimeout(() => {
            if (map) {
                map.invalidateSize();
                if (geojsonLayer && currentGeojson && currentGeojson.features && currentGeojson.features.length > 0) {
                    map.fitBounds(geojsonLayer.getBounds(), { padding: [25, 25] });
                }
            }
        }, 150);
        setTimeout(() => {
            if (map) map.invalidateSize();
        }, 400);

        // Auto-open modal if specified in URL query
        if (window.location.search) {
            const urlParams = new URLSearchParams(window.location.search);
            const autoModal = urlParams.get('modal');
            if (autoModal === 'kanban') setTimeout(() => { if (typeof openKanbanModal === 'function') openKanbanModal(); }, 600);
            else if (autoModal === 'citizen') setTimeout(() => { if (typeof openCitizenPortalModal === 'function') openCitizenPortalModal(); }, 600);
            else if (autoModal === 'waterlogging') setTimeout(() => { if (typeof openWaterloggingModal === 'function') openWaterloggingModal(); }, 600);
            else if (autoModal === 'audit') setTimeout(() => { if (typeof openAuditChainModal === 'function') openAuditChainModal(); }, 600);
            else if (autoModal === 'xai') setTimeout(() => { if (typeof openXaiModal === 'function') openXaiModal(); }, 600);
            else if (autoModal === 'green') setTimeout(() => { if (typeof openGreenRoadsModal === 'function') openGreenRoadsModal(); }, 600);
            else if (autoModal === 'fleet') setTimeout(() => { if (typeof openFleetTelemetryModal === 'function') openFleetTelemetryModal(); }, 600);
            else if (autoModal === 'vision') setTimeout(() => { if (typeof openVisionStudioModal === 'function') openVisionStudioModal(); }, 600);
        }
    }
}

// ==========================================================================
// Authentication & User State Management (FastAPI JWT / Cookie Sessions)
// ==========================================================================
let authToken = localStorage.getItem("pavesentry_token") || null;
let currentAuthTab = "signin";

function getAuthHeaders(extraHeaders = {}) {
    const headers = { ...extraHeaders };
    const token = authToken || localStorage.getItem("pavesentry_token");
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
}

function updateUserUI() {
    const avatarEl = document.getElementById("nav-user-avatar");
    const nameEl = document.getElementById("nav-user-name");
    const roleEl = document.getElementById("prop-active-role");

    const displayName = currentUser.full_name || currentUser.name || "Delhi Officer";
    const displayRole = currentUser.role_display || currentUser.role || "Delhi PWD Engineer";

    if (avatarEl && displayName) {
        avatarEl.innerText = displayName.charAt(0).toUpperCase();
    }
    if (nameEl) {
        nameEl.innerText = displayName;
    }
    if (roleEl) {
        roleEl.innerText = displayRole;
    }

    applyRolePermissionsUI();
}

function applyRolePermissionsUI() {
    const role = (currentUser && currentUser.role) ? currentUser.role : "pwd_engineer";
    
    const btnRetrain = document.getElementById("btn-retrain");
    const btnSync = document.getElementById("btn-live-sync");
    const btnRun = document.getElementById("btn-run-pipeline");
    const btnSurveyMap = document.getElementById("btn-map-survey-upload");
    const sbSurveyLink = document.getElementById("sb-link-survey");
    const sbPotholeLink = document.getElementById("sb-link-pothole");

    if (role === "mcd_planner") {
        // MCD Urban Planner: Read-only access to budget allocations and prioritization scores
        if (btnRetrain) {
            btnRetrain.disabled = true;
            btnRetrain.style.opacity = "0.5";
            btnRetrain.title = "🔒 MCD Urban Planners have read-only access to prioritization scores";
        }
        if (btnSync) {
            btnSync.disabled = true;
            btnSync.style.opacity = "0.5";
            btnSync.title = "🔒 Live telemetry synchronization is managed by Delhi PWD infrastructure";
        }
        if (btnRun) {
            btnRun.disabled = true;
            btnRun.style.opacity = "0.5";
            btnRun.title = "🔒 ML inference pipeline is managed by Delhi PWD";
        }
        if (btnSurveyMap) {
            btnSurveyMap.disabled = true;
            btnSurveyMap.style.opacity = "0.5";
            btnSurveyMap.title = "🔒 Survey ingestion is restricted to PWD Division Engineers & CRRI Auditors";
        }
        if (sbSurveyLink) {
            sbSurveyLink.style.opacity = "0.5";
            sbSurveyLink.title = "🔒 Survey ingestion restricted to PWD Division Engineers & CRRI Auditors";
        }
    } else if (role === "crri_auditor") {
        // CSIR-CRRI Auditor: Inspection and roughness audit validation
        if (btnRetrain) {
            btnRetrain.disabled = true;
            btnRetrain.style.opacity = "0.5";
            btnRetrain.title = "🔒 CSIR-CRRI Auditors validate pavement audits; retraining is reserved for PWD Engineers";
        }
        if (btnSync) {
            btnSync.disabled = true;
            btnSync.style.opacity = "0.5";
            btnSync.title = "🔒 Live network sync is managed by Delhi PWD";
        }
        if (btnRun) {
            btnRun.disabled = false;
            btnRun.style.opacity = "1";
            btnRun.title = "Run ML inference to evaluate condition telemetry";
        }
        if (btnSurveyMap) {
            btnSurveyMap.disabled = false;
            btnSurveyMap.style.opacity = "1";
            btnSurveyMap.title = "Upload laser profilometer / ARRB calibration surveys";
        }
        if (sbSurveyLink) {
            sbSurveyLink.style.opacity = "1";
            sbSurveyLink.title = "Upload laser profilometer / ARRB calibration surveys";
        }
    } else {
        // Delhi PWD Division Engineer: Full access
        [btnRetrain, btnSync, btnRun, btnSurveyMap].forEach(btn => {
            if (btn) {
                btn.disabled = false;
                btn.style.opacity = "1";
                btn.title = "";
            }
        });
        if (sbSurveyLink) sbSurveyLink.style.opacity = "1";
    }

    if (sbPotholeLink) {
        sbPotholeLink.style.opacity = "1";
    }
}

async function handleDemoRoleLogin(email, password) {
    const errorEl = document.getElementById("auth-error-banner");
    if (errorEl) errorEl.style.display = "none";
    const submitBtn = document.getElementById("btn-auth-submit");
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...`;
    }

    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
            credentials: "include"
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Authentication failed.");

        authToken = data.access_token;
        currentUser = data.user;
        localStorage.setItem("pavesentry_token", authToken);
        localStorage.setItem("road_predictor_user", JSON.stringify(currentUser));
        updateUserUI();
        navigateTo("workspace");
    } catch (err) {
        if (errorEl) {
            errorEl.innerText = err.message;
            errorEl.style.display = "block";
        }
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `Continue to Workspace <i class="fa-solid fa-arrow-right"></i>`;
        }
    }
}

async function handleQuickDemoLogin(roleTitle) {
    await handleDemoRoleLogin("ee.central@pwd.delhi.gov.in", "Pwd@Central2026");
}
window.handleQuickDemoLogin = handleQuickDemoLogin;

async function handleFormSubmit(e) {
    e.preventDefault();
    const errorEl = document.getElementById("auth-error-banner");
    if (errorEl) errorEl.style.display = "none";

    const submitBtn = document.getElementById("btn-auth-submit");
    const originalText = submitBtn ? submitBtn.innerHTML : "";
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing...`;
    }

    const email = document.getElementById("auth-email").value.trim();
    const password = document.getElementById("auth-pass").value;

    try {
        let endpoint = "/api/auth/login";
        let bodyPayload = { email, password };

        if (currentAuthTab === "signup") {
            endpoint = "/api/auth/register";
            const fullName = document.getElementById("auth-fullname").value.trim() || "Delhi Officer";
            const role = document.getElementById("auth-role-select").value || "pwd_engineer";
            const division = document.getElementById("auth-division").value.trim() || "Delhi PWD";
            bodyPayload = {
                email,
                password,
                full_name: fullName,
                role,
                division
            };
        }

        const res = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(bodyPayload),
            credentials: "include"
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Authentication request failed.");

        authToken = data.access_token;
        currentUser = data.user;
        localStorage.setItem("pavesentry_token", authToken);
        localStorage.setItem("road_predictor_user", JSON.stringify(currentUser));
        updateUserUI();
        navigateTo("workspace");
    } catch (err) {
        if (errorEl) {
            errorEl.innerText = err.message;
            errorEl.style.display = "block";
        }
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    }
}

async function handleLogout() {
    try {
        await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch (_) {}
    authToken = null;
    currentUser = {
        name: "Guest Officer",
        role: "Guest",
        email: ""
    };
    localStorage.removeItem("pavesentry_token");
    localStorage.removeItem("road_predictor_user");
    navigateTo("landing");
}

function switchAuthTab(tab) {
    currentAuthTab = tab;
    document.querySelectorAll(".auth-tab-btn").forEach(b => b.classList.remove("active"));
    const btn = document.getElementById(`tab-btn-${tab}`);
    if (btn) btn.classList.add("active");

    const nameGroup = document.getElementById("group-auth-name");
    const roleGroup = document.getElementById("group-auth-role");
    const divGroup = document.getElementById("group-auth-division");
    const submitBtn = document.getElementById("btn-auth-submit");

    if (tab === "signup") {
        if (nameGroup) nameGroup.style.display = "block";
        if (roleGroup) roleGroup.style.display = "block";
        if (divGroup) divGroup.style.display = "block";
        if (submitBtn) submitBtn.innerHTML = `Create Account &amp; Continue <i class="fa-solid fa-arrow-right"></i>`;
    } else {
        if (nameGroup) nameGroup.style.display = "none";
        if (roleGroup) roleGroup.style.display = "none";
        if (divGroup) divGroup.style.display = "none";
        if (submitBtn) submitBtn.innerHTML = `Sign In to Workspace <i class="fa-solid fa-arrow-right"></i>`;
    }
}

async function checkAuthSession() {
    try {
        const res = await fetch("/api/auth/me", {
            headers: getAuthHeaders(),
            credentials: "include"
        });
        if (res.ok) {
            const data = await res.json();
            currentUser = data.user;
            localStorage.setItem("road_predictor_user", JSON.stringify(currentUser));
            updateUserUI();
        }
    } catch (_) {}
}

// Landing Page Use-Case Tab Switcher (Delhi Context)
function switchUseCaseTab(e, type) {
    document.querySelectorAll(".usecase-tab").forEach(t => t.classList.remove("active"));
    e.currentTarget.classList.add("active");

    const title = document.getElementById("usecase-title");
    const desc = document.getElementById("usecase-desc");
    const kpi = document.getElementById("usecase-kpi");
    const kpiSub = document.getElementById("usecase-kpi-sub");

    if (type === "pwd") {
        title.innerText = "Multi-Year Capital Allocation & IRC Compliance (Delhi PWD)";
        desc.innerText = "Transition Ring Road and arterial corridor engineering budgets from emergency patching tenders to planned preventive contracts under IRC:82 and IRC:SP:81 specifications.";
        kpi.innerText = "74% Lower Lifecycle Cost";
        kpiSub.innerText = "Replaces reactive spot-patching with scheduled micro-surfacing.";
    } else if (type === "municipal") {
        title.innerText = "MCD Ward Prioritization & Citizen Safety (Delhi NCR)";
        desc.innerText = "Empower Municipal Corporation of Delhi (MCD) planners to rank city corridor interventions based on AADT traffic densities and active pothole counts.";
        kpi.innerText = "4.5× Accident Reduction";
        kpiSub.innerText = "Eliminates high-risk road distress before the monsoon season begins.";
    } else if (type === "crri") {
        title.innerText = "CSIR-CRRI Pavement Condition Index (PCI) Audits";
        desc.innerText = "Monitor continuous IRI roughness decay along NH-44, NH-9, and Barapullah corridors to maintain contractually mandated ride quality and structural endurance.";
        kpi.innerText = "< 2.2 m/km Target IRI";
        kpiSub.innerText = "Keeps Delhi arterial networks within premium performance parameters.";
    }
}

// ==========================================================================
// Main Lifecycle Initializer
// ==========================================================================
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    checkAuthSession();
    const savedUser = localStorage.getItem("road_predictor_user");
    if (savedUser) {
        try {
            currentUser = JSON.parse(savedUser);
        } catch (e) {}
    }
    updateUserUI();

    // Check initial hash route
    const hash = window.location.hash.replace("#", "");
    if (hash === "workspace") {
        navigateTo("workspace");
    } else if (hash === "auth") {
        navigateTo("auth");
    } else {
        navigateTo("landing");
    }

    // Restore feature navigation sidebar state
    const sidebarCollapsed = localStorage.getItem("delhi_sidebar_collapsed");
    const sidebar = document.getElementById("workspace-sidebar");
    if (sidebar && sidebarCollapsed === "true" && window.innerWidth > 992) {
        sidebar.classList.add("collapsed");
    }
    initSidebarScrollSpy();

    setupEventListeners();
});

// ==========================================================================
// Map Module (Leaflet.js — Centered on Delhi NCR)
// Free & Open-Source GIS — No API Keys / Tokens Required
// ==========================================================================
function initMap() {
    if (map) return;

    const mapEl = document.getElementById("map");
    if (!mapEl) return;

    map = L.map("map", {
        zoomControl: true,
        attributionControl: true
    }).setView([28.6139, 77.2090], 11);

    // 1. Esri Satellite Imagery (High-Resolution Global Satellite Imagery — 100% Free, NO API Key)
    const esriSatellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        maxZoom: 19
    });

    // 2. Esri Boundaries, Highway & Place Name Labels Overlay (Transparent PNG)
    const esriLabels = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
        attribution: 'Labels &copy; Esri',
        maxZoom: 19
    });

    // Combined Satellite Hybrid Layer (Satellite Photography + Roads & Place Names)
    const esriHybrid = L.layerGroup([esriSatellite, esriLabels]);

    // 3. Esri World Street Map (Alternative Vector-style Cartography)
    const esriStreets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, TomTom',
        maxZoom: 19
    });

    // 4. OpenStreetMap Humanitarian / HOT (High-contrast road network)
    const osmHot = L.tileLayer("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, Tiles style by <a href="https://www.hotosm.org/">HOT</a>',
        maxZoom: 19
    });

    // Set Satellite Hybrid as the active default base layer
    esriHybrid.addTo(map);

    // Layer switcher control allowing quick toggling between Satellite and Cartographic maps
    L.control.layers({
        "🛰️ Satellite Hybrid (Default)": esriHybrid,
        "🌍 Pure Satellite (Imagery Only)": esriSatellite,
        "🛣️ Esri Streets (Road Network)": esriStreets,
        "🗺️ OSM Humanitarian (High Contrast)": osmHot
    }, null, { position: "topright" }).addTo(map);

    // Scale control
    L.control.scale({ imperial: false, metric: true, position: "bottomleft" }).addTo(map);

    // Ensure map tiles render properly after DOM rendering
    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 250);

    window.addEventListener("resize", () => {
        if (map) map.invalidateSize();
    });
}

// Fetch and populate Live Delhi Weather Telemetry
async function loadDelhiWeather() {
    try {
        const res = await fetch("/api/delhi/weather");
        const weather = await res.json();
        
        const tempEl = document.getElementById("weather-temp");
        const rainEl = document.getElementById("weather-rain");
        const humEl = document.getElementById("weather-hum");
        const badgeEl = document.getElementById("weather-source-badge");
        
        if (tempEl) tempEl.innerText = `${weather.current_temperature_c || weather.avg_temperature_c}°C`;
        if (rainEl) rainEl.innerText = `${weather.annual_rainfall_mm} mm/yr`;
        if (humEl) humEl.innerText = `${weather.humidity_pct}%`;
        if (badgeEl) {
            badgeEl.innerText = weather.is_live ? "🟢 Live Open-Meteo API" : "⚪ Delhi IMD Baseline";
        }
    } catch (err) {
        console.error("Failed to load Delhi weather telemetry:", err);
    }
}

// Fetch and populate KPI Cards
async function loadDashboardStats(zone = null) {
    try {
        const activeZone = zone || currentZoneFilter;
        const url = activeZone && activeZone !== "all" 
            ? `/api/dashboard/stats?zone=${encodeURIComponent(activeZone)}` 
            : "/api/dashboard/stats";
        const res = await fetch(url);
        const stats = await res.json();

        const zoneName = activeZone && activeZone !== "all" ? activeZone : "Delhi NCT";
        document.getElementById("stat-total-km").innerText = `${stats.total_length_km} km`;
        document.getElementById("stat-total-segments").innerText = `${stats.total_segments} Corridors (${zoneName})`;
        
        document.getElementById("stat-high-risk").innerText = stats.risk_distribution.High || 0;
        document.getElementById("stat-pothole-count").innerText = `${stats.total_active_potholes} Active Potholes`;
        
        document.getElementById("stat-avg-pci").innerText = `${stats.avg_pci} / 100`;
        document.getElementById("stat-avg-iri").innerText = `Avg IRI: ${stats.avg_iri} m/km`;
        
        document.getElementById("stat-savings").innerText = stats.potential_savings_formatted || formatINR(stats.potential_savings_inr);

        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const syncElem = document.getElementById("prop-last-sync");
        if (syncElem) syncElem.innerText = `Synced at ${timeStr} · ${zoneName}`;

        updateCharts(stats);
    } catch (err) {
        console.error("Failed to load dashboard stats:", err);
    }
}

// Fallback authentic Delhi arterial corridors if backend is starting or offline
function getDelhiFallbackGeoJSON() {
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": { "type": "LineString", "coordinates": [[77.165, 28.592], [77.208, 28.567], [77.255, 28.571], [77.247, 28.629], [77.230, 28.667], [77.170, 28.692], [77.125, 28.645], [77.165, 28.592]] },
                "properties": { "name": "Mahatma Gandhi Ring Road (Inner Ring Road)", "city_zone": "Central Delhi", "road_type": "Highway", "surface_type": "Bituminous Concrete", "length_km": 4.8, "lanes": 8, "pci": 42.0, "iri": 5.1, "aadt": 85000, "heavy_vehicle_pct": 22.0, "predicted_risk_level": "High", "pothole_probability": 0.94, "priority_score": 0.885, "est_preventive_cost_inr": 42000000, "est_reactive_cost_inr": 150000000, "recommended_action": "Full Reconstruction & Sub-base Work (IRC:37)" }
            },
            {
                "type": "Feature",
                "geometry": { "type": "LineString", "coordinates": [[77.150, 28.540], [77.210, 28.545], [77.260, 28.548], [77.295, 28.610]] },
                "properties": { "name": "Outer Ring Road (NH-44 Stretch)", "city_zone": "South Delhi", "road_type": "Highway", "surface_type": "Bituminous Concrete", "length_km": 6.2, "lanes": 6, "pci": 58.5, "iri": 3.8, "aadt": 78000, "heavy_vehicle_pct": 18.0, "predicted_risk_level": "Medium", "pothole_probability": 0.52, "priority_score": 0.612, "est_preventive_cost_inr": 29000000, "est_reactive_cost_inr": 88000000, "recommended_action": "Bituminous Concrete (BC) Mill & Overlay (IRC:82)" }
            },
            {
                "type": "Feature",
                "geometry": { "type": "LineString", "coordinates": [[77.255, 28.588], [77.240, 28.583], [77.220, 28.575], [77.210, 28.573]] },
                "properties": { "name": "Barapullah Elevated Corridor", "city_zone": "South East Delhi", "road_type": "Arterial", "surface_type": "Rigid Concrete", "length_km": 3.5, "lanes": 4, "pci": 82.0, "iri": 2.1, "aadt": 45000, "heavy_vehicle_pct": 8.0, "predicted_risk_level": "Low", "pothole_probability": 0.08, "priority_score": 0.285, "est_preventive_cost_inr": 8500000, "est_reactive_cost_inr": 28000000, "recommended_action": "Routine Inspection & Monsoon Drain Clearance" }
            },
            {
                "type": "Feature",
                "geometry": { "type": "LineString", "coordinates": [[77.248, 28.630], [77.275, 28.632], [77.295, 28.635], [77.315, 28.645]] },
                "properties": { "name": "Vikas Marg (ITO to Preet Vihar)", "city_zone": "East Delhi", "road_type": "Arterial", "surface_type": "Bituminous Concrete", "length_km": 4.1, "lanes": 6, "pci": 49.0, "iri": 4.6, "aadt": 62000, "heavy_vehicle_pct": 14.0, "predicted_risk_level": "High", "pothole_probability": 0.88, "priority_score": 0.795, "est_preventive_cost_inr": 31000000, "est_reactive_cost_inr": 112000000, "recommended_action": "Full Reconstruction & Sub-base Work (IRC:37)" }
            },
            {
                "type": "Feature",
                "geometry": { "type": "LineString", "coordinates": [[77.258, 28.570], [77.275, 28.540], [77.290, 28.510], [77.305, 28.490]] },
                "properties": { "name": "Mathura Road (Ashram to Badarpur)", "city_zone": "South East Delhi", "road_type": "Highway", "surface_type": "Bituminous Concrete", "length_km": 7.4, "lanes": 6, "pci": 62.0, "iri": 3.4, "aadt": 69000, "heavy_vehicle_pct": 19.0, "predicted_risk_level": "Medium", "pothole_probability": 0.44, "priority_score": 0.540, "est_preventive_cost_inr": 35000000, "est_reactive_cost_inr": 96000000, "recommended_action": "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)" }
            },
            {
                "type": "Feature",
                "geometry": { "type": "LineString", "coordinates": [[77.165, 28.598], [77.185, 28.602], [77.200, 28.605]] },
                "properties": { "name": "Sardar Patel Marg (Dhaula Kuan)", "city_zone": "New Delhi (NDMC)", "road_type": "Arterial", "surface_type": "Bituminous Concrete", "length_km": 2.8, "lanes": 6, "pci": 76.5, "iri": 2.6, "aadt": 54000, "heavy_vehicle_pct": 11.0, "predicted_risk_level": "Low", "pothole_probability": 0.14, "priority_score": 0.342, "est_preventive_cost_inr": 12000000, "est_reactive_cost_inr": 38000000, "recommended_action": "Routine Inspection & Monsoon Drain Clearance" }
            }
        ]
    };
}

// ==========================================================================
// Phase 1 Interactive Features: Map View Modes & Zone Filter
// ==========================================================================
let currentMapMode = "risk"; // "risk" | "iri" | "pci"
let currentZoneFilter = "all";
let segmentLayersMap = {};
let activeHighlightLayer = null;
let currentInspectedSegment = null;
let customBudgetDebounce = null;

function getFeatureColor(feature) {
    const props = feature.properties || {};
    if (currentMapMode === "iri") {
        const iri = props.iri != null ? props.iri : 3.2;
        if (iri > 4.5) return "#ff3344"; // Rough
        if (iri > 3.0) return "#ffaa00"; // Moderate
        return "#00e676"; // Smooth
    } else if (currentMapMode === "pci") {
        const pci = props.pci != null ? props.pci : 70;
        if (pci < 50) return "#ff3344"; // Poor / Failed
        if (pci < 75) return "#ffaa00"; // Fair
        return "#00e676"; // Good
    } else {
        const risk = props.predicted_risk_level || "Low";
        if (risk === "High") return "#ff3344";
        if (risk === "Medium") return "#ffaa00";
        return "#00e676";
    }
}

function setMapViewMode(mode) {
    currentMapMode = mode;
    document.querySelectorAll(".map-mode-btn").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-mode") === mode);
    });

    updateMapLegend();
    if (currentGeojson) {
        renderGeoJsonOnMap(currentGeojson);
    }
}

function updateMapLegend() {
    const legendEl = document.getElementById("map-legend");
    if (!legendEl) return;

    if (currentMapMode === "risk") {
        legendEl.innerHTML = `
            <span class="legend-item"><span class="legend-color high"></span> High (&lt; 55)</span>
            <span class="legend-item"><span class="legend-color med"></span> Med (55–70)</span>
            <span class="legend-item"><span class="legend-color low"></span> Low (&gt; 70)</span>
        `;
    } else if (currentMapMode === "iri") {
        legendEl.innerHTML = `
            <span class="legend-item"><span class="legend-color low"></span> Smooth (&lt; 3.0)</span>
            <span class="legend-item"><span class="legend-color med"></span> Moderate (3.0–4.5)</span>
            <span class="legend-item"><span class="legend-color high"></span> Rough (&gt; 4.5)</span>
        `;
    } else if (currentMapMode === "pci") {
        legendEl.innerHTML = `
            <span class="legend-item"><span class="legend-color low"></span> Good (&ge; 75)</span>
            <span class="legend-item"><span class="legend-color med"></span> Fair (50–74)</span>
            <span class="legend-item"><span class="legend-color high"></span> Poor (&lt; 50)</span>
        `;
    }
}

function toggleMapFullscreen() {
    const mapCard = document.getElementById("sec-gis-map");
    const btn = document.getElementById("btn-toggle-fullscreen");
    if (!mapCard) return;

    const isFull = mapCard.classList.toggle("fullscreen-mode");
    if (btn) {
        btn.innerHTML = isFull ? `<i class="fa-solid fa-compress"></i> Normal View` : `<i class="fa-solid fa-expand"></i> Fullscreen`;
    }

    setTimeout(() => {
        if (map) {
            map.invalidateSize();
            if (geojsonLayer && currentGeojson && currentGeojson.features && currentGeojson.features.length > 0) {
                map.fitBounds(geojsonLayer.getBounds(), { padding: [30, 30] });
            }
        }
    }, 220);
}

function resetMapBounds() {
    if (!map) return;
    if (geojsonLayer && currentGeojson && currentGeojson.features && currentGeojson.features.length > 0) {
        map.fitBounds(geojsonLayer.getBounds(), { padding: [35, 35] });
    } else {
        map.setView([28.6139, 77.2090], 11);
    }
}

function zoneMatches(itemZone, filter) {
    if (!filter || filter === "all") return true;
    if (!itemZone) return false;
    const z = filter.trim();
    if (z === "East Delhi & Shahdara" || z === "East Delhi") {
        return itemZone === "East Delhi" || itemZone === "North East Delhi" || itemZone.includes("Shahdara");
    }
    if (z === "NDMC" || z.includes("NDMC") || z.includes("New Delhi")) {
        return itemZone.includes("NDMC") || itemZone.includes("New Delhi");
    }
    if (z === "North West" || z === "North West Delhi") {
        return itemZone.includes("North West");
    }
    if (z === "South Delhi") {
        return itemZone === "South Delhi";
    }
    return itemZone === z;
}

function filterMapAndTableByZone(zone) {
    currentZoneFilter = zone;
    
    // Synchronize both administrative division dropdowns
    const mapSelect = document.getElementById("map-zone-filter");
    if (mapSelect && mapSelect.value !== zone) mapSelect.value = zone;
    
    const headerSelect = document.getElementById("header-zone-filter");
    if (headerSelect && headerSelect.value !== zone) headerSelect.value = zone;

    // Synchronize sidebar administrative division pills
    document.querySelectorAll(".sb-div-pill").forEach(pill => {
        pill.classList.toggle("active", pill.getAttribute("data-zone") === zone);
    });

    // 1. Re-render Leaflet polylines filtered by division and auto-fit bounds
    if (currentGeojson) {
        renderGeoJsonOnMap(currentGeojson);
    }

    // 2. Refresh KPI statistics and condition charts for this administrative division
    loadDashboardStats(currentZoneFilter);

    // 3. Recalculate Knapsack schedule optimizer for this administrative division
    triggerOptimization();
}

function renderGeoJsonOnMap(data) {
    if (geojsonLayer) {
        map.removeLayer(geojsonLayer);
    }
    if (activeHighlightLayer) {
        map.removeLayer(activeHighlightLayer);
        activeHighlightLayer = null;
    }
    segmentLayersMap = {};

    let featuresToRender = (data && data.features) ? data.features : [];
    if (currentZoneFilter && currentZoneFilter !== "all") {
        featuresToRender = featuresToRender.filter(f => f.properties && zoneMatches(f.properties.city_zone, currentZoneFilter));
    }

    // Update Feature Navigation Sidebar Map Corridor Count Badge
    const sbMapCount = document.getElementById("sb-map-count");
    if (sbMapCount) {
        sbMapCount.innerText = featuresToRender.length;
    }

    const filteredData = {
        type: "FeatureCollection",
        features: featuresToRender
    };

    geojsonLayer = L.geoJSON(filteredData, {
        style: (feature) => {
            return {
                color: getFeatureColor(feature),
                weight: 4.5,
                opacity: 0.95,
                lineCap: "round",
                lineJoin: "round"
            };
        },
        onEachFeature: (feature, layer) => {
            const props = feature.properties || {};
            if (props.segment_id) {
                segmentLayersMap[props.segment_id] = layer;
            }

            const prevCost = props.est_preventive_cost_inr;
            const reactCost = props.est_reactive_cost_inr;
            
            const popupContent = `
                <div style="font-size: 13px; line-height: 1.6; color: #37352f; min-width: 250px;">
                    <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px; border-bottom: 1px solid #e3e2e0; padding-bottom: 4px;">
                        ${props.name}
                    </div>
                    <div><b>Zone:</b> <span class="tag-badge" style="background:#f1f1ef; color:#37352f; font-size:11px;">${props.city_zone || 'Delhi NCT'}</span></div>
                    <div><b>Classification:</b> ${props.road_type} (${props.length_km} km, ${props.lanes} lanes)</div>
                    <div><b>PCI:</b> <span style="font-weight:600; color:${props.pci < 55 ? '#c43828' : '#0f7b6c'};">${props.pci}</span>/100 | <b>IRI:</b> ${props.iri} m/km</div>
                    <div><b>Risk Level:</b> <span class="tag-badge ${props.predicted_risk_level}">${props.predicted_risk_level}</span> (${((props.pothole_probability || 0) * 100).toFixed(1)}%)</div>
                    <div style="margin-top:6px; padding-top:6px; border-top:1px dashed #e3e2e0; display:flex; justify-content:space-between; align-items:center;">
                        <span><b>Prev:</b> ${formatINR(prevCost)}</span>
                        <button onclick="inspectSegment('${props.segment_id}')" style="background:var(--accent); color:#fff; border:none; border-radius:3px; padding:3px 8px; font-size:11px; cursor:pointer;">
                            Inspect &rarr;
                        </button>
                    </div>
                </div>
            `;
            layer.bindPopup(popupContent);

            layer.on("click", (e) => {
                L.DomEvent.stopPropagation(e);
                inspectSegment(props.segment_id);
            });
            
            layer.on("mouseover", function () {
                this.setStyle({ weight: 7.5, opacity: 1.0 });
            });
            layer.on("mouseout", function () {
                geojsonLayer.resetStyle(this);
            });
        }
    }).addTo(map);

    if (featuresToRender.length > 0) {
        map.fitBounds(geojsonLayer.getBounds(), { padding: [25, 25] });
    }
}

// Load Segment GeoJSON & Render Polylines on Delhi Map
async function loadMapGeoJSON() {
    try {
        const res = await fetch("/api/segments/geojson");
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        currentGeojson = await res.json();
        renderGeoJsonOnMap(currentGeojson);
        updateConditionChart();
        triggerOptimization();
    } catch (err) {
        console.warn("Backend /api/segments/geojson unavailable; rendering cached Delhi NCT corridor network:", err);
        currentGeojson = getDelhiFallbackGeoJSON();
        renderGeoJsonOnMap(currentGeojson);
        updateConditionChart();
        triggerOptimization();
    }
}

// ==========================================================================
// Chart.js Module
// ==========================================================================
function initCharts() {
    const ctxRisk = document.getElementById("chart-risk").getContext("2d");
    chartRisk = new Chart(ctxRisk, {
        type: "doughnut",
        data: {
            labels: ["High Risk", "Medium Risk", "Low Risk"],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: ["#c43828", "#b75e0e", "#0f7b6c"],
                borderWidth: 2,
                borderColor: "#ffffff"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { 
                    position: "bottom", 
                    labels: { 
                        color: "#605e5a", 
                        font: { family: 'Inter', size: 12, weight: 500 },
                        padding: 14
                    } 
                }
            },
            cutout: "68%"
        }
    });

    const ctxCond = document.getElementById("chart-condition").getContext("2d");
    chartCondition = new Chart(ctxCond, {
        type: "bar",
        data: {
            labels: ["Good (80-100)", "Fair (60-79)", "Poor (40-59)", "Failed (<40)"],
            datasets: [{
                label: "Segments Count",
                data: [0, 0, 0, 0],
                backgroundColor: "#0f7b6c",
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { 
                    ticks: { color: "#9b9a97", font: { family: 'Inter', size: 11 } }, 
                    grid: { display: false } 
                },
                y: { 
                    ticks: { color: "#9b9a97", font: { family: 'JetBrains Mono', size: 11 } }, 
                    grid: { color: "#edece9" } 
                }
            }
        }
    });
}

function updateConditionChart() {
    if (chartCondition && currentGeojson && currentGeojson.features) {
        let good = 0, fair = 0, poor = 0, failed = 0;
        currentGeojson.features.forEach(f => {
            const pci = f.properties.pci;
            if (pci >= 80) good++;
            else if (pci >= 60) fair++;
            else if (pci >= 40) poor++;
            else failed++;
        });

        chartCondition.data.datasets[0].data = [good, fair, poor, failed];
        chartCondition.update();
    }
}

function updateCharts(stats) {
    if (chartRisk && stats && stats.risk_distribution) {
        chartRisk.data.datasets[0].data = [
            stats.risk_distribution.High || 0,
            stats.risk_distribution.Medium || 0,
            stats.risk_distribution.Low || 0
        ];
        chartRisk.update();
    }
    updateConditionChart();
}

// ==========================================================================
// Corridor Inspection Drawer & Bidirectional Map Sync
// ==========================================================================
function inspectSegment(segmentId) {
    if (!currentGeojson || !currentGeojson.features) return;
    
    const feature = currentGeojson.features.find(f => f.properties && f.properties.segment_id === segmentId);
    if (!feature) return;

    const props = feature.properties;
    currentInspectedSegment = props;

    const sched = allScheduledSegments.find(s => s.segment_id === segmentId);

    // Update Header
    const nameEl = document.getElementById("drawer-road-name");
    if (nameEl) nameEl.innerText = props.name || "Corridor Segment";
    
    const zoneBadge = document.getElementById("drawer-zone-badge");
    if (zoneBadge) zoneBadge.innerText = props.city_zone || "Delhi NCT";
    
    const classPill = document.getElementById("drawer-classification");
    if (classPill) classPill.innerText = `${props.road_type || 'Arterial'} (${props.length_km || 0} km · ${props.lanes || 2} Lanes)`;

    // Update Health Banner
    const pciEl = document.getElementById("drawer-pci-val");
    if (pciEl) pciEl.innerText = props.pci != null ? props.pci : "--";
    
    const riskVal = document.getElementById("drawer-risk-val");
    if (riskVal) {
        riskVal.innerText = props.predicted_risk_level || "Low";
        riskVal.className = `health-val ${props.predicted_risk_level === 'High' ? 'text-alert' : (props.predicted_risk_level === 'Medium' ? 'text-orange' : 'text-accent')}`;
    }
    
    const iriEl = document.getElementById("drawer-iri-val");
    if (iriEl) iriEl.innerText = props.iri != null ? `${props.iri}` : "--";
    
    const netSav = (sched && sched.net_savings_inr) || (props.est_reactive_cost_inr - props.est_preventive_cost_inr);
    const savEl = document.getElementById("drawer-savings-val");
    if (savEl) savEl.innerText = formatINR(netSav);

    // Specifications Grid
    const lenEl = document.getElementById("drawer-length");
    if (lenEl) lenEl.innerText = `${props.length_km || 0} km`;
    
    const lanesEl = document.getElementById("drawer-lanes");
    if (lanesEl) lanesEl.innerText = `${props.lanes || 2} Lanes`;
    
    const surfEl = document.getElementById("drawer-surface");
    if (surfEl) surfEl.innerText = props.surface_type || "Bituminous Concrete";
    
    const currYear = new Date().getFullYear();
    const age = props.construction_year ? (currYear - props.construction_year) : 6;
    const builtEl = document.getElementById("drawer-built");
    if (builtEl) builtEl.innerText = props.construction_year ? `${props.construction_year} (${age} yrs old)` : "--";
    
    const maintEl = document.getElementById("drawer-maint");
    if (maintEl) maintEl.innerText = props.last_major_maintenance_year ? `${props.last_major_maintenance_year}` : "Original Construction";
    
    const aadtEl = document.getElementById("drawer-aadt");
    if (aadtEl) aadtEl.innerText = props.aadt ? `${props.aadt.toLocaleString("en-IN")} PCU` : "--";
    
    const heavyEl = document.getElementById("drawer-heavy");
    if (heavyEl) heavyEl.innerText = props.heavy_vehicle_pct ? `${props.heavy_vehicle_pct}% Commercial` : "--";
    
    const rainEl = document.getElementById("drawer-rain");
    if (rainEl) rainEl.innerText = props.annual_rainfall_mm ? `${props.annual_rainfall_mm} mm/yr` : "--";

    // Distress Indicators & Progress Bars
    const crackPct = props.crack_density_pct != null ? props.crack_density_pct : 0;
    const crackEl = document.getElementById("drawer-cracks");
    if (crackEl) crackEl.innerText = `${crackPct}%`;
    const crackBar = document.getElementById("drawer-crack-bar");
    if (crackBar) {
        crackBar.style.width = `${Math.min(100, crackPct * 2)}%`;
        crackBar.style.background = crackPct > 30 ? "#ff3344" : (crackPct > 15 ? "#ffaa00" : "#00e676");
    }

    const rutMm = props.rut_depth_mm != null ? props.rut_depth_mm : 0;
    const rutEl = document.getElementById("drawer-rut");
    if (rutEl) rutEl.innerText = `${rutMm} mm`;
    const rutBar = document.getElementById("drawer-rut-bar");
    if (rutBar) {
        rutBar.style.width = `${Math.min(100, rutMm * 4)}%`;
        rutBar.style.background = rutMm > 15 ? "#ff3344" : (rutMm > 8 ? "#ffaa00" : "#00e676");
    }

    const potholeCnt = props.pothole_count != null ? props.pothole_count : 0;
    const potEl = document.getElementById("drawer-potholes");
    if (potEl) potEl.innerText = `${potholeCnt} Active Potholes`;
    const potholeBar = document.getElementById("drawer-pothole-bar");
    if (potholeBar) {
        potholeBar.style.width = `${Math.min(100, potholeCnt * 8)}%`;
        potholeBar.style.background = potholeCnt > 5 ? "#ff3344" : (potholeCnt > 2 ? "#ffaa00" : "#00e676");
    }

    // AI Forecast
    const probPct = props.pothole_probability != null ? (props.pothole_probability * 100).toFixed(1) : "0.0";
    const probEl = document.getElementById("drawer-prob");
    if (probEl) probEl.innerText = `${probPct}% failure risk`;
    
    const prioEl = document.getElementById("drawer-priority");
    if (prioEl) prioEl.innerText = props.priority_score != null ? `${props.priority_score}` : "--";
    
    const schedMonthEl = document.getElementById("drawer-sched-month");
    if (schedMonthEl) {
        if (sched && sched.scheduled_month) {
            schedMonthEl.innerText = `Scheduled in ${sched.scheduled_month}`;
            schedMonthEl.style.color = "var(--accent)";
        } else {
            schedMonthEl.innerText = "Deferred (Beyond current 12-month budget)";
            schedMonthEl.style.color = "var(--text-muted)";
        }
    }

    // IRC Action & Costs
    const actionBadge = document.getElementById("drawer-action-badge");
    if (actionBadge) actionBadge.innerText = props.recommended_action || "Routine Pavement Inspection";
    
    const prevEl = document.getElementById("drawer-prev-cost");
    if (prevEl) prevEl.innerText = formatINR(props.est_preventive_cost_inr);
    
    const reactEl = document.getElementById("drawer-react-cost");
    if (reactEl) reactEl.innerText = formatINR(props.est_reactive_cost_inr);

    // Open Drawer & Backdrop
    const drawer = document.getElementById("inspection-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    if (drawer) drawer.classList.add("open");
    if (backdrop) backdrop.classList.add("active");

    // Highlight row in table
    document.querySelectorAll(".notion-table tbody tr").forEach(tr => {
        tr.classList.remove("row-selected");
    });
    const targetRow = document.getElementById(`row-${segmentId}`);
    if (targetRow) {
        targetRow.classList.add("row-selected");
        targetRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // Highlight polyline on map
    highlightSegmentOnMap(feature);

    // Load CSIR-CRRI audit validation status for this corridor
    loadSegmentAuditStatus(segmentId, props);

    // Load Phase D: TreeSHAP Feature Attribution & Explainable AI
    loadCorridorXai(segmentId);
}

// ==========================================================================
// CSIR-CRRI Roughness Audit & IRC:82 Compliance Certification
// ==========================================================================
async function loadSegmentAuditStatus(segmentId, props) {
    const iriInput = document.getElementById("audit-input-iri");
    const pciInput = document.getElementById("audit-input-pci");
    const notesInput = document.getElementById("audit-input-notes");
    const certDisplay = document.getElementById("drawer-audit-cert-display");
    const statusBadge = document.getElementById("drawer-audit-status-badge");
    const btnSubmit = document.getElementById("btn-submit-audit");

    if (iriInput) iriInput.value = (props.iri != null) ? props.iri : 2.4;
    if (pciInput) pciInput.value = (props.pci != null) ? Math.round(props.pci) : 75;
    if (notesInput) notesInput.value = "";
    if (certDisplay) certDisplay.style.display = "none";

    const userRole = (currentUser && currentUser.role) ? currentUser.role : "pwd_engineer";
    if (btnSubmit) {
        if (userRole === "mcd_planner") {
            btnSubmit.disabled = true;
            btnSubmit.style.opacity = "0.5";
            btnSubmit.title = "🔒 MCD Urban Planners have read-only access. Only CRRI Auditors & PWD Engineers can certify.";
        } else {
            btnSubmit.disabled = false;
            btnSubmit.style.opacity = "1";
            btnSubmit.title = "Issue official IRC:82 compliance certificate";
        }
    }

    try {
        const res = await fetch(`/api/audit/validations?segment_id=${encodeURIComponent(segmentId)}`);
        if (res.ok) {
            const data = await res.json();
            if (data.audits && data.audits.length > 0) {
                const latest = data.audits[0];
                if (statusBadge) {
                    const isPass = latest.compliance_status && latest.compliance_status.includes("Compliant");
                    const isCond = latest.compliance_status && latest.compliance_status.includes("Conditional");
                    const bg = isPass ? "#e8f4f0" : (isCond ? "#fef3c7" : "#fee2e2");
                    const color = isPass ? "#0f7b6c" : (isCond ? "#92400e" : "#991b1b");
                    const icon = isPass ? "fa-circle-check" : (isCond ? "fa-triangle-exclamation" : "fa-circle-xmark");
                    statusBadge.innerHTML = `<span class="tag-badge" style="background:${bg}; color:${color}; font-size:11px;"><i class="fa-solid ${icon}"></i> ${isPass ? 'IRC:82 Certified' : (isCond ? 'Conditional' : 'Non-Compliant')}</span>`;
                }

                const certCodeEl = document.getElementById("audit-cert-code");
                const certStatusEl = document.getElementById("audit-cert-status");
                const certAuditorEl = document.getElementById("audit-cert-auditor");

                if (certCodeEl) certCodeEl.innerText = latest.certificate_code || "CRRI-NCT-2026-VAL";
                if (certStatusEl) certStatusEl.innerText = latest.compliance_status || "Compliant with IRC:82";
                if (certAuditorEl) {
                    const dStr = latest.audit_date ? new Date(latest.audit_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "Recent";
                    certAuditorEl.innerText = `Certified by ${latest.auditor_name || 'CSIR-CRRI Auditor'} (${latest.auditor_email || 'crri.res.in'}) on ${dStr}`;
                }
                if (certDisplay) certDisplay.style.display = "block";
                return;
            }
        }
    } catch (_) {}

    if (statusBadge) {
        statusBadge.innerHTML = `<span class="tag-badge" style="background:var(--tag-gray-bg); color:var(--text-secondary); font-size:11px;">Pending Inspection</span>`;
    }
}

async function submitCrriAudit() {
    if (!currentInspectedSegment) {
        alert("Please select a corridor segment on the map or table first.");
        return;
    }

    const userRole = (currentUser && currentUser.role) ? currentUser.role : "pwd_engineer";
    if (userRole === "mcd_planner") {
        alert("🔒 Permission Denied (HTTP 403):\nMCD Urban Planners have read-only access to prioritization scores.\nOnly CSIR-CRRI Auditors and Delhi PWD Engineers can issue official IRC:82 roughness audit certificates.");
        return;
    }

    const iriVal = parseFloat(document.getElementById("audit-input-iri").value);
    const pciVal = parseFloat(document.getElementById("audit-input-pci").value);
    const notesVal = document.getElementById("audit-input-notes").value.trim();

    if (isNaN(iriVal) || isNaN(pciVal)) {
        alert("Please enter valid numeric values for measured IRI and PCI.");
        return;
    }

    const btnSubmit = document.getElementById("btn-submit-audit");
    const originalText = btnSubmit ? btnSubmit.innerHTML : "";
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Certifying with CRRI Digital Seal...`;
    }

    try {
        const res = await fetch("/api/audit/validate", {
            method: "POST",
            headers: getAuthHeaders({ "Content-Type": "application/json" }),
            credentials: "include",
            body: JSON.stringify({
                segment_id: currentInspectedSegment.segment_id,
                measured_iri: iriVal,
                measured_pci: pciVal,
                audit_notes: notesVal || "Official CSIR-CRRI Laser Profilometer Network Audit"
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Audit certification request failed.");
        }

        const v = data.validation;
        const certCodeEl = document.getElementById("audit-cert-code");
        const certStatusEl = document.getElementById("audit-cert-status");
        const certAuditorEl = document.getElementById("audit-cert-auditor");
        const certDisplay = document.getElementById("drawer-audit-cert-display");
        const statusBadge = document.getElementById("drawer-audit-status-badge");

        if (certCodeEl) certCodeEl.innerText = v.certificate_code;
        if (certStatusEl) certStatusEl.innerText = v.compliance_status;
        if (certAuditorEl) {
            certAuditorEl.innerText = `Certified by ${v.auditor_name} (${v.auditor_email}) on ${new Date(v.audit_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`;
        }
        if (certDisplay) certDisplay.style.display = "block";

        const isPass = v.compliance_status && v.compliance_status.includes("Compliant");
        const isCond = v.compliance_status && v.compliance_status.includes("Conditional");
        const bg = isPass ? "#e8f4f0" : (isCond ? "#fef3c7" : "#fee2e2");
        const color = isPass ? "#0f7b6c" : (isCond ? "#92400e" : "#991b1b");
        const icon = isPass ? "fa-circle-check" : (isCond ? "fa-triangle-exclamation" : "fa-circle-xmark");
        if (statusBadge) {
            statusBadge.innerHTML = `<span class="tag-badge" style="background:${bg}; color:${color}; font-size:11px;"><i class="fa-solid ${icon}"></i> ${isPass ? 'IRC:82 Certified' : (isCond ? 'Conditional' : 'Non-Compliant')}</span>`;
        }

        alert(`🏛️ CSIR-CRRI Digital Certificate Issued!\n\nReference: ${v.certificate_code}\nCorridor: ${currentInspectedSegment.name}\nCompliance: ${v.compliance_status}\nAuditor: ${v.auditor_name}`);
    } catch (err) {
        alert(`Audit Certification Error: ${err.message}`);
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = originalText;
        }
    }
}

function highlightSegmentOnMap(feature) {
    if (!map) return;
    if (activeHighlightLayer) {
        map.removeLayer(activeHighlightLayer);
        activeHighlightLayer = null;
    }

    activeHighlightLayer = L.geoJSON(feature, {
        style: {
            color: "#ffffff",
            weight: 9,
            opacity: 0.95,
            lineCap: "round",
            lineJoin: "round"
        }
    }).addTo(map);

    const innerStroke = L.geoJSON(feature, {
        style: {
            color: "#00e5ff",
            weight: 5.5,
            opacity: 1.0,
            lineCap: "round",
            lineJoin: "round"
        }
    }).addTo(map);

    activeHighlightLayer.addLayer(innerStroke);
}

function flyToCurrentSegment() {
    if (!currentInspectedSegment || !map) return;
    const layer = segmentLayersMap[currentInspectedSegment.segment_id];
    if (layer) {
        map.fitBounds(layer.getBounds(), { maxZoom: 16, padding: [60, 60] });
    }
}

function closeInspectionDrawer() {
    const drawer = document.getElementById("inspection-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    if (drawer) drawer.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");
    if (activeHighlightLayer && map) {
        map.removeLayer(activeHighlightLayer);
        activeHighlightLayer = null;
    }
    document.querySelectorAll(".notion-table tbody tr").forEach(tr => {
        tr.classList.remove("row-selected");
    });
    currentInspectedSegment = null;
}

// ==========================================================================
// Schedule Optimization & Database Table Rendering
// ==========================================================================
function onBudgetSelectChange(val) {
    const slider = document.getElementById("custom-budget-slider");
    const label = document.getElementById("custom-budget-label");
    if (slider) slider.value = val;
    if (label) label.innerText = formatINR(parseFloat(val));
    triggerOptimization();
}

function onCustomBudgetSlider(val) {
    const label = document.getElementById("custom-budget-label");
    if (label) label.innerText = formatINR(parseFloat(val));
    
    const select = document.getElementById("opt-budget-select");
    if (select) {
        let matched = false;
        for (let opt of select.options) {
            if (opt.value === val) {
                select.value = val;
                matched = true;
                break;
            }
        }
        if (!matched) select.selectedIndex = -1;
    }

    clearTimeout(customBudgetDebounce);
    customBudgetDebounce = setTimeout(() => {
        triggerOptimization();
    }, 200);
}

// ==========================================================================
// Phase B: Multi-Year Capital Planning & Cost of Inaction State
// ==========================================================================
let currentPlanningHorizon = 1;     // 1, 3, or 5
let currentInactionDelay = 3;       // 1 to 5 years
let currentMultiYearPlan = null;
let currentNetworkInactionSim = null;
let chartDecayInstance = null;
let activeCipYearFilter = "all";

function switchPlanningHorizon(years) {
    currentPlanningHorizon = years;

    // Update button states
    [1, 3, 5, 'scenarios'].forEach(y => {
        const btn = document.getElementById(`btn-horizon-${y}`);
        if (btn) btn.classList.toggle("active", y === years);
    });

    const scenarioPanel = document.getElementById("scenario-panel");
    const decayWrap = document.getElementById("decay-chart-wrap");
    const cipTabs = document.getElementById("cip-year-tabs");
    const badge = document.getElementById("horizon-status-badge");

    const lblSpent = document.getElementById("lbl-opt-spent");
    const lblRemaining = document.getElementById("lbl-opt-remaining");
    const lblCount = document.getElementById("lbl-opt-count");
    const lblSavings = document.getElementById("lbl-opt-savings");

    if (years === 'scenarios') {
        if (scenarioPanel) scenarioPanel.style.display = "block";
        if (decayWrap) decayWrap.style.display = "none";
        if (cipTabs) cipTabs.style.display = "none";
        if (badge) badge.innerHTML = `<span class="status-dot"></span> Active Master Plan: <strong>What-If Scenario Sensitivity Simulator</strong>`;
        if (lblSpent) lblSpent.innerText = "Baseline 5-Yr Spend:";
        if (lblRemaining) lblRemaining.innerText = "Discounted NPV Outlay:";
        if (lblCount) lblCount.innerText = "Planned 5-Yr Projects:";
        if (lblSavings) lblSavings.innerText = "Baseline Net Savings:";
        loadMultiYearScenarios();
        return;
    }

    if (scenarioPanel) scenarioPanel.style.display = "none";

    if (years === 1) {
        if (decayWrap) decayWrap.style.display = "none";
        if (cipTabs) cipTabs.style.display = "none";
        if (badge) badge.innerHTML = `<span class="status-dot"></span> Active Master Plan: <strong>12-Month Tactical Knapsack</strong>`;
        if (lblSpent) lblSpent.innerText = "Allocated Spend:";
        if (lblRemaining) lblRemaining.innerText = "Unused Budget:";
        if (lblCount) lblCount.innerText = "Scheduled Corridors:";
        if (lblSavings) lblSavings.innerText = "Net Projected Savings:";
    } else {
        if (decayWrap) decayWrap.style.display = "block";
        if (cipTabs) cipTabs.style.display = "flex";
        if (badge) badge.innerHTML = `<span class="status-dot"></span> Active Master Plan: <strong>${years}-Year Master Capital Plan (CIP)</strong>`;
        if (lblSpent) lblSpent.innerText = `Total Investment (${years} Yrs):`;
        if (lblRemaining) lblRemaining.innerText = "Discounted NPV Outlay:";
        if (lblCount) lblCount.innerText = `Total Projects (${years} Yrs):`;
        if (lblSavings) lblSavings.innerText = "Net Multi-Year Savings:";
    }

    triggerOptimization();
}

let chartScenariosInstance = null;

async function loadMultiYearScenarios() {
    const params = getOptimizationParams();
    const annualBudget = params.budget;
    const maxKmPerYear = 160.0;
    const zoneVal = params.zone || null;

    const verdictEl = document.getElementById("scenario-verdict-box");
    const gridEl = document.getElementById("scenario-cards-grid");

    if (verdictEl) {
        verdictEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="margin-right:6px;"></i> Simulating 3 Master Plan capital scenarios with CPWD cost escalation across 5 years...`;
    }

    try {
        const res = await fetch("/api/optimization/multi-year/scenarios", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                annual_budget: annualBudget,
                horizon_years: 5,
                max_km_per_year: maxKmPerYear,
                zone: zoneVal,
                discount_rate: 0.06,
                inflation_rate: 0.055
            })
        });

        const data = await res.json();
        if (data.status === "success" && data.scenarios_comparison) {
            renderScenariosComparison(data.scenarios_comparison);
        } else {
            if (verdictEl) verdictEl.innerText = "Failed to load scenario comparison.";
        }
    } catch (err) {
        console.error("Scenario simulation error:", err);
        if (verdictEl) verdictEl.innerText = "Error running scenario simulation.";
    }
}

function renderScenariosComparison(sim) {
    const verdictEl = document.getElementById("scenario-verdict-box");
    const gridEl = document.getElementById("scenario-cards-grid");

    if (verdictEl) {
        verdictEl.innerHTML = `<i class="fa-solid fa-scale-balanced" style="margin-right:6px; color:#15803d;"></i> <strong>Executive Scenario Verdict:</strong> ${sim.scenario_verdict}`;
    }

    if (gridEl && sim.scenarios) {
        gridEl.innerHTML = sim.scenarios.map(s => {
            const isBaseline = s.id === "baseline";
            return `
                <div style="background:${isBaseline ? '#f8fafc' : '#ffffff'}; border:2px solid ${isBaseline ? '#0ea5e9' : 'var(--border)'}; border-radius:var(--radius-sm); padding:0.85rem; position:relative; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
                        <span style="font-weight:700; font-size:13px; color:var(--text-primary);">${s.name}</span>
                        <span class="tag-badge" style="background:${s.tag_color}18; color:${s.tag_color}; font-size:10px; font-weight:600;">${s.tag}</span>
                    </div>
                    <div style="font-size:11px; color:var(--text-secondary); margin-bottom:0.6rem;">
                        Annual Allocation: <strong style="color:var(--text-primary);">${s.annual_budget_formatted}</strong>
                    </div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; font-size:11.5px; border-top:1px dashed var(--border); padding-top:0.5rem;">
                        <div>
                            <span style="color:var(--text-muted); font-size:10.5px;">5-Yr Total Outlay:</span><br/>
                            <strong>${s.total_invested_formatted}</strong>
                        </div>
                        <div>
                            <span style="color:var(--text-muted); font-size:10.5px;">Final Network PCI:</span><br/>
                            <strong style="color:${s.final_pci < 55 ? '#ef4444' : (s.final_pci >= 80 ? '#059669' : '#0284c7')}">${s.final_pci} / 100</strong>
                        </div>
                        <div>
                            <span style="color:var(--text-muted); font-size:10.5px;">Net Savings:</span><br/>
                            <strong style="color:#059669;">${s.net_savings_formatted}</strong>
                        </div>
                        <div>
                            <span style="color:var(--text-muted); font-size:10.5px;">Corridors / Length:</span><br/>
                            <strong>${s.corridors_treated} roads (${s.km_treated} km)</strong>
                        </div>
                    </div>
                </div>
            `;
        }).join("");
    }

    // Render Scenario Multi-Line Chart
    const canvas = document.getElementById("chart-scenarios");
    if (canvas && window.Chart) {
        if (chartScenariosInstance) {
            chartScenariosInstance.destroy();
        }
        const ctx = canvas.getContext("2d");
        
        const labels = sim.years || ["Baseline", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"];
        const scMap = {};
        (sim.scenarios || []).forEach(sc => { scMap[sc.id] = sc; });

        chartScenariosInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Optimal Preservation (+50%)",
                        data: scMap["preservation"] ? scMap["preservation"].trajectory_pci : [],
                        borderColor: "#3b82f6",
                        backgroundColor: "rgba(59, 130, 246, 0.05)",
                        borderWidth: 2.5,
                        pointRadius: 3,
                        tension: 0.3
                    },
                    {
                        label: "Planned Baseline (Recommended)",
                        data: scMap["baseline"] ? scMap["baseline"].trajectory_pci : [],
                        borderColor: "#10b981",
                        backgroundColor: "rgba(16, 185, 129, 0.08)",
                        borderWidth: 3,
                        pointRadius: 4,
                        tension: 0.3
                    },
                    {
                        label: "Austerity (-30% Cut)",
                        data: scMap["austerity"] ? scMap["austerity"].trajectory_pci : [],
                        borderColor: "#f59e0b",
                        borderWidth: 2.2,
                        pointRadius: 3,
                        borderDash: [5, 4],
                        tension: 0.3
                    },
                    {
                        label: "Do Nothing / Neglect",
                        data: sim.do_nothing_trajectory || [],
                        borderColor: "#ef4444",
                        borderWidth: 2,
                        pointRadius: 3,
                        borderDash: [2, 3],
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: "top",
                        labels: { boxWidth: 12, font: { size: 10 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${ctx.raw} PCI`
                        }
                    }
                },
                scales: {
                    y: {
                        min: 0,
                        max: 100,
                        title: { display: true, text: "Network Avg PCI", font: { size: 10 } },
                        grid: { color: "rgba(0, 0, 0, 0.05)" }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // Populate the schedule table with baseline plan
    if (sim.baseline_plan) {
        currentMultiYearPlan = sim.baseline_plan;
        allScheduledSegments = sim.baseline_plan.master_schedule || [];
        renderMultiYearResults(sim.baseline_plan);
    }
}

function export5YearCipExcel() {
    const params = getOptimizationParams();
    const query = new URLSearchParams({
        annual_budget: params.budget,
        horizon_years: 5,
        max_km_per_year: 160.0,
        discount_rate: 0.06,
        inflation_rate: 0.055
    });
    if (params.zone) query.append("zone", params.zone);

    const btn = document.getElementById("btn-export-5yr-cip");
    const origHtml = btn ? btn.innerHTML : "";
    if (btn) {
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating 3-Sheet CIP...`;
        btn.disabled = true;
    }

    const a = document.createElement("a");
    a.href = `/api/export/multi-year-excel?${query.toString()}`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => {
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }, 2000);
}

async function loadNetworkCostOfInaction(zone = null) {
    try {
        const activeZone = zone || currentZoneFilter;
        const res = await fetch("/api/decay/simulate-inaction", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                horizon_years: 5,
                zone: activeZone && activeZone !== "all" ? activeZone : "all"
            })
        });
        const data = await res.json();
        if (data.status === "success" && data.simulation) {
            currentNetworkInactionSim = data.simulation;
            renderInactionMetrics();
        }
    } catch (err) {
        console.error("Failed to load Cost of Inaction simulation:", err);
    }
}

function setInactionDelay(delayYears) {
    currentInactionDelay = delayYears;
    const btns = document.querySelectorAll(".delay-btn");
    btns.forEach(b => {
        b.classList.toggle("active", parseInt(b.dataset.delay, 10) === delayYears);
    });

    const deferredLabel = document.getElementById("inaction-deferred-label");
    if (deferredLabel) {
        deferredLabel.innerText = delayYears === 1 ? "Year 1 Proactive Cost" : `Deferred Year ${delayYears} Outlay`;
    }

    renderInactionMetrics();
}

function renderInactionMetrics() {
    if (!currentNetworkInactionSim) return;
    const sim = currentNetworkInactionSim;
    const yearly = sim.yearly_network_costs || [];
    const item = yearly[currentInactionDelay - 1] || yearly[0];

    const baselineEl = document.getElementById("inaction-baseline-cost");
    const deferredEl = document.getElementById("inaction-deferred-cost");
    const penaltyEl = document.getElementById("inaction-penalty-cost");
    const penaltyPctEl = document.getElementById("inaction-penalty-pct");
    const pciValEl = document.getElementById("inaction-pci-val");
    const pciSubEl = document.getElementById("inaction-pci-sub");
    const headlineEl = document.getElementById("inaction-headline-text");

    if (baselineEl) baselineEl.innerText = sim.year_1_baseline_formatted || "₹10.00 Cr";
    if (deferredEl) deferredEl.innerText = item ? item.cost_formatted : "--";
    if (penaltyEl) penaltyEl.innerText = item ? item.penalty_formatted : "--";
    if (penaltyPctEl) {
        penaltyPctEl.innerText = item ? `+${item.penalty_pct}% Cost Escalation (${item.cost_multiplier}x penalty)` : "--";
    }
    if (pciValEl) pciValEl.innerText = item ? `${item.avg_pci} / 100` : "--";
    if (pciSubEl) {
        const baselinePci = yearly[0] ? yearly[0].avg_pci : 70;
        pciSubEl.innerText = `Condition drop from ${baselinePci} (Year 1) to ${item ? item.avg_pci : '--'}`;
    }

    if (headlineEl) {
        const zoneName = currentZoneFilter === "all" ? "Delhi NCT road" : `${currentZoneFilter} network`;
        if (currentInactionDelay === 1) {
            headlineEl.innerHTML = `Timely <strong>Year 1 Proactive Intervention</strong> on the ${zoneName} preserves structural integrity at lowest life-cycle cost (<strong>${sim.year_1_baseline_formatted}</strong>). No deferred penalties incurred.`;
        } else {
            headlineEl.innerHTML = `Deferring ${zoneName} maintenance from Year 1 to Year ${currentInactionDelay} escalates municipal repair liability by <strong>+${item ? item.penalty_pct : 220}%</strong> (an avoidable penalty of <strong>${item ? item.penalty_formatted : '--'}</strong>). Neglect compounds costs as surface distress collapses into sub-base reconstruction.`;
        }
    }
}

function renderDecayChart(trajectory) {
    const canvas = document.getElementById("chart-decay");
    if (!canvas || !window.Chart) return;

    if (chartDecayInstance) {
        chartDecayInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    chartDecayInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: trajectory.years || ["Baseline", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"],
            datasets: [
                {
                    label: "PaveSentry Proactive CIP Plan (PCI)",
                    data: trajectory.managed_pci || [],
                    borderColor: "#0f766e",
                    backgroundColor: "rgba(15, 118, 110, 0.12)",
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2.5,
                    pointRadius: 4,
                    pointBackgroundColor: "#0f766e"
                },
                {
                    label: "Do Nothing / Neglect Decay (Weibull PCI)",
                    data: trajectory.do_nothing_pci || [],
                    borderColor: "#ef4444",
                    backgroundColor: "rgba(239, 68, 68, 0.05)",
                    fill: false,
                    borderDash: [6, 4],
                    tension: 0.3,
                    borderWidth: 2.2,
                    pointRadius: 4,
                    pointBackgroundColor: "#ef4444"
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: ${ctx.raw} / 100 PCI`
                    }
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    title: { display: true, text: "Pavement Condition Index (PCI)", font: { size: 11 } },
                    grid: { color: "rgba(0, 0, 0, 0.05)" }
                },
                x: {
                    grid: { display: false }
                }
            }
        }
    });
}

function filterCipByYear(year) {
    activeCipYearFilter = year;
    const tabs = document.querySelectorAll(".cip-year-tab");
    tabs.forEach(t => {
        t.classList.toggle("active", t.dataset.year == year);
    });
    renderTable();
}

async function triggerOptimization() {
    const slider = document.getElementById("custom-budget-slider");
    const budgetEl = document.getElementById("opt-budget-select");
    const crewEl = document.getElementById("opt-km-select");

    const budget = slider ? parseFloat(slider.value) : (budgetEl ? parseFloat(budgetEl.value) : 100000000);
    const crew = crewEl ? parseFloat(crewEl.value) : 120.0;
    const zoneVal = currentZoneFilter && currentZoneFilter !== "all" ? currentZoneFilter : null;

    if (currentPlanningHorizon === 1) {
        // Standard 12-Month Knapsack Schedule
        try {
            const res = await fetch("/api/optimize", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    annual_budget: budget,
                    max_km_per_month: 15.0,
                    max_months: 12,
                    zone: zoneVal
                })
            });

            const data = await res.json();
            allScheduledSegments = data.scheduled_segments || [];
            currentMultiYearPlan = null;
            renderOptimizationResults(data);
        } catch (err) {
            console.error("12-Month optimization failed:", err);
        }
    } else {
        // Multi-Year Capital Improvement Plan (3-Year or 5-Year Horizon)
        try {
            const res = await fetch("/api/optimization/multi-year", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    annual_budget: budget,
                    horizon_years: currentPlanningHorizon,
                    max_km_per_year: crew,
                    zone: zoneVal,
                    discount_rate: 0.06
                })
            });

            const data = await res.json();
            if (data.status === "success" && data.plan) {
                currentMultiYearPlan = data.plan;
                allScheduledSegments = data.plan.master_schedule || [];
                renderMultiYearResults(data.plan);
            }
        } catch (err) {
            console.error("Multi-Year CIP optimization failed:", err);
        }
    }
}

function renderMultiYearResults(plan) {
    const fin = plan.financial_summary || {};
    
    const countEl = document.getElementById("opt-count");
    if (countEl) countEl.innerText = `${fin.total_corridors_treated || 0} Corridors (${fin.total_km_treated || 0} km)`;
    
    const spentEl = document.getElementById("opt-spent");
    if (spentEl) spentEl.innerText = fin.total_invested_nominal_formatted || formatINR(fin.total_invested_nominal_inr || 0);

    const remEl = document.getElementById("opt-remaining");
    if (remEl) remEl.innerText = fin.total_invested_npv_formatted || formatINR(fin.total_invested_npv_inr || 0);

    const savingsEl = document.getElementById("opt-savings");
    if (savingsEl) savingsEl.innerText = fin.total_net_savings_formatted || formatINR(fin.total_net_savings_nominal_inr || 0);

    const roiEl = document.getElementById("opt-roi");
    if (roiEl) roiEl.innerText = `${fin.roi_percentage || 0}%`;

    const schedBadge = document.getElementById("sb-sched-count");
    if (schedBadge) {
        schedBadge.innerText = (allScheduledSegments || []).length;
    }

    if (plan.trajectory) {
        renderDecayChart(plan.trajectory);
    }

    renderTable();
}

function renderOptimizationResults(data) {
    const summary = data.summary || {};
    
    const countEl = document.getElementById("opt-count");
    if (countEl) countEl.innerText = `${summary.scheduled_count || 0} Corridors (${summary.total_km_repaired || 0} km)`;
    
    const spentEl = document.getElementById("opt-spent");
    if (spentEl) spentEl.innerText = summary.total_spent_formatted || formatINR(summary.total_spent_inr || 0);

    const remEl = document.getElementById("opt-remaining");
    if (remEl) remEl.innerText = formatINR(summary.remaining_budget_inr || 0);

    const savingsEl = document.getElementById("opt-savings");
    if (savingsEl) savingsEl.innerText = summary.total_savings_formatted || formatINR(summary.total_net_savings_inr || 0);

    const roiEl = document.getElementById("opt-roi");
    if (roiEl) roiEl.innerText = `${summary.roi_percentage || 0}%`;

    const schedBadge = document.getElementById("sb-sched-count");
    if (schedBadge) {
        schedBadge.innerText = (allScheduledSegments || []).length;
    }

    renderTable();
}

function renderTable() {
    const tbody = document.getElementById("schedule-table-body");
    if (!tbody) return;
    const label = document.getElementById("table-count-label");

    let filtered = allScheduledSegments.filter(s => {
        const matchFilter = (currentFilter === "all") || (s.predicted_risk_level === currentFilter);
        const matchZone = zoneMatches(s.city_zone, currentZoneFilter);
        const matchYear = (currentPlanningHorizon === 1) || (activeCipYearFilter === "all") || (s.scheduled_year == activeCipYearFilter);
        const matchSearch = !searchTerm || 
            (s.name && s.name.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (s.road_name && s.road_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (s.city_zone && s.city_zone.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (s.pwd_division && s.pwd_division.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (s.recommended_action && s.recommended_action.toLowerCase().includes(searchTerm.toLowerCase()));
        return matchFilter && matchZone && matchYear && matchSearch;
    });

    if (label) {
        const zoneText = currentZoneFilter === "all" ? "Delhi NCT" : currentZoneFilter;
        const horizonText = currentPlanningHorizon === 1 ? "12-month" : `${currentPlanningHorizon}-year CIP`;
        label.innerText = `Showing ${filtered.length} of ${allScheduledSegments.length} ${horizonText} ${zoneText} corridors`;
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 2rem; color: var(--text-muted);">No scheduled segments match the current filters.</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(s => {
        const isSelected = currentInspectedSegment && currentInspectedSegment.segment_id === s.segment_id;
        const segName = s.road_name || s.name || "Corridor";
        const crriCode = s.tender_code || s.crri_compliance_code || `CRRI-NCT-2026-PCI${Math.round(s.pci || s.pre_repair_pci || 50)}-${(s.segment_id || '0000').slice(-4)}`;
        
        let scheduleLabel = s.scheduled_month || "Month 1";
        if (currentPlanningHorizon > 1 || currentPlanningHorizon === "scenarios") {
            scheduleLabel = `${s.year_label || 'Year ' + s.scheduled_year} · ${s.scheduled_quarter || 'Q1'}`;
        }

        let pciDisplay = s.pci != null ? s.pci : (s.pre_repair_pci != null ? `${s.pre_repair_pci} ➔ ${s.post_repair_pci}` : '70');

        const clusterBadge = s.spatial_cluster_id ? `
            <span class="tag-badge" style="background:#e0f2fe; color:#0369a1; font-size:10px; margin-top:3px; display:inline-block;" title="Contiguous Corridor Cluster: ${s.cluster_label || s.spatial_cluster_id}">
                <i class="fa-solid fa-route"></i> ${s.spatial_cluster_id}
            </span>
        ` : '';

        const rslBadge = (s.rsl_years != null) ? `
            <span class="tag-badge" style="background:${s.rsl_years <= 1.5 ? '#fee2e2' : '#fef3c7'}; color:${s.rsl_years <= 1.5 ? '#b91c1c' : '#b45309'}; font-size:10px; margin-top:2px; display:inline-block;" title="IRC:37 Fatigue Remaining Service Life">
                RSL ${s.rsl_years}y
            </span>
        ` : '';

        const mobSavingsSub = (s.mobilization_savings_inr && s.mobilization_savings_inr > 0) ? `
            <div style="font-size:10px; color:#0369a1; font-weight:500;" title="14% Route Mobilization Savings via Spatial Clustering">
                +₹${Math.round(s.mobilization_savings_inr / 1000)}k cluster saved
            </div>
        ` : '';

        return `
            <tr id="row-${s.segment_id}" onclick="inspectSegment('${s.segment_id}')" class="${isSelected ? 'row-selected' : ''}">
                <td><strong style="color:var(--accent); font-family:var(--font-mono); font-size:12px;">${scheduleLabel}</strong></td>
                <td>
                    <strong>${segName}</strong>
                    ${clusterBadge}
                </td>
                <td><span class="tag-badge" style="background:var(--tag-gray-bg); color:var(--text-primary); font-size:11px;">${s.pwd_division || s.city_zone || 'Delhi NCT'}</span></td>
                <td class="mono-cell">
                    <strong>${pciDisplay}</strong>
                    ${rslBadge}
                </td>
                <td><span class="tag-badge ${s.predicted_risk_level || 'Medium'}">${s.predicted_risk_level || 'Medium'}</span></td>
                <td class="mono-cell">${s.priority_score || '--'}</td>
                <td><span class="tag-badge action" style="background:#e8f4f0; color:#0f7b6c; font-size:11px;">${s.recommended_action || 'Preventive Micro-Surfacing'}</span></td>
                <td class="mono-cell">${formatINR(s.allocated_cost_inr)}</td>
                <td class="mono-cell" style="color:var(--accent); font-weight:600;">
                    +${formatINR(s.net_savings_inr)}
                    ${mobSavingsSub}
                </td>
                <td class="mono-cell" style="font-size:10.5px; color:var(--text-secondary);">${crriCode}</td>
                <td>
                    <button class="btn-inspect" onclick="event.stopPropagation(); inspectSegment('${s.segment_id}')" title="Inspect engineering telemetry">
                        <i class="fa-solid fa-chart-line"></i> Inspect
                    </button>
                </td>
            </tr>
        `;
    }).join("");
}

// ==========================================================================
// Phase 2: One-Click Data Export (CSV, Excel, PDF) & Executive Work Order
// ==========================================================================
function getOptimizationParams() {
    const slider = document.getElementById("custom-budget-slider");
    const budgetEl = document.getElementById("opt-budget-select");
    const crewEl = document.getElementById("opt-km-select");

    const budget = slider ? parseFloat(slider.value) : (budgetEl ? parseFloat(budgetEl.value) : 100000000);
    const crew = crewEl ? parseFloat(crewEl.value) : 15.0;
    const zoneParam = currentZoneFilter && currentZoneFilter !== "all" ? currentZoneFilter : "";
    return { budget, crew, zone: zoneParam };
}

function exportScheduleData(format) {
    const params = getOptimizationParams();
    const btn = document.getElementById(`btn-export-${format}`);
    const originalText = btn ? btn.innerHTML : "";
    
    if (btn) {
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Exporting...`;
        btn.disabled = true;
    }
    
    let url = `/api/export/${format}?annual_budget=${params.budget}&max_km_per_month=${params.crew}&max_months=12`;
    if (params.zone) {
        url += `&zone=${encodeURIComponent(params.zone)}`;
    }
    
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    setTimeout(() => {
        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }, 1500);
}

function openExecutiveWorkOrderModal() {
    const modal = document.getElementById("tender-modal");
    const backdrop = document.getElementById("tender-modal-backdrop");
    if (!modal || !backdrop) return;

    const params = getOptimizationParams();
    const zoneName = params.zone ? `${params.zone} Division` : "Delhi NCT Network (All Divisions)";
    
    // Set Header Metadata
    const nitRefEl = document.getElementById("modal-nit-ref");
    if (nitRefEl) {
        nitRefEl.innerText = `PWD/NCTD/EE-R-2026/NIT-W-104`;
    }
    
    const dateEl = document.getElementById("modal-nit-date");
    if (dateEl) {
        dateEl.innerText = new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    }
    
    const divEl = document.getElementById("modal-nit-division");
    if (divEl) divEl.innerText = zoneName;

    // Financial & Physical Summary
    const budgetVal = params.budget;
    const spentVal = allScheduledSegments.reduce((acc, s) => acc + (s.allocated_cost_inr || 0), 0);
    const savingsVal = allScheduledSegments.reduce((acc, s) => acc + (s.net_savings_inr || 0), 0);
    const kmVal = allScheduledSegments.reduce((acc, s) => acc + (s.length_km || 0), 0);
    const countVal = allScheduledSegments.length;
    const roiVal = spentVal > 0 ? ((savingsVal / spentVal) * 100).toFixed(1) : "0.0";

    const bEl = document.getElementById("modal-sum-budget");
    if (bEl) bEl.innerText = formatINR(budgetVal);
    
    const spEl = document.getElementById("modal-sum-spent");
    if (spEl) spEl.innerText = formatINR(spentVal);
    
    const savEl = document.getElementById("modal-sum-savings");
    if (savEl) savEl.innerText = `+${formatINR(savingsVal)}`;
    
    const cntEl = document.getElementById("modal-sum-count");
    if (cntEl) cntEl.innerText = `${countVal} Corridors`;
    
    const kmEl = document.getElementById("modal-sum-km");
    if (kmEl) kmEl.innerText = `${kmVal.toFixed(1)} km`;
    
    const roiEl = document.getElementById("modal-sum-roi");
    if (roiEl) roiEl.innerText = `${roiVal}%`;

    // Populate Table Body
    const tbody = document.getElementById("modal-tender-table-body");
    if (tbody) {
        if (allScheduledSegments.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:1.5rem; color:#64748b;">No scheduled corridors under current parameters.</td></tr>`;
        } else {
            tbody.innerHTML = allScheduledSegments.map((s, idx) => {
                const riskColor = s.predicted_risk_level === "High" ? "#991b1b" : (s.predicted_risk_level === "Medium" ? "#b45309" : "#047857");
                return `
                    <tr>
                        <td style="text-align:center; font-weight:700;">${idx + 1}</td>
                        <td style="font-family:var(--font-mono); font-weight:600;">${s.segment_id}</td>
                        <td><strong>${s.name}</strong></td>
                        <td>${s.pwd_division || s.city_zone || 'PWD Delhi'}</td>
                        <td style="text-align:center;">${s.length_km} km</td>
                        <td style="text-align:center;"><b>${s.pci}</b> | ${s.iri}</td>
                        <td style="text-align:center; font-weight:700; color:${riskColor};">${s.predicted_risk_level}</td>
                        <td style="font-size:11px;">${s.recommended_action || 'Preventive Resurfacing'}</td>
                        <td style="text-align:right; font-family:var(--font-mono); font-weight:600;">${formatINR(s.allocated_cost_inr)}</td>
                        <td style="text-align:right; font-family:var(--font-mono); font-weight:700; color:#047857;">+${formatINR(s.net_savings_inr)}</td>
                    </tr>
                `;
            }).join("");
        }
    }

    modal.classList.add("open");
    backdrop.classList.add("active");
}

function closeExecutiveWorkOrderModal() {
    const modal = document.getElementById("tender-modal");
    const backdrop = document.getElementById("tender-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");
}

function downloadOfficialPdf() {
    const params = getOptimizationParams();
    let url = `/api/export/pdf?annual_budget=${params.budget}&max_km_per_month=${params.crew}&max_months=12`;
    if (params.zone) {
        url += `&zone=${encodeURIComponent(params.zone)}`;
    }
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function printExecutiveWorkOrder() {
    window.print();
}

// ==========================================================================
// Phase 3: Field Survey Ingestion Portal (ROMDAS / ARRB Hawkeye)
// ==========================================================================
let selectedSurveyFile = null;

function openSurveyModal() {
    const userRole = (currentUser && currentUser.role) ? currentUser.role : "pwd_engineer";
    if (userRole === "mcd_planner") {
        alert("🔒 Access Restricted (Role: MCD Urban Planner)\n\nMCD Urban Planners have read-only access to budget allocations and prioritization scores.\nSurvey file ingestion (ROMDAS / ARRB) requires Delhi PWD Division Engineer or CSIR-CRRI Auditor credentials.");
        return;
    }
    const modal = document.getElementById("survey-modal");
    const backdrop = document.getElementById("survey-modal-backdrop");
    if (modal) modal.classList.add("open");
    if (backdrop) backdrop.classList.add("active");
}

function closeSurveyModal() {
    const modal = document.getElementById("survey-modal");
    const backdrop = document.getElementById("survey-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");
}

function handleSurveyFileSelected(input) {
    if (!input.files || input.files.length === 0) return;
    selectedSurveyFile = input.files[0];

    const label = document.getElementById("dropzone-label");
    const info = document.getElementById("survey-file-info");
    const uploadBtn = document.getElementById("btn-upload-survey-action");

    if (label) {
        label.innerHTML = `<strong>Selected:</strong> ${selectedSurveyFile.name} (${(selectedSurveyFile.size / 1024).toFixed(1)} KB)`;
    }
    if (info) {
        info.innerText = `${selectedSurveyFile.name} ready for server parsing`;
    }
    if (uploadBtn) {
        uploadBtn.disabled = false;
    }
}

async function submitSurveyUpload() {
    if (!selectedSurveyFile) {
        alert("Please select a ROMDAS CSV or ARRB GeoJSON file first.");
        return;
    }

    const userRole = (currentUser && currentUser.role) ? currentUser.role : "pwd_engineer";
    if (userRole === "mcd_planner") {
        alert("🔒 Permission Denied (HTTP 403):\nMCD Urban Planners have read-only permissions and cannot ingest field surveys.");
        return;
    }

    const uploadBtn = document.getElementById("btn-upload-survey-action");
    const statusEl = document.getElementById("survey-upload-status");
    const resultsCard = document.getElementById("survey-results-card");
    const originalText = uploadBtn ? uploadBtn.innerHTML : "";

    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Ingesting &amp; Running ML Pipeline...`;
    }
    if (statusEl) {
        statusEl.style.display = "block";
        statusEl.style.background = "#eff6ff";
        statusEl.style.border = "1px solid #bfdbfe";
        statusEl.style.color = "#1e40af";
        statusEl.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Uploading, parsing telemetry, and updating neural risk matrix...`;
    }

    try {
        const formData = new FormData();
        formData.append("file", selectedSurveyFile);

        const res = await fetch("/api/surveys/upload", {
            method: "POST",
            headers: getAuthHeaders(),
            credentials: "include",
            body: formData
        });

        if (res.status === 403) {
            throw new Error("HTTP 403 Forbidden: Ingesting field surveys is restricted to Delhi PWD Division Engineers and CSIR-CRRI Auditors.");
        }

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Survey ingestion failed.");
        }

        const sum = data.summary || data;
        const uploadId = sum.upload_id || "--";
        const fileFmt = (sum.file_format || "Survey").toUpperCase();
        const fileName = sum.filename || sum.file_name || "Survey File";
        const recordsCount = sum.records_total || sum.records_matched || sum.records_parsed || 0;
        const affectedCount = sum.segments_affected || sum.affected_corridors_count || (sum.updated_segments ? sum.updated_segments.length : 0);
        const avgIri = sum.avg_iri != null ? sum.avg_iri : "--";
        const avgPci = sum.avg_pci != null ? sum.avg_pci : "--";
        const corridorsList = sum.updated_segments || sum.affected_corridors || [];

        if (statusEl) {
            statusEl.style.background = "#f0fdf4";
            statusEl.style.border = "1px solid #bbf7d0";
            statusEl.style.color = "#15803d";
            statusEl.innerHTML = `✅ <strong>Survey Ingestion Successful!</strong> Ingested ${fileName} (${fileFmt}). Parsed ${recordsCount} records, updated ${affectedCount} corridors across Delhi PWD network.`;
        }

        const idEl = document.getElementById("res-upload-id");
        const fmtEl = document.getElementById("res-upload-format");
        const recEl = document.getElementById("res-upload-records");
        const affEl = document.getElementById("res-upload-affected");
        const iriEl = document.getElementById("res-upload-iri");
        const pciEl = document.getElementById("res-upload-pci");

        if (idEl) idEl.innerText = uploadId;
        if (fmtEl) fmtEl.innerText = fileFmt;
        if (recEl) recEl.innerText = recordsCount;
        if (affEl) affEl.innerText = affectedCount;
        if (iriEl) iriEl.innerText = `${avgIri} m/km`;
        if (pciEl) pciEl.innerText = `${avgPci} / 100`;

        const tbody = document.getElementById("survey-results-table-body");
        if (tbody && corridorsList.length > 0) {
            tbody.innerHTML = corridorsList.map(c => `
                <tr>
                    <td style="font-family:var(--font-mono); font-weight:600;">${c.segment_id}</td>
                    <td><strong>${c.name}</strong></td>
                    <td>${c.pwd_division || c.zone || 'Delhi PWD'}</td>
                    <td class="mono-cell"><strong>${c.pci}</strong></td>
                    <td class="mono-cell">${c.iri} m/km</td>
                    <td class="mono-cell">${c.pothole_count}</td>
                    <td class="mono-cell" style="font-size:11px;">${new Date().toLocaleDateString("en-IN")}</td>
                </tr>
            `).join("");
        }

        if (resultsCard) resultsCard.style.display = "block";

        // Refresh Map, KPIs, and Optimizer
        await loadDashboardStats();
        await loadMapGeoJSON();
    } catch (err) {
        if (statusEl) {
            statusEl.style.display = "block";
            statusEl.style.background = "#fef2f2";
            statusEl.style.border = "1px solid #fecaca";
            statusEl.style.color = "#b91c1c";
            statusEl.innerHTML = `❌ <strong>Ingestion Failed:</strong> ${err.message}`;
        }
    } finally {
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = originalText;
        }
    }
}

// ==========================================================================
// Phase 3: Active Pothole Reporting Web Form
// ==========================================================================
function openPotholeModal(roadName, lat, lon) {
    const modal = document.getElementById("pothole-modal");
    const backdrop = document.getElementById("pothole-modal-backdrop");
    if (modal) modal.classList.add("open");
    if (backdrop) backdrop.classList.add("active");

    const latInput = document.getElementById("pot-lat");
    const lonInput = document.getElementById("pot-lon");
    const roadInput = document.getElementById("pot-road-name");
    const statusBanner = document.getElementById("pot-status-banner");
    const previewWrap = document.getElementById("pot-photo-preview-wrap");
    const photoInput = document.getElementById("pot-photo");

    if (statusBanner) statusBanner.style.display = "none";
    if (previewWrap) previewWrap.style.display = "none";
    if (photoInput) photoInput.value = "";

    if (roadName && roadInput) {
        roadInput.value = roadName;
    }

    if (lat != null && lon != null && latInput && lonInput) {
        latInput.value = Number(lat).toFixed(6);
        lonInput.value = Number(lon).toFixed(6);
    } else if (map && latInput && lonInput && (!latInput.value || !lonInput.value)) {
        const center = map.getCenter();
        latInput.value = center.lat.toFixed(6);
        lonInput.value = center.lng.toFixed(6);
    }
}

function closePotholeModal() {
    const modal = document.getElementById("pothole-modal");
    const backdrop = document.getElementById("pothole-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");
}

function populateCurrentLocation() {
    const latInput = document.getElementById("pot-lat");
    const lonInput = document.getElementById("pot-lon");

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                if (latInput) latInput.value = pos.coords.latitude.toFixed(6);
                if (lonInput) lonInput.value = pos.coords.longitude.toFixed(6);
            },
            () => {
                // Fallback to map center
                if (map && latInput && lonInput) {
                    const c = map.getCenter();
                    latInput.value = c.lat.toFixed(6);
                    lonInput.value = c.lng.toFixed(6);
                }
            },
            { timeout: 5000, enableHighAccuracy: true }
        );
    } else if (map && latInput && lonInput) {
        const c = map.getCenter();
        latInput.value = c.lat.toFixed(6);
        lonInput.value = c.lng.toFixed(6);
    }
}

async function handlePotholePhotoPreview(input) {
    const card = document.getElementById("pot-cv-card");
    const loading = document.getElementById("pot-cv-loading");
    const results = document.getElementById("pot-cv-results");
    const imgPreview = document.getElementById("pot-photo-preview");
    const annotatedPreview = document.getElementById("pot-annotated-preview");
    const badge = document.getElementById("pot-cv-badge");
    const latencyLabel = document.getElementById("pot-cv-latency");
    const areaVal = document.getElementById("pot-metric-area");
    const depthVal = document.getElementById("pot-metric-depth");
    const catVal = document.getElementById("pot-metric-cat");
    const notice = document.getElementById("pot-cv-notice");
    const calibModeSelect = document.getElementById("pot-calibration-mode");

    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (card) card.style.display = "block";
        if (loading) loading.style.display = "block";
        if (results) results.style.display = "none";

        // Display local uploaded thumbnail
        if (imgPreview) {
            const reader = new FileReader();
            reader.onload = (e) => { imgPreview.src = e.target.result; };
            reader.readAsDataURL(file);
        }

        try {
            const formData = new FormData();
            formData.append("file", file);
            if (calibModeSelect && calibModeSelect.value) {
                formData.append("calibration_mode", calibModeSelect.value);
            }

            const res = await fetch("/api/vision/analyze", {
                method: "POST",
                body: formData
            });
            const data = await res.json();

            if (loading) loading.style.display = "none";
            if (results) results.style.display = "block";

            if (latencyLabel) {
                latencyLabel.innerText = `${data.processing_time_ms || 28} ms inference`;
            }

            if (data.is_defect) {
                if (badge) {
                    badge.className = "badge badge-emerald";
                    const distressName = (data.primary_distress_type || 'pothole').replace('_', ' ').toUpperCase();
                    badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${distressName} VERIFIED (${(data.confidence * 100).toFixed(1)}% conf)`;
                }
                if (annotatedPreview && data.annotated_image_url) {
                    annotatedPreview.src = data.annotated_image_url;
                }
                if (areaVal) areaVal.innerText = `${data.surface_area_cm2} cm²`;
                if (depthVal) depthVal.innerText = `${data.estimated_depth_mm} mm`;
                if (catVal) catVal.innerText = data.depth_category || "Medium (25-50mm)";

                // Auto-populate manual form inputs to eliminate human bias
                const sevSelect = document.getElementById("pot-severity");
                const depthInput = document.getElementById("pot-depth");
                const widthInput = document.getElementById("pot-width");

                if (sevSelect && data.estimated_depth_mm) {
                    if (data.estimated_depth_mm > 50) sevSelect.value = "Severe (>50mm depth)";
                    else if (data.estimated_depth_mm >= 25) sevSelect.value = "Moderate (25-50mm)";
                    else sevSelect.value = "Minor (<25mm)";
                }
                if (depthInput && data.estimated_depth_mm) {
                    depthInput.value = Math.round(data.estimated_depth_mm);
                }
                if (widthInput && data.width_cm) {
                    widthInput.value = Math.round(data.width_cm);
                }

                if (notice) {
                    notice.style.background = "#f0fdf4";
                    notice.style.border = "1px solid #bbf7d0";
                    notice.style.color = "#15803d";
                    const deductNotice = data.astm_total_deduct_points ? ` | ASTM D6433 Deduct: -${data.astm_total_deduct_points} pts` : '';
                    notice.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span><strong>AI Graded:</strong> ${data.surface_area_cm2} cm² ${data.primary_distress_type} measured objectively via ${data.calibration_info?.preset || 'Photogrammetric Calibration'}${deductNotice}.</span>`;
                }
            } else {
                if (badge) {
                    badge.className = "badge";
                    badge.style.background = "#fef2f2";
                    badge.style.color = "#b91c1c";
                    badge.style.border = "1px solid #fecaca";
                    badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${data.verification_status || 'No Road Defect'} (${(data.confidence * 100).toFixed(1)}%)`;
                }
                if (annotatedPreview) annotatedPreview.src = "";
                if (areaVal) areaVal.innerText = "0 cm²";
                if (depthVal) depthVal.innerText = "0 mm";
                if (catVal) catVal.innerText = "None";

                if (notice) {
                    notice.style.background = "#fffbeb";
                    notice.style.border = "1px solid #fde68a";
                    notice.style.color = "#92400e";
                    notice.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <span><strong>AI Verification Notice:</strong> ${data.rejection_reason || 'Image does not contain a characteristic pavement cavity.'}</span>`;
                }
            }
        } catch (err) {
            console.error("YOLOv8 Edge analysis error:", err);
            if (loading) loading.style.display = "none";
            if (results) results.style.display = "block";
            if (badge) {
                badge.className = "badge";
                badge.style.background = "#f1f5f9";
                badge.style.color = "#64748b";
                badge.innerText = "Manual Review Mode";
            }
        }
    } else if (card) {
        card.style.display = "none";
    }
}

// ==========================================================================
// AI COMPUTER VISION INSPECTION STUDIO (Photo & Video Dashcam Engine)
// ==========================================================================
let currentVisionStudioMode = "photo"; // 'photo' | 'video'
let lastVisionStudioResult = null;
let lastUploadedVisionFile = null;

function openVisionStudioModal() {
    const modal = document.getElementById("vision-studio-modal");
    const backdrop = document.getElementById("vision-studio-modal-backdrop");
    if (modal) modal.classList.add("open");
    if (backdrop) backdrop.classList.add("open");
}

function closeVisionStudioModal() {
    const modal = document.getElementById("vision-studio-modal");
    const backdrop = document.getElementById("vision-studio-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

function switchVisionStudioMode(mode) {
    currentVisionStudioMode = mode;
    const btnPhoto = document.getElementById("btn-vs-mode-photo");
    const btnVideo = document.getElementById("btn-vs-mode-video");
    const dropTitle = document.getElementById("vs-drop-title");
    const dropSub = document.getElementById("vs-drop-sub");
    const dropIcon = document.getElementById("vs-drop-icon");
    const fileInput = document.getElementById("vs-file-input");

    if (mode === "video") {
        if (btnPhoto) btnPhoto.className = "btn btn-sm btn-secondary";
        if (btnVideo) btnVideo.className = "btn btn-sm btn-primary";
        if (dropTitle) dropTitle.innerText = "Drop Dashcam Survey Video (.mp4, .mov, .avi, .webm)";
        if (dropSub) dropSub.innerText = "AI will sample frames, track defects across moving perspective & eliminate duplicate counts";
        if (dropIcon) dropIcon.className = "fa-solid fa-video";
        if (fileInput) fileInput.accept = "video/*";
    } else {
        if (btnPhoto) btnPhoto.className = "btn btn-sm btn-primary";
        if (btnVideo) btnVideo.className = "btn btn-sm btn-secondary";
        if (dropTitle) dropTitle.innerText = "Drop Pavement Image or Click to Browse";
        if (dropSub) dropSub.innerText = "Supported formats: .jpg, .png, .webp (High-res inspection photos)";
        if (dropIcon) dropIcon.className = "fa-solid fa-cloud-arrow-up";
        if (fileInput) fileInput.accept = "image/*";
    }
}

async function handleVisionStudioUpload(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    lastUploadedVisionFile = file;

    const isVideo = file.type.startsWith("video") || /\.(mp4|mov|avi|webm|mkv)$/i.test(file.name);
    if (isVideo && currentVisionStudioMode !== "video") {
        switchVisionStudioMode("video");
    }

    const dropzone = document.getElementById("vs-dropzone");
    const loading = document.getElementById("vs-loading");
    const results = document.getElementById("vs-results");
    const loadingMsg = document.getElementById("vs-loading-msg");

    if (loading) loading.style.display = "block";
    if (results) results.style.display = "none";
    if (dropzone) dropzone.style.display = "none";

    const calibPreset = document.getElementById("vs-calibration-preset")?.value || "auto_perspective";
    const camHeight = parseFloat(document.getElementById("vs-camera-height")?.value) || 1.35;
    const camTilt = parseFloat(document.getElementById("vs-camera-tilt")?.value) || 18.0;

    try {
        if (isVideo) {
            if (loadingMsg) loadingMsg.innerText = "Analyzing Dashcam Video: Sampling frames, tracking defects & deduplicating route...";
            const formData = new FormData();
            formData.append("file", file);
            formData.append("sample_fps", "2.0");
            formData.append("calibration_mode", calibPreset);
            formData.append("camera_height_m", camHeight);
            formData.append("camera_tilt_deg", camTilt);

            const res = await fetch("/api/vision/analyze-video", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Video analysis failed");

            lastVisionStudioResult = data;
            renderVisionStudioVideoResults(data);
        } else {
            if (loadingMsg) loadingMsg.innerText = "Running YOLOv8 Inspection, Boundary Segmentation & Photometric Depth Measurement...";
            const formData = new FormData();
            formData.append("file", file);
            formData.append("calibration_mode", calibPreset);
            formData.append("camera_height_m", camHeight);
            formData.append("camera_tilt_deg", camTilt);

            const res = await fetch("/api/vision/analyze", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Image analysis failed");

            lastVisionStudioResult = data;
            renderVisionStudioPhotoResults(data, file);
        }
    } catch (err) {
        alert("Vision Studio Analysis Failed: " + err.message);
    } finally {
        if (loading) loading.style.display = "none";
        if (results) results.style.display = "block";
        if (dropzone) dropzone.style.display = "block";
    }
}

function renderVisionStudioPhotoResults(data, file) {
    const photoView = document.getElementById("vs-photo-view");
    const videoView = document.getElementById("vs-video-view");
    if (photoView) photoView.style.display = "grid";
    if (videoView) videoView.style.display = "none";

    const badgeStatus = document.getElementById("vs-badge-status");
    const distressPill = document.getElementById("vs-distress-pill");
    const latencyEl = document.getElementById("vs-latency");
    const statArea = document.getElementById("vs-stat-area");
    const statDepth = document.getElementById("vs-stat-depth");
    const statCat = document.getElementById("vs-stat-category");
    const statDeduct = document.getElementById("vs-stat-deduct");
    const origImg = document.getElementById("vs-photo-orig");
    const annotatedImg = document.getElementById("vs-photo-annotated");
    const downloadLink = document.getElementById("vs-download-link");
    const calibInfoText = document.getElementById("vs-calib-info-text");

    if (latencyEl) latencyEl.innerText = `${data.processing_time_ms} ms latency`;
    if (calibInfoText) calibInfoText.innerText = data.calibration_info?.preset || "Handheld Inspector (1.35m)";

    if (origImg && file) {
        const reader = new FileReader();
        reader.onload = (e) => { origImg.src = e.target.result; };
        reader.readAsDataURL(file);
    }

    if (data.is_defect) {
        if (badgeStatus) {
            badgeStatus.className = "badge badge-emerald";
            badgeStatus.innerHTML = `<i class="fa-solid fa-circle-check"></i> Genuine Pavement Defect (${(data.confidence * 100).toFixed(1)}% conf)`;
        }
        if (distressPill) {
            distressPill.style.display = "inline-block";
            distressPill.innerText = `Distress: ${(data.primary_distress_type || 'Pothole').replace('_', ' ').toUpperCase()}`;
        }
        if (statArea) statArea.innerText = `${data.surface_area_cm2} cm²`;
        if (statDepth) statDepth.innerText = `${data.estimated_depth_mm} mm`;
        if (statCat) statCat.innerText = data.depth_category || "Medium";
        if (statDeduct) statDeduct.innerText = `-${data.astm_total_deduct_points || 0} pts`;

        if (annotatedImg && data.annotated_image_url) {
            annotatedImg.src = data.annotated_image_url;
        }
        if (downloadLink && data.annotated_image_url) {
            downloadLink.href = data.annotated_image_url;
        }
    } else {
        if (badgeStatus) {
            badgeStatus.className = "badge";
            badgeStatus.style.background = "#fef2f2";
            badgeStatus.style.color = "#b91c1c";
            badgeStatus.style.border = "1px solid #fecaca";
            badgeStatus.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${data.verification_status || 'No Road Defect'}`;
        }
        if (distressPill) distressPill.style.display = "none";
        if (statArea) statArea.innerText = "0 cm²";
        if (statDepth) statDepth.innerText = "0 mm";
        if (statCat) statCat.innerText = "Intact Pavement";
        if (statDeduct) statDeduct.innerText = "0 pts";
        if (annotatedImg) annotatedImg.src = "";
    }
}

function renderVisionStudioVideoResults(data) {
    const photoView = document.getElementById("vs-photo-view");
    const videoView = document.getElementById("vs-video-view");
    if (photoView) photoView.style.display = "none";
    if (videoView) videoView.style.display = "block";

    const badgeStatus = document.getElementById("vs-badge-status");
    const distressPill = document.getElementById("vs-distress-pill");
    const latencyEl = document.getElementById("vs-latency");
    const statArea = document.getElementById("vs-stat-area");
    const statDepth = document.getElementById("vs-stat-depth");
    const statCat = document.getElementById("vs-stat-category");
    const statDeduct = document.getElementById("vs-stat-deduct");
    const vidSummaryText = document.getElementById("vs-vid-summary-text");
    const vidRating = document.getElementById("vs-vid-rating");
    const keyframesContainer = document.getElementById("vs-video-keyframes");

    if (latencyEl) latencyEl.innerText = `${data.processing_time_ms} ms total`;
    if (badgeStatus) {
        badgeStatus.className = "badge badge-emerald";
        badgeStatus.innerHTML = `<i class="fa-solid fa-video"></i> ${data.unique_defects_count} Unique Distress Instances Detected`;
    }
    if (distressPill) {
        distressPill.style.display = "inline-block";
        distressPill.innerText = `Sampled ${data.frames_analyzed} frames across ${data.video_duration_sec}s`;
    }

    // Aggregates
    const totalArea = data.unique_defects.reduce((acc, d) => acc + (d.surface_area_cm2 || 0), 0);
    const maxDepth = data.unique_defects.reduce((acc, d) => Math.max(acc, d.estimated_depth_mm || 0), 0);

    if (statArea) statArea.innerText = `${totalArea.toFixed(1)} cm²`;
    if (statDepth) statDepth.innerText = `${maxDepth.toFixed(1)} mm`;
    if (statCat) statCat.innerText = `${data.unique_defects_count} Defect Tracks`;
    if (statDeduct) statDeduct.innerText = `-${data.total_astm_deduct_points} pts`;

    if (vidSummaryText) {
        vidSummaryText.innerText = `${data.frames_analyzed} frames analyzed, tracking ${data.unique_defects_count} unique defects along trajectory without duplicate counting.`;
    }
    if (vidRating) {
        vidRating.innerText = data.survey_rating || "Evaluated";
    }

    if (keyframesContainer) {
        if (!data.unique_defects || data.unique_defects.length === 0) {
            keyframesContainer.innerHTML = `<div style="font-size:12px; color:var(--text-muted); padding:1rem;">No severe pavement distress detected in this survey video segment.</div>`;
        } else {
            keyframesContainer.innerHTML = data.unique_defects.map(d => `
                <div style="flex:0 0 240px; background:#ffffff; border:1px solid var(--border); border-radius:var(--radius-sm); padding:0.6rem; font-size:11.5px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <strong style="color:var(--text-primary); text-transform:uppercase;">${d.class_display} #${d.unique_defect_id}</strong>
                        <span class="badge" style="font-size:10px; background:#eff6ff; color:#1d4ed8;">t=${d.first_seen_sec}s</span>
                    </div>
                    <img src="${d.hero_image_url}" alt="Hero Frame" style="width:100%; height:130px; object-fit:cover; border-radius:3px; border:1px solid var(--border); margin-bottom:5px;">
                    <div style="display:flex; justify-content:space-between; color:var(--text-secondary);">
                        <span>Area: <strong>${d.surface_area_cm2} cm²</strong></span>
                        <span>Depth: <strong>${d.estimated_depth_mm} mm</strong></span>
                    </div>
                    <div style="margin-top:3px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:10.5px; color:#ef4444; font-weight:600;">ASTM Deduct: -${d.astm_deduct_points} pts</span>
                        <span style="font-size:10px; color:var(--text-muted);">${d.frame_observations} hits</span>
                    </div>
                </div>
            `).join('');
        }
    }
}

function copyVisionStudioToReport() {
    if (!lastVisionStudioResult) {
        alert("Please analyze a photo first.");
        return;
    }
    closeVisionStudioModal();
    openPotholeModal();

    const d = lastVisionStudioResult;
    const sevSelect = document.getElementById("pot-severity");
    const depthInput = document.getElementById("pot-depth");
    const widthInput = document.getElementById("pot-width");
    const notesInput = document.getElementById("pot-notes");

    if (d.estimated_depth_mm && depthInput) depthInput.value = Math.round(d.estimated_depth_mm);
    if (d.width_cm && widthInput) widthInput.value = Math.round(d.width_cm);
    if (d.estimated_depth_mm && sevSelect) {
        if (d.estimated_depth_mm > 50) sevSelect.value = "Severe (>50mm depth)";
        else if (d.estimated_depth_mm >= 25) sevSelect.value = "Moderate (25-50mm)";
        else sevSelect.value = "Minor (<25mm)";
    }
    if (notesInput) {
        const cls = d.primary_distress_type || 'pothole';
        notesInput.value = `[AI Verified: ${cls.toUpperCase()}, Area: ${d.surface_area_cm2} cm², Depth: ${d.estimated_depth_mm} mm, ASTM Deduct: -${d.astm_total_deduct_points || 0} pts]`;
    }
}

async function handlePotholeReportSubmit(e) {
    e.preventDefault();

    const submitBtn = document.getElementById("btn-pot-submit");
    const statusBanner = document.getElementById("pot-status-banner");
    const originalText = submitBtn ? submitBtn.innerHTML : "";

    const latVal = parseFloat(document.getElementById("pot-lat").value);
    const lonVal = parseFloat(document.getElementById("pot-lon").value);
    const roadName = document.getElementById("pot-road-name").value.trim();
    const severity = document.getElementById("pot-severity").value;
    const depthVal = parseFloat(document.getElementById("pot-depth").value) || 45;
    const widthVal = parseFloat(document.getElementById("pot-width").value) || 35;
    const notesVal = document.getElementById("pot-notes").value.trim();
    const photoInput = document.getElementById("pot-photo");

    if (isNaN(latVal) || isNaN(lonVal)) {
        alert("Please enter valid GPS Latitude and Longitude.");
        return;
    }

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Registering Distress Report...`;
    }

    try {
        const formData = new FormData();
        formData.append("latitude", latVal);
        formData.append("longitude", lonVal);
        if (roadName) formData.append("road_name", roadName);
        formData.append("severity", severity);
        formData.append("estimated_depth_mm", depthVal);
        formData.append("estimated_width_cm", widthVal);
        if (notesVal) formData.append("notes", notesVal);
        if (photoInput && photoInput.files && photoInput.files[0]) {
            formData.append("photo", photoInput.files[0]);
        }

        const res = await fetch("/api/potholes/report", {
            method: "POST",
            headers: getAuthHeaders(),
            credentials: "include",
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Pothole submission failed.");
        }

        if (statusBanner) {
            statusBanner.style.display = "block";
            statusBanner.style.background = "#f0fdf4";
            statusBanner.style.border = "1px solid #bbf7d0";
            statusBanner.style.color = "#15803d";
            const distInfo = data.report.distance_to_segment_km != null ? `(${data.report.distance_to_segment_km} km away)` : "";
            statusBanner.innerHTML = `
                <div><strong>✅ Pothole Report Registered (${data.report.report_id})</strong></div>
                <div style="font-size:11.5px; margin-top:2px;">Linked to: <strong>${data.report.associated_segment_name || 'Corridor Segment'}</strong> ${distInfo}</div>
                <div style="font-size:11px; color:#166534; margin-top:2px;">Dispatched to Delhi PWD Quick Response Team (QRT) for 48-hr patching.</div>
            `;
        }

        // Refresh stats and map
        await loadDashboardStats();
        await loadMapGeoJSON();

        setTimeout(() => {
            closePotholeModal();
        }, 2200);
    } catch (err) {
        if (statusBanner) {
            statusBanner.style.display = "block";
            statusBanner.style.background = "#fef2f2";
            statusBanner.style.border = "1px solid #fecaca";
            statusBanner.style.color = "#b91c1c";
            statusBanner.innerHTML = `❌ <strong>Submission Failed:</strong> ${err.message}`;
        }
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    }
}

// ==========================================================================
// Event Listeners & Interaction Handlers
// ==========================================================================
function setupEventListeners() {
    const optBudget = document.getElementById("opt-budget-select");
    const optKm = document.getElementById("opt-km-select");

    if (optBudget) {
        optBudget.addEventListener("change", (e) => {
            onBudgetSelectChange(e.target.value);
        });
    }

    if (optKm) {
        optKm.addEventListener("change", () => {
            triggerOptimization();
        });
    }

function setFilterTab(btnEl, filterVal) {
    document.querySelectorAll(".table-tab-btn").forEach(b => b.classList.remove("active"));
    if (btnEl) btnEl.classList.add("active");
    currentFilter = filterVal;
    renderTable();
}
window.setFilterTab = setFilterTab;

    const filterButtons = document.querySelectorAll(".table-tab-btn");
    filterButtons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            const targetBtn = e.currentTarget;
            setFilterTab(targetBtn, targetBtn.getAttribute("data-filter") || "all");
        });
    });

    const searchInput = document.getElementById("global-search-input");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            searchTerm = e.target.value.trim();
            renderTable();
        });
    }

    // Keyboard navigation (Escape closes inspection drawer, modals, and exits fullscreen map)
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeInspectionDrawer();
            closeExecutiveWorkOrderModal();
            closeSurveyModal();
            closePotholeModal();
            const mapCard = document.getElementById("sec-gis-map");
            if (mapCard && mapCard.classList.contains("fullscreen-mode")) {
                toggleMapFullscreen();
            }
        }
    });

    // Live Real-Time Delhi Sync Button
    const btnSync = document.getElementById("btn-live-sync");
    if (btnSync) {
        btnSync.addEventListener("click", async () => {
            btnSync.innerHTML = `<i class="fa-solid fa-satellite-dish fa-spin"></i> Syncing Live Data...`;
            btnSync.disabled = true;
            try {
                const res = await fetch("/api/delhi/live-sync", {
                    method: "POST",
                    headers: getAuthHeaders(),
                    credentials: "include"
                });
                if (res.status === 403) {
                    alert("🔒 Permission Denied (HTTP 403):\nLive telemetry synchronization is restricted to Delhi PWD Division Engineers.\nMCD Urban Planners and CSIR-CRRI Auditors have read-only access to telemetry.");
                    return;
                }
                const result = await res.json();
                if (!res.ok) throw new Error(result.detail || "Sync failed.");
                await loadDashboardStats();
                await loadDelhiWeather();
                await loadMapGeoJSON();
                alert(`✅ Real-Time Sync Complete!\n${result.message}\nLive Delhi Temp: ${result.weather.current_temperature_c}°C`);
            } catch (e) {
                alert(`Sync note: ${e.message}`);
            } finally {
                btnSync.innerHTML = `<i class="fa-solid fa-satellite-dish"></i> Live Delhi Sync`;
                btnSync.disabled = false;
            }
        });
    }

    const btnRun = document.getElementById("btn-run-pipeline");
    if (btnRun) {
        btnRun.addEventListener("click", async () => {
            btnRun.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Running...`;
            btnRun.disabled = true;
            try {
                const res = await fetch("/api/predict", {
                    method: "POST",
                    headers: getAuthHeaders(),
                    credentials: "include"
                });
                if (res.status === 403) {
                    alert("🔒 Permission Denied (HTTP 403):\nRunning ML inference is restricted to Delhi PWD Division Engineers and CSIR-CRRI Auditors.\nMCD Urban Planners have read-only access.");
                    return;
                }
                const result = await res.json();
                if (!res.ok) throw new Error(result.detail || "Pipeline failed.");
                await loadDashboardStats();
                await loadMapGeoJSON();
            } catch (e) {
                alert(`Pipeline note: ${e.message}`);
            } finally {
                btnRun.innerHTML = `<i class="fa-solid fa-bolt"></i> Run Inference`;
                btnRun.disabled = false;
            }
        });
    }

    const btnRetrain = document.getElementById("btn-retrain");
    if (btnRetrain) {
        btnRetrain.addEventListener("click", async () => {
            btnRetrain.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Retraining...`;
            btnRetrain.disabled = true;
            try {
                const res = await fetch("/api/train", {
                    method: "POST",
                    headers: getAuthHeaders(),
                    credentials: "include"
                });
                if (res.status === 403) {
                    alert("🔒 Permission Denied (HTTP 403):\nRetraining machine learning models is restricted strictly to Delhi PWD Division Engineers.\nMCD Urban Planners and CSIR-CRRI Auditors receive HTTP 403 Forbidden.");
                    return;
                }
                const result = await res.json();
                if (!res.ok) throw new Error(result.detail || "Retraining failed.");
                await loadDashboardStats();
                await loadMapGeoJSON();
            } catch (e) {
                alert(`Retrain note: ${e.message}`);
            } finally {
                btnRetrain.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Retrain`;
                btnRetrain.disabled = false;
            }
        });
    }
}

// ==========================================================================
// Workspace Feature Navigation Sidebar Controls
// ==========================================================================
function toggleSidebar(forceState) {
    const sidebar = document.getElementById("workspace-sidebar");
    const backdrop = document.getElementById("sidebar-mobile-backdrop");
    if (!sidebar) return;

    const isMobile = window.innerWidth <= 992;
    if (isMobile) {
        const shouldOpen = (typeof forceState === "boolean") ? forceState : !sidebar.classList.contains("open");
        sidebar.classList.toggle("open", shouldOpen);
        if (backdrop) backdrop.classList.toggle("open", shouldOpen);
    } else {
        const isCollapsed = (typeof forceState === "boolean") ? !forceState : !sidebar.classList.contains("collapsed");
        sidebar.classList.toggle("collapsed", isCollapsed);
        try {
            localStorage.setItem("delhi_sidebar_collapsed", isCollapsed ? "true" : "false");
        } catch (_) {}
    }

    // Ensure Leaflet map recalculates its dimensions smoothly as sidebar toggles
    setTimeout(() => {
        if (window.map) {
            window.map.invalidateSize();
        }
    }, 240);
}

function scrollToSection(e, sectionId) {
    if (e && e.preventDefault) e.preventDefault();
    const target = document.getElementById(sectionId);
    if (!target) return;

    const navOffset = 64; // Sticky notion-navbar height + breathing room
    const elementPosition = target.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - navOffset;

    window.scrollTo({
        top: offsetPosition,
        behavior: "smooth"
    });

    // On mobile devices, auto-close the drawer after clicking a feature
    if (window.innerWidth <= 992) {
        toggleSidebar(false);
    }

    // Set active link in sidebar
    document.querySelectorAll(".sidebar-menu .sidebar-link").forEach(link => {
        const href = link.getAttribute("href");
        if (href && href.startsWith("#")) {
            link.classList.toggle("active", href === `#${sectionId}`);
        }
    });
}

function setWorkspaceFlow(flowName) {
    document.querySelectorAll(".flow-tab").forEach(tab => {
        if (tab.dataset.flow === flowName) {
            tab.classList.add("active");
        } else if (tab.dataset.flow) {
            tab.classList.remove("active");
        }
    });

    if (flowName === 'gis') {
        const el = document.getElementById("sec-gis-map");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        setTimeout(() => { if (map) map.invalidateSize(); }, 200);
    } else if (flowName === 'planning') {
        const el = document.getElementById("sec-optimizer");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (flowName === 'schedule') {
        const el = document.getElementById("sec-schedule-table");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
        const el = document.getElementById("sec-overview");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}
window.setWorkspaceFlow = setWorkspaceFlow;

function selectDivisionFromSidebar(zone) {
    filterMapAndTableByZone(zone);
    if (window.innerWidth <= 992) {
        toggleSidebar(false);
    }
}

function initSidebarScrollSpy() {
    const sectionIds = ["sec-overview", "sec-kpis", "sec-gis-map", "sec-charts", "sec-optimizer", "sec-schedule-table"];
    const sections = sectionIds.map(id => document.getElementById(id)).filter(Boolean);
    if (sections.length === 0) return;

    let throttleTimer = null;
    window.addEventListener("scroll", () => {
        if (throttleTimer) return;
        throttleTimer = setTimeout(() => {
            throttleTimer = null;
            const scrollPos = window.pageYOffset + 120;
            let currentId = null;

            for (let i = sections.length - 1; i >= 0; i--) {
                const sec = sections[i];
                if (sec.offsetTop <= scrollPos) {
                    currentId = sec.id;
                    break;
                }
            }

            if (currentId) {
                document.querySelectorAll(".sidebar-menu .sidebar-link").forEach(link => {
                    const href = link.getAttribute("href");
                    if (href && href.startsWith("#")) {
                        link.classList.toggle("active", href === `#${currentId}`);
                    }
                });
            }
        }, 100);
    }, { passive: true });
}

// Window resize listener to handle responsive transition
window.addEventListener("resize", () => {
    const sidebar = document.getElementById("workspace-sidebar");
    const backdrop = document.getElementById("sidebar-mobile-backdrop");
    if (!sidebar) return;

    if (window.innerWidth > 992) {
        if (backdrop) backdrop.classList.remove("open");
        sidebar.classList.remove("open");
        const saved = localStorage.getItem("delhi_sidebar_collapsed");
        if (saved === "true") {
            sidebar.classList.add("collapsed");
        } else {
            sidebar.classList.remove("collapsed");
        }
    } else {
        sidebar.classList.remove("collapsed");
    }
});

// ==========================================================================
// Phase C: Contractor SLA & Work Order Lifecycle Kanban & DLP Warranty Engine
// ==========================================================================
let currentActiveIncidents = [];
let activeInspectingIncident = null;

function openKanbanModal() {
    const modal = document.getElementById("kanban-modal");
    const backdrop = document.getElementById("kanban-modal-backdrop");
    if (!modal || !backdrop) return;
    modal.classList.add("open");
    backdrop.classList.add("open");
    loadKanbanWorkOrders();
}

function closeKanbanModal() {
    const modal = document.getElementById("kanban-modal");
    const backdrop = document.getElementById("kanban-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

async function loadKanbanWorkOrders() {
    const zoneEl = document.getElementById("kb-zone-filter");
    const slaEl = document.getElementById("kb-sla-filter");
    const zone = zoneEl ? zoneEl.value : "all";
    const sla = slaEl ? slaEl.value : "all";

    let url = `/api/kanban/work-orders?`;
    if (zone && zone !== "all") url += `zone=${encodeURIComponent(zone)}&`;
    if (sla && sla !== "all") url += `sla_status=${encodeURIComponent(sla)}&`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        if (data.status === "success") {
            renderKanbanStats(data.stats);
            renderKanbanBoard(data.work_orders || []);
        }
    } catch (err) {
        console.error("Failed to load Kanban work orders:", err);
    }
}

function renderKanbanStats(stats) {
    if (!stats) return;
    const totalEl = document.getElementById("kb-kpi-total");
    const valEl = document.getElementById("kb-kpi-value");
    const compEl = document.getElementById("kb-kpi-compliance");
    const dlpEl = document.getElementById("kb-kpi-dlp");
    const penEl = document.getElementById("kb-kpi-penalties");

    if (totalEl) totalEl.innerText = `${stats.total_work_orders || 0} Orders`;
    if (valEl) valEl.innerText = stats.total_contract_value_formatted || "₹0.00 Cr";
    if (compEl) {
        const comp = stats.sla ? stats.sla.compliance_pct : 100;
        compEl.innerText = `${comp}% On Track`;
    }
    if (dlpEl) {
        const dlpCount = stats.dlp ? stats.dlp.active_warranty_contracts : 0;
        dlpEl.innerText = `${dlpCount} Active Contracts`;
    }
    if (penEl) {
        const penFmt = stats.dlp ? stats.dlp.total_penalties_formatted : "₹0.00";
        penEl.innerText = penFmt;
    }
}

function renderKanbanBoard(orders) {
    const stages = {
        "Reported": { id: "kb-cards-reported", countId: "kb-count-reported", items: [] },
        "Inspected": { id: "kb-cards-inspected", countId: "kb-count-inspected", items: [] },
        "Tender Issued": { id: "kb-cards-tender_issued", countId: "kb-count-tender_issued", items: [] },
        "Under Repair": { id: "kb-cards-under_repair", countId: "kb-count-under_repair", items: [] },
        "Audited & Closed": { id: "kb-cards-audited_closed", countId: "kb-count-audited_closed", items: [] }
    };

    orders.forEach(wo => {
        const st = wo.stage || "Reported";
        if (stages[st]) {
            stages[st].items.push(wo);
        } else {
            stages["Reported"].items.push(wo);
        }
    });

    Object.keys(stages).forEach(stageKey => {
        const cfg = stages[stageKey];
        const container = document.getElementById(cfg.id);
        const countBadge = document.getElementById(cfg.countId);

        if (countBadge) countBadge.innerText = cfg.items.length;
        if (!container) return;

        if (cfg.items.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:1.5rem 0.5rem; color:var(--text-muted); font-size:11.5px; border:1px dashed #cbd5e1; border-radius:var(--radius-sm); background:#ffffff;">No work orders in this stage</div>`;
            return;
        }

        container.innerHTML = cfg.items.map(wo => {
            const isBreach = wo.dlp_status === "Breach Flagged (Penalty Pending)" || wo.sla_status === "SLA Breached";
            const isDlpActive = wo.stage === "Audited & Closed" && wo.dlp_status === "Active Warranty";

            // SLA Badge styling
            let slaBadgeHtml = "";
            if (wo.stage === "Audited & Closed") {
                slaBadgeHtml = `<span class="sla-badge sla-completed"><i class="fa-solid fa-check-double"></i> Completed</span>`;
            } else if (wo.sla_days_remaining < 0) {
                slaBadgeHtml = `<span class="sla-badge sla-breached"><i class="fa-solid fa-circle-exclamation"></i> Overdue by ${Math.abs(wo.sla_days_remaining)}d</span>`;
            } else if (wo.sla_days_remaining <= 3) {
                slaBadgeHtml = `<span class="sla-badge sla-approaching"><i class="fa-solid fa-hourglass-half"></i> ${wo.sla_days_remaining}d left</span>`;
            } else {
                slaBadgeHtml = `<span class="sla-badge sla-on-track"><i class="fa-solid fa-clock"></i> ${wo.sla_days_remaining}d left</span>`;
            }

            // DLP Warranty Badge
            let dlpBadgeHtml = "";
            if (wo.stage === "Audited & Closed") {
                if (wo.dlp_status === "Breach Flagged (Penalty Pending)") {
                    dlpBadgeHtml = `<button class="tag-badge" onclick="openDlpNoticeForWo('${wo.work_order_id}')" style="background:#fee2e2; color:#b91c1c; font-size:10px; font-weight:700; cursor:pointer; border:1px solid #fca5a5; margin-top:3px;"><i class="fa-solid fa-triangle-exclamation"></i> Clause 17 Notice</button>`;
                } else {
                    dlpBadgeHtml = `<span class="tag-badge" style="background:#ecfdf5; color:#059669; font-size:10px; margin-top:3px;"><i class="fa-solid fa-shield"></i> ${wo.dlp_days_remaining}d DLP Active</span>`;
                }
            }

            // Next Stage Progress Button
            let nextActionBtn = "";
            if (wo.stage === "Reported") {
                nextActionBtn = `<button class="btn-kanban-step" onclick="advanceWorkOrderStage('${wo.work_order_id}', 'Inspected')" title="Advance to Field Engineer Inspection">Verify ➔</button>`;
            } else if (wo.stage === "Inspected") {
                nextActionBtn = `<button class="btn-kanban-step" onclick="advanceWorkOrderStage('${wo.work_order_id}', 'Tender Issued')" title="Approve estimate &amp; issue e-Tender">Issue Tender ➔</button>`;
            } else if (wo.stage === "Tender Issued") {
                nextActionBtn = `<button class="btn-kanban-step" onclick="advanceWorkOrderStage('${wo.work_order_id}', 'Under Repair')" title="Mobilize paving contractor crews on site">Mobilize ➔</button>`;
            } else if (wo.stage === "Under Repair") {
                nextActionBtn = `<button class="btn-kanban-step" onclick="advanceWorkOrderStage('${wo.work_order_id}', 'Audited & Closed')" style="background:#0f766e; color:#ffffff; border-color:#0f766e;" title="Complete CSIR-CRRI NSV audit and activate 3-year DLP warranty">Audit &amp; Handover ➔</button>`;
            } else {
                nextActionBtn = `<button class="btn-kanban-step" style="color:#059669; background:#f0fdf4;" disabled><i class="fa-solid fa-circle-check"></i> Audited</button>`;
            }

            return `
                <div class="kanban-card ${isBreach ? 'breach' : ''} ${isDlpActive ? 'active-dlp' : ''}" id="kcard-${wo.work_order_id}">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <span style="font-family:var(--font-mono); font-size:10.5px; color:var(--text-muted); font-weight:600;">${wo.work_order_id}</span>
                        <span class="tag-badge ${wo.priority_level || 'Medium'}" style="font-size:9.5px; padding:1px 5px;">${wo.priority_level || 'Medium'}</span>
                    </div>

                    <div class="kanban-card-title">${wo.road_name}</div>

                    <div class="kanban-card-row">
                        <span style="color:var(--text-secondary); font-size:11px;"><i class="fa-solid fa-building-columns"></i> ${wo.pwd_division || wo.city_zone}</span>
                    </div>

                    <div class="kanban-card-row">
                        <span style="font-size:11px; color:#475569;"><strong>${wo.contractor_name}</strong></span>
                        <strong style="color:var(--text-primary); font-size:11.5px;">${wo.contract_value_formatted}</strong>
                    </div>

                    <div style="font-size:10.5px; color:var(--text-muted); line-height:1.3; background:#fafaf9; border-radius:3px; padding:3px 6px;">
                        ${wo.treatment_type}
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:2px;">
                        ${slaBadgeHtml}
                        ${dlpBadgeHtml}
                    </div>

                    <div class="kanban-card-actions">
                        <button class="btn-kanban-boq" onclick="inspectWorkOrderBoq('${wo.work_order_id}')" title="Inspect CPWD DSR 2023 Bill of Quantities">
                            <i class="fa-solid fa-receipt"></i> View BOQ
                        </button>
                        ${nextActionBtn}
                    </div>
                </div>
            `;
        }).join("");
    });
}

async function advanceWorkOrderStage(woId, nextStage) {
    const notes = prompt(`Confirm stage progression to "${nextStage}":\n(Optional engineering notes / inspection comments)`);
    if (notes === null) return; // User cancelled

    try {
        const res = await fetch(`/api/kanban/work-orders/${woId}/stage`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                stage: nextStage,
                notes: notes || "Advanced via PaveSentry SLA Kanban Board",
                updated_by: "PWD Executive Engineer"
            })
        });
        const data = await res.json();
        if (data.status === "success") {
            loadKanbanWorkOrders();
        } else {
            alert(`Error advancing work order: ${data.detail || 'Unknown error'}`);
        }
    } catch (err) {
        console.error("Failed to advance stage:", err);
        alert("Network error updating work order stage.");
    }
}

async function inspectWorkOrderBoq(woId) {
    try {
        const res = await fetch(`/api/kanban/work-orders`);
        const data = await res.json();
        const wo = (data.work_orders || []).find(w => w.work_order_id === woId);
        if (!wo) {
            alert("Work order not found.");
            return;
        }

        const boqRes = await fetch("/api/dsr/generate-boq", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                road_name: wo.road_name,
                length_km: 2.8,
                lanes: 4,
                treatment_type: wo.treatment_type,
                city_zone: wo.city_zone
            })
        });
        const boqData = await boqRes.json();
        if (boqData.status === "success" && boqData.boq) {
            renderBoqData(boqData.boq, wo);
            openBoqModal();
        }
    } catch (err) {
        console.error("Failed to load BOQ:", err);
    }
}

function openBoqModal() {
    const modal = document.getElementById("boq-modal");
    const backdrop = document.getElementById("boq-modal-backdrop");
    if (modal && backdrop) {
        modal.classList.add("open");
        backdrop.classList.add("open");
    }
}

function closeBoqModal() {
    const modal = document.getElementById("boq-modal");
    const backdrop = document.getElementById("boq-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

function renderBoqData(boq, wo) {
    const roadEl = document.getElementById("boq-road-name");
    const metaEl = document.getElementById("boq-road-meta");
    const dlpEl = document.getElementById("boq-dlp-badge");
    const tbody = document.getElementById("boq-table-body");

    if (roadEl) roadEl.innerText = boq.road_name;
    if (metaEl) metaEl.innerText = `${boq.city_zone} · Length: ${boq.length_km} km · Lanes: ${boq.lanes} · Total Pavement Area: ${boq.pavement_area_sqm.toLocaleString()} sqm`;
    if (dlpEl) dlpEl.innerText = boq.dlp_warranty_label;

    if (tbody) {
        tbody.innerHTML = (boq.items || []).map(item => `
            <tr>
                <td><strong style="color:var(--accent); font-family:var(--font-mono);">${item.item_code}</strong></td>
                <td>
                    <div style="font-weight:600; color:var(--text-primary);">${item.description}</div>
                    <span style="font-size:10px; color:var(--text-muted);">${item.category}</span>
                </td>
                <td>${item.unit}</td>
                <td style="text-align:right; font-family:var(--font-mono);">${item.quantity.toLocaleString()}</td>
                <td style="text-align:right; font-family:var(--font-mono);">${item.formatted_rate}</td>
                <td style="text-align:right; font-family:var(--font-mono); font-weight:600;">${item.formatted_amount}</td>
            </tr>
        `).join("");
    }

    const fin = boq.financial_breakdown || {};
    const baseEl = document.getElementById("boq-base-subtotal");
    const idxEl = document.getElementById("boq-index-addition");
    const overEl = document.getElementById("boq-overhead-gst");
    const grossEl = document.getElementById("boq-gross-total");

    if (baseEl) baseEl.innerText = formatINR(fin.base_dsr_subtotal_inr);
    if (idxEl) idxEl.innerText = `+${formatINR(fin.delhi_index_addition_inr)} (+8.5%)`;
    if (overEl) overEl.innerText = `Profit ₹${Math.round(fin.contractor_profit_inr/100000)}L + GST ₹${Math.round(fin.gst_amount_inr/100000)}L`;
    if (grossEl) grossEl.innerText = fin.gross_tender_value_formatted || formatINR(fin.gross_tender_value_inr);
}

function openNewWoModal() {
    const modal = document.getElementById("new-wo-modal");
    const backdrop = document.getElementById("new-wo-modal-backdrop");
    if (!modal || !backdrop) return;

    // Populate segment selector from allScheduledSegments or default list
    const sel = document.getElementById("new-wo-segment");
    if (sel && allScheduledSegments && allScheduledSegments.length > 0) {
        sel.innerHTML = allScheduledSegments.map(s => `
            <option value="${s.segment_id}">${s.road_name || s.name} (${s.city_zone || 'Delhi'})</option>
        `).join("");
    }

    modal.classList.add("open");
    backdrop.classList.add("open");
}

function closeNewWoModal() {
    const modal = document.getElementById("new-wo-modal");
    const backdrop = document.getElementById("new-wo-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

async function submitNewWorkOrder(e) {
    e.preventDefault();
    const segId = document.getElementById("new-wo-segment").value;
    const treat = document.getElementById("new-wo-treatment").value;
    const cont = document.getElementById("new-wo-contractor").value;
    const prio = document.getElementById("new-wo-priority").value;
    const sla = parseInt(document.getElementById("new-wo-sla-days").value, 10);
    const cost = parseFloat(document.getElementById("new-wo-cost").value);
    const notes = document.getElementById("new-wo-notes").value;

    const matched = (allScheduledSegments || []).find(s => s.segment_id === segId);
    const roadName = matched ? (matched.road_name || matched.name) : "Delhi PWD Arterial Corridor";
    const zone = matched ? matched.city_zone : "Central Delhi";

    try {
        const res = await fetch("/api/kanban/work-orders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: segId,
                road_name: roadName,
                city_zone: zone,
                contractor_name: cont,
                treatment_type: treat,
                priority_level: prio,
                sla_target_days: sla,
                contract_value_inr: cost,
                notes: notes,
                stage: "Reported"
            })
        });
        const data = await res.json();
        if (data.status === "success") {
            closeNewWoModal();
            loadKanbanWorkOrders();
            alert(`Work Order ${data.work_order.work_order_id} successfully issued to ${cont}!`);
        }
    } catch (err) {
        console.error("Failed to create work order:", err);
    }
}

async function triggerDlpScan() {
    try {
        const res = await fetch("/api/dlp/scan-breaches", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            const count = data.breaches_detected || 0;
            if (count > 0) {
                alert(`🚨 DLP Warranty Watchdog Scan Complete:\nDetected ${count} recurring road defect(s) on active warranty corridors.\nAutomated Show Cause Notices served under CPWD GCC Clause 17.`);
            } else {
                alert("✅ DLP Warranty Watchdog Scan Complete:\nNo recurring defect breaches detected on active warranty corridors. All contractor assets intact.");
            }
            loadKanbanWorkOrders();
        }
    } catch (err) {
        console.error("DLP scan failed:", err);
    }
}

async function openDlpNoticeForWo(woId) {
    try {
        const res = await fetch("/api/dlp/incidents");
        const data = await res.json();
        const incidents = data.incidents || [];
        const inc = incidents.find(i => i.work_order_id === woId);
        if (!inc) {
            alert("No active DLP incident notice found for this work order.");
            return;
        }

        activeInspectingIncident = inc;
        const modal = document.getElementById("dlp-notice-modal");
        const backdrop = document.getElementById("dlp-notice-modal-backdrop");
        const textEl = document.getElementById("dlp-notice-content");
        const penTag = document.getElementById("dlp-notice-penalty-tag");

        if (textEl) textEl.innerText = inc.show_cause_notice_text;
        if (penTag) penTag.innerText = `Levied Penalty: ${inc.penalty_amount_formatted}`;

        if (modal && backdrop) {
            modal.classList.add("open");
            backdrop.classList.add("open");
        }
    } catch (err) {
        console.error("Failed to fetch DLP incident notice:", err);
    }
}

function closeDlpNoticeModal() {
    const modal = document.getElementById("dlp-notice-modal");
    const backdrop = document.getElementById("dlp-notice-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
    activeInspectingIncident = null;
}

async function resolveDlpIncident() {
    if (!activeInspectingIncident) return;
    const incId = activeInspectingIncident.incident_id;

    try {
        const res = await fetch(`/api/dlp/incidents/${incId}/status`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                status: "Rectified by Contractor",
                notes: "Contractor mobilized repair team within 48h; defect patched per IRC:SP:81 specifications."
            })
        });
        const data = await res.json();
        if (data.status === "success") {
            alert("Defect marked as rectified by contractor. DLP warranty status updated.");
            closeDlpNoticeModal();
            loadKanbanWorkOrders();
        }
    } catch (err) {
        console.error("Failed to resolve DLP incident:", err);
    }
}

// ==========================================================================
// Phase D: Explainable AI (XAI) & TreeSHAP Attribution
// ==========================================================================
let currentXaiExplanation = null;
let currentGlobalShapData = null;

async function loadCorridorXai(segmentId) {
    const loadingEl = document.getElementById("drawer-xai-loading");
    const contentEl = document.getElementById("drawer-xai-content");
    const probEl = document.getElementById("drawer-xai-prob");
    const baseEl = document.getElementById("drawer-xai-base");
    const narrativeEl = document.getElementById("drawer-xai-narrative");
    const driversList = document.getElementById("drawer-xai-drivers-list");
    const mitList = document.getElementById("drawer-xai-mitigating-list");
    const cfResult = document.getElementById("cf-result-box");

    if (loadingEl) loadingEl.style.display = "block";
    if (contentEl) contentEl.style.display = "none";
    if (cfResult) cfResult.style.display = "none";

    try {
        const res = await fetch(`/api/xai/corridor/${segmentId}`);
        const data = await res.json();

        if (data.status !== "success" || !data.explanation) {
            throw new Error(data.detail || "Failed to load XAI explanation");
        }

        const exp = data.explanation;
        currentXaiExplanation = exp;

        if (loadingEl) loadingEl.style.display = "none";
        if (contentEl) contentEl.style.display = "block";

        if (probEl) {
            const probPct = (exp.pothole_probability * 100).toFixed(1);
            probEl.innerText = `${probPct}% (${exp.predicted_risk.toUpperCase()} RISK)`;
            probEl.style.color = exp.predicted_risk === "High" ? "#dc2626" : (exp.predicted_risk === "Medium" ? "#d97706" : "#059669");
        }

        if (baseEl) {
            baseEl.innerText = `${exp.base_expected_value > 0 ? '+' : ''}${exp.base_expected_value}`;
        }

        if (narrativeEl) {
            narrativeEl.innerText = exp.audit_justification;
        }

        // Render Positive Risk Drivers
        if (driversList) {
            const drivers = exp.top_risk_drivers || [];
            if (drivers.length === 0) {
                driversList.innerHTML = `<div style="font-size:11px; color:var(--text-muted);">No positive risk drivers identified.</div>`;
            } else {
                driversList.innerHTML = drivers.map(d => {
                    const barW = Math.min(100, Math.max(10, d.influence_pct * 2.2));
                    return `
                        <div class="shap-item-card">
                            <div class="shap-item-header">
                                <span class="shap-feat-name">${d.display_name}</span>
                                <span class="shap-feat-meta" style="color:#c2410c;">+${d.influence_pct}% (+${d.shap_value})</span>
                            </div>
                            <div class="shap-bar-track">
                                <div class="shap-bar-fill risk" style="width:${barW}%;"></div>
                            </div>
                            <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-muted); margin-top:2px;">
                                <span>Observed: <strong>${d.raw_value} ${d.unit}</strong></span>
                                <span>${d.category}</span>
                            </div>
                            <div class="shap-feat-rationale">${d.engineering_rationale}</div>
                        </div>
                    `;
                }).join("");
            }
        }

        // Render Mitigating Factors
        if (mitList) {
            const mitigating = exp.top_mitigating_factors || [];
            if (mitigating.length === 0) {
                mitList.innerHTML = `<div style="font-size:11px; color:var(--text-muted);">No mitigating structural factors identified.</div>`;
            } else {
                mitList.innerHTML = mitigating.map(m => {
                    const barW = Math.min(100, Math.max(10, m.influence_pct * 2.2));
                    return `
                        <div class="shap-item-card">
                            <div class="shap-item-header">
                                <span class="shap-feat-name">${m.display_name}</span>
                                <span class="shap-feat-meta" style="color:#059669;">-${m.influence_pct}% (${m.shap_value})</span>
                            </div>
                            <div class="shap-bar-track">
                                <div class="shap-bar-fill mitigating" style="width:${barW}%;"></div>
                            </div>
                            <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-muted); margin-top:2px;">
                                <span>Observed: <strong>${m.raw_value} ${m.unit}</strong></span>
                                <span>${m.category}</span>
                            </div>
                            <div class="shap-feat-rationale">${m.engineering_rationale}</div>
                        </div>
                    `;
                }).join("");
            }
        }
    } catch (err) {
        console.error("Error loading corridor XAI attribution:", err);
        if (loadingEl) {
            loadingEl.innerHTML = `<span style="color:#dc2626;"><i class="fa-solid fa-triangle-exclamation"></i> Error computing TreeSHAP attribution: ${err.message}</span>`;
        }
    }
}

async function runCounterfactualSimulation() {
    if (!currentInspectedSegment) return;
    const segmentId = currentInspectedSegment.segment_id;

    const heavySlider = document.getElementById("cf-slider-heavy");
    const drainCheck = document.getElementById("cf-check-drainage");
    const potCheck = document.getElementById("cf-check-potholes");
    const resultBox = document.getElementById("cf-result-box");

    const diversionPct = heavySlider ? parseFloat(heavySlider.value) : 50;
    const doDrainage = drainCheck ? drainCheck.checked : true;
    const doPotholes = potCheck ? potCheck.checked : true;

    // Build realistic engineering overrides
    const overrides = {};
    const origHeavy = currentInspectedSegment.heavy_vehicle_pct || 22.0;
    const origAadt = currentInspectedSegment.aadt || 45000;
    const origRain = currentInspectedSegment.annual_rainfall_mm || 790;

    // Heavy vehicle traffic diversion
    const factor = (100 - diversionPct) / 100.0;
    overrides["heavy_vehicle_pct"] = Math.max(2.0, origHeavy * factor);
    overrides["traffic_load_index"] = Math.max(10.0, (currentInspectedSegment.traffic_load_index || 60) * factor);

    // Monsoon storm drainage maintenance
    if (doDrainage) {
        overrides["annual_rainfall_mm"] = Math.min(origRain, 520.0);
        overrides["weather_exposure_index"] = 28.0;
    }

    // Pothole jet-patching & crack sealing
    if (doPotholes) {
        overrides["pothole_count"] = 0;
        overrides["crack_density_pct"] = Math.min(3.0, (currentInspectedSegment.crack_density_pct || 15) * 0.15);
        overrides["structural_distress_index"] = Math.min(20.0, (currentInspectedSegment.structural_distress_index || 50) * 0.3);
    }

    if (resultBox) {
        resultBox.style.display = "block";
        resultBox.style.background = "#eff6ff";
        resultBox.style.border = "1px solid #bfdbfe";
        resultBox.style.color = "#1e40af";
        resultBox.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Simulating counterfactual engineering interventions...`;
    }

    try {
        const res = await fetch("/api/xai/counterfactual", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: segmentId,
                overrides: overrides
            })
        });

        const data = await res.json();
        if (data.status !== "success" || !data.counterfactual) {
            throw new Error(data.detail || "Counterfactual simulation failed");
        }

        const cf = data.counterfactual;
        if (resultBox) {
            const shiftText = `${cf.baseline_risk} ➔ ${cf.counterfactual_risk}`;
            const dropPct = cf.percentage_risk_drop;
            const probBefore = (cf.baseline_probability * 100).toFixed(1);
            const probAfter = (cf.counterfactual_probability * 100).toFixed(1);

            resultBox.style.background = "#f0fdf4";
            resultBox.style.border = "1px solid #bbf7d0";
            resultBox.style.color = "#166534";
            resultBox.innerHTML = `
                <div style="font-weight:700; font-size:11.5px; margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
                    <span><i class="fa-solid fa-circle-check"></i> Risk Reduction: -${dropPct}%</span>
                    <span class="tag-badge" style="background:#dcfce7; color:#15803d; font-weight:700;">${shiftText}</span>
                </div>
                <div style="font-size:11px; margin-bottom:4px;">
                    Failure probability drops from <strong>${probBefore}%</strong> to <strong>${probAfter}%</strong>.
                </div>
                <div style="font-size:10px; color:#15803d; line-height:1.35;">
                    ${cf.verdict}
                </div>
            `;
        }
    } catch (err) {
        console.error("Counterfactual error:", err);
        if (resultBox) {
            resultBox.style.background = "#fef2f2";
            resultBox.style.border = "1px solid #fecaca";
            resultBox.style.color = "#b91c1c";
            resultBox.innerHTML = `❌ Simulation failed: ${err.message}`;
        }
    }
}

// Global XAI Modal Functions
async function openXaiModal() {
    const modal = document.getElementById("xai-modal");
    const backdrop = document.getElementById("xai-modal-backdrop");
    const selectEl = document.getElementById("xai-corridor-select");

    if (modal && backdrop) {
        modal.classList.add("open");
        backdrop.classList.add("open");
    }

    // Populate corridor dropdown from currentGeojson
    if (selectEl && currentGeojson && currentGeojson.features) {
        selectEl.innerHTML = currentGeojson.features.map(f => {
            const p = f.properties || {};
            return `<option value="${p.segment_id}">${p.segment_id} - ${p.name || 'Corridor'} (${p.city_zone || 'Delhi NCT'})</option>`;
        }).join("");

        // Select currently inspected or default to first
        const targetId = (currentInspectedSegment && currentInspectedSegment.segment_id) || (currentGeojson.features[0] && currentGeojson.features[0].properties.segment_id);
        if (targetId) {
            selectEl.value = targetId;
            loadQuickXaiCorridor(targetId);
        }
    }

    loadGlobalXaiData();
}

function closeXaiModal() {
    const modal = document.getElementById("xai-modal");
    const backdrop = document.getElementById("xai-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

async function loadGlobalXaiData() {
    const topDriverEl = document.getElementById("xai-macro-top-driver");
    const barsListEl = document.getElementById("xai-global-bars-list");

    try {
        const res = await fetch("/api/xai/global-importance");
        const data = await res.json();

        if (data.status !== "success" || !data.ranked_global_features) {
            throw new Error(data.message || "Failed to load global SHAP importance");
        }

        currentGlobalShapData = data;

        if (topDriverEl) {
            topDriverEl.innerText = `${data.top_macro_driver} (${data.top_macro_driver_pct}%)`;
        }

        if (barsListEl) {
            barsListEl.innerHTML = data.ranked_global_features.map((feat, idx) => {
                const cat = feat.category || "";
                let catClass = "shap-cat-geo";
                if (cat.includes("Traffic")) catClass = "shap-cat-traffic";
                else if (cat.includes("Environmental")) catClass = "shap-cat-env";
                else if (cat.includes("Distress") || cat.includes("Condition")) catClass = "shap-cat-distress";
                else if (cat.includes("Age")) catClass = "shap-cat-age";

                const barWidth = Math.min(100, Math.max(8, feat.global_importance_pct * 2.8));

                return `
                    <div class="shap-global-item">
                        <div class="shap-global-top-row">
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span style="font-weight:700; font-size:11px; color:var(--text-muted); width:18px;">#${idx + 1}</span>
                                <span style="font-weight:600; font-size:11.5px; color:var(--text-primary);">${feat.display_name}</span>
                                <span class="shap-category-badge ${catClass}">${cat.split("&")[0].trim()}</span>
                            </div>
                            <span style="font-weight:700; font-size:11px; font-family:var(--font-mono); color:var(--accent);">
                                ${feat.global_importance_pct}%
                            </span>
                        </div>
                        <div class="shap-bar-track">
                            <div class="shap-bar-fill global" style="width:${barWidth}%;"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-muted);">
                            <span>Telemetry Key: <code>${feat.feature_name}</code></span>
                            <span>Mean |&phi;|: ${feat.mean_shap}</span>
                        </div>
                    </div>
                `;
            }).join("");
        }
    } catch (err) {
        console.error("Global XAI load error:", err);
        if (barsListEl) {
            barsListEl.innerHTML = `<div style="color:#dc2626; padding:1rem; font-size:11px;">Error loading global importance: ${err.message}</div>`;
        }
    }
}

async function loadQuickXaiCorridor(segmentId) {
    const summaryBox = document.getElementById("xai-quick-summary-box");
    const riskEl = document.getElementById("xai-quick-risk");
    const probEl = document.getElementById("xai-quick-prob");
    const driversEl = document.getElementById("xai-quick-top-drivers");
    const narrativeEl = document.getElementById("xai-quick-narrative");

    if (summaryBox) summaryBox.style.display = "block";

    try {
        const res = await fetch(`/api/xai/corridor/${segmentId}`);
        const data = await res.json();
        if (data.status !== "success" || !data.explanation) return;

        const exp = data.explanation;
        if (riskEl) {
            riskEl.innerText = `${exp.predicted_risk.toUpperCase()} RISK`;
            riskEl.style.color = exp.predicted_risk === "High" ? "#dc2626" : (exp.predicted_risk === "Medium" ? "#d97706" : "#059669");
        }

        if (probEl) {
            probEl.innerText = `${(exp.pothole_probability * 100).toFixed(1)}% failure probability`;
        }

        if (driversEl) {
            const drivers = exp.top_risk_drivers || [];
            driversEl.innerHTML = drivers.slice(0, 3).map(d => `
                <div style="display:flex; justify-content:space-between; font-size:11px; padding:3px 6px; background:#fff; border:1px solid #e5e7eb; border-radius:3px;">
                    <span><strong>${d.display_name}:</strong> ${d.raw_value} ${d.unit}</span>
                    <span style="color:#c2410c; font-weight:700;">+${d.influence_pct}%</span>
                </div>
            `).join("");
        }

        if (narrativeEl) {
            narrativeEl.innerText = exp.audit_justification;
        }
    } catch (err) {
        console.error("Quick XAI load error:", err);
    }
}

function openCorridorAuditMemo() {
    if (!currentInspectedSegment) return;
    openXaiAuditMemo(currentInspectedSegment.segment_id);
}

function openSelectedCorridorAuditMemo() {
    const selectEl = document.getElementById("xai-corridor-select");
    if (selectEl && selectEl.value) {
        openXaiAuditMemo(selectEl.value);
    }
}

async function openXaiAuditMemo(segmentId) {
    const modal = document.getElementById("xai-audit-modal");
    const backdrop = document.getElementById("xai-audit-modal-backdrop");
    const refEl = document.getElementById("memo-ref");
    const dateEl = document.getElementById("memo-date");
    const roadEl = document.getElementById("memo-road-name");
    const segEl = document.getElementById("memo-segment-id");
    const zoneEl = document.getElementById("memo-zone");
    const findingEl = document.getElementById("memo-finding-text");
    const tableBody = document.getElementById("memo-drivers-table-body");

    try {
        const res = await fetch(`/api/xai/audit-report/${segmentId}`);
        const data = await res.json();
        if (data.status !== "success" || !data.audit_memo) {
            throw new Error(data.detail || "Failed to load audit memo");
        }

        const memo = data.audit_memo;

        if (refEl) refEl.innerText = memo.memo_ref;
        if (dateEl) dateEl.innerText = memo.generated_at;
        if (roadEl) roadEl.innerText = memo.corridor_name;
        if (segEl) segEl.innerText = memo.corridor_id;
        if (zoneEl) zoneEl.innerText = memo.city_zone;

        if (findingEl) {
            findingEl.innerHTML = `
                The corridor has been evaluated under the PaveSentry real-time predictive intelligence engine. 
                The model has classified this corridor as <strong style="color:${memo.predicted_risk_level === 'HIGH' ? '#dc2626' : '#d97706'};">${memo.predicted_risk_level} RISK</strong> 
                with a severe distress emergence probability of <strong>${memo.failure_probability}</strong>. 
                Baseline log-odds E[f(x)] is ${memo.base_log_odds}.
            `;
        }

        if (tableBody) {
            const drivers = memo.top_drivers || [];
            tableBody.innerHTML = drivers.map(d => `
                <tr style="border-bottom:1px solid #cbd5e1;">
                    <td style="padding:5px 8px; font-weight:600; border-right:1px solid #cbd5e1;">${d.display_name}</td>
                    <td style="padding:5px 8px; border-right:1px solid #cbd5e1;">${d.raw_value} ${d.unit}</td>
                    <td style="padding:5px 8px; text-align:center; font-family:var(--font-mono); border-right:1px solid #cbd5e1; color:#c2410c;">+${d.shap_value}</td>
                    <td style="padding:5px 8px; text-align:center; font-weight:700; border-right:1px solid #cbd5e1;">${d.influence_pct}%</td>
                    <td style="padding:5px 8px; font-size:10.5px; color:#374151;">${d.engineering_rationale}</td>
                </tr>
            `).join("");
        }

        if (modal && backdrop) {
            modal.classList.add("open");
            backdrop.classList.add("open");
        }
    } catch (err) {
        alert("Failed to load official audit memo: " + err.message);
    }
}

function closeXaiAuditModal() {
    const modal = document.getElementById("xai-audit-modal");
    const backdrop = document.getElementById("xai-audit-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

function printXaiAuditMemo() {
    window.print();
}

// Window global bindings for Phase D
window.loadCorridorXai = loadCorridorXai;
window.runCounterfactualSimulation = runCounterfactualSimulation;
window.openXaiModal = openXaiModal;
window.closeXaiModal = closeXaiModal;
window.loadQuickXaiCorridor = loadQuickXaiCorridor;
window.openCorridorAuditMemo = openCorridorAuditMemo;
window.openSelectedCorridorAuditMemo = openSelectedCorridorAuditMemo;
window.openXaiAuditMemo = openXaiAuditMemo;
window.closeXaiAuditModal = closeXaiAuditModal;
window.printXaiAuditMemo = printXaiAuditMemo;

// ==========================================================================
// Phase E: Connected DTC Fleet Telemetry & PostGIS Spatial Studio
// ==========================================================================
let chartFleetOscilloscopeInstance = null;
let activeFleetVehicleId = "DTC-DL1PC-4021";

async function openFleetTelemetryModal() {
    const modal = document.getElementById("fleet-telemetry-modal");
    const backdrop = document.getElementById("fleet-telemetry-modal-backdrop");
    const segmentSelect = document.getElementById("fleet-sim-segment");

    if (modal && backdrop) {
        modal.classList.add("open");
        backdrop.classList.add("open");
    }

    // Populate corridor options from currentGeojson
    if (segmentSelect && currentGeojson && currentGeojson.features) {
        segmentSelect.innerHTML = currentGeojson.features.map(f => {
            const p = f.properties || {};
            return `<option value="${p.segment_id}">${p.name || 'Corridor'} (${p.segment_id} · ${p.city_zone || 'Delhi NCT'})</option>`;
        }).join("");

        if (currentInspectedSegment && currentInspectedSegment.segment_id) {
            segmentSelect.value = currentInspectedSegment.segment_id;
        }
    }

    await loadFleetStatusAndTelemetry();
}

function closeFleetTelemetryModal() {
    const modal = document.getElementById("fleet-telemetry-modal");
    const backdrop = document.getElementById("fleet-telemetry-modal-backdrop");
    if (modal) modal.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

async function loadFleetStatusAndTelemetry() {
    const listEl = document.getElementById("fleet-vehicles-list");
    const countEl = document.getElementById("fleet-stat-count");
    const iriEl = document.getElementById("fleet-stat-avg-iri");
    const spikesEl = document.getElementById("fleet-stat-spikes");

    try {
        const res = await fetch("/api/telemetry/live-fleet");
        const data = await res.json();
        const fleet = data.fleet || [];

        if (countEl) countEl.innerText = `${fleet.length} Connected Units`;

        if (fleet.length > 0) {
            const avgIri = (fleet.reduce((acc, v) => acc + (v.computed_iri || 2.5), 0) / fleet.length).toFixed(1);
            if (iriEl) iriEl.innerText = `${avgIri} m/km`;
        }

        // Fetch spikes
        const resSpikes = await fetch("/api/telemetry/spikes");
        const dataSpikes = await resSpikes.json();
        const spikes = dataSpikes.spikes || [];
        if (spikesEl) spikesEl.innerText = `${spikes.length} Active`;

        if (listEl) {
            listEl.innerHTML = fleet.map(v => {
                const isActive = v.vehicle_id === activeFleetVehicleId;
                return `
                    <div class="fleet-vehicle-card ${isActive ? 'active' : ''}" onclick="selectFleetVehicle('${v.vehicle_id}')">
                        <div class="fleet-card-header">
                            <div>
                                <span class="fleet-pulse-dot"></span>
                                <strong style="font-size:12px; margin-left:4px; color:var(--text-primary);">${v.vehicle_id}</strong>
                                <span style="font-size:11px; color:var(--text-secondary); margin-left:4px;">${v.model || 'Electric Bus'}</span>
                            </div>
                            <span class="tag-badge" style="background:#e0f2fe; color:#0369a1; font-size:10px;">${v.route_code || 'Route 429'}</span>
                        </div>
                        <div style="font-size:11px; color:#334155; margin-bottom:3px;">
                            <i class="fa-solid fa-location-dot" style="color:#ef4444; font-size:10px;"></i>
                            Snapped: <strong>${v.snapped_corridor || 'Mahatma Gandhi Ring Road'}</strong>
                        </div>
                        <div class="fleet-telemetry-grid">
                            <div>Speed: <strong>${v.speed_kmh} km/h</strong></div>
                            <div>Roughness: <strong style="color:${v.computed_iri > 4.0 ? '#b91c1c' : '#059669'};">${v.computed_iri} m/km</strong></div>
                            <div>RMS Bounce: <strong>${v.vertical_rms_g || '0.12'} g</strong></div>
                        </div>
                    </div>
                `;
            }).join("");
        }

        renderFleetOscilloscope(activeFleetVehicleId);
    } catch (err) {
        console.error("Fleet telemetry error:", err);
    }
}

function selectFleetVehicle(vehicleId) {
    activeFleetVehicleId = vehicleId;
    const label = document.getElementById("oscilloscope-vehicle-label");
    if (label) label.innerText = `Vehicle: ${vehicleId}`;

    document.querySelectorAll(".fleet-vehicle-card").forEach(c => c.classList.remove("active"));
    loadFleetStatusAndTelemetry();
}

async function renderFleetOscilloscope(vehicleId) {
    const canvas = document.getElementById("chart-fleet-oscilloscope");
    if (!canvas || !window.Chart) return;

    try {
        const res = await fetch(`/api/telemetry/waveform/${vehicleId}`);
        const data = await res.json();
        const waveform = data.waveform || [];

        // Synthesize baseline wave if empty
        let points = waveform.map(w => w.accel_z);
        if (points.length < 5) {
            points = [1.02, 1.05, 0.98, 1.08, 1.01, 0.97, 1.04, 1.12, 1.00, 0.99, 1.03, 1.06];
        }

        const labels = points.map((_, i) => `${i * 20}ms`);
        const thresholdLine = points.map(() => 2.2);

        if (chartFleetOscilloscopeInstance) {
            chartFleetOscilloscopeInstance.destroy();
        }

        const ctx = canvas.getContext("2d");
        chartFleetOscilloscopeInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Vertical Bounce az (g)",
                        data: points,
                        borderColor: "#0284c7",
                        backgroundColor: "rgba(2, 132, 199, 0.08)",
                        borderWidth: 2,
                        tension: 0.25,
                        pointRadius: 2,
                        fill: true
                    },
                    {
                        label: "Pothole Shock Threshold (2.2g)",
                        data: thresholdLine,
                        borderColor: "#ef4444",
                        borderWidth: 1.5,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 300 },
                scales: {
                    y: {
                        min: 0.4,
                        max: 2.8,
                        grid: { color: "#f1f5f9" },
                        ticks: { font: { size: 10 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { display: false }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    } catch (err) {
        console.error("Oscilloscope render error:", err);
    }
}

async function triggerDtcBusTripSimulation() {
    const segmentSelect = document.getElementById("fleet-sim-segment");
    const vehicleSelect = document.getElementById("fleet-sim-vehicle");
    const speedInput = document.getElementById("fleet-sim-speed");
    const resultBox = document.getElementById("fleet-sim-result");
    const btn = document.getElementById("btn-stream-trip");

    if (!segmentSelect || !segmentSelect.value) return;

    const segmentId = segmentSelect.value;
    const vehicleId = vehicleSelect ? vehicleSelect.value : "DTC-DL1PC-4021";
    const speed = speedInput ? parseFloat(speedInput.value) : 42.0;

    const originalText = btn ? btn.innerHTML : "";
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Streaming 50 Hz Live DTC Run...`;
    }

    try {
        const res = await fetch("/api/telemetry/simulate-trip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                segment_id: segmentId,
                vehicle_id: vehicleId,
                speed_kmh: speed,
                samples_count: 18
            })
        });

        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.detail || "Trip simulation failed");
        }

        if (resultBox) {
            resultBox.style.display = "block";
            resultBox.style.background = "#f0fdf4";
            resultBox.style.border = "1px solid #bbf7d0";
            resultBox.style.color = "#166534";
            resultBox.innerHTML = `
                <div style="font-weight:700; margin-bottom:3px; display:flex; justify-content:space-between;">
                    <span><i class="fa-solid fa-circle-check"></i> ${data.total_samples} Telemetry Points Ingested</span>
                    <span class="tag-badge" style="background:#dcfce7; color:#15803d;">IRI: ${data.mean_dynamic_iri} m/km</span>
                </div>
                <div style="font-size:10.5px;">
                    Corridor: <strong>${data.corridor_name}</strong> · Speed: ${data.simulated_speed_kmh} km/h<br/>
                    Pothole Shock Spikes Flagged: <strong style="color:${data.pothole_spikes_flagged > 0 ? '#b91c1c' : '#15803d'};">${data.pothole_spikes_flagged}</strong>
                </div>
            `;
        }

        activeFleetVehicleId = vehicleId;
        await loadFleetStatusAndTelemetry();
    } catch (err) {
        alert("Trip simulation failed: " + err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

async function executePostGisRadiusQuery() {
    const lonInput = document.getElementById("postgis-query-lon");
    const latInput = document.getElementById("postgis-query-lat");
    const radiusInput = document.getElementById("postgis-query-radius");
    const outputEl = document.getElementById("postgis-query-output");

    const lon = lonInput ? parseFloat(lonInput.value) : 77.2090;
    const lat = latInput ? parseFloat(latInput.value) : 28.6139;
    const radius = radiusInput ? parseFloat(radiusInput.value) : 2000;

    if (outputEl) {
        outputEl.innerHTML = `<span style="color:#0284c7;"><i class="fa-solid fa-spinner fa-spin"></i> Executing PostGIS ST_DWithin(geometry, ST_SetSRID(ST_MakePoint(${lon}, ${lat}), 4326), ${radius})...</span>`;
    }

    try {
        const startTime = performance.now();
        const res = await fetch(`/api/spatial/corridors/radius?lon=${lon}&lat=${lat}&radius_m=${radius}`);
        const data = await res.json();
        const elapsed = (performance.now() - startTime).toFixed(1);

        if (data.status === "success" && outputEl) {
            const list = data.corridors || [];
            if (list.length === 0) {
                outputEl.innerHTML = `PostGIS Query Complete (${elapsed}ms): 0 corridors within ${radius}m.`;
            } else {
                const nearest = list[0];
                outputEl.innerHTML = `
                    <div style="color:#15803d; font-weight:700;">✅ PostGIS ST_DWithin Executed in ${elapsed}ms</div>
                    <div>Corridors in ${radius}m radius: <strong>${data.corridors_found}</strong></div>
                    <div>Closest: <strong>${nearest.name}</strong> (${nearest.distance_meters}m away, ${nearest.road_type})</div>
                `;
            }
        }
    } catch (err) {
        if (outputEl) outputEl.innerHTML = `<span style="color:#dc2626;">PostGIS Query Error: ${err.message}</span>`;
    }
}

async function triggerPostGisSqlDump() {
    try {
        const res = await fetch("/api/spatial/migrate", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            const sizeKb = (data.dump_size_bytes / 1024).toFixed(1);
            alert(`✅ PostGIS 16 SQL Migration Dump Generated Successfully!\n\n` +
                  `File: ${data.dump_file}\n` +
                  `Size: ${sizeKb} KB\n` +
                  `Corridors Converted: ${data.corridors_migrated} WKT LineStrings\n` +
                  `Spatial Indexes: GIST(geometry) & GIST(location)\n\n` +
                  `Ready for zero-downtime pg_restore to Enterprise PostgreSQL 16 server.`);
        }
    } catch (err) {
        alert("Migration dump failed: " + err.message);
    }
}

// Window global bindings for Phase E
window.openFleetTelemetryModal = openFleetTelemetryModal;
window.closeFleetTelemetryModal = closeFleetTelemetryModal;
window.selectFleetVehicle = selectFleetVehicle;
window.triggerDtcBusTripSimulation = triggerDtcBusTripSimulation;
window.executePostGisRadiusQuery = executePostGisRadiusQuery;
window.triggerPostGisSqlDump = triggerPostGisSqlDump;

// ==========================================================================
// Phase F: Green Roads & Carbon Footprint Calculator (IRC:SP:98-2020)
// ==========================================================================
let activeGreenSegmentId = null;

async function openGreenRoadsModal() {
    const modal = document.getElementById("green-roads-modal");
    const backdrop = document.getElementById("green-roads-modal-backdrop");
    const corridorSelect = document.getElementById("green-corridor-select");

    if (modal && backdrop) {
        modal.style.display = "flex";
        modal.classList.add("open");
        backdrop.classList.add("open");
        backdrop.classList.add("active");
    }

    // Populate corridor options if available
    if (corridorSelect) {
        if (typeof currentGeojson !== "undefined" && currentGeojson && currentGeojson.features && currentGeojson.features.length > 0) {
            corridorSelect.innerHTML = currentGeojson.features.map(f => {
                const p = f.properties || {};
                return `<option value="${p.segment_id}">${p.name || 'Corridor'} (${p.segment_id} · ${p.city_zone || 'Delhi NCT'})</option>`;
            }).join("");
            
            if (typeof currentInspectedSegment !== "undefined" && currentInspectedSegment && currentInspectedSegment.segment_id) {
                corridorSelect.value = currentInspectedSegment.segment_id;
            }
        }
    }

    // Load ESG Summary stats
    await loadGreenRoadsSummary();

    // Trigger Corridor calculation for selected
    await onGreenCorridorChange();
}

function closeGreenRoadsModal() {
    const modal = document.getElementById("green-roads-modal");
    const backdrop = document.getElementById("green-roads-modal-backdrop");
    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("open");
    }
    if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.classList.remove("active");
    }
}

async function loadGreenRoadsSummary() {
    try {
        const res = await fetch("/api/green-roads/network-summary");
        if (!res.ok) return;
        const json = await res.json();
        const data = json.esg_summary || {};

        const elEmbodied = document.getElementById("green-stat-embodied");
        const elFuel = document.getElementById("green-stat-fuel");
        const elLifetime = document.getElementById("green-stat-lifetime");
        const elTrees = document.getElementById("green-stat-trees");

        if (elEmbodied) elEmbodied.innerText = `${(Math.round(data.total_embodied_co2e_saved_tco2e || 0)).toLocaleString()} tCO₂e`;
        if (elFuel) elFuel.innerText = `${(Math.round((data.total_annual_diesel_saved_litres || 0) / 1000)).toLocaleString()} kL / yr`;
        if (elLifetime) elLifetime.innerText = `${(Math.round(data.total_lifecycle_co2e_abated_tco2e || 0)).toLocaleString()} tCO₂e`;
        if (elTrees) elTrees.innerText = `${(data.total_equivalent_trees_offset || 0).toLocaleString()} 🌳`;
    } catch (err) {
        console.error("Error loading network ESG summary:", err);
    }
}

async function onGreenCorridorChange() {
    const select = document.getElementById("green-corridor-select");
    let segmentId = select ? select.value : null;
    if (!segmentId && typeof currentInspectedSegment !== "undefined" && currentInspectedSegment) {
        segmentId = currentInspectedSegment.segment_id;
    }
    if (!segmentId) segmentId = "DL-NCT-0001";

    activeGreenSegmentId = segmentId;
    await Promise.all([
        loadCorridorGreenLca(segmentId),
        loadCorridorGreenComparison(segmentId)
    ]);
}

async function loadCorridorGreenLca(segmentId) {
    try {
        const res = await fetch(`/api/green-roads/corridor/${encodeURIComponent(segmentId)}`);
        if (!res.ok) return;
        const json = await res.json();
        const lca = json.carbon_lca || {};

        // Update corridor info strip
        const elLanes = document.getElementById("gc-length-lanes");
        const elAadt = document.getElementById("gc-aadt");
        const elTreatment = document.getElementById("gc-treatment");
        const elRapTemp = document.getElementById("gc-rap-temp");
        const elGreenScore = document.getElementById("gc-green-score");

        if (elLanes) elLanes.innerText = `${lca.length_km || 0} km (${lca.lanes || 4} lanes · ${lca.lane_km || 0} ln-km)`;
        if (elAadt) elAadt.innerText = `${(lca.aadt || 0).toLocaleString()} veh/day`;
        if (elTreatment) elTreatment.innerText = `${lca.selected_treatment || 'Standard Maintenance'}`;
        if (elRapTemp) elRapTemp.innerText = `${lca.rap_recycled_content_pct || 0}% RAP · ${lca.plant_mixing_temp_c || 160}°C`;
        if (elGreenScore) {
            elGreenScore.innerText = `${lca.irc_sp_98_score || 0} / 100 (${lca.star_rating || '3-Star'})`;
            elGreenScore.style.background = lca.badge_color || "#10b981";
            elGreenScore.style.color = "#ffffff";
        }

        // Update Right Column: Category breakdown
        const cats = lca.category_scores || {};
        const updateCat = (catKey, scoreId, fillId) => {
            const cat = cats[catKey] || { score: 0, max: 1 };
            const scoreEl = document.getElementById(scoreId);
            const fillEl = document.getElementById(fillId);
            if (scoreEl) scoreEl.innerText = `${cat.score} / ${cat.max}`;
            if (fillEl) {
                const pct = Math.min(100, Math.round((cat.score / cat.max) * 100));
                fillEl.style.width = `${pct}%`;
            }
        };

        updateCat("materials_and_recycling", "score-cat-materials", "fill-cat-materials");
        updateCat("energy_and_low_temp", "score-cat-energy", "fill-cat-energy");
        updateCat("haulage_and_insitu", "score-cat-haulage", "fill-cat-haulage");
        updateCat("drainage_preservation", "score-cat-drainage", "fill-cat-drainage");
        updateCat("vehicle_operational_efficiency", "score-cat-vehicle", "fill-cat-vehicle");

        // Total score & star badge
        const totalScoreEl = document.getElementById("green-score-total");
        if (totalScoreEl) totalScoreEl.innerText = `${lca.irc_sp_98_score || 0} / 100`;

        const starBadge = document.getElementById("green-overall-star-badge");
        if (starBadge) {
            starBadge.innerText = `${lca.star_rating || '3-Star Silver'}`;
            starBadge.style.background = lca.badge_color || "#10b981";
        }
    } catch (err) {
        console.error("Error loading corridor LCA:", err);
    }
}

async function loadCorridorGreenComparison(segmentId) {
    try {
        const res = await fetch(`/api/green-roads/comparison/${encodeURIComponent(segmentId)}`);
        if (!res.ok) return;
        const json = await res.json();
        const comparisons = json.comparison || [];
        const tbody = document.getElementById("green-tech-table-body");
        if (!tbody) return;

        if (comparisons.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:12px; color:var(--text-muted);">No comparison data available</td></tr>`;
            return;
        }

        tbody.innerHTML = comparisons.map(c => {
            const isBase = c.savings_pct === 0;
            const rowBg = isBase ? "background:#fff1f2;" : (c.recycled_rap_pct >= 80 ? "background:#ecfdf5;" : "");
            const badgeClass = c.star_rating.includes("Platinum") ? "platinum" :
                               c.star_rating.includes("Gold") ? "gold" :
                               c.star_rating.includes("Silver") ? "silver" : "bronze";

            return `
                <tr style="border-bottom:1px solid #e2e8f0; ${rowBg}">
                    <td style="padding:6px 8px; font-weight:600; color:#0f172a;">
                        ${c.treatment_name}
                        ${isBase ? '<span style="font-size:9.5px; color:#be123c; margin-left:4px; font-weight:700;">(Baseline)</span>' : ''}
                    </td>
                    <td style="padding:6px 8px; text-align:center; font-family:var(--font-mono);">${c.mixing_temp_c}°C</td>
                    <td style="padding:6px 8px; text-align:center; font-family:var(--font-mono); font-weight:600;">${c.recycled_rap_pct}%</td>
                    <td style="padding:6px 8px; text-align:right; font-family:var(--font-mono);">${c.embodied_tco2e.toLocaleString()}</td>
                    <td style="padding:6px 8px; text-align:right; font-family:var(--font-mono); font-weight:700; color:${isBase ? '#e11d48' : '#059669'};">
                        ${isBase ? '0.0%' : `-${c.savings_pct}%`}
                    </td>
                    <td style="padding:6px 8px; text-align:center;">
                        <span class="green-star-pill ${badgeClass}">
                            <i class="fa-solid fa-star"></i> ${c.star_rating.split(' ')[0]} (${c.green_score} pts)
                        </span>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        console.error("Error loading comparison matrix:", err);
    }
}

async function openGreenCertificate(segmentId) {
    const segId = segmentId || activeGreenSegmentId || (typeof currentInspectedSegment !== "undefined" && currentInspectedSegment ? currentInspectedSegment.segment_id : "DL-NCT-0001");
    if (!segId) return;

    try {
        const res = await fetch(`/api/green-roads/certificate/${encodeURIComponent(segId)}`);
        if (!res.ok) {
            alert("Could not load green certificate for segment: " + segId);
            return;
        }
        const json = await res.json();
        const cert = json.certificate || {};

        // Populate certificate fields
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.innerText = val || "--";
        };

        setVal("cert-id", cert.certificate_id);
        setVal("cert-date", cert.issued_date);
        setVal("cert-rating", cert.star_rating);
        setVal("cert-corridor-name", cert.corridor_name);
        setVal("cert-segment-zone", `${cert.corridor_id} (${cert.city_zone || 'Delhi NCT'})`);
        setVal("cert-length-lanes", `${cert.corridor_length_km} km (${cert.lane_km} lane-km)`);
        setVal("cert-assigned-tech", cert.assigned_technology);
        setVal("cert-rap-pct", cert.rap_recycled_content);
        setVal("cert-mix-temp", `${cert.plant_mixing_temp_c}°C Process Temperature`);

        // Abatement metrics
        setVal("cert-baseline-emissions", `${cert.technical_specifications?.baseline_emissions_tco2e || '--'} Metric Tonnes CO₂e`);
        setVal("cert-embodied-saved", `${cert.technical_specifications?.embodied_co2e_saved_tco2e || '--'} Metric Tonnes CO₂e`);
        setVal("cert-abatement-pct", cert.carbon_abatement_pct);
        setVal("cert-fuel-saved", cert.annual_diesel_fuel_conserved);
        setVal("cert-lifetime-saved", cert.total_lifecycle_co2e_saved);
        setVal("cert-trees", cert.equivalent_trees_planted);

        // Open modal
        const certModal = document.getElementById("green-cert-modal");
        const certBackdrop = document.getElementById("green-cert-modal-backdrop");
        if (certModal && certBackdrop) {
            certModal.style.display = "flex";
            certBackdrop.classList.add("open");
        }
    } catch (err) {
        alert("Failed to load certificate: " + err.message);
    }
}

function closeGreenCertificate() {
    const certModal = document.getElementById("green-cert-modal");
    const certBackdrop = document.getElementById("green-cert-modal-backdrop");
    if (certModal) certModal.style.display = "none";
    if (certBackdrop) certBackdrop.classList.remove("open");
}

function printGreenCertificate() {
    window.print();
}

// Window global bindings for Phase F
window.openGreenRoadsModal = openGreenRoadsModal;
window.closeGreenRoadsModal = closeGreenRoadsModal;
window.onGreenCorridorChange = onGreenCorridorChange;
window.openGreenCertificate = openGreenCertificate;
window.closeGreenCertificate = closeGreenCertificate;
window.printGreenCertificate = printGreenCertificate;

// ==========================================================================
// Additional Capability 1: Citizen Crowdsourcing Portal (Delhi 311 / WhatsApp PWA)
// ==========================================================================
function openCitizenPortalModal() {
    const modal = document.getElementById("citizen-portal-modal");
    const backdrop = document.getElementById("citizen-portal-modal-backdrop");
    if (modal && backdrop) {
        modal.style.display = "flex";
        modal.classList.add("open");
        backdrop.classList.add("open");
        backdrop.classList.add("active");
    }
}

function closeCitizenPortalModal() {
    const modal = document.getElementById("citizen-portal-modal");
    const backdrop = document.getElementById("citizen-portal-modal-backdrop");
    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("open");
    }
    if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.classList.remove("active");
    }
}

function switchCitizenTab(tab) {
    const submitPane = document.getElementById("cit-tab-submit-pane");
    const trackPane = document.getElementById("cit-tab-track-pane");
    const btnSubmit = document.getElementById("btn-cit-tab-submit");
    const btnTrack = document.getElementById("btn-cit-tab-track");

    if (tab === "submit") {
        if (submitPane) submitPane.style.display = "block";
        if (trackPane) trackPane.style.display = "none";
        if (btnSubmit) {
            btnSubmit.style.borderBottomColor = "#0284c7";
            btnSubmit.style.color = "#0369a1";
        }
        if (btnTrack) {
            btnTrack.style.borderBottomColor = "transparent";
            btnTrack.style.color = "#64748b";
        }
    } else {
        if (submitPane) submitPane.style.display = "none";
        if (trackPane) trackPane.style.display = "block";
        if (btnSubmit) {
            btnSubmit.style.borderBottomColor = "transparent";
            btnSubmit.style.color = "#64748b";
        }
        if (btnTrack) {
            btnTrack.style.borderBottomColor = "#0284c7";
            btnTrack.style.color = "#0369a1";
        }
    }
}

function captureCitizenGps() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            pos => {
                const latInput = document.getElementById("cit-lat");
                const lonInput = document.getElementById("cit-lon");
                if (latInput) latInput.value = pos.coords.latitude.toFixed(5);
                if (lonInput) lonInput.value = pos.coords.longitude.toFixed(5);
            },
            err => {
                alert("GPS access denied or unavailable. Using default Central Delhi coordinates.");
            }
        );
    } else {
        alert("Geolocation is not supported by your browser.");
    }
}

async function submitCitizenReport() {
    const photoInput = document.getElementById("cit-photo");
    if (!photoInput || !photoInput.files || photoInput.files.length === 0) {
        alert("Please select or capture a road pothole photo.");
        return;
    }

    const submitBtn = document.getElementById("btn-cit-submit");
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Running YOLOv8 Verification...`;
    }

    const formData = new FormData();
    formData.append("file", photoInput.files[0]);
    formData.append("latitude", document.getElementById("cit-lat").value || "28.6139");
    formData.append("longitude", document.getElementById("cit-lon").value || "77.2090");
    formData.append("citizen_name", document.getElementById("cit-name").value || "Delhi Resident");
    formData.append("citizen_mobile", document.getElementById("cit-mobile").value || "9811002233");
    formData.append("road_description", document.getElementById("cit-landmark").value || "");
    formData.append("source_channel", document.getElementById("cit-channel").value || "delhi_311");

    try {
        const res = await fetch("/api/citizen/report", {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        if (data.status === "success") {
            const card = document.getElementById("cit-result-card");
            if (card) card.style.display = "block";

            const elTicket = document.getElementById("cit-res-ticket");
            const elAi = document.getElementById("cit-res-ai-status");
            const elDims = document.getElementById("cit-res-dims");
            const elDiv = document.getElementById("cit-res-division");
            const elSla = document.getElementById("cit-res-sla");

            if (elTicket) elTicket.innerText = data.ticket_id;
            if (elAi) elAi.innerText = `${data.verification_details?.status} (${data.verification_details?.confidence_score}%)`;
            if (elDims) elDims.innerText = `${data.verification_details?.estimated_surface_area_cm2} cm² · ${data.verification_details?.depth_category}`;
            if (elDiv) elDiv.innerText = `${data.routing?.assigned_division}`;
            if (elSla) elSla.innerHTML = `Target SLA: <strong>${data.routing?.target_sla_resolution_hours} Hours</strong> (${data.routing?.assigned_executive_engineer})`;
        } else {
            alert("Submission error: " + (data.detail || "Unknown error"));
        }
    } catch (err) {
        alert("Network error: " + err.message);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<i class="fa-solid fa-paper-plane"></i> Submit Verified Pothole Report`;
        }
    }
}

async function trackCitizenTicket() {
    const queryInput = document.getElementById("cit-track-query");
    const ticketId = queryInput ? queryInput.value.trim() : "";
    if (!ticketId) {
        alert("Please enter a valid ticket number (e.g. DEL-311-2026-XXXX).");
        return;
    }

    try {
        const res = await fetch(`/api/citizen/track/${encodeURIComponent(ticketId)}`);
        if (!res.ok) {
            alert("Ticket not found. Please verify ticket ID.");
            return;
        }
        const data = await res.json();

        const resultPane = document.getElementById("cit-track-result");
        if (resultPane) resultPane.style.display = "block";

        const elRoad = document.getElementById("cit-track-road");
        const elBadge = document.getElementById("cit-track-status-badge");
        const elDiv = document.getElementById("cit-track-div-info");
        const elStepper = document.getElementById("cit-stepper-container");

        if (elRoad) elRoad.innerText = data.road_name || "Delhi Arterial Corridor";
        if (elBadge) {
            elBadge.innerText = data.current_status || "In Review";
            elBadge.style.background = data.current_status === "Repaired" ? "#059669" : "#0284c7";
        }
        if (elDiv) elDiv.innerText = `Assigned to: ${data.assigned_division} · Engineer: ${data.assigned_engineer}`;

        if (elStepper && data.milestones) {
            elStepper.innerHTML = data.milestones.map(m => `
                <div class="cit-milestone-step ${m.completed ? 'completed' : ''}">
                    <div class="cit-milestone-dot"></div>
                    <div class="cit-step-title">
                        <span>${m.stage}</span>
                        <span style="font-size:10px; color:${m.completed ? '#0284c7' : '#94a3b8'};">${m.completed ? '✓ Completed' : 'Pending'}</span>
                    </div>
                    <div class="cit-step-desc">${m.description}</div>
                </div>
            `).join("");
        }
    } catch (err) {
        alert("Failed to track ticket: " + err.message);
    }
}

// ==========================================================================
// Additional Capability 2: Monsoon Waterlogging & Hydroplaning Vulnerability
// ==========================================================================
async function openWaterloggingModal() {
    const modal = document.getElementById("waterlogging-modal");
    const backdrop = document.getElementById("waterlogging-modal-backdrop");
    if (modal && backdrop) {
        modal.style.display = "flex";
        modal.classList.add("open");
        backdrop.classList.add("open");
        backdrop.classList.add("active");
    }

    await loadWaterloggingData();
}

function closeWaterloggingModal() {
    const modal = document.getElementById("waterlogging-modal");
    const backdrop = document.getElementById("waterlogging-modal-backdrop");
    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("open");
    }
    if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.classList.remove("active");
    }
}

async function loadWaterloggingData() {
    try {
        const res = await fetch("/api/waterlogging/network-summary");
        if (!res.ok) return;
        const data = await res.json();

        // 1. Metric strip
        const elAvg = document.getElementById("wl-stat-avg-wprf");
        const elCrit = document.getElementById("wl-stat-critical-count");
        const elCbr = document.getElementById("wl-stat-cbr-loss");

        if (elAvg) elAvg.innerText = `${data.network_average_wprf} / 100`;
        if (elCrit) elCrit.innerText = `${data.vulnerability_distribution?.critical || 0} Corridors`;
        if (elCbr) elCbr.innerText = `-45.2 %`;

        // 2. Hotspots table
        const tbody = document.getElementById("wl-hotspots-tbody");
        if (tbody && data.delhi_underpass_hotspots) {
            tbody.innerHTML = data.delhi_underpass_hotspots.map(h => {
                const badgeClass = h.vulnerability_tier === "Critical" ? "wl-badge-critical" :
                                   h.vulnerability_tier === "High" ? "wl-badge-high" : "wl-badge-moderate";
                return `
                    <tr style="border-bottom:1px solid #e2e8f0;">
                        <td style="padding:6px 8px; font-weight:600; color:#0f172a;">${h.name}</td>
                        <td style="padding:6px 8px; color:#64748b;">${h.city_zone}</td>
                        <td style="padding:6px 8px; text-align:center; font-family:var(--font-mono);">${h.depression_depth_m} m</td>
                        <td style="padding:6px 8px; text-align:center; font-family:var(--font-mono);">${h.historical_max_inundation_cm} cm</td>
                        <td style="padding:6px 8px; text-align:center;"><span class="${badgeClass}">${h.vulnerability_tier}</span></td>
                    </tr>
                `;
            }).join("");
        }

        // 3. Populate corridor dropdown
        const select = document.getElementById("wl-corridor-select");
        if (select && typeof currentGeojson !== "undefined" && currentGeojson && currentGeojson.features) {
            select.innerHTML = currentGeojson.features.map(f => {
                const p = f.properties || {};
                return `<option value="${p.segment_id}">${p.name || 'Corridor'} (${p.segment_id})</option>`;
            }).join("");
        }

        await onWaterloggingCorridorChange();
    } catch (err) {
        console.error("Error loading waterlogging summary:", err);
    }
}

async function onWaterloggingCorridorChange() {
    const select = document.getElementById("wl-corridor-select");
    const segmentId = select ? select.value : "DL-NCT-0001";
    if (!segmentId) return;

    try {
        const res = await fetch(`/api/waterlogging/corridor/${encodeURIComponent(segmentId)}`);
        if (!res.ok) return;
        const json = await res.json();
        const wl = json.waterlogging_analysis || {};

        const elScore = document.getElementById("wl-corridor-score");
        const elTier = document.getElementById("wl-corridor-tier");
        const elBanner = document.getElementById("wl-corridor-banner");
        const elCbr = document.getElementById("wl-cbr-comparison");
        const elMr = document.getElementById("wl-mr-comparison");
        const elFatigue = document.getElementById("wl-fatigue-loss");
        const elHydro = document.getElementById("wl-hydro-index");
        const elFilm = document.getElementById("wl-water-film");
        const elBoost = document.getElementById("wl-priority-boost");

        if (elScore) elScore.innerText = `${wl.waterlogging_risk_score} / 100`;
        if (elTier) elTier.innerText = wl.risk_tier || "Moderate Vulnerability";
        if (elBanner) {
            elBanner.style.borderColor = wl.risk_color || "#bbf7d0";
        }

        const sub = wl.soaked_subgrade_mechanics || {};
        if (elCbr) elCbr.innerText = `${sub.dry_cbr_pct}% → ${sub.soaked_cbr_pct}% (-${sub.cbr_loss_pct}%)`;
        if (elMr) elMr.innerText = `${sub.dry_resilient_modulus_mpa} MPa → ${sub.soaked_resilient_modulus_mpa} MPa`;
        if (elFatigue) elFatigue.innerText = `-${sub.fatigue_life_reduction_pct}% Under Heavy Axles`;

        const hydro = wl.hydroplaning_assessment || {};
        if (elHydro) elHydro.innerText = `${hydro.hydroplaning_risk_index} / 100 (${hydro.verdict ? hydro.verdict.split(' ')[0] : 'Normal'})`;
        if (elFilm) elFilm.innerText = `${hydro.estimated_water_film_depth_mm} mm`;

        const prep = wl.pre_monsoon_preparedness || {};
        if (elBoost) elBoost.innerText = `+${prep.pre_monsoon_priority_multiplier}% Priority Score`;
    } catch (err) {
        console.error("Error loading corridor waterlogging:", err);
    }
}

// ==========================================================================
// Additional Capability 3: Anti-Corruption Cryptographic Audit Trail (CAG)
// ==========================================================================
async function openAuditChainModal() {
    const modal = document.getElementById("audit-chain-modal");
    const backdrop = document.getElementById("audit-chain-modal-backdrop");
    if (modal && backdrop) {
        modal.style.display = "flex";
        modal.classList.add("open");
        backdrop.classList.add("open");
        backdrop.classList.add("active");
    }

    await Promise.all([
        loadAuditChain(),
        verifyAuditChain()
    ]);
}

function closeAuditChainModal() {
    const modal = document.getElementById("audit-chain-modal");
    const backdrop = document.getElementById("audit-chain-modal-backdrop");
    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("open");
    }
    if (backdrop) {
        backdrop.classList.remove("open");
        backdrop.classList.remove("active");
    }
}

async function loadAuditChain() {
    try {
        const res = await fetch("/api/audit-trail/chain?limit=30");
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.getElementById("audit-chain-tbody");
        if (!tbody || !data.chain) return;

        tbody.innerHTML = data.chain.map(b => `
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:6px 8px; font-weight:700; color:#0f172a;">#${b.block_index}</td>
                <td style="padding:6px 8px; color:#64748b; font-size:10px;">${b.timestamp}</td>
                <td style="padding:6px 8px; font-weight:600; color:#0369a1;">${b.event_type}</td>
                <td style="padding:6px 8px; font-weight:600;">${b.entity_id}</td>
                <td style="padding:6px 8px; font-size:10.5px; color:#475569;">${b.actor} (${b.division})</td>
                <td style="padding:6px 8px;">
                    <span class="audit-hash-pill" title="Prev: ${b.prev_hash}">
                        ${b.block_hash.slice(0, 16)}...
                    </span>
                </td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("Error loading audit chain:", err);
    }
}

async function verifyAuditChain() {
    try {
        const res = await fetch("/api/audit-trail/verify");
        if (!res.ok) return;
        const data = await res.json();
        const v = data.verification || {};

        const elBadge = document.getElementById("audit-status-badge");
        const elBlocks = document.getElementById("audit-total-blocks");
        const elRoot = document.getElementById("audit-merkle-root");

        if (elBlocks) elBlocks.innerText = `${v.total_blocks_verified} Blocks Verified`;
        if (elRoot) elRoot.innerText = v.merkle_root_hash ? `${v.merkle_root_hash.slice(0, 32)}...` : "--";

        if (elBadge) {
            if (v.is_tamper_free) {
                elBadge.style.background = "#059669";
                elBadge.innerHTML = `<i class="fa-solid fa-circle-check"></i> CHAIN INTACT — ZERO TAMPERING DETECTED`;
            } else {
                elBadge.style.background = "#dc2626";
                elBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> TAMPER DETECTED AT BLOCK #${v.tampered_blocks?.[0]?.block_index || '?'}`;
            }
        }
    } catch (err) {
        console.error("Error verifying audit chain:", err);
    }
}

async function openCagCertificate() {
    try {
        const res = await fetch("/api/audit-trail/certificate");
        if (!res.ok) return;
        const data = await res.json();
        const cert = data.certificate || {};

        alert(`🏛️ ${cert.certificate_title}\n\n` +
              `Certificate ID: ${cert.certificate_id}\n` +
              `Issue Date: ${cert.issue_date}\n` +
              `Status: ${cert.verification_status}\n` +
              `Total Blocks Verified: ${cert.total_blocks_verified} SHA-256 blocks\n` +
              `Merkle Root Hash: ${cert.merkle_root_hash.slice(0, 24)}...\n\n` +
              `Statutory Mandate: CAG Section 18 / Delhi Lokayukta Act, 1995\n` +
              `Audited for Government of NCT of Delhi Public Works Department`);
    } catch (err) {
        alert("Failed to load CAG certificate: " + err.message);
    }
}

// Window global bindings for 3 Additional Capabilities
window.openCitizenPortalModal = openCitizenPortalModal;
window.closeCitizenPortalModal = closeCitizenPortalModal;
window.switchCitizenTab = switchCitizenTab;
window.captureCitizenGps = captureCitizenGps;
window.submitCitizenReport = submitCitizenReport;
window.trackCitizenTicket = trackCitizenTicket;

window.openWaterloggingModal = openWaterloggingModal;
window.closeWaterloggingModal = closeWaterloggingModal;
window.loadWaterloggingData = loadWaterloggingData;
window.onWaterloggingCorridorChange = onWaterloggingCorridorChange;

window.openAuditChainModal = openAuditChainModal;
window.closeAuditChainModal = closeAuditChainModal;
window.loadAuditChain = loadAuditChain;
window.verifyAuditChain = verifyAuditChain;
window.openCagCertificate = openCagCertificate;





