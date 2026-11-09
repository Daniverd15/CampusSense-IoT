"use strict";
/* CampusSense UNAB — front en tiempo real. Todo número sale de la API; el stream llega por SSE (/api/stream). */

// ================================================================== utilidades
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TZ = "America/Bogota";
const hora = (ms, seg = true) => ms ? new Date(ms).toLocaleTimeString("es-CO", { timeZone: TZ, hour12: false, hour: "2-digit", minute: "2-digit", ...(seg ? { second: "2-digit" } : {}) }) : "–";
const fecha = (ms) => ms ? new Date(ms).toLocaleString("es-CO", { timeZone: TZ, hour12: false, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const icono = (id, t = 18) => `<svg width="${t}" height="${t}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
function fmt(v, dec) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (typeof v !== "number") return esc(v);
  if (dec !== undefined) return v.toLocaleString("es-CO", { maximumFractionDigits: dec, minimumFractionDigits: dec });
  const a = Math.abs(v);
  return v.toLocaleString("es-CO", { maximumFractionDigits: a >= 1000 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : 3 });
}
const fmtMs = (ms) => (ms == null ? "–" : ms >= 1000 ? `${fmt(ms / 1000, 1)} s` : `${fmt(ms, 0)} ms`);
const hace = (ms) => {
  if (!ms) return "sin datos";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  return s < 60 ? `hace ${Math.round(s)} s` : s < 3600 ? `hace ${Math.round(s / 60)} min` : s < 86400 ? `hace ${(s / 3600).toFixed(1)} h` : `hace ${(s / 86400).toFixed(1)} d`;
};
function guardar(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* sin almacenamiento */ } }
function leer(k) { try { return sessionStorage.getItem(k) || ""; } catch (e) { return ""; } }
async function api(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) throw Object.assign(new Error(`${r.status}`), { status: r.status, cuerpo: await r.json().catch(() => ({})) });
  return r.json();
}

// ================================================================== modelo
const TIPOS = { real: "Real", twin: "Gemelo digital", api: "API", dataset: "Dataset" };
const COLOR = { real: "--real", twin: "--twin", api: "--api", dataset: "--dataset" };
const FAMILIAS = {
  real: ["Reales", "Nodos de campo. Tres son firmware emulado en Python (sin hardware) y uno es un ESP32 con firmware Arduino real corriendo en el simulador Wokwi."],
  twin: ["Gemelos digitales", "Modelos que corren en la nube y se alimentan con datos reales del bus: comparan lo que predicen con lo que se mide."],
  api: ["API", "Datos reales de servicios externos: Azure Maps (clima y calidad del aire en el campus) y el GPS del bus de Rutas UNAB."],
  dataset: ["Dataset", "Mediciones reales de datasets públicos de UCI, repetidas como si fueran sensores en vivo y alineadas a la hora del día."],
};
const ORIGEN = (id, d) => id === "esp32-wokwi" ? "firmware real · Wokwi" : d.tipo === "real" ? "emulado en Python" : d.tipo === "twin" ? "modelo en la nube" : d.tipo === "api" ? "dato externo real" : "dataset UCI repetido";
const PRINCIPAL = {
  "aula-101": "co2", "lab-quimica": "pm25", "medidor-bloque-a": "potencia", "esp32-wokwi": "temperatura",
  "twin-hvac-aula101": "temp_modelo", "twin-tanque-agua": "nivel", "twin-panel-solar": "potencia", "api-clima-unab": "temperatura",
  "api-aire-unab": "indice_global", "api-bus-ruta1": "velocidad", "ds-ocupacion-uci": "co2", "ds-aire-uci": "no2",
};
const MODOS = ["apagado", "auto", "ventilación", "eco"];
const PROTO = {
  mqtt: ["MQTT 3.1.1", "Mosquitto, QoS 1, sesión persistente y última voluntad. La latencia excluye al ESP32: el reloj de Wokwi corre más lento que el real.", "campus/cmd/<id>", "SUBSCRIBE QoS 1"],
  amqp: ["AMQP 0-9-1", "RabbitMQ, exchange topic y publisher confirms.", "cola cmd.<id>", "exchange campus.cmd"],
  stomp: ["STOMP 1.2", "Plugin STOMP de RabbitMQ, mismo exchange que AMQP.", "/exchange/campus.cmd/<id>", "SUBSCRIBE"],
  coap: ["CoAP", "UDP, POST confirmable al ingestor.", "POST /cmd", "la respuesta 2.04 es el ACK"],
  http: ["HTTP REST", "POST /api/ingest con token.", "respuesta del POST", "llega en el siguiente envío"],
};
const INICIO_TOMA = Date.parse("2026-11-09T04:19:00Z");   // primer dato guardado (8-nov 23:19, Bogotá)

const E = {
  disp: {}, orden: [], filtro: "todos", buscar: "", spark: {}, consolaFiltro: "todo", pausa: false, ventana: [],
  abierto: null, charts: [], rango: 24, pendientes: {}, desde: 0, protocolos: {}, alertas: { activas: [], historial: [] },
  reglas: [], comandos: [], anaDisp: "aula-101", anaHoras: 24,
};
const acksVistos = new Set();
const acksRecientes = new Map();   // el ACK puede llegar por SSE antes que la respuesta del POST

// ================================================================== tema y toasts
$("#tema").addEventListener("click", () => {
  const actual = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const nuevo = actual === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nuevo;
  try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento */ }
  dibujarFlujo(); pintarFamilias(); dibujarSpark(); if (E.abierto) cargarGraficas();
});
function toast(titulo, detalle = "", tipo = "ok", ms = 4800) {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.innerHTML = `${icono({ ok: "ok", mal: "x", cmd: "cmd", alerta: "alerta" }[tipo] || "ok")}<div><b>${esc(titulo)}</b><small>${esc(detalle)}</small></div>`;
  $("#toasts").prepend(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 320); }, ms);
}

// ================================================================== flujo animado
const F = {
  grupos: { real: [16, 30], twin: [16, 128], api: [16, 226], dataset: [16, 324] },
  protos: { mqtt: 54, amqp: 138, stomp: 222, coap: 306, http: 390 },
  brokers: { mqtt: ["Mosquitto", "broker MQTT", 24, 62], amqp: ["RabbitMQ", "AMQP 0-9-1 y STOMP", 118, 124], coap: ["Servidor CoAP", "UDP 5683", 272, 62], http: ["Endpoint HTTP", "POST /api/ingest", 356, 62] },
  ingestor: [722, 130, 165, 70], apiBox: [722, 300, 165, 70], influx: [930, 130, 125, 70], front: [1092, 82, 96, 70], grafana: [1092, 196, 96, 70],
  cuentas: { mqtt: [], amqp: [], stomp: [], coap: [], http: [] }, activos: 0,
};
const brokerDe = (p) => (p === "stomp" ? "amqp" : p);
function yBroker(p) { const b = F.brokers[brokerDe(p)]; return p === "amqp" ? b[2] + 40 : p === "stomp" ? b[2] + 92 : b[2] + b[3] / 2; }
const protosDe = (tipo) => [...new Set(E.orden.filter((id) => E.disp[id].tipo === tipo).map((id) => E.disp[id].protocolo))];
function curva(a, b) { const mx = (a[0] + b[0]) / 2; return [a, [mx, a[1]], [mx, b[1]], b]; }
const camino = (r) => { const c = curva(r[0], r[1]); return `M${c[0]} C${c[1]} ${c[2]} ${c[3]}`; };

function dibujarFlujo() {
  const n = (x, y, w, h, t, sub, cls = "") => `<g class="nodo ${cls}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="11"/><text x="${x + 14}" y="${y + 26}" class="titulo">${esc(t)}</text>${sub ? `<text x="${x + 14}" y="${y + 46}" class="sub">${esc(sub)}</text>` : ""}</g>`;
  let h = [["dispositivos", 16], ["protocolo", 296], ["broker", 470], ["procesamiento", 722], ["base de datos", 930], ["visualización", 1092]]
    .map(([t, x]) => `<text x="${x}" y="14" class="col-tit">${t}</text>`).join("");
  const rutas = [];
  for (const [tipo, [gx, gy]] of Object.entries(F.grupos)) for (const p of protosDe(tipo)) rutas.push([[gx + 214, gy + 40], [303, F.protos[p]]]);
  for (const p of Object.keys(F.protos)) rutas.push([[357, F.protos[p]], [470, yBroker(p)]]);
  for (const p of ["mqtt", "amqp", "coap"]) rutas.push([[680, yBroker(p)], [F.ingestor[0], F.ingestor[1] + 35]]);
  rutas.push([[680, yBroker("http")], [F.apiBox[0], F.apiBox[1] + 35]]);
  rutas.push([[F.ingestor[0] + F.ingestor[2], F.ingestor[1] + 35], [F.influx[0], F.influx[1] + 35]]);
  rutas.push([[F.apiBox[0] + F.apiBox[2], F.apiBox[1] + 35], [F.influx[0], F.influx[1] + 55]]);
  rutas.push([[F.influx[0] + F.influx[2], F.influx[1] + 22], [F.front[0], F.front[1] + 35]]);
  rutas.push([[F.influx[0] + F.influx[2], F.influx[1] + 48], [F.grafana[0], F.grafana[1] + 35]]);
  h += rutas.map((r) => `<path class="ruta" d="${camino(r)}"/>`).join("");
  h += `<path class="ruta" d="M${F.apiBox[0] + 82},${F.apiBox[1]} L${F.ingestor[0] + 82},${F.ingestor[1] + 70}"/>`;
  for (const [tipo, [gx, gy]] of Object.entries(F.grupos)) {
    const ids = E.orden.filter((id) => E.disp[id].tipo === tipo);
    h += `<g class="nodo grupo" id="g-${tipo}" style="--c:var(${COLOR[tipo]})"><rect x="${gx}" y="${gy}" width="214" height="80" rx="11"/>
      <text x="${gx + 14}" y="${gy + 25}" class="titulo">${FAMILIAS[tipo][0]} · ${ids.length}</text>
      ${ids.slice(0, 4).map((id, i) => `<text x="${gx + 14 + (i % 2) * 100}" y="${gy + 47 + Math.floor(i / 2) * 18}" class="sub">${esc(id.length > 14 ? id.slice(0, 13) + "…" : id)}</text>`).join("")}</g>`;
  }
  for (const [p, y] of Object.entries(F.protos)) h += `<g class="proto" id="p-${p}"><circle cx="330" cy="${y}" r="27"/><text x="330" y="${y + 1}">${p.toUpperCase()}</text><text x="330" y="${y + 14}" class="cuenta" id="pc-${p}">–</text></g>`;
  for (const [, [t, sub, y, hh]] of Object.entries(F.brokers)) h += n(470, y, 210, hh, t, sub);
  h += `<g class="nodo"><text x="484" y="${yBroker("amqp") + 30}" class="sub">exchange campus.tele</text><text x="484" y="${yBroker("stomp") + 6}" class="sub">STOMP → mismo exchange</text></g>`;
  h += n(...F.ingestor, "Ingestor", "valida y guarda", "central") + n(...F.apiBox, "API y reglas", "retroceso · R1 a R7", "central");
  h += n(...F.influx, "InfluxDB", "series de tiempo", "central") + n(...F.front, "Este panel", "SSE") + n(...F.grafana, "Grafana", "5 tableros");
  h += `<g id="paquetes"></g>`;
  $("#flujo-svg").innerHTML = h;
  cuentasProto();
}
function bezier(p, t) {
  const u = 1 - t;
  return [u ** 3 * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t ** 3 * p[3][0], u ** 3 * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t ** 3 * p[3][1]];
}
function animar(tramos, color, dur = 1700, radio = 4.3) {
  if (F.activos > 70 || document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const g = $("#paquetes"); if (!g) return;
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("r", radio); c.style.fill = color;
  g.appendChild(c); F.activos++;
  const curvas = tramos.map(([a, b]) => curva(a, b)), t0 = performance.now();
  (function paso(ahora) {
    const t = Math.min(1, (ahora - t0) / dur), k = Math.min(curvas.length - 1, Math.floor(t * curvas.length));
    const [x, y] = bezier(curvas[k], t * curvas.length - k);
    c.setAttribute("cx", x); c.setAttribute("cy", y);
    if (t < 1) requestAnimationFrame(paso); else { c.remove(); F.activos--; }
  })(t0);
}
function latido(sel) { const r = $(`${sel} rect, ${sel} circle`); if (!r) return; r.classList.remove("latido"); void r.getBBox(); r.classList.add("latido"); }
function animarDato(d) {
  const p = d.protocolo, [gx, gy] = F.grupos[d.tipo], yb = yBroker(p);
  const dst = p === "http" ? F.apiBox : F.ingestor;
  animar([[[gx + 214, gy + 40], [303, F.protos[p]]], [[357, F.protos[p]], [470, yb]], [[680, yb], [dst[0], dst[1] + 35]], [[dst[0] + dst[2], dst[1] + 35], [F.influx[0], F.influx[1] + 35]]], css(COLOR[d.tipo]));
  latido(`#g-${d.tipo}`); setTimeout(() => latido(`#p-${p}`), 420);
}
function animarCmd(dev) {
  const d = E.disp[dev]; if (!d) return;
  const p = d.protocolo, [gx, gy] = F.grupos[d.tipo], yb = yBroker(p);
  animar([[[F.apiBox[0], F.apiBox[1] + 35], [680, yb]], [[470, yb], [357, F.protos[p]]], [[303, F.protos[p]], [gx + 214, gy + 40]]], css("--cmd"), 1500, 5.6);
}
function cuentasProto() {
  const vivo = E.desde && Date.now() - E.desde > 60000, lim = Date.now() - 60000;
  for (const p of Object.keys(F.cuentas)) {
    F.cuentas[p] = F.cuentas[p].filter((t) => t > lim);
    const v = vivo ? F.cuentas[p].length : Math.max(F.cuentas[p].length, Math.round(E.protocolos[p]?.msg_min || 0));
    const el = $(`#pc-${p}`); if (el) el.textContent = `${v}/min`;
  }
}

// ================================================================== dispositivos
const color = (d) => `var(${COLOR[d.tipo]})`;
function unidad(d, k) { const u = d.variables[k]?.unidad || ""; return ["on/off", "0/1"].includes(u) || k === "modo" || u.length > 8 ? "" : u; }
function valor(d, k, v) {
  if (v === null || v === undefined) return "–";
  const u = d.variables[k]?.unidad || "";
  if (k === "modo") return MODOS[v] ?? fmt(v);
  if (u === "on/off" || u === "0/1") return v ? "ON" : "OFF";
  return fmt(v);
}
function enLinea(d) {
  if (!d.ts) return false;
  return (Date.now() - d.ts) / 1000 <= Math.max(3 * (d.estado?.intervalo_s ?? d.intervalo_fabrica), 180) && d.estado?.encendido !== 0;
}
function edad(id, d) {
  if (d.estado?.encendido === 0) return "apagado por comando";
  return id === "esp32-wokwi" && !enLinea(d) ? `fuera de sesión · ${hace(d.ts)}` : hace(d.ts);
}
function spark(id) {
  const pts = E.spark[id] || [];
  if (pts.length < 2) return `<svg viewBox="0 0 128 42" aria-hidden="true"></svg>`;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = (x) => ((x - x0) / (x1 - x0 || 1)) * 126 + 1, Y = (y) => 39 - ((y - y0) / (y1 - y0 || 1)) * 34;
  const l = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
  return `<svg viewBox="0 0 128 42" aria-hidden="true"><path class="spark-area" d="${l}L127,42L1,42Z"/><path class="spark-linea" d="${l}"/></svg>`;
}
function tarjeta(id) {
  const d = E.disp[id], pv = PRINCIPAL[id], u = d.ultimo || {}, apagado = d.estado?.encendido === 0;
  const cls = apagado ? "off" : enLinea(d) ? "on" : "";
  const est = apagado ? "apagado" : cls ? "en línea" : id === "esp32-wokwi" ? "fuera de sesión" : "sin datos";
  const otros = Object.keys(d.variables).filter((k) => k !== pv).slice(0, 4)
    .map((k) => `<div><span>${esc(k.replace(/_/g, " "))}</span><b>${valor(d, k, u[k])} <small>${esc(unidad(d, k))}</small></b></div>`).join("");
  return `<button class="disp" data-id="${esc(id)}" style="--c:${color(d)}" aria-label="${esc(d.nombre)}: abrir gráficas y controles">
    <div class="disp-cab"><div><h4>${esc(d.nombre)}</h4><div class="id">${esc(id)}</div></div><span class="estado-pt ${cls}"><i></i>${est}</span></div>
    <div class="etqs"><span class="etq origen">${esc(ORIGEN(id, d))}</span><span class="etq">${esc(d.protocolo.toUpperCase())}</span><span class="etq">cada ${esc(d.estado?.intervalo_s ?? d.intervalo_fabrica)} s</span></div>
    <div class="principal"><div><div class="valor">${valor(d, pv, u[pv])}<small>${esc(unidad(d, pv))}</small></div><span class="var">${esc(pv.replace(/_/g, " "))}</span></div>${spark(id)}</div>
    <div class="secund">${otros}</div>
    <div class="pie"><span data-edad="${esc(id)}">${edad(id, d)}</span><span>mensaje #${esc(d.seq ?? "–")}</span></div></button>`;
}
function visibles(tipo) {
  const q = E.buscar.toLowerCase();
  return E.orden.filter((id) => E.disp[id].tipo === tipo && (E.filtro === "todos" || E.filtro === tipo) &&
    (!q || id.includes(q) || E.disp[id].nombre.toLowerCase().includes(q) || E.disp[id].protocolo.includes(q)));
}
function pintarFamilias() {
  const html = Object.keys(FAMILIAS).map((t) => {
    const ids = visibles(t); if (!ids.length) return "";
    return `<div class="familia" style="--c:var(${COLOR[t]})"><div class="familia-cab"><h3>${FAMILIAS[t][0]} · ${ids.length}</h3><p>${esc(FAMILIAS[t][1])}</p></div>
      <div class="grilla">${ids.map(tarjeta).join("")}</div></div>`;
  }).join("");
  $("#familias").innerHTML = html || `<p class="vacio">Ningún dispositivo coincide con la búsqueda.</p>`;
  for (const t of ["todos", ...Object.keys(FAMILIAS)]) $(`#c-${t}`).textContent = E.orden.filter((id) => t === "todos" || E.disp[id].tipo === t).length;
}
function repintar(id, flash) {
  const el = $(`.disp[data-id="${CSS.escape(id)}"]`); if (!el) return;
  const tmp = document.createElement("div"); tmp.innerHTML = tarjeta(id);
  if (flash) tmp.firstElementChild.classList.add("flash");
  el.replaceWith(tmp.firstElementChild);
}
$("#familias").addEventListener("click", (e) => { const b = e.target.closest(".disp"); if (b) abrirPanel(b.dataset.id); });
$("#filtros").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  E.filtro = b.dataset.f;
  $$("#filtros button").forEach((x) => { x.classList.toggle("activo", x === b); x.setAttribute("aria-pressed", x === b); });
  pintarFamilias();
});
$("#buscar").addEventListener("input", (e) => { E.buscar = e.target.value.trim(); pintarFamilias(); });

