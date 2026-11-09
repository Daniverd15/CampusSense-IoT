"use strict";
/* CampusSense UNAB — centro de control en tiempo real (SSE /api/stream) */

// ------------------------------------------------------------------ utilidades
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TZ = "America/Bogota";
const hora = (ms, seg = true) => ms ? new Date(ms).toLocaleTimeString("es-CO", { timeZone: TZ, hour12: false, hour: "2-digit", minute: "2-digit", ...(seg ? { second: "2-digit" } : {}) }) : "–";
const fecha = (ms) => ms ? new Date(ms).toLocaleString("es-CO", { timeZone: TZ, hour12: false, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function fmt(v, dec) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (typeof v !== "number") return esc(v);
  if (dec !== undefined) return v.toLocaleString("es-CO", { maximumFractionDigits: dec, minimumFractionDigits: dec });
  const a = Math.abs(v);
  const d = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 1 : a >= 1 ? 2 : 3;
  return v.toLocaleString("es-CO", { maximumFractionDigits: d });
}
const fmtMs = (ms) => (ms == null ? "–" : ms >= 1000 ? `${fmt(ms / 1000, 1)} s` : `${fmt(ms, 0)} ms`);
function fmtVar(d, k, v) {
  if (v === null || v === undefined) return "–";
  const u = d.variables[k]?.unidad || "";
  if (k === "modo") return MODOS[v] ?? fmt(v);
  if (u === "on/off" || u === "0/1") return v ? "ON" : "OFF";
  return fmt(v);
}
function unidadCorta(d, k) { const u = d.variables[k]?.unidad || ""; return u === "on/off" || u === "0/1" || k === "modo" || u.length > 8 ? "" : u; }
const hace = (ms) => {
  if (!ms) return "sin datos";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  return s < 60 ? `hace ${Math.round(s)} s` : s < 3600 ? `hace ${Math.round(s / 60)} min` : `hace ${(s / 3600).toFixed(1)} h`;
};
function guardar(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* sin almacenamiento */ } }
function leer(k) { try { return sessionStorage.getItem(k) || ""; } catch (e) { return ""; } }

const TIPOS = { real: "Real", twin: "Gemelo digital", api: "API", dataset: "Dataset" };
const COLOR_TIPO = { real: "--real", twin: "--twin", api: "--api", dataset: "--dataset" };
// variable que se muestra en grande en cada tarjeta
const PRINCIPAL = {
  "aula-101": "co2", "lab-quimica": "pm25", "medidor-bloque-a": "potencia", "esp32-wokwi": "temperatura",
  "twin-hvac-aula101": "temp_modelo", "twin-tanque-agua": "nivel", "twin-panel-solar": "potencia", "api-clima-unab": "temperatura",
  "api-aire-unab": "indice_global", "api-bus-ruta1": "velocidad", "ds-ocupacion-uci": "co2", "ds-aire-uci": "no2",
};
const MODOS = ["apagado", "auto", "ventilación", "eco"];
const DESC_PROTO = {
  mqtt: ["MQTT 3.1.1", "Mosquitto · QoS 1, sesión persistente y LWT. Retroceso: SUBSCRIBE campus/cmd/<id>."],
  amqp: ["AMQP 0-9-1", "RabbitMQ · exchange topic + publisher confirms. Retroceso: cola durable cmd.<id>."],
  stomp: ["STOMP 1.2", "Plugin STOMP de RabbitMQ, mismo exchange que AMQP. Retroceso: SUBSCRIBE /exchange/campus.cmd/<id>."],
  coap: ["CoAP", "UDP, POST confirmable al ingestor. Retroceso: cada gemelo expone POST /cmd (2.04 = ACK)."],
  http: ["HTTP REST", "POST /api/ingest con token. Retroceso: los comandos viajan en la respuesta del siguiente POST."],
};

const estado = {
  disp: {}, orden: [], filtro: "todos", buscar: "", spark: {}, consolaFiltro: "todo", pausa: false,
  datosVentana: [], abiertos: null, charts: [], rango: 24, pendientes: {}, conectadoDesde: 0, protocolos: {}, alertas: { activas: [], historial: [] },
  reglas: [], comandos: [],
};

// ------------------------------------------------------------------ tema
$("#tema").addEventListener("click", () => {
  const actual = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const nuevo = actual === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento */ }
  dibujarFlujo(); pintarGrilla(); dibujarKpiSpark();
  if (estado.abiertos) cargarGraficas();
});

// ------------------------------------------------------------------ toasts
function toast(titulo, detalle = "", tipo = "ok", ms = 4500) {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.innerHTML = `<span class="ico">${tipo === "ok" ? "✅" : tipo === "mal" ? "⛔" : tipo === "cmd" ? "📡" : "🔔"}</span><div><b>${esc(titulo)}</b><small>${esc(detalle)}</small></div>`;
  $("#toasts").prepend(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 320); }, ms);
  return t;
}

// ------------------------------------------------------------------ API
async function api(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) throw Object.assign(new Error(`${r.status}`), { status: r.status, cuerpo: await r.json().catch(() => ({})) });
  return r.json();
}

// ================================================================== FLUJO ANIMADO
const F = {
  grupos: { real: [20, 28], twin: [20, 128], api: [20, 228], dataset: [20, 328] },
  protos: { mqtt: 52, amqp: 136, stomp: 220, coap: 304, http: 388 },
  brokers: { mqtt: ["Mosquitto", "broker MQTT", 22, 62], amqp: ["RabbitMQ", "AMQP + STOMP", 116, 124], coap: ["Servidor CoAP", "UDP 5683", 272, 62], http: ["Endpoint HTTP", "/api/ingest", 356, 62] },
  ingestor: [720, 130, 165, 70], apiBox: [720, 300, 165, 70], influx: [930, 130, 125, 70], front: [1090, 90, 95, 70], grafana: [1090, 200, 95, 70],
  cuentas: { mqtt: [], amqp: [], stomp: [], coap: [], http: [] }, activos: 0,
};
const brokerDe = (p) => (p === "stomp" ? "amqp" : p);
function yBroker(p) { const b = F.brokers[brokerDe(p)]; return p === "amqp" ? b[2] + 38 : p === "stomp" ? b[2] + 86 : b[2] + b[3] / 2; }

