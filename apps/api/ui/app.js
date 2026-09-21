(() => {
  "use strict";
  const $ = (s, r=document) => r.querySelector(s);
  const ls = {
    get(k, d=null){ try{ const v=localStorage.getItem(k); return v===null?d:JSON.parse(v);}catch{return d;} },
    set(k, v){ localStorage.setItem(k, JSON.stringify(v)); }
  };
  function originOnly(u){
    try{ const x=new URL(String(u||"").trim(), window.location.href); return x.origin; }
    catch{ return String(u||"").trim().replace(/\/+$/,""); }
  }
  function setChips(health=0, keySet=false){
    const h=$("#healthChip"); const a=$("#authChip");
    if (health===200){ h.textContent="Health: OK"; h.className="chip ok"; }
    else if (health===0){ h.textContent="Health: —"; h.className="chip"; }
    else { h.textContent=`Health: ${health}`; h.className="chip err"; }
    if (!keySet){ a.textContent="Auth: not set"; a.className="chip warn"; }
    else { a.textContent="Auth: set"; a.className="chip"; }
  }
  function cfg(){
    const base = originOnly(ls.get("baseUrl","http://127.0.0.1:8000"));
    const key  = ls.get("apiKey","");
    return { base, key };
  }
  function saveCfg(){
    const base = originOnly($("#baseUrl").value);
    const key  = $("#apiKey").value || "";
    ls.set("baseUrl", base); ls.set("apiKey", key);
    $("#docsLink").href = base + "/docs"; $("#docsFooter").href = base + "/docs";
    $("#cfgMsg").textContent = "Saved."; setTimeout(()=>$("#cfgMsg").textContent="", 1200);
    setChips(0, !!key);
  }
  async function ping(){
    const {base, key} = cfg();
    try{
      const r = await fetch(base+"/health");
      setChips(r.status, !!key);
      const t = await r.text();
      $("#cfgMsg").textContent = `Health ${r.status}: ${t.slice(0,200)}`;
      setTimeout(()=>$("#cfgMsg").textContent="",1500);
    }catch(e){
      setChips(0, !!key);
      $("#cfgMsg").textContent = String(e);
    }
  }
  async function apiPost(path, body){
    const {base, key} = cfg();
    const r = await fetch(base + path, {
      method:"POST",
      headers: { "Content-Type":"application/json", ...(key? {"X-API-Key": key}: {}) },
      body: JSON.stringify(body || {})
    });
    const text = await r.text();
    let data = null; try{ data = text ? JSON.parse(text) : null; }catch{ data = { raw:text }; }
    return { status: r.status, data };
  }
  async function loadLedger(){
    const {base, key} = cfg();
    const n = Math.max(1, Math.min(200, parseInt($("#rows").value || "50", 10)));
    const r = await fetch(`${base}/ledger?n=${n}`, { headers: key ? {"X-API-Key": key} : {} });
    const t = await r.text(); let data=null; try{ data = JSON.parse(t); }catch{ data={raw:t}; }
    const tb = $("#ledgerTable tbody"); tb.innerHTML = "";
    if (!data || !data.entries || data.entries.length===0){
      $("#ledgerEmpty").style.display="block"; return;
    }
    $("#ledgerEmpty").style.display="none";
    data.entries.forEach(e => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${e.id}</td>
        <td>${e.created_at ?? ""}</td>
        <td>${e.event_type ?? ""}</td>
        <td>${(e.delta_usd ?? 0).toFixed ? e.delta_usd.toFixed(2) : e.delta_usd}</td>
        <td>${(e.confidence ?? 0).toFixed ? e.confidence.toFixed(2) : e.confidence}</td>
        <td>${e.dry_run ? "yes" : "no"}</td>
        <td>${(e.explanation ?? "").toString().slice(0,120)}</td>
      `;
      tb.appendChild(tr);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("#baseUrl").value = originOnly(ls.get("baseUrl","http://127.0.0.1:8000"));
    $("#apiKey").value  = ls.get("apiKey","") || "";
    $("#docsLink").href = $("#baseUrl").value + "/docs";
    $("#docsFooter").href = $("#baseUrl").value + "/docs";
    setChips(0, !!$("#apiKey").value);

    $("#toggleKey").addEventListener("click", () => {
      const i=$("#apiKey"); const isPwd=i.type==="password";
      i.type = isPwd ? "text" : "password"; $("#toggleKey").textContent = isPwd ? "Hide" : "Show";
    });
    $("#saveCfg").addEventListener("click", saveCfg);
    $("#testHealth").addEventListener("click", ping);

    $("#sendTrigger").addEventListener("click", async () => {
      const evt = $("#triggerEvent").value.trim();
      let payload = {}; try{ payload = JSON.parse($("#triggerPayload").value || "{}"); }catch{ $("#outTrigger").textContent="Invalid JSON"; return; }
      const t0 = performance.now();
      const res = await apiPost("/trigger", { event_type: evt, payload, user_id: "web-ui" });
      const ms = Math.round(performance.now()-t0);
      $("#triggerCode").textContent = `HTTP ${res.status}`; $("#triggerLatency").textContent = `${ms} ms`;
      $("#outTrigger").textContent = JSON.stringify(res.data, null, 2);
      if (res.status===200) loadLedger();
      if (res.status===401) setChips(200, false);
    });

    $("#sendTrigger2").addEventListener("click", async () => {
      const evt = $("#trigger2Event").value.trim();
      let payload = {}; try{ payload = JSON.parse($("#trigger2Payload").value || "{}"); }catch{ $("#outTrigger2").textContent="Invalid JSON"; return; }
      const dry = $("#dryRun").checked ? "true" : "false";
      const t0 = performance.now();
      const res = await apiPost(`/trigger2?dry_run=${dry}`, { event_type: evt, payload, user_id: "web-ui" });
      const ms = Math.round(performance.now()-t0);
      $("#trigger2Code").textContent = `HTTP ${res.status}`; $("#trigger2Latency").textContent = `${ms} ms`;
      $("#outTrigger2").textContent = JSON.stringify(res.data, null, 2);
      if (res.status===200 && dry==="false") loadLedger();
      if (res.status===401) setChips(200, false);
    });

    $("#refreshLedger").addEventListener("click", loadLedger);
    $("#downloadCsv").addEventListener("click", async () => {
      const {base, key} = cfg();
      const n = Math.max(1, Math.min(200, parseInt($("#rows").value || "50", 10)));
      const r = await fetch(`${base}/ledger?n=${n}`, { headers: key ? {"X-API-Key": key} : {} });
      const data = await r.json();
      const rows = [["id","created_at","event_type","delta_usd","confidence","dry_run","explanation"]];
      (data.entries||[]).forEach(e => rows.push([e.id,e.created_at,e.event_type,e.delta_usd,e.confidence,e.dry_run,e.explanation]));
      const csv = rows.map(arr => arr.map(v => `"${String(v??"").replace(/"/g,'""')}"`).join(",")).join("\n");
      const blob = new Blob([csv], {type:"text/csv"}); const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "ledger.csv"; a.click(); URL.revokeObjectURL(url);
    });

    ping().then(loadLedger).catch(()=>{});
  });
})();