async function cargarDispositivos() {
  for (const d of await api("/api/dispositivos")) {
    const prev = E.disp[d.id];
    E.disp[d.id] = prev && prev.ts > (d.ts || 0) ? { ...d, ultimo: prev.ultimo, ts: prev.ts, seq: prev.seq, estado: prev.estado } : d;
    if (!E.orden.includes(d.id)) E.orden.push(d.id);
  }
}
async function cargarSparks() {
  await Promise.all(E.orden.map(async (id) => {
    try { E.spark[id] = ((await api(`/api/historia/${id}?horas=6&puntos=60`)).series[PRINCIPAL[id]] || []).slice(-60); } catch (e) { E.spark[id] = []; }
  }));
  pintarFamilias();
}

// ================================================================== indicadores y toma de datos
function indicadores() {
  const lin = E.orden.filter((id) => enLinea(E.disp[id]));
  $("#k-linea").textContent = lin.length;
  const fuera = E.orden.filter((id) => !lin.includes(id));
  $("#k-linea-nota").textContent = fuera.length ? `fuera: ${fuera.join(", ")}` : "todos transmitiendo";
  const vivo = E.desde && Date.now() - E.desde > 60000;
  const pm = vivo ? E.ventana.filter((t) => t > Date.now() - 60000).length : Object.values(E.protocolos).reduce((s, p) => s + (p.msg_min || 0), 0);
  $("#k-msg").textContent = fmt(pm, pm < 100 ? 1 : 0);
  const act = E.alertas.activas || [];
  $("#k-alertas").textContent = act.length;
  $("#k-alertas").style.color = act.length ? "var(--mal)" : "";
  $("#k-alertas-nota").textContent = act.length ? act.map((a) => a.regla).join(" · ") : "ninguna regla disparada";
  $("#k-cmd").textContent = E.comandos.length;
  const u = E.comandos[0];
  $("#k-cmd-nota").textContent = u ? `último: ${u.accion} → ${u.dispositivo}` : "ninguno aún";
  const dias = (Date.now() - INICIO_TOMA) / 86400000;
  $("#toma-dias").textContent = `${fmt(dias, 2)} días`;
  $("#toma-relleno").style.width = `${Math.min(100, (dias / 6) * 100)}%`;
  $("#toma-desde").textContent = `desde ${fecha(INICIO_TOMA)}`;
}
function dibujarSpark() {
  const cv = $("#k-spark"), w = cv.clientWidth, h = 30;
  if (!w) return;
  cv.width = w * devicePixelRatio; cv.height = h * devicePixelRatio;
  const ctx = cv.getContext("2d"); ctx.scale(devicePixelRatio, devicePixelRatio);
  const ahora = Date.now(), cubos = new Array(30).fill(0);
  for (const t of E.ventana) { const k = Math.floor((ahora - t) / 10000); if (k < 30) cubos[29 - k]++; }
  const mx = Math.max(1, ...cubos), col = css("--marca");
  ctx.beginPath();
  cubos.forEach((v, i) => { const x = (i / 29) * w, y = h - 3 - (v / mx) * (h - 8); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.stroke();
  ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath(); ctx.globalAlpha = .12; ctx.fillStyle = col; ctx.fill();
}

// ================================================================== consola y ticker
function consola(tipo, texto) {
  if (E.pausa) return;
  const grupo = tipo === "ack" ? "cmd" : tipo === "conexion" ? "alerta" : tipo;
  if (E.consolaFiltro !== "todo" && E.consolaFiltro !== grupo) return;
  const li = document.createElement("li");
  li.className = "nuevo";
  li.innerHTML = `<time>${hora(Date.now())}</time><span class="tag ${tipo}">${{ cmd: "comando", dato: "dato", ack: "ack", alerta: "alerta", conexion: "conexión" }[tipo]}</span><span class="txt">${texto}</span>`;
  const ol = $("#consola"); ol.prepend(li);
  while (ol.children.length > 160) ol.lastChild.remove();
}
$("#c-filtros").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.id === "pausa") { E.pausa = !E.pausa; b.textContent = E.pausa ? "seguir" : "pausa"; b.classList.toggle("activo", E.pausa); return; }
  E.consolaFiltro = b.dataset.c; $$("#c-filtros button[data-c]").forEach((x) => x.classList.toggle("activo", x === b)); $("#consola").innerHTML = "";
});
const resumen = (d, v, n = 3) => Object.entries(v || {}).slice(0, n).map(([k, x]) => `${esc(k)}=${valor(d, k, x)}`).join(" ");
function ticker(d, ev) {
  const pv = PRINCIPAL[ev.id];
  $("#ticker").innerHTML = `<b>${esc(ev.id)}</b> → ${esc(d.protocolo.toUpperCase())} → ${d.protocolo === "http" ? "API" : "ingestor"} → InfluxDB · ${esc(pv.replace(/_/g, " "))} ${valor(d, pv, ev.v?.[pv])} ${esc(unidad(d, pv))} · ${fmtMs(ev.lat_ms)}`;
}