function dibujarFlujo() {
  const s = $("#flujo-svg");
  const n = (x, y, w, h, t, sub, cls = "", estilo = "") =>
    `<g class="nodo ${cls}" style="${estilo}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12"/><text x="${x + 14}" y="${y + 26}" class="titulo">${esc(t)}</text>${sub ? `<text x="${x + 14}" y="${y + 46}" class="sub">${esc(sub)}</text>` : ""}</g>`;
  let h = "";
  [["dispositivos", 20], ["protocolo", 296], ["broker", 470], ["procesamiento", 720], ["TSDB", 930], ["visualización", 1090]].forEach(([t, x]) => { h += `<text x="${x}" y="14" class="col-tit">${t}</text>`; });
  // rutas fijas
  const rutas = [];
  for (const [tipo, [gx, gy]] of Object.entries(F.grupos)) {
    for (const p of protosDeTipo(tipo)) rutas.push([[gx + 210, gy + 40], [330 - 26, F.protos[p]]]);
  }
  for (const p of Object.keys(F.protos)) rutas.push([[356, F.protos[p]], [470, yBroker(p)]]);
  for (const p of ["mqtt", "amqp", "coap"]) rutas.push([[680, yBroker(p)], [F.ingestor[0], F.ingestor[1] + 35]]);
  rutas.push([[680, yBroker("http")], [F.apiBox[0], F.apiBox[1] + 35]]);
  rutas.push([[F.ingestor[0] + F.ingestor[2], F.ingestor[1] + 35], [F.influx[0], F.influx[1] + 35]]);
  rutas.push([[F.apiBox[0] + F.apiBox[2], F.apiBox[1] + 35], [F.influx[0], F.influx[1] + 55]]);
  rutas.push([[F.influx[0] + F.influx[2], F.influx[1] + 25], [F.front[0], F.front[1] + 35]]);
  rutas.push([[F.influx[0] + F.influx[2], F.influx[1] + 45], [F.grafana[0], F.grafana[1] + 35]]);
  rutas.push([[F.apiBox[0] + 80, F.apiBox[1]], [F.ingestor[0] + 80, F.ingestor[1] + 70]]);
  h += rutas.map((r) => `<path class="ruta" d="M${r[0][0]},${r[0][1]} C${(r[0][0] + r[1][0]) / 2},${r[0][1]} ${(r[0][0] + r[1][0]) / 2},${r[1][1]} ${r[1][0]},${r[1][1]}"/>`).join("");
  // grupos de dispositivos
  for (const [tipo, [gx, gy]] of Object.entries(F.grupos)) {
    const ids = estado.orden.filter((id) => estado.disp[id].tipo === tipo);
    h += `<g class="nodo grupo" id="g-${tipo}" style="--c:var(${COLOR_TIPO[tipo]})"><rect x="${gx}" y="${gy}" width="210" height="80" rx="12"/>
      <text x="${gx + 14}" y="${gy + 24}" class="titulo">${TIPOS[tipo]} · ${ids.length}</text>
      ${ids.slice(0, 4).map((id, i) => `<text x="${gx + 14 + (i % 2) * 98}" y="${gy + 46 + Math.floor(i / 2) * 18}" class="sub">${esc(id.length > 14 ? id.slice(0, 13) + "…" : id)}</text>`).join("")}</g>`;
  }
  for (const [p, y] of Object.entries(F.protos)) {
    h += `<g class="proto" id="p-${p}"><circle cx="330" cy="${y}" r="27"/><text x="330" y="${y + 1}">${p.toUpperCase()}</text><text x="330" y="${y + 14}" class="cuenta" id="pc-${p}">0/min</text></g>`;
  }
  for (const [k, [t, sub, y, hh]] of Object.entries(F.brokers)) h += n(470, y, 210, hh, t, sub, "broker", "");
  h += `<g class="nodo"><text x="484" y="${yBroker("amqp") + 30}" class="sub">exchange campus.tele</text><text x="484" y="${yBroker("stomp") + 4}" class="sub">STOMP → mismo exchange</text></g>`;
  h += n(...F.ingestor, "Ingestor", "valida → InfluxDB");
  h += n(...F.apiBox, "API + reglas", "retroceso · R1–R7");
  h += n(...F.influx, "InfluxDB", "bucket campus");
  h += n(...F.front, "Front", "este panel");
  h += n(...F.grafana, "Grafana", "5 dashboards");
  h += `<g id="paquetes"></g>`;
  s.innerHTML = h;
  actualizarCuentasProto();
}
function protosDeTipo(tipo) { return [...new Set(estado.orden.filter((id) => estado.disp[id].tipo === tipo).map((id) => estado.disp[id].protocolo))]; }

