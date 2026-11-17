#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueba de humo y de seguridad de CampusSense contra la URL pública, desde cualquier PC.

Comprueba lo que debe funcionar (HTTPS, API, Grafana, dispositivos, un comando con ACK) y lo que
debe estar BLOQUEADO (puertos internos, MQTT anónimo, ACL del ESP32, endpoints sin clave).
No cambia nada: el comando de prueba vuelve a poner el intervalo de fábrica del aula 101.

Uso:  CONTROL_KEY=... ESP32_USER=... ESP32_PASS=... python scripts/prueba_humo.py [salida.txt]
      (sin las variables se omiten solo las pruebas que las necesitan)
"""
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

DOM = os.environ.get("CAMPUS_DOMINIO", "campussense-unab.northcentralus.cloudapp.azure.com")
URL = "https://" + DOM
CLAVE = os.environ.get("CONTROL_KEY")
E_USER, E_PASS = os.environ.get("ESP32_USER"), os.environ.get("ESP32_PASS")
lineas, total, bien = [], 0, 0


def reporte(ok, nombre, detalle=""):
    global total, bien
    total += 1
    bien += ok
    linea = "%s  %-58s %s" % ("OK  " if ok else "FALLA", nombre, detalle)
    print(linea)
    lineas.append(linea)


def seccion(t):
    print("\n== " + t)
    lineas.append("\n== " + t)


def http(ruta, metodo="GET", cuerpo=None, cabeceras=None, base=URL):
    req = urllib.request.Request(base + ruta, method=metodo,
                                 data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", **(cabeceras or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def puerto_abierto(p, t=3):
    try:
        socket.create_connection((DOM, p), timeout=t).close()
        return True
    except OSError:
        return False


def mqtt_conectar(usuario=None, clave=None):
    """Devuelve el código de CONNACK (0 = aceptado)."""
    res = {}
    c = mqtt.Client(client_id="humo-%d" % time.time_ns(), protocol=mqtt.MQTTv311)
    if usuario:
        c.username_pw_set(usuario, clave)
    c.on_connect = lambda cl, u, f, rc: res.setdefault("rc", rc)
    c.connect(DOM, 1883, 10)
    c.loop_start()
    for _ in range(50):
        if "rc" in res:
            break
        time.sleep(0.1)
    c.loop_stop()
    c.disconnect()
    return res.get("rc")


def mqtt_escuchar(usuario, clave, topico, segundos, accion=None):
    """Se suscribe y devuelve los mensajes que REALMENTE llegan como (tópico, carga).
    Mosquitto 2 concede cualquier suscripción y aplica la ACL al entregar cada mensaje."""
    recibidos = []
    c = mqtt.Client(client_id="humo-%d" % time.time_ns(), protocol=mqtt.MQTTv311)
    c.username_pw_set(usuario, clave)
    c.on_connect = lambda cl, u, f, rc: cl.subscribe(topico, 1)
    c.on_message = lambda cl, u, m: recibidos.append((m.topic, m.payload))
    c.connect(DOM, 1883, 10)
    c.loop_start()
    time.sleep(1.5)
    if accion:
        accion()
    time.sleep(segundos)
    c.loop_stop()
    c.disconnect()
    return recibidos


def mqtt_publicar(usuario, clave, topico, carga):
    c = mqtt.Client(client_id="humo-%d" % time.time_ns(), protocol=mqtt.MQTTv311)
    c.username_pw_set(usuario, clave)
    c.connect(DOM, 1883, 10)
    c.loop_start()
    c.publish(topico, carga, qos=1).wait_for_publish(5)
    time.sleep(0.5)
    c.loop_stop()
    c.disconnect()


inicio = datetime.now(timezone.utc)
lineas.append("Prueba de humo CampusSense · %s · %s" % (DOM, inicio.strftime("%Y-%m-%d %H:%M:%S UTC")))
print(lineas[0])

seccion("Nube y HTTPS")
ip = socket.gethostbyname(DOM)
reporte(True, "DNS resuelve", ip)
ctx = ssl.create_default_context()
with ctx.wrap_socket(socket.create_connection((DOM, 443), timeout=10), server_hostname=DOM) as s:
    cert = s.getpeercert()
emisor = dict(x[0] for x in cert["issuer"]).get("organizationName", "?")
vence = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
reporte(True, "Certificado TLS válido", "%s, vence %s" % (emisor, vence.date()))
try:
    urllib.request.urlopen(urllib.request.Request("http://" + DOM + "/", method="HEAD"), timeout=10)
    redirige = False
except urllib.error.HTTPError as e:
    redirige = e.code in (301, 308)
req = urllib.request.Request("http://" + DOM + "/")
opener = urllib.request.build_opener(type("NoRedir", (urllib.request.HTTPRedirectHandler,),
                                          {"redirect_request": lambda *a, **k: None}))
try:
    opener.open(req, timeout=10)
    cod = 200
except urllib.error.HTTPError as e:
    cod = e.code
reporte(cod in (301, 308), "HTTP (80) redirige a HTTPS", "código %s" % cod)

seccion("Servicios")
cod, cuerpo = http("/")
reporte(cod == 200 and b"CampusSense" in cuerpo, "Front (centro de control)", "HTTP %s" % cod)
cod, cuerpo = http("/api/salud")
salud = json.loads(cuerpo)
reporte(cod == 200 and salud.get("ok"), "API /api/salud",
        "%s/%s dispositivos en línea" % (salud.get("en_linea"), salud.get("dispositivos")))
cod, cuerpo = http("/docs")
reporte(cod == 200, "Documentación OpenAPI /docs", "HTTP %s" % cod)
cod, cuerpo = http("/grafana/api/health")
reporte(cod == 200 and json.loads(cuerpo).get("database") == "ok", "Grafana /grafana/api/health", "HTTP %s" % cod)
cod, cuerpo = http("/api/dispositivos")
devs = json.loads(cuerpo)
viejos = [d["id"] for d in devs if not d.get("en_linea") and d["id"] != "esp32-wokwi"]
reporte(len(devs) == 12 and not viejos, "12 dispositivos registrados, 11 permanentes en línea",
        "fuera: %s" % (", ".join(viejos) or "ninguno (el ESP32 solo en sesiones Wokwi)"))
cod, cuerpo = http("/api/resumen/aula-101?ventana=oficial")
r = json.loads(cuerpo)
reporte(cod == 200, "Resumen de la ventana oficial (aula-101)", str(r)[:70])

seccion("Puertos: solo 22, 80, 443 y 1883 hacia Internet")
for p, nombre in [(443, "HTTPS"), (1883, "MQTT")]:
    reporte(puerto_abierto(p), "Puerto %d (%s) abierto" % (p, nombre))
for p, nombre in [(5672, "AMQP RabbitMQ"), (61613, "STOMP"), (15672, "consola RabbitMQ"),
                  (8086, "InfluxDB"), (3000, "Grafana directo"), (8000, "API directa"), (8081, "Caddy local")]:
    reporte(not puerto_abierto(p), "Puerto %d (%s) cerrado" % (p, nombre))

seccion("Seguridad MQTT")
rc = mqtt_conectar()
reporte(rc not in (0, None), "Conexión anónima rechazada", "CONNACK %s" % rc)
rc = mqtt_conectar("intruso", "clave-falsa")
reporte(rc not in (0, None), "Usuario/clave falsos rechazados", "CONNACK %s" % rc)
if E_USER:
    reporte(mqtt_conectar(E_USER, E_PASS) == 0, "Usuario del ESP32 aceptado", "CONNACK 0")
    ADM_U, ADM_P = os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASS")
    if ADM_U:
        n = len(mqtt_escuchar(ADM_U, ADM_P, "campus/#", 6))
        reporte(n > 0, "Control: un usuario de la plataforma SÍ ve campus/#", "%d mensajes en 6 s" % n)
    n = len(mqtt_escuchar(E_USER, E_PASS, "campus/#", 6))
    reporte(n == 0, "ACL: el ESP32 suscrito a campus/# no recibe nada", "%d mensajes en 6 s" % n)
    if CLAVE:
        envio = lambda: http("/api/dispositivos/aula-101/comando", "POST",
                             {"accion": "intervalo", "params": {"segundos": 15}}, {"X-Clave": CLAVE})
        n = len(mqtt_escuchar(E_USER, E_PASS, "campus/cmd/aula-101", 3, envio))
        reporte(n == 0, "ACL: el ESP32 no recibe los comandos de otro equipo", "%d mensajes" % n)
    if ADM_U:
        marca = b"prueba-acl-humo"  # no es JSON: aunque pasara, el ingestor la descartaría
        espia = lambda: mqtt_publicar(E_USER, E_PASS, "campus/tele/aula-101", marca)
        llegan = [c for _, c in mqtt_escuchar(ADM_U, ADM_P, "campus/tele/aula-101", 3, espia) if c == marca]
        reporte(not llegan, "ACL: el ESP32 no puede suplantar al aula-101", "%d mensajes falsos entregados" % len(llegan))
else:
    print("   (sin ESP32_USER/ESP32_PASS: se omiten las pruebas de ACL)")

seccion("Seguridad de la API")
cod, _ = http("/api/dispositivos/aula-101/comando", "POST", {"accion": "apagar"})
reporte(cod == 401, "Comando SIN clave rechazado", "HTTP %s" % cod)
cod, _ = http("/api/dispositivos/aula-101/comando", "POST", {"accion": "apagar"}, {"X-Clave": "falsa"})
reporte(cod == 401, "Comando con clave falsa rechazado", "HTTP %s" % cod)
cod, _ = http("/api/ingest/twin-panel-solar", "POST", {"id": "twin-panel-solar"})
reporte(cod == 401, "Ingesta HTTP sin token rechazada", "HTTP %s" % cod)
cod, _ = http("/api/alertas/grafana", "POST", {"alerts": []})
reporte(cod == 401, "Webhook de alertas sin token rechazado", "HTTP %s" % cod)
cod, _ = http("/grafana/api/dashboards/db", "POST", {"dashboard": {"title": "x"}})
reporte(cod in (401, 403), "Grafana anónimo no puede crear tableros", "HTTP %s" % cod)

seccion("Retroceso de extremo a extremo")
if CLAVE:
    t0 = time.time()
    cod, cuerpo = http("/api/dispositivos/aula-101/comando", "POST",
                       {"accion": "intervalo", "params": {"segundos": 15}}, {"X-Clave": CLAVE})
    r = json.loads(cuerpo)
    ack = r.get("ack")
    while not ack and time.time() - t0 < 15:
        time.sleep(0.5)
        ack = next((c.get("ack") for c in json.loads(http("/api/comandos?n=20")[1])
                    if c["cmd_id"] == r.get("cmd_id")), None)
    reporte(bool(ack and ack.get("ok")), "Comando MQTT a aula-101 con ACK",
            "RTT %s ms, ida y vuelta por Internet %.0f ms" % (ack and ack.get("rtt_ms"), (time.time() - t0) * 1000))
else:
    print("   (sin CONTROL_KEY: se omite el comando de prueba)")

resumen = "\nResultado: %d de %d pruebas correctas (%.1f s)" % (bien, total,
                                                             (datetime.now(timezone.utc) - inicio).total_seconds())
print(resumen)
lineas.append(resumen)
if len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
sys.exit(0 if bien == total else 1)