// ================================================================== stream SSE
function conectar() {
  const es = new EventSource("/api/stream");
  es.onopen = () => { $("#vivo").classList.add("ok"); $(".en-vivo").classList.add("ok"); E.desde = E.desde || Date.now(); };
  es.onerror = () => { $("#vivo").classList.remove("ok"); $(".en-vivo").classList.remove("ok"); $("#vivo-txt").textContent = "reconectando"; };
  es.onmessage = (m) => { try { manejar(JSON.parse(m.data)); } catch (e) { console.warn(e); } };
}
let tRefresco;
const refrescar = () => { clearTimeout(tRefresco); tRefresco = setTimeout(() => { cargarComandos(); cargarAlertas(); }, 900); };
function manejar(ev) {
  if (ev.t === "dato") {
    const d = E.disp[ev.id]; if (!d) return;
    Object.assign(d, { ultimo: ev.v, ts: ev.ts, seq: ev.seq }); if (ev.estado) d.estado = ev.estado;
    const pv = PRINCIPAL[ev.id];
    if (ev.v && pv in ev.v) { (E.spark[ev.id] ||= []).push([ev.ts, ev.v[pv]]); if (E.spark[ev.id].length > 80) E.spark[ev.id].shift(); }
    E.ventana.push(Date.now()); F.cuentas[d.protocolo]?.push(Date.now());
    if (E.ventana.length > 4000) E.ventana = E.ventana.slice(-3000);
    animarDato(d); repintar(ev.id, true); ticker(d, ev); mapaDato(ev.id);
    consola("dato", `<b>${esc(ev.id)}</b> <i>${esc(d.protocolo)}</i> ${resumen(d, ev.v)} <i>· ${fmtMs(ev.lat_ms)}</i>`);
    if (E.abierto === ev.id) { pintarEstado(); empujar(ev); }
  } else if (ev.t === "cmd") {
    animarCmd(ev.dispositivo);
    consola("cmd", `<b>${esc(ev.accion)}</b> → ${esc(ev.dispositivo)} <i>${esc(JSON.stringify(ev.params))} · ${esc(ev.origen)} · ${esc(ev.protocolo)}</i>`);
    if (String(ev.origen).startsWith("regla")) toast(`Acción automática (${ev.origen})`, `${ev.accion} → ${ev.dispositivo} ${JSON.stringify(ev.params)}`, "cmd", 7000);
    refrescar();
  } else if (ev.t === "ack") {
    if (ev.cmd_id && acksVistos.has(ev.cmd_id)) return;
    if (ev.cmd_id) { acksVistos.add(ev.cmd_id); if (acksVistos.size > 500) acksVistos.clear(); }
    if (ev.cmd_id) { acksRecientes.set(ev.cmd_id, ev); if (acksRecientes.size > 200) acksRecientes.delete(acksRecientes.keys().next().value); }
    const d = E.disp[ev.id]; if (d && ev.estado) d.estado = ev.estado;
    consola("ack", `<b>${esc(ev.id)}</b> ${ev.ok ? "aceptó" : "rechazó"} ${esc(ev.accion)}: ${esc(ev.detalle)} <i>· ${fmtMs(ev.rtt_ms)}</i>`);
    if (E.pendientes[ev.cmd_id]) { delete E.pendientes[ev.cmd_id]; toast(`${ev.ok ? "El dispositivo aceptó" : "El dispositivo rechazó"}: ${ev.accion}`, `${ev.id} · ${ev.detalle} · ida y vuelta ${fmtMs(ev.rtt_ms)}`, ev.ok ? "ok" : "mal"); }
    if (d) repintar(ev.id, false);
    if (E.abierto === ev.id) { pintarEstado(); pintarControles(); }
    refrescar();
  } else if (ev.t === "alerta") {
    consola("alerta", `<b>${esc(ev.regla)}</b> ${ev.estado === "firing" ? "disparada" : "resuelta"} · ${esc(ev.dispositivo)} <i>${esc(ev.mensaje)}</i>`);
    toast(`${ev.estado === "firing" ? "Alerta" : "Resuelta"}: ${ev.regla}`, `${ev.dispositivo} · ${ev.mensaje}`, ev.estado === "firing" ? "alerta" : "ok", 7000);
    refrescar();
  } else if (ev.t === "conexion") {
    consola("conexion", `<b>${esc(ev.id)}</b> ${ev.conectado ? "se conectó al broker" : "se desconectó (última voluntad MQTT)"}`);
  }
}