function curva(a, b) { const mx = (a[0] + b[0]) / 2; return [a, [mx, a[1]], [mx, b[1]], b]; }
function bezier(p, t) {
  const u = 1 - t;
  return [u * u * u * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t * t * t * p[3][0],
    u * u * u * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t * t * t * p[3][1]];
}
function animar(tramos, color, dur = 1700, radio = 4.2) {
  if (F.activos > 70 || document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const g = $("#paquetes"); if (!g) return;
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("r", radio); c.setAttribute("class", "paquete"); c.style.fill = color; c.style.color = color;
  g.appendChild(c); F.activos++;
  const curvas = tramos.map(([a, b]) => curva(a, b));
  const t0 = performance.now();
  (function paso(ahora) {
    const t = Math.min(1, (ahora - t0) / dur);
    const k = Math.min(curvas.length - 1, Math.floor(t * curvas.length));
    const [x, y] = bezier(curvas[k], t * curvas.length - k);
    c.setAttribute("cx", x); c.setAttribute("cy", y);
    if (t < 1) requestAnimationFrame(paso); else { c.remove(); F.activos--; }
  })(t0);
}
function latido(sel) { const r = $(sel + " rect, " + sel + " circle"); if (!r) return; r.classList.remove("latido"); void r.getBBox(); r.classList.add("latido"); }

function animarDato(ev) {
  const d = estado.disp[ev.id]; if (!d) return;
  const p = d.protocolo, tipo = d.tipo, [gx, gy] = F.grupos[tipo];
  const color = css(COLOR_TIPO[tipo]);
  const yb = yBroker(p);
  const destino = p === "http" ? [F.apiBox[0], F.apiBox[1] + 35] : [F.ingestor[0], F.ingestor[1] + 35];
  const desde = p === "http" ? [F.apiBox[0] + F.apiBox[2], F.apiBox[1] + 35] : [F.ingestor[0] + F.ingestor[2], F.ingestor[1] + 35];
  animar([[[gx + 210, gy + 40], [303, F.protos[p]]], [[357, F.protos[p]], [470, yb]], [[680, yb], destino], [desde, [F.influx[0], F.influx[1] + 35]]], color);
  latido(`#g-${tipo}`);
  setTimeout(() => latido(`#p-${p}`), 400);
}
function animarCmd(ev) {
  const d = estado.disp[ev.dispositivo || ev.id]; if (!d) return;
  const p = d.protocolo, [gx, gy] = F.grupos[d.tipo], yb = yBroker(p);
  animar([[[F.apiBox[0], F.apiBox[1] + 35], [680, yb]], [[470, yb], [357, F.protos[p]]], [[303, F.protos[p]], [gx + 210, gy + 40]]], css("--cmd"), 1500, 5.5);
}
function actualizarCuentasProto() {
  const lim = Date.now() - 60000;
  for (const p of Object.keys(F.cuentas)) {
    F.cuentas[p] = F.cuentas[p].filter((t) => t > lim);
    const el = $(`#pc-${p}`);
    const base = estado.conectadoDesde && Date.now() - estado.conectadoDesde > 60000 ? F.cuentas[p].length : Math.max(F.cuentas[p].length, Math.round(estado.protocolos[p]?.msg_min || 0));
    if (el) el.textContent = `${base}/min`;
  }
}

// ================================================================== DISPOSITIVOS
function color(d) { return `var(${COLOR_TIPO[d.tipo]})`; }
function sparkSvg(id, d) {
  const pts = estado.spark[id] || [];
  if (pts.length < 2) return `<svg viewBox="0 0 120 40"></svg>`;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = (x) => ((x - x0) / (x1 - x0 || 1)) * 118 + 1, Y = (y) => 37 - ((y - y0) / (y1 - y0 || 1)) * 33;
  const linea = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
  return `<svg viewBox="0 0 120 40" aria-hidden="true" style="--c:${color(d)}"><path class="spark-area" d="${linea}L119,40L1,40Z"/><path class="spark-linea" d="${linea}"/></svg>`;
}
function enLinea(d) {
  if (!d.ts) return false;
  const lim = Math.max(3 * (d.estado?.intervalo_s ?? d.intervalo_fabrica), 180);
  return (Date.now() - d.ts) / 1000 <= lim && d.estado?.encendido !== 0;
}
function tarjeta(id) {
  const d = estado.disp[id];
  const pv = PRINCIPAL[id];
  const u = d.ultimo || {};
  const apagado = d.estado?.encendido === 0;
  const cls = apagado ? "off" : enLinea(d) ? "on" : "";
  const otros = Object.keys(d.variables).filter((k) => k !== pv).slice(0, 4)
    .map((k) => `<div><span>${esc(k.replace(/_/g, " "))}</span><b>${fmtVar(d, k, u[k])} <small>${esc(unidadCorta(d, k))}</small></b></div>`).join("");
  return `<button class="disp" data-id="${esc(id)}" style="--c:${color(d)}">
    <div class="disp-cab"><div><h3>${esc(d.nombre)}</h3><div class="id">${esc(id)}</div></div><span class="estado-pt ${cls}" title="${apagado ? "apagado por comando" : cls ? "en línea" : "sin datos recientes"}"></span></div>
    <div class="etqs"><span class="etq tipo">${TIPOS[d.tipo]}</span><span class="etq">${esc(d.protocolo)}</span><span class="etq">${esc(d.estado?.intervalo_s ?? d.intervalo_fabrica)} s</span>${apagado ? `<span class="etq" style="color:var(--mal)">apagado</span>` : ""}</div>
    <div class="principal"><div><div class="valor">${fmtVar(d, pv, u[pv])}<small>${esc(unidadCorta(d, pv))}</small></div><span class="var">${esc(pv.replace(/_/g, " "))}</span></div>${sparkSvg(id, d)}</div>
    <div class="secund">${otros}</div>
    <div class="pie"><span data-edad="${id}">${apagado ? "apagado por comando" : etiquetaEdad(id, d)}</span><span>seq ${esc(d.seq ?? "–")}</span></div>
  </button>`;
}
function etiquetaEdad(id, d) {
  return id === "esp32-wokwi" && !enLinea(d) ? `fuera de sesión · ${hace(d.ts)}` : hace(d.ts);
}
function visibles() {
  const q = estado.buscar.toLowerCase();
  return estado.orden.filter((id) => (estado.filtro === "todos" || estado.disp[id].tipo === estado.filtro) &&
    (!q || id.includes(q) || estado.disp[id].nombre.toLowerCase().includes(q) || estado.disp[id].protocolo.includes(q)));
}
function pintarGrilla() {
  $("#grilla").innerHTML = visibles().map(tarjeta).join("") || `<p class="vacio">Ningún dispositivo coincide.</p>`;
  const cuenta = (t) => estado.orden.filter((id) => t === "todos" || estado.disp[id].tipo === t).length;
  ["todos", "real", "twin", "api", "dataset"].forEach((t) => { $(`#c-${t}`).textContent = cuenta(t); });
}
function repintarTarjeta(id, flash) {
  const el = $(`.disp[data-id="${CSS.escape(id)}"]`);
  if (!el) return;
  const tmp = document.createElement("div"); tmp.innerHTML = tarjeta(id);
  const nuevo = tmp.firstElementChild;
  if (flash) nuevo.classList.add("flash");
  el.replaceWith(nuevo);
}
$("#grilla").addEventListener("click", (e) => { const b = e.target.closest(".disp"); if (b) abrirPanel(b.dataset.id); });
$("#filtros").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  estado.filtro = b.dataset.f; $$("#filtros button").forEach((x) => x.classList.toggle("activo", x === b)); pintarGrilla();
});
$("#buscar").addEventListener("input", (e) => { estado.buscar = e.target.value.trim(); pintarGrilla(); });

async function cargarDispositivos() {
  const lista = await api("/api/dispositivos");
  for (const d of lista) {
    const prev = estado.disp[d.id];
    estado.disp[d.id] = prev && prev.ts > (d.ts || 0) ? { ...d, ultimo: prev.ultimo, ts: prev.ts, seq: prev.seq, estado: prev.estado } : d;
  }
  if (!estado.orden.length) estado.orden = lista.map((d) => d.id);
}
async function cargarSparks() {
  await Promise.all(estado.orden.map(async (id) => {
    try {
      const h = await api(`/api/historia/${id}?horas=6&puntos=60`);
      estado.spark[id] = (h.series[PRINCIPAL[id]] || []).slice(-60);
    } catch (e) { estado.spark[id] = []; }
  }));
  pintarGrilla();
}

