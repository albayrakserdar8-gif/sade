const $ = (id) => document.getElementById(id);

const PII_LABELS = {
  TCKN: "T.C. kimlik no", IBAN: "IBAN", TELEFON: "telefon", EPOSTA: "e-posta",
  PLAKA: "plaka", AD: "ad soyad", ADRES: "adres",
};

function setStatus(text, isError = false) {
  const el = $("status");
  el.textContent = text;
  el.classList.toggle("hidden", !text);
  el.classList.toggle("error", isError);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function analyze(file) {
  setStatus("Belge okunuyor ve açık modellerle analiz ediliyor… (10–40 sn)");
  $("empty").classList.add("hidden");
  $("result").classList.add("hidden");
  const form = new FormData();
  form.append("file", file);
  form.append("persona", currentPersona);
  form.append("simulate_outage", $("outage").checked);
  form.append("skip_masking", $("nomask").checked);
  try {
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) {
      if (body.calls?.length || body.guardrails?.length) renderBlocked(body);
      loadPersonas();
      throw new Error(body.detail || res.statusText);
    }
    render(body);
    setStatus("");
    loadPersonas();
  } catch (err) {
    setStatus(err.message, true);
    if ($("result").classList.contains("hidden")) $("empty").classList.remove("hidden");
  }
}

let lastRun = null;

function render(r) {
  lastRun = r;
  $("draftbox").classList.add("hidden");
  $("maskedblock").classList.remove("hidden");
  $("datesblock").classList.remove("hidden");
  $("card").innerHTML = r.card ? renderCard(r.card, r.calendar || []) : '<p class="note">Analiz yapılamadı.</p>';
  $("otari").innerHTML = renderCalls(r.calls || [], r.cost_usd) + renderGuardrails(r.guardrails) + renderMcp(r.mcp);
  const pii = Object.entries(r.pii || {});
  $("pii").innerHTML = pii.length
    ? pii.map(([k, n]) => `<span class="chip">${esc(PII_LABELS[k] || k)} × ${n} maskelendi</span>`).join("")
    : '<span class="chip ok">kişisel veri bulunmadı</span>';
  $("masked").textContent = r.masked_text;
  $("dates").innerHTML = (r.dates || [])
    .map((d) => `<li><strong>${esc(d.text)}</strong> — ${esc(d.context || "")}</li>`).join("");
  $("result").classList.remove("hidden");
  const mk = $("mkdraft");
  if (mk) mk.addEventListener("click", () => makeDraft(r.run_id, mk));
}

async function makeDraft(runId, btn) {
  btn.disabled = true;
  btn.textContent = "Dilekçe yazılıyor…";
  try {
    const res = await fetch(`/api/draft/${encodeURIComponent(runId)}`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || res.statusText);
    $("draft").value = body.draft;
    $("dl").href = URL.createObjectURL(new Blob([body.draft], { type: "text/plain;charset=utf-8" }));
    $("draftbox").classList.remove("hidden");
    lastRun.calls.push(body.call);
    lastRun.cost_usd = Number(lastRun.cost_usd || 0) + Number(body.call.cost_usd || 0);
    $("otari").innerHTML = renderCalls(lastRun.calls, lastRun.cost_usd) + renderGuardrails(lastRun.guardrails) + renderMcp(lastRun.mcp);
    $("draftbox").scrollIntoView({ behavior: "smooth" });
    btn.textContent = "Dilekçe hazır ↓";
    loadPersonas();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Tekrar dene";
    setStatus(err.message, true);
  }
}

const URGENCY = { "yüksek": "high", "orta": "mid", "düşük": "low" };

function fmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  const dt = new Date(+y, +m - 1, +d);
  return dt.toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric", weekday: "long" });
}

function daysLeft(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const n = Math.round((new Date(+y, +m - 1, +d) - today) / 86400000);
  if (n < 0) return `<span class="left past">${-n} gün geçti</span>`;
  if (n === 0) return '<span class="left soon">bugün son gün</span>';
  return `<span class="left ${n <= 7 ? "soon" : ""}">${n} gün kaldı</span>`;
}

