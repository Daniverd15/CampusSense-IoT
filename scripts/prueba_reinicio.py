#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueba de reinicio: reinicia la VM completa y mide cuánto tarda TODO en volver solo.

No toca nada después del reinicio: Docker arranca con el sistema y los 11 contenedores tienen
`restart: unless-stopped`. Comprueba desde Internet:
  1. cuándo vuelve HTTPS (Caddy) y la API,
  2. cuándo los 11 dispositivos permanentes vuelven a estar en línea,
  3. que el estado ordenado por retroceso sobrevivió (intervalos, modo del HVAC, seq),
  4. cuánto duró el hueco de datos.

Uso:  VM_SSH="ssh -i <llave> azureuser@<ip>" python scripts/prueba_reinicio.py [salida.txt]
"""
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

URL = os.environ.get("CAMPUS_URL", "https://campussense-unab.northcentralus.cloudapp.azure.com")
SSH = shlex.split(os.environ["VM_SSH"])
lineas = []


def log(t):
    linea = "%s  %s" % (datetime.now(timezone.utc).strftime("%H:%M:%S"), t)
    print(linea, flush=True)
    lineas.append(linea)


def get(ruta):
    with urllib.request.urlopen(URL + ruta, timeout=8) as r:
        return json.loads(r.read())


def foto():
    devs = {d["id"]: d for d in get("/api/dispositivos")}
    return {i: {"en_linea": d.get("en_linea"), "ts": d.get("ts"), "seq": d.get("seq"),
                "intervalo_s": (d.get("estado") or {}).get("intervalo_s")} for i, d in devs.items()}


antes = foto()
hvac = get("/api/dispositivos/twin-hvac-aula101")["ultimo"].get("modo")
log("antes: %d/12 en línea · HVAC modo=%s · uptime VM: %s" % (
    sum(1 for v in antes.values() if v["en_linea"]), hvac,
    subprocess.run(SSH + ["uptime -p"], capture_output=True, text=True).stdout.strip()))

log("reiniciando la VM (sudo reboot)…")
t0 = time.time()
subprocess.run(SSH + ["sudo systemctl reboot"], capture_output=True, text=True)
time.sleep(5)

hitos, primero = {}, {}
permanentes = [i for i in antes if i != "esp32-wokwi"]
while time.time() - t0 < 600:
    try:
        get("/api/salud")
        hitos.setdefault("https_api", time.time() - t0)
        for i, d in foto().items():          # primer dato NUEVO (ts posterior al reinicio) de cada dispositivo
            if i in permanentes and i not in primero and (d["ts"] or 0) / 1000 > t0:
                primero[i] = (d["ts"] / 1000) - t0
        if len(primero) == len(permanentes):
            hitos["11_en_linea"] = max(primero.values())
            break
    except Exception:
        pass
    time.sleep(3)

log("HTTPS y API de vuelta a los %.0f s" % hitos.get("https_api", -1))
for i in sorted(primero, key=primero.get):
    log("   primer dato nuevo de %-18s a los %4.0f s" % (i, primero[i]))
log("los 11 dispositivos permanentes enviaron datos nuevos a los %.0f s" % hitos.get("11_en_linea", -1))

time.sleep(60)  # dejar que todos publiquen al menos una vez
despues = foto()
hvac2 = get("/api/dispositivos/twin-hvac-aula101")["ultimo"].get("modo")
ok_int = [i for i in antes if antes[i]["intervalo_s"] == despues[i]["intervalo_s"]]
seq_sigue = [i for i in antes if antes[i]["seq"] and despues[i]["seq"] and despues[i]["seq"] > antes[i]["seq"]]
log("estado conservado: intervalo igual en %d/12 dispositivos · HVAC modo %s → %s" % (len(ok_int), hvac, hvac2))
salud = get("/api/salud")
log("historial recuperado por la API: %s comandos desde el 8-nov" % salud.get("comandos_total"))
log("contador seq: siguió en %d/12; los demás lo reinician con su contenedor (cada dato se ordena por su ts)" % len(seq_sigue))
contenedores = subprocess.run(SSH + ["cd ~/campus && docker compose ps --format '{{.Name}} {{.Status}}'"],
                              capture_output=True, text=True).stdout.strip()
log("contenedores después del reinicio:\n" + contenedores)
log("uptime VM: %s" % subprocess.run(SSH + ["uptime -p"], capture_output=True, text=True).stdout.strip())
log("RESULTADO: sin intervención; HTTPS a los %.0f s y los 11 dispositivos con datos nuevos a los %.0f s"
    % (hitos.get("https_api", -1), hitos.get("11_en_linea", -1)))

if len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write("Prueba de reinicio de la VM · %s\n\n" % datetime.now(timezone.utc).strftime("%Y-%m-%d") + "\n".join(lineas) + "\n")