// ================================================================== KPIs
function kpis() {
  const lin = estado.orden.filter((id) => enLinea(estado.disp[id])).length;
  $("#k-linea").textContent = lin;
  $("#k-anillo").style.setProperty("--p", (lin / Math.max(1, estado.orden.length)) * 100);
  const vivo = estado.conectadoDesde && Date.now() - estado.conectadoDesde > 60000;
  const porMin = vivo ? estado.datosVentana.filter((t) => t > Date.now() - 60000).length
    : Object.values(estado.protocolos).reduce((s, p) => s + (p.msg_min || 0), 0);
  $("#k-msg").textContent = fmt(porMin, porMin < 100 ? 1 : 0);
  const act = estado.alertas.activas || [];
  $("#k-alertas").textContent = act.length;
  $("#k-alertas-nota").textContent = act.length ? act.map((a) => a.regla.split(" ")[0]).join(" · ") : "todo en orden";
  $("#k-alertas").style.color = act.length ? "var(--mal)" : "";
  $("#k-cmd").textContent = estado.comandos.length;
  const ult = estado.comandos[0];
  $("#k-cmd-nota").textContent = ult ? `último: ${ult.accion} → ${ult.dispositivo}` : "ninguno aún";
}
function dibujarKpiSpark() {
  const cv = $("#k-spark"); const w = cv.clientWidth, h = 42;
  cv.width = w * devicePixelRatio; cv.height = h * devicePixelRatio;
  const ctx = cv.getContext("2d"); ctx.scale(devicePixelRatio, devicePixelRatio);
  const ahora = Date.now(), cubos = new Array(30).fill(0);
  for (const t of estado.datosVentana) { const k = Math.floor((ahora - t) / 10000); if (k < 30) cubos[29 - k]++; }
  const mx = Math.max(1, ...cubos), col = css("--acento");
  ctx.beginPath();
  cubos.forEach((v, i) => { const x = (i / 29) * w, y = h - 4 - (v / mx) * (h - 10); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = col; ctx.lineWidth = 1.8; ctx.stroke();
  ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath(); ctx.globalAlpha = .14; ctx.fillStyle = col; ctx.fill();
}

// ================================================================== CONSOLA
function consola(tipo, texto) {
  if (estado.pausa) return;
  const grupo = tipo === "ack" ? "cmd" : tipo === "conexion" ? "alerta" : tipo;
  if (estado.consolaFiltro !== "todo" && estado.consolaFiltro !== grupo) return;
  const li = document.createElement("li");
  li.innerHTML = `<time>${hora(Date.now())}</time><span class="tag ${tipo}">${tipo === "cmd" ? "comando" : tipo}</span><span class="txt">${texto}</span>`;
  const ol = $("#consola"); ol.prepend(li);
  while (ol.children.length > 160) ol.lastChild.remove();
}
$("#c-filtros").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.id === "pausa") { estado.pausa = !estado.pausa; b.textContent = estado.pausa ? "▶" : "❚❚"; b.classList.toggle("activo", estado.pausa); return; }
  estado.consolaFiltro = b.dataset.c; $$("#c-filtros button[data-c]").forEach((x) => x.classList.toggle("activo", x === b));
  $("#consola").innerHTML = "";
});
function resumenValores(v, n = 3) { return Object.entries(v || {}).slice(0, n).map(([k, x]) => `${esc(k)}=${fmt(x)}`).join(" "); }

// ================================================================== STREAM SSE
function conectarStream() {
  const es = new EventSource("/api/stream");
  es.onopen = () => { $("#vivo").classList.add("ok"); estado.conectadoDesde = estado.conectadoDesde || Date.now(); };
  es.onerror = () => { $("#vivo").classList.remove("ok"); $("#vivo-txt").textContent = "reconectando…"; };
  es.onmessage = (m) => { try { manejar(JSON.parse(m.data)); } catch (e) { console.warn(e); } };
}
let pendRefresco = null;
const acksVistos = new Set();
function refrescarLuego() { clearTimeout(pendRefresco); pendRefresco = setTimeout(() => { cargarComandos(); cargarAlertas(); }, 900); }

function manejar(ev) {
  if (ev.t === "dato") {
    const d = estado.disp[ev.id]; if (!d) return;
    d.ultimo = ev.v; d.ts = ev.ts; d.seq = ev.seq; if (ev.estado) d.estado = ev.estado;
    const pv = PRINCIPAL[ev.id];
    if (ev.v && pv in ev.v) { (estado.spark[ev.id] ||= []).push([ev.ts, ev.v[pv]]); if (estado.spark[ev.id].length > 80) estado.spark[ev.id].shift(); }
    estado.datosVentana.push(Date.now()); F.cuentas[d.protocolo]?.push(Date.now());
    if (estado.datosVentana.length > 4000) estado.datosVentana = estado.datosVentana.slice(-3000);
    animarDato(ev); repintarTarjeta(ev.id, true);
    consola("dato", `<b>${esc(ev.id)}</b> <i>${esc(d.protocolo)}</i> ${resumenValores(ev.v)} <i>· ${fmt(ev.lat_ms, 0)} ms</i>`);
    actualizarMapa(ev.id);
    if (estado.abiertos === ev.id) { pintarEstadoPanel(); empujarGraficas(ev); }
  } else if (ev.t === "cmd") {
    animarCmd(ev);
    consola("cmd", `<b>${esc(ev.accion)}</b> → ${esc(ev.dispositivo)} <i>${esc(JSON.stringify(ev.params))} · ${esc(ev.origen)} · ${esc(ev.protocolo)}</i>`);
    if (String(ev.origen).startsWith("regla")) toast(`Regla automática: ${ev.accion}`, `${ev.origen} → ${ev.dispositivo} ${JSON.stringify(ev.params)}`, "cmd", 7000);
    refrescarLuego();
  } else if (ev.t === "ack") {
    if (ev.cmd_id && acksVistos.has(ev.cmd_id)) return;          // CoAP: llega en la respuesta y por el bus
    if (ev.cmd_id) { acksVistos.add(ev.cmd_id); if (acksVistos.size > 500) acksVistos.clear(); }
    const d = estado.disp[ev.id]; if (d && ev.estado) d.estado = ev.estado;
    consola("ack", `<b>${esc(ev.id)}</b> ${ev.ok ? "✓" : "✗"} ${esc(ev.accion)}: ${esc(ev.detalle)} <i>· RTT ${fmtMs(ev.rtt_ms)}</i>`);
    const p = estado.pendientes[ev.cmd_id];
    if (p) { delete estado.pendientes[ev.cmd_id]; toast(`${ev.ok ? "ACK" : "Rechazado"}: ${ev.accion}`, `${ev.id} · ${ev.detalle} · ${fmtMs(ev.rtt_ms)}`, ev.ok ? "ok" : "mal"); }
    if (d) repintarTarjeta(ev.id, false);
    if (estado.abiertos === ev.id) { pintarEstadoPanel(); pintarControles(); }
    refrescarLuego();
  } else if (ev.t === "alerta") {
    consola("alerta", `<b>${esc(ev.regla)}</b> ${ev.estado === "firing" ? "DISPARADA" : "resuelta"} · ${esc(ev.dispositivo)} <i>${esc(ev.mensaje)}</i>`);
    toast(`${ev.estado === "firing" ? "Alerta" : "Resuelta"}: ${ev.regla}`, `${ev.dispositivo} · ${ev.mensaje}`, ev.estado === "firing" ? "mal" : "ok", 7000);
    refrescarLuego();
  } else if (ev.t === "conexion") {
    consola("conexion", `<b>${esc(ev.id)}</b> ${ev.conectado ? "se conectó al broker" : "se desconectó (LWT)"}`);
  }
}

