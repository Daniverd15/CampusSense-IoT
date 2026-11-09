"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const hora = (ms) => ms ? new Date(ms).toLocaleString("es-CO", { timeZone: "America/Bogota", hour12: false, month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "–";
const TIPOS = { real: "Real", twin: "Gemelo digital", api: "API", dataset: "Dataset" };
const PLANTILLAS = {
  intervalo: { segundos: 30 }, calibrar: { variable: "temperatura", offset: -0.5, ganancia: 1.0 },
  setpoint: { valor: 23 }, modo: { valor: "eco" }, bomba: { estado: "auto" }, consumo: { factor: 1.5 },
  limite: { kw: 6 }, extractor: { estado: "on" }, led: { estado: "on" }, velocidad: { factor: 5 }, saltar: { filas: 60 },
};
let datos = [], filtro = "todos", actual = null;
try { $("#p-clave").value = sessionStorage.getItem("clave") || ""; } catch (e) { /* sin almacenamiento */ }

function fmt(v) {
  if (typeof v !== "number") return esc(v);
  const a = Math.abs(v);
  return a >= 1000 ? v.toFixed(0) : a >= 100 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3);
}

function tarjeta(d) {
  const vars = Object.entries(d.ultimo || {}).slice(0, 6).map(([k, v]) =>
    `<div><span>${esc(k)}</span><b>${fmt(v)} <small>${esc(d.variables[k]?.unidad || "")}</small></b></div>`).join("");
  const apagado = d.estado && d.estado.encendido === 0;
  const clase = apagado ? "off" : d.en_linea ? "on" : "";
  const texto = apagado ? "apagado por comando" : d.edad_s == null ? "sin datos aún" : `hace ${Math.round(d.edad_s)} s · seq ${d.seq ?? "–"}`;
  return `<button class="disp" data-id="${esc(d.id)}">
    <div class="cab"><div><h3>${esc(d.nombre)}</h3><div class="id">${esc(d.id)}</div></div><span class="punto ${clase}" title="${esc(texto)}"></span></div>
    <div class="chips"><span class="chip ${esc(d.tipo)}">${TIPOS[d.tipo] || esc(d.tipo)}</span><span class="chip proto">${esc(d.protocolo)}</span>
      <span class="chip proto">cada ${esc(d.estado?.intervalo_s ?? d.intervalo_fabrica)} s</span></div>
    <div class="vals">${vars || "<div><span>esperando datos</span></div>"}</div>
    <div class="edad">${esc(texto)}</div></button>`;
}

function pintar() {
  const lista = datos.filter((d) => filtro === "todos" || d.tipo === filtro);
  $("#grilla").innerHTML = lista.map(tarjeta).join("");
  $("#k-linea").textContent = `${datos.filter((d) => d.en_linea).length} / ${datos.length}`;
}