// ================================================================== analisis del periodo
async function cargarAnalisis() {
  const id = E.anaDisp, d = E.disp[id]; if (!d) return;
  const tb = $("#t-ana tbody");
  tb.innerHTML = `<tr><td colspan="6"><span class="vacio">Calculando en InfluxDB…</span></td></tr>`;
  let r;
  try { r = await api(`/api/resumen/${id}?horas=${E.anaHoras}`); } catch (e) { tb.innerHTML = `<tr><td colspan="6"><span class="vacio">No se pudo consultar.</span></td></tr>`; return; }
  if (E.anaDisp !== id) return;
  const vars = Object.keys(d.variables).filter((k) => r.variables[k]);
  tb.innerHTML = vars.map((k) => {
    const s = r.variables[k], { min: lo, max: hi } = d.variables[k];
    const P = (x) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo || 1)) * 100));
    return `<tr style="--c:${color(d)}"><td><b>${esc(k.replace(/_/g, " "))}</b><br><small>${esc(d.variables[k].unidad)}</small></td>
      <td class="d">${valor(d, k, s.min)}</td><td class="d"><b>${valor(d, k, s.mean)}</b></td><td class="d">${valor(d, k, s.max)}</td>
      <td><div class="rango-fis" title="rango físico aceptado: ${lo} a ${hi}"><span class="tramo" style="left:${P(s.min)}%;width:${Math.max(1, P(s.max) - P(s.min))}%"></span><span class="media" style="left:calc(${P(s.mean)}% - 1px)"></span></div></td>
      <td class="d">${fmt(s.count, 0)}</td></tr>`;
  }).join("") || `<tr><td colspan="6"><span class="vacio">Sin datos en este rango.</span></td></tr>`;
  const total = vars.reduce((s, k) => s + (r.variables[k].count || 0), 0);
  $("#ana-lado").innerHTML = `<h4 style="color:${color(d)}">${esc(d.nombre)}</h4><p>${esc(ORIGEN(id, d))} · ${esc(d.protocolo.toUpperCase())} · ${esc(d.ubicacion)}</p>
    <dl><dt>Rango</dt><dd>${E.anaHoras >= 336 ? "toda la toma" : E.anaHoras >= 24 ? `${E.anaHoras / 24} d` : `${E.anaHoras} h`}</dd><dt>Valores leídos</dt><dd>${fmt(total, 0)}</dd>
    <dt>Intervalo actual</dt><dd>${esc(d.estado?.intervalo_s ?? d.intervalo_fabrica)} s</dd><dt>Último dato</dt><dd>${hace(d.ts)}</dd></dl>
    <p>La barra muestra dónde cayó el periodo dentro del rango físico que acepta el ingestor; la marca es el promedio.</p>
    <a class="btn chico" href="/grafana/d/campus-resumen" target="_blank" rel="noopener">Ver en Grafana ${icono("ext", 13)}</a>`;
}
$("#a-disp").addEventListener("change", (e) => { E.anaDisp = e.target.value; cargarAnalisis(); });
$("#a-rango").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  E.anaHoras = Number(b.dataset.h); $$("#a-rango button").forEach((x) => x.classList.toggle("activo", x === b)); cargarAnalisis();
});