// ================================================================== MAPA
const UBIC = {
  "aula-101": [7.11712, -73.10548], "twin-hvac-aula101": [7.11718, -73.10556], "lab-quimica": [7.11680, -73.10498],
  "medidor-bloque-a": [7.11748, -73.10505], "twin-panel-solar": [7.11740, -73.10488], "twin-tanque-agua": [7.11765, -73.10575],
  "api-clima-unab": [7.11703, -73.10534], "api-aire-unab": [7.11696, -73.10522],
};
let mapa, marcas = {}, bus, rastro;
function iniciarMapa() {
  if (!window.L) { $("#mapa").innerHTML = `<p class="vacio">No se pudo cargar el mapa.</p>`; return; }
  mapa = L.map("mapa", { zoomControl: true, scrollWheelZoom: false, attributionControl: true }).setView([7.1172, -73.1053], 17);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
  for (const [id, ll] of Object.entries(UBIC)) {
    const d = estado.disp[id]; if (!d) continue;
    const icono = L.divIcon({ className: "", html: `<div class="marcador" style="--c:${css(COLOR_TIPO[d.tipo])}"></div>`, iconSize: [16, 16], iconAnchor: [8, 8] });
    marcas[id] = L.marker(ll, { icon: icono, title: d.nombre }).addTo(mapa).bindPopup("");
    marcas[id].on("click", () => marcas[id].setPopupContent(popup(id)));
  }
  rastro = L.polyline([], { color: css("--cmd"), weight: 3, opacity: .75, dashArray: "6 6" }).addTo(mapa);
  bus = L.marker([7.1123, -73.1052], { icon: L.divIcon({ className: "", html: `<div class="marcador bus">🚌</div>`, iconSize: [26, 26], iconAnchor: [13, 13] }), zIndexOffset: 1000 })
    .addTo(mapa).bindPopup("");
  bus.on("click", () => bus.setPopupContent(popup("api-bus-ruta1")));
  cargarRastro();
}
function popup(id) {
  const d = estado.disp[id];
  return `<b>${esc(d.nombre)}</b><br><small>${esc(id)} · ${esc(d.protocolo)}</small><br>${Object.entries(d.ultimo || {}).slice(0, 6).map(([k, v]) => `${esc(k)}: <b>${fmt(v)}</b> ${esc(d.variables[k]?.unidad || "")}`).join("<br>")}<br><small>${hace(d.ts)}</small>`;
}
async function cargarRastro() {
  try {
    const h = await api("/api/historia/api-bus-ruta1?horas=12&puntos=240");
    const lat = h.series.lat || [], lon = new Map((h.series.lon || []).map(([t, v]) => [t, v]));
    const pts = lat.filter(([t]) => lon.has(t)).map(([t, v]) => [v, lon.get(t)]);
    rastro.setLatLngs(pts);
    actualizarMapa("api-bus-ruta1");
    if (pts.length) mapa.fitBounds(L.latLngBounds([...pts, ...Object.values(UBIC)]).pad(0.15), { maxZoom: 17 });
  } catch (e) { /* sin datos */ }
}
function actualizarMapa(id) {
  if (!mapa) return;
  const d = estado.disp[id];
  const el = marcas[id]?.getElement()?.querySelector(".marcador");
  if (el) { el.classList.remove("pulso"); void el.offsetWidth; el.classList.add("pulso"); }
  if (id === "api-bus-ruta1" && d?.ultimo?.lat) {
    const ll = [d.ultimo.lat, d.ultimo.lon];
    bus.setLatLng(ll);
    const pts = rastro.getLatLngs(); const ult = pts[pts.length - 1];
    if (!ult || ult.lat !== ll[0] || ult.lng !== ll[1]) rastro.addLatLng(ll);
    $("#bus-estado").textContent = `bus: ${fmt(d.ultimo.velocidad, 0)} km/h · ${fmt(d.ultimo.distancia_campus, 2)} km del campus`;
  }
}

// ================================================================== PROTOCOLOS
async function cargarProtocolos() {
  try { estado.protocolos = await api("/api/protocolos"); } catch (e) { return; }
  const maxRtt = Math.max(1, ...Object.values(estado.protocolos).map((p) => Math.log10(1 + (p.rtt_ms || 0))));
  $("#protos").innerHTML = Object.entries(DESC_PROTO).map(([p, [nombre, desc]]) => {
    const s = estado.protocolos[p] || {};
    return `<article class="proto-t"><div><h3>${nombre}</h3><p class="desc">${esc(desc)}</p></div>
      <div class="metricas"><div><b>${fmt(s.msg_min, 1)}</b><small>msg/min</small></div><div><b>${fmt(s.latencia_ms, 0)}</b><small>ms subida</small></div><div><b>${s.rtt_ms == null ? "–" : s.rtt_ms >= 1000 ? fmt(s.rtt_ms / 1000, 1) : fmt(s.rtt_ms, 0)}</b><small>${s.rtt_ms >= 1000 ? "s" : "ms"} ACK</small></div></div>
      <div class="barra-rtt" title="Tiempo de ida y vuelta del ACK (escala logarítmica)"><i style="width:${(Math.log10(1 + (s.rtt_ms || 0)) / maxRtt) * 100}%"></i></div>
      <div class="devs">${(s.dispositivos || []).map((d) => `<span>${esc(d)}</span>`).join("")}</div></article>`;
  }).join("");
  kpis();
}

