#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gráficas del informe a partir de mediciones/export (ventana oficial 9-nov 04:19Z -> 15-nov 04:19Z).
Uso: python informe/graficas.py  ->  informe/graficas/*.png
"""
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(RAIZ, "plataforma"))
from registro import DISPOSITIVOS  # noqa: E402

EXP = os.path.join(RAIZ, "mediciones", "export")
OUT = os.path.join(RAIZ, "informe", "graficas")
os.makedirs(OUT, exist_ok=True)
COLOR = {"real": "#2563EB", "twin": "#7B35B3", "api": "#0B8574", "dataset": "#BE185D"}
MARCA, NARANJA, TEXTO, SUAVE, BORDE = "#6D2CA0", "#F59C00", "#1D1428", "#5F566C", "#E3DCEC"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9, "axes.edgecolor": BORDE, "axes.labelcolor": SUAVE, "xtick.color": SUAVE,
                     "ytick.color": SUAVE, "axes.titleweight": "semibold", "axes.titlesize": 10, "axes.titlecolor": TEXTO,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#EEE9F4", "grid.linewidth": .8,
                     "figure.dpi": 150, "savefig.bbox": "tight", "savefig.facecolor": "white"})
FMT_FECHA = mdates.DateFormatter("%d-%b\n%H:%M")


def serie(dev):
    ruta = os.path.join(EXP, "series_%s.csv" % dev)
    if not os.path.exists(ruta):
        return None
    df = pd.read_csv(ruta)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601").dt.tz_convert("America/Bogota").dt.tz_localize(None)
    return df.set_index("ts")


EST = json.load(open(os.path.join(EXP, "estadisticas.json"), encoding="utf-8"))
PRO = json.load(open(os.path.join(EXP, "protocolos.json"), encoding="utf-8"))
RET = json.load(open(os.path.join(RAIZ, "mediciones", "prueba_retroceso.json"), encoding="utf-8"))


def fmt(x):
    a = abs(x)
    return "%.0f" % x if a >= 100 else "%.1f" % x if a >= 10 else "%.2f" % x if a >= 1 else "%.3f" % x


# ------------------------------------------------------------------ 1. mensajes por dispositivo
cont = {}
for d in DISPOSITIVOS:
    st = EST.get(d, {})
    cont[d] = int(max((v.get("count", 0) for v in st.values()), default=0))
orden = sorted(cont, key=lambda d: -cont[d])
fig, ax = plt.subplots(figsize=(9, 3.6))
b = ax.barh(orden[::-1], [cont[d] for d in orden[::-1]], color=[COLOR[DISPOSITIVOS[d]["tipo"]] for d in orden[::-1]])
for r, d in zip(b, orden[::-1]):
    ax.text(r.get_width() + 300, r.get_y() + r.get_height() / 2, "{:,}".format(cont[d]).replace(",", "."), va="center", fontsize=8, color=TEXTO)
ax.set_xlabel("mensajes guardados en InfluxDB (ventana de 6 días)")
ax.set_title("Mensajes por dispositivo · total %s" % "{:,}".format(sum(cont.values())).replace(",", "."), loc="left")
ax.grid(axis="y", visible=False)
from matplotlib.patches import Patch  # noqa: E402
ax.legend(handles=[Patch(color=c, label=t) for t, c in [("real", COLOR["real"]), ("gemelo", COLOR["twin"]), ("API", COLOR["api"]), ("dataset", COLOR["dataset"])]],
          loc="lower right", frameon=False, fontsize=8)
fig.savefig(os.path.join(OUT, "g01_mensajes.png"))
plt.close(fig)

# ------------------------------------------------------------------ 2. una figura por dispositivo
for d, reg in DISPOSITIVOS.items():
    df = serie(d)
    if df is None or len(df) < 10:
        continue
    vars_ = [v for v in reg["variables"] if v in df.columns]
    n = len(vars_)
    cols = 2
    filas = (n + 1) // 2
    fig, axs = plt.subplots(filas, cols, figsize=(10, 1.9 * filas + .4), sharex=True, squeeze=False)
    col = COLOR[reg["tipo"]]
    for i, v in enumerate(vars_):
        ax = axs[i // cols][i % cols]
        s = df[v].dropna()
        st = EST.get(d, {}).get(v, {})
        binaria = reg["variables"][v][0] in ("on/off", "0/1")
        if binaria:
            ax.fill_between(s.index, s.values, step="post", color=col, alpha=.25, linewidth=0)
            ax.step(s.index, s.values, where="post", color=col, linewidth=1)
        else:
            ax.plot(s.index, s.values, color=col, linewidth=1)
            ax.fill_between(s.index, s.values, s.min(), color=col, alpha=.08, linewidth=0)
        if st:
            ax.axhline(st["mean"], color=NARANJA, linewidth=.9, linestyle="--")
            ax.set_title("%s (%s)" % (v.replace("_", " "), reg["variables"][v][0]), loc="left", fontsize=9)
            ax.text(.995, .97, "mín %s · prom %s · máx %s" % (fmt(st["min"]), fmt(st["mean"]), fmt(st["max"])), transform=ax.transAxes,
                    ha="right", va="top", fontsize=7.5, color=SUAVE, bbox=dict(facecolor="white", edgecolor="none", alpha=.8, pad=1))
        ax.xaxis.set_major_formatter(FMT_FECHA)
        ax.xaxis.set_major_locator(mdates.DayLocator())
    for j in range(n, filas * cols):
        axs[j // cols][j % cols].axis("off")
    fig.suptitle("%s · %s · %s" % (reg["nombre"], reg["protocolo"].upper(), d), x=.01, ha="left", fontsize=11, fontweight="semibold", color=TEXTO)
    fig.text(.01, -.01, "Promedio cada 10 min, hora de Bogotá. Línea naranja: promedio de la ventana. Mín/prom/máx calculados en InfluxDB sobre los datos crudos.",
             fontsize=7.5, color=SUAVE)
    fig.tight_layout(rect=(0, 0, 1, .97))
    fig.savefig(os.path.join(OUT, "dev_%s.png" % d))
    plt.close(fig)

# ------------------------------------------------------------------ 3. perfiles por hora del dia
per = pd.read_csv(os.path.join(EXP, "perfil_horario.csv"))
P = lambda d, v: per[(per.dispositivo == d) & (per.variable == v)].sort_values("hora_bogota")
fig, axs = plt.subplots(2, 2, figsize=(10, 6))
a = axs[0][0]
p1, p2 = P("aula-101", "co2"), P("aula-101", "ocupacion")
a.bar(p2.hora_bogota, p2.promedio, color=COLOR["real"], alpha=.25, label="ocupación (personas)")
a2 = a.twinx()
a2.plot(p1.hora_bogota, p1.promedio, color=COLOR["real"], marker="o", ms=3, label="CO₂ (ppm)")
a2.axhline(1000, color="#C2253A", linestyle="--", linewidth=.8)
a.set_title("Aula 101: CO₂ sigue a la ocupación", loc="left"); a.set_ylabel("personas"); a2.set_ylabel("CO₂ ppm"); a2.grid(False)
a = axs[0][1]
a.plot(P("medidor-bloque-a", "potencia").hora_bogota, P("medidor-bloque-a", "potencia").promedio, color=COLOR["real"], marker="o", ms=3, label="red Bloque A")
a.plot(P("twin-panel-solar", "potencia").hora_bogota, P("twin-panel-solar", "potencia").promedio, color=NARANJA, marker="o", ms=3, label="solar")
a.set_title("Energía: la solar recorta la demanda al mediodía", loc="left"); a.set_ylabel("kW"); a.legend(frameon=False, fontsize=8)
a = axs[1][0]
a.plot(P("twin-tanque-agua", "nivel").hora_bogota, P("twin-tanque-agua", "nivel").promedio, color=COLOR["twin"], marker="o", ms=3)
a3 = a.twinx()
a3.bar(P("twin-tanque-agua", "caudal_salida").hora_bogota, P("twin-tanque-agua", "caudal_salida").promedio, color=COLOR["twin"], alpha=.2)
a.set_title("Tanque: nivel (línea) y consumo (barras)", loc="left"); a.set_ylabel("nivel %"); a3.set_ylabel("L/min"); a3.grid(False)
a = axs[1][1]
a.plot(P("api-clima-unab", "temperatura").hora_bogota, P("api-clima-unab", "temperatura").promedio, color=COLOR["api"], marker="o", ms=3, label="temperatura exterior")
a4 = a.twinx()
a4.plot(P("api-clima-unab", "nubosidad").hora_bogota, P("api-clima-unab", "nubosidad").promedio, color=SUAVE, linestyle="--", label="nubosidad")
a.set_title("Clima real del campus (Azure Maps)", loc="left"); a.set_ylabel("°C"); a4.set_ylabel("nubosidad %"); a4.grid(False)
for ax in axs.flat:
    ax.set_xlabel("hora del día (Bogotá)"); ax.set_xticks(range(0, 24, 3))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "g20_perfiles.png"))
plt.close(fig)

# ------------------------------------------------------------------ 4. lazo cerrado R1 en un dia de clase
aula, hvac = serie("aula-101"), serie("twin-hvac-aula101")
reglas = pd.read_csv(os.path.join(EXP, "reglas.csv"))
reglas["ts"] = pd.to_datetime(reglas["ts"], utc=True, format="ISO8601").dt.tz_convert("America/Bogota").dt.tz_localize(None)
dia0, dia1 = pd.Timestamp("2026-11-10 06:00"), pd.Timestamp("2026-11-10 23:00")
fig, (a, b) = plt.subplots(2, 1, figsize=(10, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]})
s = aula.loc[dia0:dia1]
a.plot(s.index, s["co2"], color=COLOR["real"], linewidth=1.3, label="CO₂ aula-101")
a.axhline(1000, color="#C2253A", linestyle="--", linewidth=.9); a.text(dia0, 1010, " 1000 ppm: dispara R1", color="#C2253A", fontsize=7.5)
a.axhline(750, color=COLOR["api"], linestyle="--", linewidth=.9); a.text(dia0, 690, " 750 ppm: libera R1", color=COLOR["api"], fontsize=7.5)
ra = reglas[(reglas.origen == "regla R1") & (reglas.ts >= dia0) & (reglas.ts <= dia1)]
for _, r in ra.iterrows():
    vent = "ventilacion" in r["params"]
    a.axvline(r.ts, color=NARANJA if vent else SUAVE, linewidth=.8, alpha=.8)
a.set_ylabel("CO₂ ppm"); a.set_title("Lazo cerrado del 10-nov: R1 manda ventilación (naranja) y vuelve a auto (gris) al bajar el CO₂", loc="left")
a2 = a.twinx(); a2.fill_between(s.index, s["ocupacion"], color=COLOR["real"], alpha=.12, step="post"); a2.set_ylabel("personas"); a2.grid(False)
h = hvac.loc[dia0:dia1]
b.step(h.index, h["modo"], where="post", color=COLOR["twin"]); b.set_yticks([0, 1, 2, 3]); b.set_yticklabels(["apagado", "auto", "ventilación", "eco"], fontsize=7.5)
b.set_title("Modo del gemelo HVAC (CoAP)", loc="left", fontsize=9)
b.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "g21_lazo_r1.png"))
plt.close(fig)

# ------------------------------------------------------------------ 5. gemelo digital: modelo vs medido
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.4), gridspec_kw={"width_ratios": [2.2, 1]})
s = aula.loc["2026-11-11 00:00":"2026-11-12 00:00"]; h = hvac.loc["2026-11-11 00:00":"2026-11-12 00:00"]
a.plot(s.index, s["temperatura"], color=COLOR["real"], label="medida (aula-101)")
a.plot(h.index, h["temp_modelo"], color=COLOR["twin"], linestyle="--", label="modelo del gemelo")
a.set_title("11-nov: temperatura medida vs predicha", loc="left"); a.set_ylabel("°C"); a.legend(frameon=False, fontsize=8)
a.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
err = hvac["error_modelo"].dropna()
b.hist(err, bins=40, color=COLOR["twin"], alpha=.8)
st = EST["twin-hvac-aula101"]["error_modelo"]
b.set_title("Error del modelo, 6 días", loc="left"); b.set_xlabel("medido − modelo (°C)")
b.text(.98, .95, "media %.2f °C\nσ %.2f °C" % (st["mean"], st["stddev"]), transform=b.transAxes, ha="right", va="top", fontsize=8, color=TEXTO)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "g22_gemelo.png"))
plt.close(fig)

# ------------------------------------------------------------------ 6. protocolos
res = RET["resultados"]
orden_p = ["mqtt", "coap", "stomp", "amqp", "mqtt-internet", "http"]
nombres = {"mqtt": "MQTT", "coap": "CoAP", "stomp": "STOMP", "amqp": "AMQP", "mqtt-internet": "MQTT\n(ESP32 por Internet)", "http": "HTTP\n(sondeo)"}
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.4))
med = [res[p]["rtt_mediana_ms"] for p in orden_p]
bars = a.bar([nombres[p] for p in orden_p], med, color=[MARCA, MARCA, MARCA, MARCA, "#3B1561", NARANJA])
a.set_yscale("log"); a.set_ylabel("ms (escala log)")
for r, v, p in zip(bars, med, orden_p):
    a.text(r.get_x() + r.get_width() / 2, v * 1.15, ("%.1f s" % (v / 1000)) if v >= 1000 else "%g ms" % v, ha="center", fontsize=8, color=TEXTO)
    a.text(r.get_x() + r.get_width() / 2, 0.75, "%d/%d" % (res[p]["ack_ok"], res[p]["comandos"]), ha="center", fontsize=7, color="white")
a.set_ylim(.6, 1e5); a.set_title("Retroceso: mediana del tiempo de ida y vuelta del ACK", loc="left"); a.tick_params(axis="x", labelsize=7.5)
pp = ["mqtt", "amqp", "stomp", "coap", "http"]
lat = [PRO[p]["latencia_mean_ms"] for p in pp]
msg = [PRO[p]["mensajes"] for p in pp]
b.bar([p.upper() for p in pp], lat, color=MARCA)
for i, (v, m) in enumerate(zip(lat, msg)):
    b.text(i, v + .1, "%.1f ms\n%s msj" % (v, "{:,}".format(m).replace(",", ".")), ha="center", fontsize=7.5, color=TEXTO)
b.set_ylabel("ms"); b.set_ylim(0, max(lat) * 1.6); b.set_title("Subida: latencia media dispositivo → InfluxDB", loc="left")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "g23_protocolos.png"))
plt.close(fig)

# ------------------------------------------------------------------ 7. linea de tiempo de alertas
al = pd.read_csv(os.path.join(EXP, "alertas.csv"))
al["ts"] = pd.to_datetime(al["ts"], utc=True, format="ISO8601").dt.tz_convert("America/Bogota").dt.tz_localize(None)
fin = pd.Timestamp("2026-11-14 23:19")
reglas_u = list(dict.fromkeys(al["regla"] + " · " + al["origen"]))
fig, ax = plt.subplots(figsize=(10, .42 * len(reglas_u) + 1))
for i, rg in enumerate(reglas_u):
    sub = al[(al["regla"] + " · " + al["origen"]) == rg].sort_values("ts")
    ini = None
    for _, r in sub.iterrows():
        if r.estado == "firing" and ini is None:
            ini = r.ts
        elif r.estado == "resolved" and ini is not None:
            ax.barh(i, (r.ts - ini).total_seconds() / 86400, left=mdates.date2num(ini), height=.55,
                    color=NARANJA if "reglas" in rg else MARCA)
            ini = None
    if ini is not None:
        ax.barh(i, (fin - ini).total_seconds() / 86400, left=mdates.date2num(ini), height=.55, color=NARANJA if "reglas" in rg else MARCA)
ax.set_yticks(range(len(reglas_u))); ax.set_yticklabels(reglas_u, fontsize=8)
ax.xaxis_date(); ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b")); ax.xaxis.set_major_locator(mdates.DayLocator())
ax.set_title("Alertas disparadas en la ventana: motor de reglas (naranja) y Grafana Alerting (morado)", loc="left")
ax.invert_yaxis(); ax.grid(axis="y", visible=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "g24_alertas.png"))
plt.close(fig)
print("OK", len(os.listdir(OUT)), "gráficas en", OUT)
