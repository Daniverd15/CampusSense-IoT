#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueba formal del retroceso: N comandos por protocolo contra la API publica y medicion del ACK.

Los comandos son inofensivos: vuelven a poner el intervalo de fabrica (o alternan el LED del ESP32).
Uso:  CONTROL_KEY=... python scripts/prueba_retroceso.py [salida.json]
"""
import json
import os
import statistics
import sys
import time
import urllib.request

URL = os.environ.get("CAMPUS_URL", "https://campussense-unab.northcentralus.cloudapp.azure.com")
CLAVE = os.environ["CONTROL_KEY"]
CASOS = [  # (protocolo, dispositivo, accion, params, repeticiones)
    ("mqtt", "aula-101", "intervalo", {"segundos": 15}, 20),
    ("amqp", "medidor-bloque-a", "intervalo", {"segundos": 30}, 20),
    ("stomp", "ds-ocupacion-uci", "intervalo", {"segundos": 60}, 20),
    ("coap", "twin-tanque-agua", "intervalo", {"segundos": 30}, 20),
    ("http", "twin-panel-solar", "intervalo", {"segundos": 30}, 5),
    ("mqtt-internet", "esp32-wokwi", "led", None, 10),
]


def llamar(ruta, cuerpo=None):
    req = urllib.request.Request(URL + ruta, data=json.dumps(cuerpo).encode() if cuerpo else None,
                                 method="POST" if cuerpo else "GET",
                                 headers={"Content-Type": "application/json", "X-Clave": CLAVE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def esperar_ack(cmd_id, limite_s):
    t0 = time.time()
    while time.time() - t0 < limite_s:
        for c in llamar("/api/comandos?n=40"):
            if c["cmd_id"] == cmd_id and c.get("ack"):
                return c["ack"]
        time.sleep(0.5)
    return None


SOLO = os.environ.get("SOLO", "").split(",") if os.environ.get("SOLO") else None
resultado = {}
for proto, dev, accion, params, n in CASOS:
    if SOLO and proto not in SOLO:
        continue
    rtts, fallos = [], 0
    for i in range(n):
        p = params if params is not None else {"estado": "on" if i % 2 == 0 else "off"}
        r = llamar("/api/dispositivos/%s/comando" % dev, {"accion": accion, "params": p})
        ack = r.get("ack") or esperar_ack(r["cmd_id"], 70 if proto == "http" else 15)
        if ack and ack.get("ok") and ack.get("rtt_ms") is not None:
            rtts.append(ack["rtt_ms"])
        else:
            fallos += 1
        time.sleep(0.3 if proto != "http" else 1)
    resultado[proto] = {"dispositivo": dev, "comandos": n, "ack_ok": len(rtts), "sin_ack": fallos,
                        "rtt_min_ms": min(rtts) if rtts else None, "rtt_mediana_ms": statistics.median(rtts) if rtts else None,
                        "rtt_media_ms": round(statistics.mean(rtts), 1) if rtts else None, "rtt_max_ms": max(rtts) if rtts else None,
                        "rtt_p95_ms": sorted(rtts)[max(0, int(len(rtts) * 0.95) - 1)] if rtts else None}
    print(proto, resultado[proto], flush=True)
salida = sys.argv[1] if len(sys.argv) > 1 else "mediciones/prueba_retroceso.json"
json.dump({"fecha_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "resultados": resultado}, open(salida, "w"), indent=1)
print("guardado en", salida)