// ================================================================== REGLAS, ALERTAS, COMANDOS
async function cargarAlertas() {
  try { estado.alertas = await api("/api/alertas?n=40"); } catch (e) { return; }
  const act = estado.alertas.activas.map((a) => a.regla.split(" ")[0]);
  $("#l-reglas").innerHTML = estado.reglas.map((r) => {
    const on = act.includes(r.id);
    return `<li class="${on ? "activa" : ""}"><span class="rid">${esc(r.id)}</span><div><b>${esc(r.nombre)}</b><p>${esc(r.condicion)} → ${esc(r.accion)}</p></div><span class="estado">${on ? "disparada" : "vigilando"}</span></li>`;
  }).join("");
  $("#l-alertas").innerHTML = estado.alertas.historial.map((a) => `<li class="${a.estado === "firing" ? "firing" : ""} ${esc(a.severidad)}"><i></i><div>
      <b>${esc(a.regla)}</b> <time>${fecha(a.ts)}</time><p>${esc(a.dispositivo)} · ${esc(a.mensaje)} <small>(${esc(a.origen)})</small></p></div></li>`).join("")
    || `<li class="vacio">Sin alertas en el periodo. Las reglas siguen vigilando.</li>`;
  kpis();
}
async function cargarReglas() { try { estado.reglas = (await api("/api/reglas")).reglas; } catch (e) { /* */ } }
async function cargarComandos() {
  try { estado.comandos = await api("/api/comandos?n=80"); } catch (e) { return; }
  $("#t-cmd tbody").innerHTML = estado.comandos.map((c) => `<tr><td class="mono">${fecha(c.ts)}</td><td><b>${esc(c.dispositivo)}</b><br><small>${esc(c.protocolo)}</small></td>
    <td><b>${esc(c.accion)}</b><br><small class="mono">${esc(JSON.stringify(c.params))}</small></td><td>${esc(c.origen)}</td><td><small>${esc(c.via)}</small></td>
    <td>${c.ack ? `<span class="${c.ack.ok ? "ok" : "mal"}">${c.ack.ok ? "✓ OK" : "✗ error"}</span><br><small>${esc(c.ack.detalle)} · ${fmtMs(c.ack.rtt_ms)}</small>` : "<small>esperando…</small>"}</td></tr>`).join("")
    || `<tr><td colspan="6" class="vacio">Sin comandos todavía.</td></tr>`;
  kpis();
  if (estado.abiertos) pintarCmdsPanel();
}

// ================================================================== PANEL DE DISPOSITIVO
function abrirPanel(id) {
  estado.abiertos = id;
  const d = estado.disp[id];
  $("#panel").style.setProperty("--c", color(d));
  $("#p-chips").innerHTML = `<span class="etq tipo" style="--c:${color(d)}">${TIPOS[d.tipo]}</span><span class="etq">${esc(d.protocolo)}</span><span class="etq">${esc(id)}</span>`;
  $("#p-nombre").textContent = d.nombre;
  $("#p-sub").textContent = `${d.hardware} · ${d.ubicacion}`;
  $("#p-via").textContent = {
    mqtt: `MQTT → campus/cmd/${id}`, amqp: `AMQP → cola cmd.${id}`, stomp: `STOMP → /exchange/campus.cmd/${id}`,
    coap: "CoAP POST /cmd (ACK inmediato)", http: "HTTP: llega en la respuesta al próximo POST (≤ 30 s)",
  }[d.protocolo];
  $("#p-clave").value = leer("clave");
  $("#p-accion").innerHTML = Object.keys(d.comandos).map((k) => `<option>${esc(k)}</option>`).join("");
  ayudaAccion();
  pintarEstadoPanel(); pintarControles(); pintarCmdsPanel(); cargarGraficas();
  $("#velo").hidden = false; $("#panel").classList.add("abierto"); $("#panel").setAttribute("aria-hidden", "false");
  setTimeout(() => $("#p-cerrar").focus(), 50);
}
function cerrarPanel() {
  estado.abiertos = null; $("#velo").hidden = true; $("#panel").classList.remove("abierto"); $("#panel").setAttribute("aria-hidden", "true");
  estado.charts.forEach((c) => c.destroy()); estado.charts = [];
}
$("#p-cerrar").addEventListener("click", cerrarPanel);
$("#velo").addEventListener("click", cerrarPanel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && estado.abiertos) cerrarPanel(); });

function pintarEstadoPanel() {
  const d = estado.disp[estado.abiertos]; if (!d) return;
  const e = d.estado || {};
  const celdas = [
    ["estado", enLinea(d) ? "en línea" : e.encendido === 0 ? "apagado" : "sin datos"], ["último dato", hace(d.ts)], ["intervalo", `${e.intervalo_s ?? d.intervalo_fabrica}<em>s</em>`],
    ...Object.entries(d.ultimo || {}).map(([k, v]) => [k.replace(/_/g, " "), `${fmtVar(d, k, v)}<em>${esc(unidadCorta(d, k))}</em>`]),
    ...Object.entries(e).filter(([k]) => k.startsWith("offset_") || k.startsWith("ganancia_")).map(([k, v]) => [k.replace("_", " "), fmt(v)]),
  ];
  $("#p-estado").innerHTML = celdas.map(([k, v]) => `<div><small>${esc(k)}</small><b>${v}</b></div>`).join("");
}