function renderCard(c, calendar) {
  const used = new Set();
  const calFor = (a) => {
    const i = calendar.findIndex((e, j) => !used.has(j) && e.date === a.deadline);
    if (i < 0) return "";
    used.add(i);
    return `<a class="cal" href="${esc(calendar[i].url)}" download>📅 Takvime ekle</a>`;
  };
  const actions = (c.actions || []).map((a) => `
    <li class="action">
      <div class="action-head">
        <strong>${esc(a.title)}</strong>
        <span class="deadline">${a.deadline ? "Son gün: " + esc(fmtDate(a.deadline)) : ""} ${daysLeft(a.deadline)} ${calFor(a)}</span>
      </div>
      <p>${esc(a.detail)}</p>
      <p class="meta">${a.days ? esc(a.days) + " gün · " : ""}${esc(a.legal_basis || "")}</p>
      <p class="consequence">Yapılmazsa: ${esc(a.consequence)}</p>
    </li>`).join("");
  const warnings = (c.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const sources = (c.sources || []).filter((x) => /^https?:\/\//.test(x.url))
    .map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a> — ${esc(x.supports)}</li>`).join("");
  return `
    <div class="card-head">
      <div>
        <div class="doc-type">${esc(c.doc_type)}</div>
        <div class="issuer">${esc(c.issuer)}</div>
      </div>
      <span class="urgency ${URGENCY[c.urgency] || ""}">Aciliyet: ${esc(c.urgency)}</span>
    </div>
    <p class="summary">${esc(c.summary)}</p>
    <div class="facts">
      ${c.amount ? `<div><span>Tutar</span><strong>${esc(c.amount)}</strong></div>` : ""}
      <div><span>Tebliğ tarihi</span><strong>${esc(fmtDate(c.service_date))}</strong></div>
      ${c.reply_needed ? `<div><span>Gerekli cevap</span><strong>${esc(c.reply_type || "Evet")}</strong></div>` : ""}
    </div>
    ${c.reply_needed ? `<button id="mkdraft" class="btn primary">✍️ ${esc(c.reply_type || "Cevap")} için dilekçe taslağı hazırla</button>` : ""}
    <h3>Ne yapmalısın?</h3>
    <ol class="actions">${actions}</ol>
    ${sources ? `<h3>Kaynaklar (web'den doğrulandı)</h3><ul class="sources">${sources}</ul>` : ""}
    ${warnings ? `<div class="warnings"><strong>Dikkat</strong><ul>${warnings}</ul></div>` : ""}`;
}

const ROLE_LABELS = { analyze: "Analiz", ocr: "Görüntüden metin", classify: "Belge türü", draft: "Dilekçe", guard: "Guardrail hakemi" };

function renderCalls(calls, total) {
  const rows = calls.map((c) => `
    ${(c.failed_attempts || []).map((f) => `
    <tr class="failed">
      <td>${esc(ROLE_LABELS[c.role] || c.role)} <span class="chip">${esc(f.code || f.status)}</span></td>
      <td><code>${esc(f.model)}</code>${f.served ? `<br><small>→ ${esc(f.served)}</small>` : ""}</td>
      <td>${esc(f.provider || "")}</td>
      <td>${f.duration_ms ? (f.duration_ms / 1000).toFixed(1) + " sn" : ""}</td>
      <td>—</td>
    </tr>`).join("")}
    <tr>
      <td>${esc(ROLE_LABELS[c.role] || c.role)}${c.error ? ` <span class="chip">${esc(c.error)}</span>` : ""}</td>
      <td><code>${esc(c.model_requested)}</code>${c.model_served && c.model_served !== c.model_requested ? `<br><small>→ ${esc(c.model_served)}</small>` : ""}</td>
      <td>${esc(c.provider || "")}${c.fallback ? ` <span class="chip">Otari fallback · ${esc(c.attempts)}. deneme</span>` : ""}${c.client_fallback ? ' <span class="chip" title="Otari, araçlı stream isteklerde policy içinde yedeğe geçmiyor (bildirdik); uygulama sonraki policy\'yi denedi.">uygulama yedeği → sonraki policy</span>' : ""}</td>
      <td>${c.duration_ms ? (c.duration_ms / 1000).toFixed(1) + " sn" : ""}</td>
      <td>$${Number(c.cost_usd || 0).toFixed(4)}</td>
    </tr>
    ${(c.web_calls || []).map((w) => `<tr class="sub"><td colspan="5">${w.type === "web_fetch" ? "Sayfa okundu" : "Web araması"}: <em>${esc(w.query || w.url || "")}</em> ${w.status === "completed" ? "" : `<span class="chip">${esc(w.status)}</span>`}</td></tr>`).join("")}
    ${(c.code_runs || []).map((r) => `<tr class="sub"><td colspan="5"><details><summary>Sandbox'ta çalışan kod</summary><pre>${esc(r.code)}</pre><pre class="out">${esc(r.output)}</pre></details></td></tr>`).join("")}
  `).join("");
  return `<table class="calls"><thead><tr><th>Rol</th><th>Model</th><th>Sağlayıcı</th><th>Süre</th><th>Maliyet</th></tr></thead>
    <tbody>${rows}</tbody><tfoot><tr><td colspan="4">Toplam</td><td>$${Number(total || 0).toFixed(4)}</td></tr></tfoot></table>`;
}

function renderBlocked(b) {
  const why = b.otari?.code === "budget_exceeded"
    ? "Bu kullanıcının Otari bütçesi doldu; istek modele ulaşmadan reddedildi."
    : "Belge yapay zekâ modeline gönderilmedi.";
  $("card").innerHTML = `<div class="blocked"><strong>Analiz durduruldu</strong><p>${esc(why)}</p></div>`;
  const total = (b.calls || []).reduce((n, c) => n + Number(c.cost_usd || 0), 0);
  $("otari").innerHTML = renderCalls(b.calls || [], total) + renderGuardrails(b.guardrails);
  $("pii").innerHTML = ""; $("masked").textContent = ""; $("dates").innerHTML = "";
  $("maskedblock").classList.add("hidden"); $("datesblock").classList.add("hidden"); $("draftbox").classList.add("hidden");
  $("result").classList.remove("hidden");
}

const GUARD_LABELS = { "tr-pii": "Kişisel veri sızıntısı", "tr-injection": "Gizli talimat (prompt injection)" };

function renderGuardrails(list) {
  if (!list || !list.length) return "";
  const rows = list.map((g) => `<tr><td>${esc(GUARD_LABELS[g.profile] || g.profile)}<br><small><code>${esc(g.profile)}</code></small></td>
    <td>${g.valid === false ? '<span class="chip">engellendi</span>' : g.valid ? '<span class="chip ok">geçti</span>' : "?"}</td>
    <td>${esc(g.explanation || "")}</td></tr>`).join("");
  return `<h3>Guardrail'ler (Otari, modele göndermeden önce bizim servisimize sordu)</h3>
    <table class="calls"><thead><tr><th>Kontrol</th><th>Karar</th><th>Açıklama</th></tr></thead><tbody>${rows}</tbody></table>`;
}

const MCP_LABELS = {
  resmi_tatiller: "Resmi tatiller", is_gunu_mu: "İş günü mü?", takvim_etkinligi_olustur: "Takvim etkinliği",
};

function renderMcp(m) {
  if (!m || !m.connected) return '<p class="note">MCP sunucusu bağlı değil (tunnel kapalı).</p>';
  const rows = (m.calls || []).map((c) => {
    const args = Object.entries(c.args || {}).map(([k, v]) => `${esc(k)}=${esc(String(v).slice(0, 60))}`).join(", ");
    const res = typeof c.result === "string" ? c.result
      : c.result && c.result.sonraki_is_gunu ? `${c.result.gun}, iş günü: ${c.result.is_gunu ? "evet" : "hayır → " + c.result.sonraki_is_gunu}`
      : c.result && c.result.ics_id ? `.ics oluşturuldu (${c.result.tarih})` : "";
    return `<tr><td>${esc(MCP_LABELS[c.tool] || c.tool)}</td><td><code>${args}</code></td><td>${esc(res)}</td></tr>`;
  }).join("");
  return `<h3>MCP: sade-takvim sunucumuz (Otari çağırdı)</h3>
    <table class="calls"><thead><tr><th>Araç</th><th>Model gönderdi</th><th>Sonuç</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="3">Bu analizde MCP aracı çağrılmadı.</td></tr>'}</tbody></table>`;
}

async function loadSamples() {
  const list = await (await fetch("/api/samples")).json();
  $("samples").innerHTML = list
    .map((s, i) => `<button data-i="${i}">${esc(s.label)}<small>${esc(s.file)}</small></button>`).join("");
  $("samples").querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    const s = list[b.dataset.i];
    const blob = await (await fetch(s.url)).blob();
    analyze(new File([blob], s.file, { type: blob.type }));
  }));
}

