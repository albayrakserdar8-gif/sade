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
  try {
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || res.statusText);
    render(body);
    setStatus("");
  } catch (err) {
    setStatus(err.message, true);
    $("empty").classList.remove("hidden");
  }
}

function render(r) {
  $("card").innerHTML = r.card ? renderCard(r.card) : '<p class="note">Analiz yapılamadı.</p>';
  $("otari").innerHTML = renderCalls(r.calls || [], r.cost_usd);
  const pii = Object.entries(r.pii || {});
  $("pii").innerHTML = pii.length
    ? pii.map(([k, n]) => `<span class="chip">${esc(PII_LABELS[k] || k)} × ${n} maskelendi</span>`).join("")
    : '<span class="chip ok">kişisel veri bulunmadı</span>';
  $("masked").textContent = r.masked_text;
  $("dates").innerHTML = (r.dates || [])
    .map((d) => `<li><strong>${esc(d.text)}</strong> — ${esc(d.context || "")}</li>`).join("");
  $("result").classList.remove("hidden");
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

function renderCard(c) {
  const actions = (c.actions || []).map((a) => `
    <li class="action">
      <div class="action-head">
        <strong>${esc(a.title)}</strong>
        <span class="deadline">${a.deadline ? "Son gün: " + esc(fmtDate(a.deadline)) : ""} ${daysLeft(a.deadline)}</span>
      </div>
      <p>${esc(a.detail)}</p>
      <p class="meta">${a.days ? esc(a.days) + " gün · " : ""}${esc(a.legal_basis || "")}</p>
      <p class="consequence">Yapılmazsa: ${esc(a.consequence)}</p>
    </li>`).join("");
  const warnings = (c.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
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
    <h3>Ne yapmalısın?</h3>
    <ol class="actions">${actions}</ol>
    ${warnings ? `<div class="warnings"><strong>Dikkat</strong><ul>${warnings}</ul></div>` : ""}`;
}

const ROLE_LABELS = { analyze: "Analiz", ocr: "Görüntüden metin", classify: "Belge türü", draft: "Dilekçe", guard: "Güvenlik" };

function renderCalls(calls, total) {
  const rows = calls.map((c) => `
    <tr>
      <td>${esc(ROLE_LABELS[c.role] || c.role)}${c.error ? ` <span class="chip">${esc(c.error)}</span>` : ""}</td>
      <td><code>${esc(c.model_requested)}</code>${c.model_served && c.model_served !== c.model_requested ? `<br><small>→ ${esc(c.model_served)}</small>` : ""}</td>
      <td>${esc(c.provider || "")}${c.fallback ? ' <span class="chip">fallback</span>' : ""}</td>
      <td>${c.duration_ms ? (c.duration_ms / 1000).toFixed(1) + " sn" : ""}</td>
      <td>$${Number(c.cost_usd || 0).toFixed(4)}</td>
    </tr>
    ${(c.code_runs || []).map((r) => `<tr class="sub"><td colspan="5"><details><summary>Sandbox'ta çalışan kod</summary><pre>${esc(r.code)}</pre><pre class="out">${esc(r.output)}</pre></details></td></tr>`).join("")}
  `).join("");
  return `<table class="calls"><thead><tr><th>Rol</th><th>Model</th><th>Sağlayıcı</th><th>Süre</th><th>Maliyet</th></tr></thead>
    <tbody>${rows}</tbody><tfoot><tr><td colspan="4">Toplam</td><td>$${Number(total || 0).toFixed(4)}</td></tr></tfoot></table>`;
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

$("file").addEventListener("change", (e) => e.target.files[0] && analyze(e.target.files[0]));
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("over");
  if (e.dataTransfer.files[0]) analyze(e.dataTransfer.files[0]);
});
loadSamples();