function pintarControles() {
  const id = estado.abiertos, d = estado.disp[id]; if (!d) return;
  const e = d.estado || {}, u = d.ultimo || {}, c = d.comandos;
  const intMin = id.startsWith("api-clima") || id.startsWith("api-aire") ? 300 : id.startsWith("api-") ? 60 : 5;
  const intMax = id.startsWith("api-") || id === "ds-aire-uci" ? 3600 : 600;
  const intVal = e.intervalo_s ?? d.intervalo_fabrica;
  const encendido = id === "twin-panel-solar" ? e.inversor !== 0 : e.encendido !== 0;
  let h = `<div class="control"><h5>${id === "twin-panel-solar" ? "Inversor" : "Telemetría"} <span>${encendido ? "encendido" : "apagado"}</span></h5>
      <div class="fila"><button class="interruptor ${encendido ? "on" : ""}" data-accion="${encendido ? "apagar" : "encender"}" aria-label="Encender o apagar"></button>
      <span class="nota">${id === "twin-panel-solar" ? "desconecta la planta de la red" : "apagar deja solo un latido cada 60 s"}</span></div></div>
    <div class="control"><h5>Intervalo de muestreo <span>${intVal} s</span></h5>
      <div class="fila"><input type="range" id="c-int" min="${intMin}" max="${intMax}" step="${intMin >= 60 ? 60 : 5}" value="${intVal}"><output id="o-int">${intVal} s</output></div>
      <button class="btn chico" data-enviar="intervalo">Aplicar intervalo</button></div>
    <div class="control ancho"><h5>Calibración <span>valor = medido × ganancia + offset</span></h5>
      <div class="fila"><select id="c-var">${Object.keys(d.variables).map((k) => `<option>${esc(k)}</option>`).join("")}</select>
      <label class="nota">offset <input type="number" id="c-off" step="0.1" value="0"></label><label class="nota">ganancia <input type="number" id="c-gan" step="0.01" value="1"></label>
      <button class="btn chico" data-enviar="calibrar">Calibrar</button><button class="btn chico" data-accion="reset">Reset de fábrica</button></div></div>`;
  if (c.setpoint) h += `<div class="control"><h5>Setpoint <span>${fmt(u.setpoint)} °C</span></h5><div class="fila"><input type="range" id="c-sp" min="16" max="30" step="0.5" value="${u.setpoint ?? 23}"><output id="o-sp">${u.setpoint ?? 23} °C</output></div><button class="btn chico" data-enviar="setpoint">Aplicar setpoint</button></div>`;
  if (c.modo) h += `<div class="control"><h5>Modo del HVAC <span>${MODOS[u.modo] ?? "–"}</span></h5><div class="seg">${["apagado", "auto", "ventilacion", "eco"].map((m, i) => `<button class="${u.modo === i ? "on" : ""}" data-accion="modo" data-p='{"valor":"${m}"}'>${MODOS[i]}</button>`).join("")}</div></div>`;
  if (c.bomba) h += `<div class="control"><h5>Bomba <span>${["auto", "forzada on", "forzada off"][e.bomba_modo ?? 0]} · ${u.bomba ? "funcionando" : "detenida"}</span></h5><div class="seg">${["auto", "on", "off"].map((m, i) => `<button class="${(e.bomba_modo ?? 0) === i ? "on" : ""}" data-accion="bomba" data-p='{"estado":"${m}"}'>${m}</button>`).join("")}</div></div>`;
  if (c.consumo) h += `<div class="control"><h5>Demanda de agua <span>×${fmt(e.factor_consumo ?? 1)}</span></h5><div class="fila"><input type="range" id="c-cons" min="0.5" max="3" step="0.1" value="${e.factor_consumo ?? 1}"><output id="o-cons">×${e.factor_consumo ?? 1}</output></div><button class="btn chico" data-enviar="consumo">Aplicar demanda</button></div>`;
  if (c.limite) h += `<div class="control"><h5>Límite del inversor <span>${fmt(e.limite_kw ?? 12)} kW</span></h5><div class="fila"><input type="range" id="c-lim" min="0" max="12" step="0.5" value="${e.limite_kw ?? 12}"><output id="o-lim">${e.limite_kw ?? 12} kW</output></div><button class="btn chico" data-enviar="limite">Aplicar límite</button></div>`;
  if (c.extractor) h += `<div class="control"><h5>Extractor <span>${["auto", "forzado on", "forzado off"][e.extractor_modo ?? 0]} · ${u.extractor ? "encendido" : "apagado"}</span></h5><div class="seg">${["auto", "on", "off"].map((m, i) => `<button class="${(e.extractor_modo ?? 0) === i ? "on" : ""}" data-accion="extractor" data-p='{"estado":"${m}"}'>${m}</button>`).join("")}</div></div>`;
  if (c.led) h += `<div class="control"><h5>LED del ESP32 <span>${e.led ? "encendido" : "apagado"}</span></h5><div class="fila"><button class="interruptor ${e.led ? "on" : ""}" data-accion="led" data-p='{"estado":"${e.led ? "off" : "on"}"}' aria-label="LED"></button><span class="nota">actuador físico del firmware</span></div></div>`;
  if (c.velocidad) h += `<div class="control"><h5>Velocidad de repetición <span>×${e.velocidad ?? 1}</span></h5><div class="fila"><input type="range" id="c-vel" min="1" max="20" step="1" value="${e.velocidad ?? 1}"><output id="o-vel">×${e.velocidad ?? 1}</output></div><button class="btn chico" data-enviar="velocidad">Aplicar velocidad</button></div>`;
  if (c.saltar) h += `<div class="control"><h5>Saltar filas del dataset <span>fila ${e.fila ?? "–"}</span></h5><div class="fila"><input type="number" id="c-salto" value="60" step="10"><button class="btn chico" data-enviar="saltar">Saltar</button></div></div>`;
  $("#p-controles").innerHTML = h;
  const enlazar = (inp, out, suf, pre = "") => { const i = $(inp); if (i) i.addEventListener("input", () => { $(out).textContent = `${pre}${i.value}${suf}`; }); };
  enlazar("#c-int", "#o-int", " s"); enlazar("#c-sp", "#o-sp", " °C"); enlazar("#c-cons", "#o-cons", "", "×"); enlazar("#c-lim", "#o-lim", " kW"); enlazar("#c-vel", "#o-vel", "", "×");
}
$("#p-controles").addEventListener("click", (e) => {
  const b = e.target.closest("[data-accion],[data-enviar]"); if (!b) return;
  if (b.dataset.accion) return enviar(b.dataset.accion, b.dataset.p ? JSON.parse(b.dataset.p) : {}, b);
  const a = b.dataset.enviar, v = (s) => Number($(s).value);
  const params = {
    intervalo: () => ({ segundos: v("#c-int") }), calibrar: () => ({ variable: $("#c-var").value, offset: v("#c-off"), ganancia: v("#c-gan") }),
    setpoint: () => ({ valor: v("#c-sp") }), consumo: () => ({ factor: v("#c-cons") }), limite: () => ({ kw: v("#c-lim") }),
    velocidad: () => ({ factor: v("#c-vel") }), saltar: () => ({ filas: v("#c-salto") }),
  }[a]();
  enviar(a, params, b);
});