// ================================================================== mapa
const UBIC = {
  "aula-101": [7.11712, -73.10548], "twin-hvac-aula101": [7.11720, -73.10560], "lab-quimica": [7.11680, -73.10498],
  "medidor-bloque-a": [7.11748, -73.10505], "twin-panel-solar": [7.11738, -73.10486], "twin-tanque-agua": [7.11765, -73.10575],
  "api-clima-unab": [7.11703, -73.10534], "api-aire-unab": [7.11694, -73.10520],
};
let mapa, marcas = {}, bus, rastro;
function iniciarMapa() {
  if (!window.L) { $("#mapa").innerHTML = `<p class="vacio">No se pudo cargar el mapa.</p>`; return; }
  mapa = L.map("mapa", { scrollWheelZoom: false }).setView([7.1172, -73.1053], 17);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
  for (const [id, ll] of Object.entries(UBIC)) {
    const d = E.disp[id]; if (!d) continue;
    marcas[id] = L.marker(ll, { icon: L.divIcon({ className: "", html: `<div class="marcador" style="--c:${css(COLOR[d.tipo])}"></div>`, iconSize: [16, 16], iconAnchor: [8, 8] }), title: d.nombre, alt: d.nombre })
      .addTo(mapa).bindPopup("");
    marcas[id].on("click", () => marcas[id].setPopupContent(popup(id)));
  }
  rastro = L.polyline([], { color: css("--marca"), weight: 3, opacity: .7, dashArray: "6 6" }).addTo(mapa);
  bus = L.marker([7.1123, -73.1052], { icon: L.divIcon({ className: "", html: `<div class="marcador-bus">${icono("bus", 18)}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] }), zIndexOffset: 1000, alt: "Bus Ruta 1" })
    .addTo(mapa).bindPopup("");
  bus.on("click", () => bus.setPopupContent(popup("api-bus-ruta1")));
  cargarRastro();
}
function popup(id) {
  const d = E.disp[id];
  return `<b>${esc(d.nombre)}</b><br><small>${esc(ORIGEN(id, d))} · ${esc(d.protocolo.toUpperCase())}</small><br>${Object.entries(d.ultimo || {}).slice(0, 6).map(([k, v]) => `${esc(k.replace(/_/g, " "))}: <b>${valor(d, k, v)}</b> ${esc(unidad(d, k))}`).join("<br>")}<br><small>${edad(id, d)}</small>`;
}
async function cargarRastro() {
  try {
    const h = await api("/api/historia/api-bus-ruta1?horas=12&puntos=240");
    const lon = new Map((h.series.lon || []).map(([t, v]) => [t, v]));
    const pts = (h.series.lat || []).filter(([t]) => lon.has(t)).map(([t, v]) => [v, lon.get(t)]);
    rastro.setLatLngs(pts); mapaDato("api-bus-ruta1");
    if (pts.length) mapa.fitBounds(L.latLngBounds([...pts, ...Object.values(UBIC)]).pad(0.12), { maxZoom: 17 });
  } catch (e) { /* sin datos del bus */ }
}
function mapaDato(id) {
  if (!mapa) return;
  const el = marcas[id]?.getElement()?.querySelector(".marcador");
  if (el) { el.classList.remove("pulso"); void el.offsetWidth; el.classList.add("pulso"); }
  const d = E.disp[id];
  if (id === "api-bus-ruta1" && d?.ultimo?.lat) {
    const ll = [d.ultimo.lat, d.ultimo.lon];
    bus.setLatLng(ll);
    const pts = rastro.getLatLngs(), u = pts[pts.length - 1];
    if (!u || u.lat !== ll[0] || u.lng !== ll[1]) rastro.addLatLng(ll);
    $("#bus-estado").textContent = `bus: ${fmt(d.ultimo.velocidad, 0)} km/h · a ${fmt(d.ultimo.distancia_campus, 2)} km del campus`;
  }
}

// ================================================================== protocolos y caminos de retroceso
async function cargarProtocolos() {
  try { E.protocolos = await api("/api/protocolos"); } catch (e) { return; }
  const P = E.protocolos;
  const maxLat = Math.max(1, ...Object.values(P).map((p) => p.latencia_ms || 0));
  const maxRtt = Math.max(1, ...Object.values(P).map((p) => Math.log10(1 + (p.rtt_ms || 0))));
  $("#protos").innerHTML = Object.entries(PROTO).map(([p, [nombre, desc]]) => {
    const s = P[p] || {};
    return `<article class="proto-t"><div><h3>${nombre}</h3><p class="desc">${esc(desc)}</p></div>
      <div class="medida"><span>mensajes por minuto</span><b>${fmt(s.msg_min, 1)}</b></div>
      <div class="medida"><span>latencia de subida</span><b>${fmtMs(s.latencia_ms)}</b><div class="barra-m"><i style="width:${((s.latencia_ms || 0) / maxLat) * 100}%"></i></div></div>
      <div class="medida rtt"><span>ida y vuelta del ACK</span><b>${fmtMs(s.rtt_ms)}</b><div class="barra-m"><i style="width:${(Math.log10(1 + (s.rtt_ms || 0)) / maxRtt) * 100}%"></i></div></div>
      <div class="devs">${(s.dispositivos || []).map((d) => `<span>${esc(d)}</span>`).join("")}</div></article>`;
  }).join("");
  $("#caminos").innerHTML = Object.entries(PROTO).map(([p, [nombre, , destino, como]]) => {
    const s = P[p] || {};
    return `<div class="camino"><b>${nombre}</b><code>${esc(destino)}</code><span>${esc(como)}</span><strong>${fmtMs(s.rtt_ms)}</strong><span>ida y vuelta promedio · ${fmt(s.acks || 0, 0)} ACK</span></div>`;
  }).join("");
  indicadores();
}

// ================================================================== reglas, alertas y comandos
async function cargarReglas() { try { E.reglas = (await api("/api/reglas")).reglas; } catch (e) { /* */ } }
async function cargarAlertas() {
  try { E.alertas = await api("/api/alertas?n=40"); } catch (e) { return; }
  const act = E.alertas.activas.map((a) => a.regla.split(" ")[0]);
  $("#l-reglas").innerHTML = E.reglas.map((r) => {
    const on = act.includes(r.id);
    return `<li class="${on ? "activa" : ""}"><span class="rid">${esc(r.id)}</span><div><b>${esc(r.nombre)}</b><p>${esc(r.condicion)} → ${esc(r.accion)}</p></div><span class="estado">${on ? "disparada" : "vigilando"}</span></li>`;
  }).join("");
  $("#l-alertas").innerHTML = E.alertas.historial.map((a) => `<li class="${a.estado === "firing" ? "firing" : ""} ${esc(a.severidad)}">${icono(a.estado === "firing" ? "alerta" : "ok")}<div>
      <b>${esc(a.regla)}</b><time>${fecha(a.ts)}</time><p>${esc(a.dispositivo)} · ${esc(a.mensaje)} · ${esc(a.origen)}</p></div></li>`).join("")
    || `<li class="vacio">Ninguna alerta en el periodo. Las reglas siguen vigilando.</li>`;
  indicadores();
}
async function cargarComandos() {
  try { E.comandos = await api("/api/comandos?n=80"); } catch (e) { return; }
  $("#t-cmd tbody").innerHTML = E.comandos.map((c) => `<tr><td class="mono">${fecha(c.ts)}</td><td><b>${esc(c.dispositivo)}</b><br><small>${esc(c.protocolo.toUpperCase())}</small></td>
    <td><b>${esc(c.accion)}</b><br><small class="mono">${esc(JSON.stringify(c.params))}</small></td>
    <td><span class="origen-cmd ${String(c.origen).startsWith("regla") ? "regla" : ""}">${esc(c.origen)}</span></td><td><small>${esc(c.via)}</small></td>
    <td>${c.ack ? `<span class="${c.ack.ok ? "ok" : "mal"}">${icono(c.ack.ok ? "ok" : "x", 15)} ${c.ack.ok ? "aceptado" : "rechazado"}</span><br><small>${esc(c.ack.detalle)} · ${fmtMs(c.ack.rtt_ms)}</small>` : "<small>esperando respuesta</small>"}</td></tr>`).join("")
    || `<tr><td colspan="6"><span class="vacio">Sin comandos todavía.</span></td></tr>`;
  indicadores();
  if (E.abierto) pintarCmds();
}

// ================================================================== panel del dispositivo
function abrirPanel(id) {
  E.abierto = id;
  const d = E.disp[id];
  $("#panel").style.setProperty("--c", color(d));
  $("#p-chips").innerHTML = `<span class="etq origen" style="--c:${color(d)}">${TIPOS[d.tipo]}</span><span class="etq">${esc(d.protocolo.toUpperCase())}</span><span class="etq">${esc(id)}</span>`;
  $("#p-nombre").textContent = d.nombre;
  $("#p-sub").textContent = `${d.hardware} · ${d.ubicacion}`;
  $("#p-origen").textContent = `Origen del dato: ${ORIGEN(id, d)}`;
  $("#p-via").textContent = { mqtt: `MQTT → campus/cmd/${id}`, amqp: `AMQP → cola cmd.${id}`, stomp: `STOMP → /exchange/campus.cmd/${id}`, coap: "CoAP POST /cmd · ACK inmediato", http: "HTTP · llega con el próximo POST (≤ 30 s)" }[d.protocolo];
  $("#p-clave").value = leer("clave");
  $("#p-accion").innerHTML = Object.keys(d.comandos).map((k) => `<option>${esc(k)}</option>`).join("");
  ayuda(); pintarEstado(); pintarControles(); pintarCmds(); cargarGraficas();
  $("#velo").hidden = false; $("#panel").classList.add("abierto"); $("#panel").setAttribute("aria-hidden", "false");
  setTimeout(() => $("#p-cerrar").focus(), 60);
}
function cerrarPanel() {
  const id = E.abierto; E.abierto = null;
  $("#velo").hidden = true; $("#panel").classList.remove("abierto"); $("#panel").setAttribute("aria-hidden", "true");
  E.charts.forEach((c) => c.destroy()); E.charts = [];
  $(`.disp[data-id="${CSS.escape(id || "")}"]`)?.focus();
}
$("#p-cerrar").addEventListener("click", cerrarPanel);
$("#velo").addEventListener("click", cerrarPanel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && E.abierto) cerrarPanel(); });
function pintarEstado() {
  const d = E.disp[E.abierto]; if (!d) return;
  const e = d.estado || {};
  const celdas = [["estado", enLinea(d) ? "en línea" : e.encendido === 0 ? "apagado" : "sin datos"], ["último dato", edad(E.abierto, d)], ["intervalo", `${e.intervalo_s ?? d.intervalo_fabrica}<em>s</em>`],
    ...Object.entries(d.ultimo || {}).map(([k, v]) => [k.replace(/_/g, " "), `${valor(d, k, v)}<em>${esc(unidad(d, k))}</em>`]),
    ...Object.entries(e).filter(([k]) => /^(offset|ganancia)_/.test(k)).map(([k, v]) => [k.replace("_", " "), fmt(v)])];
  $("#p-estado").innerHTML = celdas.map(([k, v]) => `<div><small>${esc(k)}</small><b>${v}</b></div>`).join("");
}
function pintarControles() {
  const id = E.abierto, d = E.disp[id]; if (!d) return;
  const e = d.estado || {}, u = d.ultimo || {}, c = d.comandos;
  const iMin = /^api-(clima|aire)/.test(id) ? 300 : id.startsWith("api-") ? 60 : 5, iMax = id.startsWith("api-") || id === "ds-aire-uci" ? 3600 : 600;
  const iVal = e.intervalo_s ?? d.intervalo_fabrica, solar = id === "twin-panel-solar", on = solar ? e.inversor !== 0 : e.encendido !== 0;
  const seg = (accion, clave, opciones, actual) => `<div class="seg" role="group">${opciones.map(([v, t], i) => `<button class="${actual === i ? "on" : ""}" aria-pressed="${actual === i}" data-accion="${accion}" data-p='{"${clave}":"${v}"}'>${t}</button>`).join("")}</div>`;
  const deslizador = (idc, min, max, paso, val, suf, accion, pre = "") => `<div class="fila"><input type="range" id="${idc}" min="${min}" max="${max}" step="${paso}" value="${val}" aria-label="${accion}"><output id="o-${idc}" data-suf="${suf}" data-pre="${pre}">${pre}${val}${suf}</output></div><button class="btn chico" data-enviar="${accion}">Aplicar</button>`;
  let h = `<div class="control"><h5>${solar ? "Inversor" : "Telemetría"} <span>${on ? "encendido" : "apagado"}</span></h5>
      <div class="fila"><button class="interruptor ${on ? "on" : ""}" role="switch" aria-checked="${on}" data-accion="${on ? "apagar" : "encender"}" aria-label="${solar ? "Inversor" : "Telemetría"}"></button>
      <span class="nota">${solar ? "desconecta la planta de la red" : "apagado solo deja un latido cada 60 s"}</span></div></div>
    <div class="control"><h5>Intervalo de muestreo <span>${iVal} s</span></h5>${deslizador("c-int", iMin, iMax, iMin >= 60 ? 60 : 5, iVal, " s", "intervalo")}</div>
    <div class="control ancho"><h5>Calibración <span>valor = medido × ganancia + offset</span></h5>
      <div class="fila"><select id="c-var" aria-label="Variable">${Object.keys(d.variables).map((k) => `<option>${esc(k)}</option>`).join("")}</select>
      <label class="nota">offset <input type="number" id="c-off" step="0.1" value="0"></label><label class="nota">ganancia <input type="number" id="c-gan" step="0.01" value="1"></label>
      <button class="btn chico" data-enviar="calibrar">Calibrar</button><button class="btn chico" data-accion="reset">Reset de fábrica</button></div></div>`;
  if (c.setpoint) h += `<div class="control"><h5>Setpoint <span>${fmt(u.setpoint)} °C</span></h5>${deslizador("c-sp", 16, 30, 0.5, u.setpoint ?? 23, " °C", "setpoint")}</div>`;
  if (c.modo) h += `<div class="control"><h5>Modo del aire <span>${MODOS[u.modo] ?? "–"}</span></h5>${seg("modo", "valor", [["apagado", "apagado"], ["auto", "auto"], ["ventilacion", "ventilación"], ["eco", "eco"]], u.modo)}</div>`;
  if (c.bomba) h += `<div class="control"><h5>Bomba <span>${u.bomba ? "funcionando" : "detenida"}</span></h5>${seg("bomba", "estado", [["auto", "auto"], ["on", "forzar on"], ["off", "forzar off"]], e.bomba_modo ?? 0)}</div>`;
  if (c.consumo) h += `<div class="control"><h5>Demanda de agua <span>×${fmt(e.factor_consumo ?? 1)}</span></h5>${deslizador("c-cons", 0.5, 3, 0.1, e.factor_consumo ?? 1, "", "consumo", "×")}</div>`;
  if (c.limite) h += `<div class="control"><h5>Límite del inversor <span>${fmt(e.limite_kw ?? 12)} kW</span></h5>${deslizador("c-lim", 0, 12, 0.5, e.limite_kw ?? 12, " kW", "limite")}</div>`;
  if (c.extractor) h += `<div class="control"><h5>Extractor <span>${u.extractor ? "encendido" : "apagado"}</span></h5>${seg("extractor", "estado", [["auto", "auto"], ["on", "forzar on"], ["off", "forzar off"]], e.extractor_modo ?? 0)}</div>`;
  if (c.led) h += `<div class="control"><h5>LED del ESP32 <span>${e.led ? "encendido" : "apagado"}</span></h5><div class="fila"><button class="interruptor ${e.led ? "on" : ""}" role="switch" aria-checked="${!!e.led}" data-accion="led" data-p='{"estado":"${e.led ? "off" : "on"}"}' aria-label="LED"></button><span class="nota">actuador del firmware</span></div></div>`;
  if (c.velocidad) h += `<div class="control"><h5>Velocidad de repetición <span>×${e.velocidad ?? 1}</span></h5>${deslizador("c-vel", 1, 20, 1, e.velocidad ?? 1, "", "velocidad", "×")}</div>`;
  if (c.saltar) h += `<div class="control"><h5>Saltar filas del dataset <span>fila ${e.fila ?? "–"}</span></h5><div class="fila"><input type="number" id="c-salto" value="60" step="10" aria-label="Filas"><button class="btn chico" data-enviar="saltar">Saltar</button></div></div>`;
  $("#p-controles").innerHTML = h;
  $$("#p-controles input[type=range]").forEach((i) => i.addEventListener("input", () => { const o = $(`#o-${i.id}`); o.textContent = `${o.dataset.pre}${i.value}${o.dataset.suf}`; }));
}
$("#p-controles").addEventListener("click", (e) => {
  const b = e.target.closest("[data-accion],[data-enviar]"); if (!b) return;
  if (b.dataset.accion) return enviar(b.dataset.accion, b.dataset.p ? JSON.parse(b.dataset.p) : {}, b);
  const v = (s) => Number($(s).value);
  const p = { intervalo: () => ({ segundos: v("#c-int") }), calibrar: () => ({ variable: $("#c-var").value, offset: v("#c-off"), ganancia: v("#c-gan") }), setpoint: () => ({ valor: v("#c-sp") }),
    consumo: () => ({ factor: v("#c-cons") }), limite: () => ({ kw: v("#c-lim") }), velocidad: () => ({ factor: v("#c-vel") }), saltar: () => ({ filas: v("#c-salto") }) }[b.dataset.enviar]();
  enviar(b.dataset.enviar, p, b);
});
async function enviar(accion, params, boton) {
  const id = E.abierto, clave = $("#p-clave").value.trim();
  if (!clave) { toast("Falta la clave de control", "Escríbela en «Clave de control», debajo de los controles.", "mal"); $("#p-clave").focus(); return; }
  guardar("clave", clave);
  if (boton) boton.disabled = true;
  try {
    const r = await api(`/api/dispositivos/${encodeURIComponent(id)}/comando`, { method: "POST", headers: { "Content-Type": "application/json", "X-Clave": clave }, body: JSON.stringify({ accion, params }) });
    if (r.ack) { acksVistos.add(r.cmd_id); toast(`${r.ack.ok ? "El dispositivo aceptó" : "El dispositivo rechazó"}: ${accion}`, `${id} · ${r.ack.detalle} · ida y vuelta ${fmtMs(r.ack.rtt_ms)}`, r.ack.ok ? "ok" : "mal"); }
    else if (acksRecientes.has(r.cmd_id)) {
      const a = acksRecientes.get(r.cmd_id);
      toast(`${a.ok ? "El dispositivo aceptó" : "El dispositivo rechazó"}: ${accion}`, `${id} · ${a.detalle} · ida y vuelta ${fmtMs(a.rtt_ms)}`, a.ok ? "ok" : "mal");
    } else { E.pendientes[r.cmd_id] = true; toast(`Comando enviado: ${accion}`, r.via, "cmd"); }
  } catch (e) {
    if (e.status === 401) { toast("Clave de control incorrecta", "El comando no salió de la plataforma.", "mal"); guardar("clave", ""); $("#p-clave").select(); }
    else toast(`No se pudo enviar (${e.status || "red"})`, e.cuerpo?.detail || e.message, "mal");
  } finally { if (boton) setTimeout(() => { boton.disabled = false; }, 600); }
}
function ayuda() { const d = E.disp[E.abierto]; $("#p-ayuda").textContent = d?.comandos[$("#p-accion").value] || ""; }
$("#p-accion").addEventListener("change", ayuda);
$("#p-json-enviar").addEventListener("click", () => {
  let p; try { p = JSON.parse($("#p-params").value || "{}"); } catch (e) { toast("El JSON no es válido", "", "mal"); return; }
  enviar($("#p-accion").value, p, $("#p-json-enviar"));
});
function pintarCmds() {
  const l = E.comandos.filter((c) => c.dispositivo === E.abierto).slice(0, 8);
  $("#p-cmds").innerHTML = l.map((c) => `<li><div><b>${esc(c.accion)}</b> <small>${esc(JSON.stringify(c.params))} · ${esc(c.origen)}</small><br><small>${fecha(c.ts)}</small></div>
    <div>${c.ack ? `<span class="${c.ack.ok ? "ok" : "mal"}">${icono(c.ack.ok ? "ok" : "x", 14)}</span> <small>${fmtMs(c.ack.rtt_ms)}</small>` : "<small>esperando</small>"}</div></li>`).join("") || `<li class="vacio">Todavía no ha recibido comandos.</li>`;
}
$("#p-rango").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  E.rango = Number(b.dataset.h); $$("#p-rango button").forEach((x) => x.classList.toggle("activo", x === b)); cargarGraficas();
});
async function cargarGraficas() {
  const id = E.abierto; if (!id) return;
  E.charts.forEach((c) => c.destroy()); E.charts = [];
  const cont = $("#p-graficas");
  cont.innerHTML = `<p class="vacio" style="grid-column:1/-1">Leyendo ${E.rango} h de InfluxDB…</p>`;
  let h;
  try { h = await api(`/api/historia/${id}?horas=${E.rango}&puntos=180`); } catch (e) { cont.innerHTML = `<p class="vacio">No se pudo leer la historia.</p>`; return; }
  if (E.abierto !== id) return;
  const d = E.disp[id], vars = Object.keys(d.variables).filter((k) => h.series[k]?.length);
  if (!vars.length) { cont.innerHTML = `<p class="vacio" style="grid-column:1/-1">Sin datos en este rango.</p>`; return; }
  cont.innerHTML = vars.map((k) => {
    const ys = h.series[k].map((p) => p[1]), prom = ys.reduce((a, b) => a + b, 0) / ys.length;
    return `<div class="grafica"><div class="g-cab"><b>${esc(k.replace(/_/g, " "))}</b><span>${esc(d.variables[k].unidad)}</span></div>
      <div class="g-stats"><span>mín <b>${fmt(Math.min(...ys))}</b></span><span>prom <b>${fmt(prom)}</b></span><span>máx <b>${fmt(Math.max(...ys))}</b></span></div><canvas data-var="${esc(k)}" role="img" aria-label="Gráfica de ${esc(k)}"></canvas></div>`;
  }).join("");
  const col = css(COLOR[d.tipo]), rej = css("--borde"), txt = css("--suave");
  for (const cv of $$("canvas", cont)) {
    const k = cv.dataset.var, s = h.series[k];
    const ch = new Chart(cv, {
      type: "line",
      data: { datasets: [{ data: s.map(([x, y]) => ({ x, y })), borderColor: col, backgroundColor: col + "1f", fill: true, borderWidth: 1.6, pointRadius: 0, tension: .25, stepped: ["on/off", "0/1"].includes(d.variables[k].unidad) || k === "modo" ? "after" : false }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, parsing: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: (it) => fecha(it[0].parsed.x), label: (it) => `${valor(d, k, it.parsed.y)} ${unidad(d, k)}` } } },
        scales: {
          x: { type: "linear", min: s[0][0], max: s[s.length - 1][0], grid: { color: rej }, ticks: { color: txt, maxTicksLimit: 5, font: { size: 10, family: "JetBrains Mono" }, callback: (v) => (E.rango > 24 ? fecha(v) : hora(v, false)) } },
          y: { grid: { color: rej }, ticks: { color: txt, maxTicksLimit: 4, font: { size: 10, family: "JetBrains Mono" } } },
        },
      },
    });
    ch.$var = k; E.charts.push(ch);
  }
}
function empujar(ev) {
  if (E.rango > 24) return;
  for (const ch of E.charts) if (ev.v && ch.$var in ev.v) { ch.data.datasets[0].data.push({ x: ev.ts, y: ev.v[ch.$var] }); ch.options.scales.x.max = ev.ts; ch.update("none"); }
}