async function refrescar() {
  try {
    const [d, c, a, s] = await Promise.all(["/api/dispositivos", "/api/comandos?n=40", "/api/alertas?n=40", "/api/salud"].map((u) => fetch(u).then((r) => r.json())));
    datos = d; pintar();
    $("#k-alertas").textContent = a.activas.length;
    $("#k-cmd").textContent = c.length;
    const h = s.uptime_s / 3600;
    $("#k-uptime").textContent = h >= 24 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`;
    $("#t-cmd tbody").innerHTML = c.map((x) => `<tr><td>${hora(x.ts)}</td><td>${esc(x.dispositivo)}</td><td><b>${esc(x.accion)}</b> <small>${esc(JSON.stringify(x.params))}</small></td>
      <td>${esc(x.origen)}</td><td><small>${esc(x.via)}</small></td>
      <td>${x.ack ? `<span class="${x.ack.ok ? "ok" : "mal"}">${x.ack.ok ? "OK" : "error"}</span> <small>${esc(x.ack.detalle)} · ${esc(x.ack.rtt_ms)} ms</small>` : "<small>esperando</small>"}</td></tr>`).join("") || `<tr><td colspan="6">Sin comandos todavía</td></tr>`;
    $("#t-alertas tbody").innerHTML = a.historial.map((x) => `<tr><td>${hora(x.ts)}</td><td>${esc(x.regla)}<br><small>${esc(x.dispositivo)}</small></td>
      <td class="${x.estado === "firing" ? (x.severidad === "critical" ? "mal" : "aviso") : "ok"}">${x.estado === "firing" ? "activa" : "resuelta"}</td><td>${esc(x.mensaje)}</td></tr>`).join("") || `<tr><td colspan="4">Sin alertas</td></tr>`;
    if (actual) mostrarValores(datos.find((x) => x.id === actual));
  } catch (e) { console.warn(e); }
}

async function reglas() {
  const r = await fetch("/api/reglas").then((x) => x.json());
  $("#t-reglas tbody").innerHTML = r.reglas.map((x) => `<tr><td><b>${esc(x.id)}</b></td><td>${esc(x.nombre)}</td><td>${esc(x.condicion)}</td><td>${esc(x.accion)}</td></tr>`).join("");
}

function mostrarValores(d) {
  if (!d) return;
  const filas = Object.entries(d.variables).map(([k, m]) => `<div><span>${esc(k)} <small>[${m.min}…${m.max}]</small></span><b>${d.ultimo && k in d.ultimo ? fmt(d.ultimo[k]) : "–"} ${esc(m.unidad)}</b></div>`);
  const est = Object.entries(d.estado || {}).map(([k, v]) => `<div><span>${esc(k)}</span><b>${fmt(v)}</b></div>`);
  $("#p-valores").innerHTML = filas.join("") + (est.length ? `<div style="grid-column:1/-1"><small>Estado reportado</small></div>` + est.join("") : "");
}

function abrir(id) {
  const d = datos.find((x) => x.id === id);
  if (!d) return;
  actual = id;
  $("#p-titulo").textContent = d.nombre;
  $("#p-sub").textContent = `${d.id} · ${TIPOS[d.tipo]} · ${d.protocolo.toUpperCase()} · ${d.hardware}`;
  mostrarValores(d);
  $("#p-accion").innerHTML = Object.keys(d.comandos).map((k) => `<option>${esc(k)}</option>`).join("");
  $("#p-resp").textContent = "";
  cambiarAccion();
  $("#panel").showModal();
}

function cambiarAccion() {
  const d = datos.find((x) => x.id === actual);
  const a = $("#p-accion").value;
  $("#p-ayuda").textContent = d?.comandos[a] || "";
  $("#p-params").value = JSON.stringify(PLANTILLAS[a] || {}, null, 0);
}

async function enviar() {
  let params;
  try { params = JSON.parse($("#p-params").value || "{}"); } catch (e) { $("#p-resp").textContent = "JSON inválido"; return; }
  const clave = $("#p-clave").value;
  try { sessionStorage.setItem("clave", clave); } catch (e) { /* sin almacenamiento */ }
  $("#p-resp").textContent = "enviando…";
  const r = await fetch(`/api/dispositivos/${encodeURIComponent(actual)}/comando`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Clave": clave },
    body: JSON.stringify({ accion: $("#p-accion").value, params }),
  });
  const j = await r.json().catch(() => ({}));
  $("#p-resp").textContent = `${r.status}\n${JSON.stringify(j, null, 2)}`;
  setTimeout(refrescar, 1500);
}

$("#grilla").addEventListener("click", (e) => { const b = e.target.closest(".disp"); if (b) abrir(b.dataset.id); });
$("#filtros").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  filtro = b.dataset.f; document.querySelectorAll("#filtros button").forEach((x) => x.classList.toggle("activo", x === b)); pintar();
});
$("#p-accion").addEventListener("change", cambiarAccion);
$("#p-enviar").addEventListener("click", enviar);
$("#panel").addEventListener("close", () => { actual = null; });
refrescar(); reglas();
setInterval(refrescar, 10000);
