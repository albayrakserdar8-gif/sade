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
  setStatus("Belge okunuyor…");
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
  $("card").innerHTML = r.card ? "" : '<p class="note">Yapay zekâ analizi henüz bağlı değil.</p>';
  const pii = Object.entries(r.pii || {});
  $("pii").innerHTML = pii.length
    ? pii.map(([k, n]) => `<span class="chip">${esc(PII_LABELS[k] || k)} × ${n} maskelendi</span>`).join("")
    : '<span class="chip ok">kişisel veri bulunmadı</span>';
  $("masked").textContent = r.masked_text;
  $("dates").innerHTML = (r.dates || [])
    .map((d) => `<li><strong>${esc(d.text)}</strong> — ${esc(d.context || "")}</li>`).join("");
  $("result").classList.remove("hidden");
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