// ================================================================== arranque
async function iniciar() {
  try { await cargarDispositivos(); } catch (e) { toast("No se pudo conectar con la API", e.message, "mal"); return; }
  $("#a-disp").innerHTML = Object.keys(FAMILIAS).map((t) => `<optgroup label="${FAMILIAS[t][0]}">${E.orden.filter((id) => E.disp[id].tipo === t).map((id) => `<option value="${esc(id)}">${esc(E.disp[id].nombre)}</option>`).join("")}</optgroup>`).join("");
  $("#a-disp").value = E.anaDisp;
  pintarFamilias(); dibujarFlujo(); indicadores();
  conectar();
  cargarReglas().then(cargarAlertas); cargarComandos(); cargarProtocolos(); cargarSparks(); cargarAnalisis(); iniciarMapa();
  setInterval(() => {
    for (const el of $$("[data-edad]")) { const d = E.disp[el.dataset.edad]; if (d) el.textContent = edad(el.dataset.edad, d); }
    cuentasProto(); indicadores();
    if ($("#vivo").classList.contains("ok")) $("#vivo-txt").textContent = `en vivo · ${(E.ventana.filter((t) => t > Date.now() - 60000).length / 60).toFixed(1)} msg/s`;
  }, 1000);
  setInterval(dibujarSpark, 5000);
  setInterval(() => cargarDispositivos().catch(() => {}), 30000);
  setInterval(cargarProtocolos, 30000);
  setInterval(cargarAlertas, 45000);
  addEventListener("resize", () => { dibujarSpark(); mapa?.invalidateSize(); });
  setTimeout(() => { mapa?.invalidateSize(); dibujarSpark(); }, 700);
}
iniciar();
