#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecuta la consulta de cada panel de los dashboards contra la API de Grafana (/api/ds/query) y reporta
errores de Flux o paneles sin datos. Se corre en la VM:  python3 grafana/verificar_paneles.py [horas]
"""
import base64
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

HORAS = float(sys.argv[1]) if len(sys.argv) > 1 else 1
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
AUTH = "Basic " + base64.b64encode(("admin:" + env["GRAFANA_ADMIN_PASS"]).encode()).decode()
URL = "http://127.0.0.1:8081/grafana/api/ds/query"
fin = int(time.time() * 1000)
ini = fin - int(HORAS * 3600 * 1000)
malos = 0
for ruta in sorted(glob.glob("grafana/dashboards/*.json")):
    d = json.load(open(ruta, encoding="utf-8"))
    for p in d["panels"]:
        for t in p.get("targets", []):
            cuerpo = {"from": str(ini), "to": str(fin), "queries": [{"refId": t["refId"], "datasource": t["datasource"],
                                                                     "query": t["query"], "intervalMs": 60000, "maxDataPoints": 500}]}
            req = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": AUTH})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    res = json.loads(r.read())["results"][t["refId"]]
                err = res.get("error")
                filas = sum(len(f["data"]["values"][0]) if f.get("data", {}).get("values") else 0 for f in res.get("frames", []))
            except urllib.error.HTTPError as e:
                err, filas = "%s %s" % (e.code, e.read()[:200]), 0
            estado = "ERROR " + str(err)[:160] if err else ("ok" if filas else "SIN DATOS")
            if err or not filas:
                malos += 1
            print("%-22s %-55s %s %s" % (os.path.basename(ruta)[:22], (p.get("title") or "")[:55], t["refId"],
                                         estado if err or not filas else "ok (%d filas)" % filas))
print("\npaneles con problema:", malos)