let currentPersona = "ayse";
try { currentPersona = localStorage.getItem("sade-persona") || "ayse"; } catch {}

async function loadPersonas() {
  const list = await (await fetch("/api/personas")).json();
  $("personas").innerHTML = list.map((p) => {
    const pct = Math.min(100, (p.spent_usd / p.limit_usd) * 100);
    return `<button class="persona ${p.id === currentPersona ? "on" : ""}" data-id="${esc(p.id)}" ${p.configured ? "" : "disabled"}>
      <strong>${esc(p.name)}</strong><small>${esc(p.note)}</small>
      <span class="meter"><span style="width:${pct.toFixed(0)}%"></span></span>
      <small>$${p.spent_usd.toFixed(4)} / $${p.limit_usd.toFixed(2)} ${p.period === "daily" ? "bugün" : "bu ay"}</small>
    </button>`;
  }).join("");
  $("personas").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    currentPersona = b.dataset.id;
    try { localStorage.setItem("sade-persona", currentPersona); } catch {}
    loadPersonas();
  }));
}
loadPersonas();

$("copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("draft").value); $("copy").textContent = "Kopyalandı"; } catch { $("draft").select(); }
});

$("file").addEventListener("change", (e) => e.target.files[0] && analyze(e.target.files[0]));
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("over");
  if (e.dataTransfer.files[0]) analyze(e.dataTransfer.files[0]);
});
loadSamples();