async function enviar(accion, params, boton) {
  const id = estado.abiertos;
  const clave = $("#p-clave").value.trim();
  if (!clave) { toast("Falta la clave de control", "Escríbela abajo, en «Clave de control».", "mal"); $("#p-clave").focus(); return; }
  guardar("clave", clave);
  if (boton) boton.disabled = true;
  try {
    const r = await api(`/api/dispositivos/${encodeURIComponent(id)}/comando`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Clave": clave }, body: JSON.stringify({ accion, params }),
    });
    if (r.ack) toast(`ACK: ${accion}`, `${id} · ${r.ack.detalle} · ${fmtMs(r.ack.rtt_ms)}`, r.ack.ok ? "ok" : "mal");
    else { estado.pendientes[r.cmd_id] = true; toast(`Enviado: ${accion}`, r.via, "cmd"); }
  } catch (e) {
    if (e.status === 401) { toast("Clave de control inválida", "El comando no se envió.", "mal"); guardar("clave", ""); $("#p-clave").select(); }
    else toast(`Error ${e.status || ""}`, e.cuerpo?.detail || e.message, "mal");
  } finally { if (boton) setTimeout(() => { boton.disabled = false; }, 600); }
}
function ayudaAccion() { const d = estado.disp[estado.abiertos]; $("#p-ayuda").textContent = d?.comandos[$("#p-accion").value] || ""; }
$("#p-accion").addEventListener("change", ayudaAccion);
$("#p-json-enviar").addEventListener("click", () => {
  let p; try { p = JSON.parse($("#p-params").value || "{}"); } catch (e) { toast("JSON inválido", "", "mal"); return; }
  enviar($("#p-accion").value, p, $("#p-json-enviar"));
});
function pintarCmdsPanel() {
  const l = estado.comandos.filter((c) => c.dispositivo === estado.abiertos).slice(0, 8);
  $("#p-cmds").innerHTML = l.map((c) => `<li><div><b>${esc(c.accion)}</b> <small>${esc(JSON.stringify(c.params))} · ${esc(c.origen)}</small><br><small>${fecha(c.ts)}</small></div>
    <div>${c.ack ? `<span class="${c.ack.ok ? "ok" : "mal"}">${c.ack.ok ? "✓" : "✗"}</span> <small>${fmtMs(c.ack.rtt_ms)}</small>` : "<small>…</small>"}</div></li>`).join("") || `<li class="vacio">Aún no ha recibido comandos.</li>`;
}

// gráficas del panel (Chart.js)
$("#p-rango").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  estado.rango = Number(b.dataset.h); $$("#p-rango button").forEach((x) => x.classList.toggle("activo", x === b)); cargarGraficas();
});
async function cargarGraficas() {
  const id = estado.abiertos; if (!id) return;
  estado.charts.forEach((c) => c.destroy()); estado.charts = [];
  const cont = $("#p-graficas");
  cont.innerHTML = `<p class="vacio" style="grid-column:1/-1">Cargando ${estado.rango} h de datos…</p>`;
  let h;
  try { h = await api(`/api/historia/${id}?horas=${estado.rango}&puntos=180`); } catch (e) { cont.innerHTML = `<p class="vacio">No se pudo leer la historia.</p>`; return; }
  if (estado.abiertos !== id) return;
  const d = estado.disp[id], vars = Object.keys(d.variables).filter((k) => h.series[k]?.length);
  if (!vars.length) { cont.innerHTML = `<p class="vacio" style="grid-column:1/-1">Sin datos en este rango.</p>`; return; }
  cont.innerHTML = vars.map((k) => {
    const ys = h.series[k].map((p) => p[1]);
    const prom = ys.reduce((a, b) => a + b, 0) / ys.length;
    return `<div class="grafica"><div class="g-cab"><b>${esc(k.replace(/_/g, " "))}</b><span>${esc(d.variables[k].unidad)}</span></div>
      <div class="g-stats"><span>mín <b>${fmt(Math.min(...ys))}</b></span><span>prom <b>${fmt(prom)}</b></span><span>máx <b>${fmt(Math.max(...ys))}</b></span></div><canvas data-var="${esc(k)}"></canvas></div>`;
  }).join("");
  const col = css(COLOR_TIPO[d.tipo]), rej = css("--borde"), txt = css("--suave");
  for (const cv of $$("canvas", cont)) {
    const k = cv.dataset.var;
    estado.charts.push(new Chart(cv, {
      type: "line",
      data: { datasets: [{ data: h.series[k].map(([x, y]) => ({ x, y })), borderColor: col, backgroundColor: col + "22", fill: true, borderWidth: 1.6, pointRadius: 0, tension: .25 }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: (it) => fecha(it[0].parsed.x), label: (it) => `${fmt(it.parsed.y)} ${d.variables[k].unidad}` } } },
        scales: {
          x: { type: "linear", min: h.series[k][0][0], max: h.series[k][h.series[k].length - 1][0], grid: { color: rej }, ticks: { color: txt, maxTicksLimit: 5, font: { size: 10 }, callback: (v) => (estado.rango > 24 ? fecha(v) : hora(v, false)) } },
          y: { grid: { color: rej }, ticks: { color: txt, maxTicksLimit: 4, font: { size: 10 } } },
        },
      },
    }));
    estado.charts[estado.charts.length - 1].$var = k;
  }
}
function empujarGraficas(ev) {
  if (estado.rango > 24) return;
  for (const ch of estado.charts) {
    if (ev.v && ch.$var in ev.v) { ch.data.datasets[0].data.push({ x: ev.ts, y: ev.v[ch.$var] }); ch.options.scales.x.max = ev.ts; ch.update("none"); }
  }
}

// ================================================================== ARRANQUE
async function iniciar() {
  try { await cargarDispositivos(); } catch (e) { toast("No se pudo conectar con la API", e.message, "mal"); return; }
  pintarGrilla(); dibujarFlujo(); kpis();
  conectarStream();
  cargarReglas().then(cargarAlertas);
  cargarComandos(); cargarProtocolos(); cargarSparks();
  iniciarMapa();
  setInterval(() => {   // relojes "hace X s" y contadores
    for (const el of $$("[data-edad]")) { const d = estado.disp[el.dataset.edad]; if (d && d.estado?.encendido !== 0) el.textContent = etiquetaEdad(el.dataset.edad, d); }
    actualizarCuentasProto(); kpis();
    const porSeg = estado.datosVentana.filter((t) => t > Date.now() - 60000).length / 60;
    if ($("#vivo").classList.contains("ok")) $("#vivo-txt").textContent = `EN VIVO · ${porSeg.toFixed(1)} msg/s`;
  }, 1000);
  setInterval(dibujarKpiSpark, 5000);
  setInterval(async () => { try { await cargarDispositivos(); } catch (e) { /* */ } }, 30000);
  setInterval(cargarProtocolos, 30000);
  setInterval(cargarAlertas, 45000);
  addEventListener("resize", () => { dibujarKpiSpark(); mapa?.invalidateSize(); });
  setTimeout(() => mapa?.invalidateSize(), 600);
  dibujarKpiSpark();
}
iniciar();
