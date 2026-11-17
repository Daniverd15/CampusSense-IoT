#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta la ventana oficial de la toma (6 dias) desde InfluxDB para el informe.
Se corre en la VM desde ~/campus:  python3 scripts/exportar_toma.py  ->  export/
  series_<dispositivo>.csv   promedio cada 10 min de cada variable
  estadisticas.json          media, minimo, maximo, desviacion y muestras por dispositivo y variable (datos crudos)
  protocolos.json            mensajes, latencia de subida y RTT del ACK por protocolo
  reglas.csv / alertas.csv   comandos automaticos y transiciones de alertas
  perfil_horario.csv         promedio por hora del dia (hora de Bogota) de variables clave
"""
import csv
import io
import json
import os
import urllib.request

INICIO, FIN = "2026-11-09T04:19:00Z", "2026-11-15T04:19:00Z"
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
OUT = "export"
os.makedirs(OUT, exist_ok=True)
DISPOSITIVOS = ["aula-101", "lab-quimica", "medidor-bloque-a", "esp32-wokwi", "twin-hvac-aula101", "twin-tanque-agua", "twin-panel-solar",
                "api-clima-unab", "api-aire-unab", "api-bus-ruta1", "ds-ocupacion-uci", "ds-aire-uci"]


def q(flux):
    req = urllib.request.Request("http://127.0.0.1:8086/api/v2/query?org=unab", data=flux.encode(), method="POST",
                                 headers={"Authorization": "Token " + env["INFLUX_TOKEN"], "Content-Type": "application/vnd.flux",
                                          "Accept": "application/csv"})
    texto = urllib.request.urlopen(req, timeout=300).read().decode()
    filas = []
    for bloque in texto.strip().split("\r\n\r\n"):
        if bloque.strip():
            filas += list(csv.DictReader(io.StringIO(bloque)))
    return filas


R = 'from(bucket:"campus") |> range(start: %s, stop: %s) ' % (INICIO, FIN)
TEL = R + '|> filter(fn:(r)=> r._measurement=="telemetria" and r._field!="seq" and r._field!="lat_ms") '

# series de 10 min
for d in DISPOSITIVOS:
    filas = q(TEL + '|> filter(fn:(r)=> r.dispositivo=="%s") |> aggregateWindow(every: 10m, fn: mean, createEmpty: false)'
              ' |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value") |> group() |> sort(columns:["_time"])' % d)
    if not filas:
        continue
    cols = ["_time"] + sorted(k for k in filas[0] if k and not k.startswith("_") and k not in ("result", "table", "dispositivo", "tipo", "protocolo"))
    with open(os.path.join(OUT, "series_%s.csv" % d), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts"] + cols[1:])
        for r in filas:
            w.writerow([r["_time"]] + [r.get(c, "") for c in cols[1:]])
    print("series", d, len(filas))

# estadisticas sobre datos crudos
est = {}
for fn in ("mean", "min", "max", "stddev", "count"):
    for r in q(TEL + '|> group(columns:["dispositivo","_field"]) |> %s()' % fn):
        est.setdefault(r["dispositivo"], {}).setdefault(r["_field"], {})[fn] = float(r["_value"])
json.dump(est, open(os.path.join(OUT, "estadisticas.json"), "w"), indent=1, ensure_ascii=False)

# protocolos
pro = {}
for r in q(R + '|> filter(fn:(r)=> r._measurement=="telemetria" and r._field=="seq") |> group(columns:["protocolo"]) |> count()'):
    pro.setdefault(r["protocolo"], {})["mensajes"] = int(r["_value"])
for fn in ("mean", "median"):
    for r in q(R + '|> filter(fn:(r)=> r._measurement=="telemetria" and r._field=="lat_ms" and r.dispositivo!="esp32-wokwi") |> group(columns:["protocolo"]) |> %s()' % fn):
        pro.setdefault(r["protocolo"], {})["latencia_%s_ms" % fn] = round(float(r["_value"]), 2)
for fn in ("mean", "min", "max", "count"):
    for r in q('from(bucket:"campus") |> range(start: 2026-11-08T00:00:00Z) |> filter(fn:(r)=> r._measurement=="ack" and r._field=="rtt_ms") |> group(columns:["protocolo"]) |> %s()' % fn):
        pro.setdefault(r["protocolo"], {})["rtt_%s_ms" % fn] = round(float(r["_value"]), 1)
json.dump(pro, open(os.path.join(OUT, "protocolos.json"), "w"), indent=1)

# reglas y alertas
with open(os.path.join(OUT, "reglas.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts", "dispositivo", "accion", "origen", "params"])
    for r in q(R + '|> filter(fn:(r)=> r._measurement=="comandos" and r._field=="params") |> group() |> sort(columns:["_time"])'):
        w.writerow([r["_time"], r["dispositivo"], r["accion"], r["origen"], r["_value"]])
with open(os.path.join(OUT, "alertas.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts", "regla", "dispositivo", "severidad", "origen", "estado"])
    for r in q(R + '|> filter(fn:(r)=> r._measurement=="alertas" and r._field=="estado") |> group() |> sort(columns:["_time"])'):
        w.writerow([r["_time"], r["regla"], r["dispositivo"], r["severidad"], r["origen"], r["_value"]])

# perfil horario (hora de Bogota)
claves = [("aula-101", "co2"), ("aula-101", "ocupacion"), ("aula-101", "temperatura"), ("lab-quimica", "pm25"), ("medidor-bloque-a", "potencia"),
          ("twin-panel-solar", "potencia"), ("twin-tanque-agua", "nivel"), ("twin-tanque-agua", "caudal_salida"), ("api-clima-unab", "temperatura"),
          ("api-clima-unab", "nubosidad"), ("api-bus-ruta1", "velocidad"), ("ds-ocupacion-uci", "co2"), ("ds-aire-uci", "no2")]
with open(os.path.join(OUT, "perfil_horario.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["dispositivo", "variable", "hora_bogota", "promedio"])
    for d, v in claves:
        filas = q(R + '|> filter(fn:(r)=> r._measurement=="telemetria" and r.dispositivo=="%s" and r._field=="%s")'
                  ' |> map(fn:(r)=> ({r with hora: (int(v: uint(v: r._time)) / 3600000000000 + 19) %% 24}))'
                  ' |> group(columns:["hora"]) |> mean()' % (d, v))
        for r in sorted(filas, key=lambda x: int(x["hora"])):
            w.writerow([d, v, r["hora"], r["_value"]])
print("listo")
