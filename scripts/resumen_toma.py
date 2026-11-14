#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resumen de la toma de datos: mensajes, primer/ultimo dato y hueco maximo por dispositivo, alertas y comandos.
Se corre en la VM desde ~/campus:  python3 scripts/resumen_toma.py [inicio_iso] [fin_iso]
"""
import csv
import io
import sys
import urllib.request

INICIO = sys.argv[1] if len(sys.argv) > 1 else "2026-11-09T04:19:00Z"
FIN = sys.argv[2] if len(sys.argv) > 2 else "now()"
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))


def q(flux):
    req = urllib.request.Request("http://127.0.0.1:8086/api/v2/query?org=unab", data=flux.encode(), method="POST",
                                 headers={"Authorization": "Token " + env["INFLUX_TOKEN"], "Content-Type": "application/vnd.flux",
                                          "Accept": "application/csv"})
    texto = urllib.request.urlopen(req, timeout=180).read().decode()
    filas = []
    for bloque in texto.strip().split("\r\n\r\n"):
        if bloque.strip():
            filas += list(csv.DictReader(io.StringIO(bloque)))
    return filas


fin = FIN if FIN == "now()" else FIN
R = 'from(bucket:"campus") |> range(start: %s, stop: %s) ' % (INICIO, fin)
T = R + '|> filter(fn:(r)=> r._measurement=="telemetria" and r._field=="seq") |> group(columns:["dispositivo"]) '
cnt = {r["dispositivo"]: int(r["_value"]) for r in q(T + "|> count()")}
pri = {r["dispositivo"]: r["_time"][:16] for r in q(T + "|> first()")}
ult = {r["dispositivo"]: r["_time"][:16] for r in q(T + "|> last()")}
hue = {r["dispositivo"]: float(r["elapsed"]) for r in q(T + '|> elapsed(unit: 1s) |> max(column: "elapsed")')}
print("== ventana %s -> %s" % (INICIO, FIN))
print("%-20s %8s  %-16s  %-16s  %s" % ("dispositivo", "mensajes", "primero (UTC)", "ultimo (UTC)", "hueco max"))
for d in sorted(cnt):
    print("%-20s %8d  %-16s  %-16s  %6.0f s" % (d, cnt[d], pri[d], ult[d], hue.get(d, 0)))
print("total de mensajes:", sum(cnt.values()))
print("\n== alertas (transiciones)")
for r in q(R + '|> filter(fn:(r)=> r._measurement=="alertas" and r._field=="estado") |> group() |> sort(columns:["_time"])'):
    print(r["_time"][:19], r["regla"], "|", r["dispositivo"], "|", r["_value"], "|", r["origen"])
print("\n== comandos por origen")
for r in q(R + '|> filter(fn:(r)=> r._measurement=="comandos" and r._field=="cmd_id") |> group(columns:["origen"]) |> count()'):
    print(r["origen"], r["_value"])
