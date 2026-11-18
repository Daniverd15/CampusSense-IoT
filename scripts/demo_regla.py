#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demostración en vivo del lazo cerrado: calibrar → regla R1 → comando CoAP al gemelo HVAC → ACK.

1. Calibra el CO₂ del aula-101 con un offset (+1200 ppm por defecto) por MQTT.
2. Espera a que el promedio de 5 min supere 1000 ppm: la regla R1 manda al twin-hvac-aula101 a "ventilacion".
3. Muestra el comando automático y su ACK por CoAP.
4. Quita la calibración (reset): cuando el promedio baje de 750 ppm, R1 devuelve el HVAC a "auto".

Uso:  CONTROL_KEY=... python scripts/demo_regla.py [offset] [--con-correo]
      --con-correo: mantiene el CO₂ alto hasta que Grafana dispare "CO2 alto Aula 101" (unos 8 min),
                    que llega a la API y por correo (Brevo) al equipo; luego hace el reset.
      (Ctrl+C en cualquier momento deja el aula en su configuración de fábrica)
"""
import json
import os
import sys
import time
import urllib.request

URL = os.environ.get("CAMPUS_URL", "https://campussense-unab.northcentralus.cloudapp.azure.com")
CLAVE = os.environ["CONTROL_KEY"]
NUMS = [a for a in sys.argv[1:] if not a.startswith("--")]
OFFSET = float(NUMS[0]) if NUMS else 1200.0


def llamar(ruta, cuerpo=None):
    req = urllib.request.Request(URL + ruta, data=json.dumps(cuerpo).encode() if cuerpo else None,
                                 method="POST" if cuerpo else "GET",
                                 headers={"Content-Type": "application/json", "X-Clave": CLAVE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def comando(dev, accion, params=None):
    r = llamar("/api/dispositivos/%s/comando" % dev, {"accion": accion, "params": params or {}})
    print("  → %s %s %s · cmd_id %s · ACK %s" % (dev, accion, params or "", r.get("cmd_id"),
                                                 (r.get("ack") or {}).get("detalle", "pendiente")))
    return r


def esperar_regla(valor, limite_s):
    """Espera un comando de la regla R1 hacia el HVAC con el modo indicado y su ACK."""
    t0 = time.time()
    while time.time() - t0 < limite_s:
        for c in llamar("/api/comandos?n=30"):
            if (c.get("origen") == "regla R1" and c.get("ts", 0) / 1000 >= t0 - 5
                    and (c.get("params") or {}).get("valor") == valor and c.get("ack")):
                return c, time.time() - t0
        co2 = (llamar("/api/dispositivos/aula-101").get("ultimo") or {}).get("co2")
        print("  … %3.0f s · CO₂ del aula-101: %s ppm" % (time.time() - t0, co2), end="\r")
        time.sleep(5)
    return None, time.time() - t0


try:
    print("Paso 1 · calibrar el CO₂ del aula-101 (offset %+.0f ppm) por MQTT" % OFFSET)
    comando("aula-101", "calibrar", {"variable": "co2", "offset": OFFSET, "ganancia": 1})
    print("Paso 2 · esperar a que R1 actúe sola (promedio 5 min > 1000 ppm)")
    c, dt = esperar_regla("ventilacion", 420)
    if c:
        print("\n  ✔ R1 a los %.0f s: twin-hvac-aula101 → ventilación por CoAP, ACK en %s ms (%s)"
              % (dt, c["ack"].get("rtt_ms"), c["ack"].get("detalle")))
    else:
        print("\n  ✘ R1 no actuó en 7 min (¿el HVAC ya estaba en ventilación?)")
    if "--con-correo" in sys.argv:
        print("Paso 2b · esperar la alerta de Grafana (webhook a la API + correo al equipo)")
        t1 = time.time()
        while time.time() - t1 < 900:
            al = [a for a in llamar("/api/alertas?n=30")["historial"]
                  if a.get("origen") == "grafana" and a.get("estado") == "firing" and a["ts"] / 1000 >= t1 - dt - 5]
            if al:
                print("  ✔ Grafana: %s · %s → correo enviado al equipo" % (al[0]["regla"], al[0]["mensaje"]))
                break
            print("  … %3.0f s esperando a Grafana" % (time.time() - t1), end="\r")
            time.sleep(10)
finally:
    print("Paso 3 · quitar la calibración (reset de fábrica del aula-101)")
    comando("aula-101", "reset")
if "--sin-esperar" not in sys.argv:
    print("Paso 4 · esperar a que R1 devuelva el HVAC a auto (promedio < 750 ppm)")
    c, dt = esperar_regla("auto", 600)
    print("\n  ✔ HVAC de vuelta en auto a los %.0f s" % dt if c else "\n  (todavía no; la regla lo hará sola)")