// --- Lottie startup animation (bottom) ---
document.addEventListener('DOMContentLoaded', () => {
  try{
    const el = document.getElementById('startupAnim');
    if (el && window.lottie){
      window.lottie.loadAnimation({
        container: el,
        renderer: 'svg',
        loop: true,
        autoplay: true,
        path: 'ae_logo.json'   // served from /ui/ae_logo.json
      });
    }
  }catch(e){ console.debug('Lottie init skipped:', e); }
});

// ===== DEBUG LOTTIE LOADER (idempotent) =====
(function(){
  if (window.__aegisops_lottie_injected__) return;
  window.__aegisops_lottie_injected__ = true;

  function log(){ try{ console.log.apply(console, ["[AegisOps UI]"].concat([].slice.call(arguments))); }catch(_){} }

  function init(){
    const el = document.getElementById('startupAnim');
    if (!el){ log("startupAnim container not found"); return; }
    if (!window.lottie){ log("lottie not available yet"); return; }

    log("Initializing Lottie…");
    // Debug fetch to verify file path
    fetch('/ui/ae_logo.json')
      .then(r => { log("ae_logo.json status:", r.status); return r.json().catch(()=>({})); })
      .then(() => {
        window.lottie.loadAnimation({
          container: el,
          renderer: 'svg',
          loop: true,
          autoplay: true,
          path: '/ui/ae_logo.json'
        });
        log("Lottie loadAnimation called.");
      })
      .catch(e => log("Failed to fetch ae_logo.json:", e));
  }

  function loadScript(cb){
    if (window.lottie){ cb(); return; }
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/lottie-web/build/player/lottie.min.js';
    s.async = true;
    s.onload = cb;
    s.onerror = () => log("Failed to load lottie script");
    document.head.appendChild(s);
  }

  document.addEventListener('DOMContentLoaded', function(){
    loadScript(() => setTimeout(init, 0));
  });
})();
// --- Lottie footer animation (guarded) ---
(function(){
  if (window.__aegisops_lottie__) return;
  window.__aegisops_lottie__ = true;
  function init(){
    const el = document.getElementById('startupAnim');
    if (!el || !window.lottie) return;
    window.lottie.loadAnimation({
      container: el,
      renderer: 'svg',
      loop: true,
      autoplay: true,
      path: '/ui/ae_logo.json'
    });
    console.log("[AegisOps UI] Lottie animation started.");
  }
  function ensureScript(cb){
    if (window.lottie) return cb();
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/lottie-web/build/player/lottie.min.js';
    s.async = true;
    s.onload = cb;
    document.head.appendChild(s);
  }
  document.addEventListener('DOMContentLoaded', () => ensureScript(init));
})();

// --- Ensure animation shows: Lottie + fallback spinner ---
(function(){
  const READY_DELAY = 1200;  // ms before fallback
  function startLottie(){
    const el = document.getElementById('startupAnim');
    if (!el) return;
    if (window.lottie) {
      try {
        window.lottie.loadAnimation({
          container: el, renderer: 'svg', loop: true, autoplay: true, path: '/ui/ae_logo.json'
        });
      } catch (_) {}
    }
    setTimeout(() => {
      if (!el.firstElementChild) {
        const spinner = document.createElement('div');
        spinner.className = 'fallback-spinner';
        spinner.setAttribute('aria-label','Loading animation');
        el.appendChild(spinner);
        console.log('[AegisOps UI] Fallback spinner applied.');
      }
    }, READY_DELAY);
  }
  function ensureLottie(cb){
    if (window.lottie) return cb();
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/lottie-web/build/player/lottie.min.js';
    s.async = true;
    s.onload = cb;
    s.onerror = cb; // still trigger fallback
    document.head.appendChild(s);
  }
  document.addEventListener('DOMContentLoaded', () => ensureLottie(startLottie));
})();
