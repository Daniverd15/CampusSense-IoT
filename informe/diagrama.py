#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arquitectura de referencia IoT de CampusSense UNAB.
Uso: python informe/diagrama.py  ->  evidencias/00-arquitectura.png y plataforma/static/arquitectura.png (Pillow)
"""
import os
import shutil

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
W, H = 2400, 1400
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)


def f(n, b=False):
    return ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf" if b else "C:/Windows/Fonts/segoeui.ttf", n)


TXT, GRIS, AZUL, VIOLETA, CIAN, NAR, VERDE, ROJO, ORO, AZURE = (25, 32, 40), (95, 105, 115), (37, 99, 235), (124, 58, 237), (8, 145, 178), (194, 65, 12), (21, 128, 61), (185, 28, 28), (180, 120, 0), (0, 120, 212)


def caja(x, y, w, h, titulo, lineas=(), col=GRIS, fondo=(248, 250, 252), tam=17, ttam=19, grosor=3):
    d.rounded_rectangle([x, y, x + w, y + h], 12, fill=fondo, outline=col, width=grosor)
    d.text((x + 12, y + 8), titulo, font=f(ttam, True), fill=col)
    for i, l in enumerate(lineas):
        d.text((x + 12, y + 38 + i * (tam + 6)), l, font=f(tam), fill=TXT)


def zona(x, y, w, h, titulo, col):
    d.rounded_rectangle([x, y, x + w, y + h], 18, outline=col, width=2)
    tw = d.textlength(titulo, font=f(18, True))
    d.rectangle([x + 18, y - 13, x + 30 + tw, y + 13], fill="white")
    d.text((x + 24, y - 13), titulo, font=f(18, True), fill=col)


def flecha(p, col, txt=None, ancho=4, punta=True, dt=(0, -24), tam=15):
    d.line(p, fill=col, width=ancho, joint="curve")
    if punta:
        (x1, y1), (x2, y2) = p[-2], p[-1]
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        d.polygon([(x2, y2), (x2 - 16 * math.cos(a) + 8 * math.sin(a), y2 - 16 * math.sin(a) - 8 * math.cos(a)),
                   (x2 - 16 * math.cos(a) - 8 * math.sin(a), y2 - 16 * math.sin(a) + 8 * math.cos(a))], fill=col)
    if txt:
        (x1, y1), (x2, y2) = p[0], p[1]
        d.text(((x1 + x2) / 2 + dt[0] - d.textlength(txt, font=f(tam)) / 2, (y1 + y2) / 2 + dt[1]), txt, font=f(tam), fill=col)


# ------------------------------------------------------------------ titulo
d.text((30, 18), "CampusSense UNAB — Arquitectura de referencia IoT", font=f(34, True), fill=TXT)
d.text((30, 64), "12 dispositivos · 5 protocolos · retroceso por el mismo protocolo · todo en una VM de Azure con URL propia y HTTPS", font=f(20), fill=GRIS)

# ------------------------------------------------------------------ capa 1: dispositivos
zona(25, 120, 520, 1000, "1. DISPOSITIVOS (12)", TXT)
filas = [
    ("REAL (python.py y ESP32)", AZUL, [("aula-101", "T, HR, CO₂, ruido, ocupación, luz", "MQTT"), ("lab-quimica", "T, HR, PM2.5, VOC, extractor", "MQTT"),
                                         ("medidor-bloque-a", "V, I, kW, fp, Hz, kWh", "AMQP"), ("esp32-wokwi", "DHT22, LDR, pot., LED", "MQTT")]),
    ("GEMELO DIGITAL", VIOLETA, [("twin-hvac-aula101", "modelo térmico vs medido", "CoAP"), ("twin-tanque-agua", "nivel, caudales, bomba", "CoAP"),
                                 ("twin-panel-solar", "irradiancia, kW, kWh", "HTTP")]),
    ("API", CIAN, [("api-clima-unab", "Azure Maps Weather", "MQTT"), ("api-aire-unab", "Azure Maps Air Quality", "MQTT"),
                   ("api-bus-ruta1", "GPS Rutas UNAB", "MQTT")]),
    ("DATASET", NAR, [("ds-ocupacion-uci", "UCI Occupancy (1 fila/min)", "STOMP"), ("ds-aire-uci", "UCI Air Quality (x12)", "AMQP")]),
]
y = 150
puertos = {}
for titulo, col, items in filas:
    d.text((45, y), titulo, font=f(17, True), fill=col)
    y += 28
    for dev, desc, proto in items:
        d.rounded_rectangle([45, y, 525, y + 46], 9, fill=(250, 251, 253), outline=col, width=2)
        d.text((57, y + 3), dev, font=f(17, True), fill=TXT)
        d.text((57, y + 23), desc, font=f(14), fill=GRIS)
        pw = d.textlength(proto, font=f(14, True)) + 16
        d.rounded_rectangle([515 - pw, y + 12, 515, y + 34], 11, fill=col)
        d.text((523 - pw, y + 14), proto, font=f(14, True), fill="white")
        puertos.setdefault(proto, []).append(y + 23)
        y += 54
    y += 10

# ------------------------------------------------------------------ zona Azure
zona(600, 120, 1775, 1000, "2–5. NUBE AZURE · VM Ubuntu 22.04 Standard_B2als_v2 (2 vCPU, 4 GB) · northcentralus · Docker Compose (12 contenedores)", AZURE)
d.text((620, 152), "https://campussense-unab.northcentralus.cloudapp.azure.com  ·  NSG: 443/80 (Caddy, TLS Let's Encrypt) y 1883 (MQTT con usuario y ACL)", font=f(17, True), fill=AZURE)

# capa 2: brokers / endpoints
caja(640, 200, 330, 150, "Mosquitto 2.0 (broker MQTT)", ["MQTT 3.1.1 · QoS 1 · sesión persistente", "usuario + ACL por dispositivo", "LWT campus/conexion/<id>", "tópicos campus/tele · cmd · datos"], AZUL)
caja(640, 380, 330, 150, "RabbitMQ 3.13 (AMQP + STOMP)", ["AMQP 0-9-1: exchange campus.tele", "STOMP 1.2 (plugin) → mismo exchange", "colas durables, publisher confirms", "comandos: exchange campus.cmd"], ORO)
caja(640, 560, 330, 120, "Servidor CoAP (aiocoap)", ["UDP 5683 · POST /tele (CON)", "gemelos exponen POST /cmd", "respuesta 2.04 = ACK"], VIOLETA)
caja(640, 710, 330, 120, "Endpoint HTTP REST", ["POST /api/ingest/<id> + X-Token", "comandos pendientes en la", "respuesta (como C2D de IoT Hub)"], CIAN)
for proto, yy, (bx, by) in [("MQTT", 0, (640, 260)), ("AMQP", 0, (640, 430)), ("STOMP", 0, (640, 480)), ("CoAP", 0, (640, 615)), ("HTTP", 0, (640, 765))]:
    for py in puertos.get(proto, []):
        d.line([(527, py), (585, py), (585, by), (bx - 2, by)], fill=(170, 180, 190), width=2)
for proto, by, col in [("MQTT", 260, AZUL), ("AMQP", 430, ORO), ("STOMP", 480, ORO), ("CoAP", 615, VIOLETA), ("HTTP", 765, CIAN)]:
    d.polygon([(638, by), (626, by - 7), (626, by + 7)], fill=col)

# capa 3: procesamiento
caja(1040, 200, 340, 170, "Ingestor (Python)", ["MQTT · AMQP (+STOMP) · CoAP", "valida rango físico por variable", "escribe en InfluxDB y confirma", "republica en campus/datos/<id>"], VERDE)
caja(1040, 400, 340, 230, "API FastAPI + motor de reglas", ["registro y estado de 12 dispositivos", "RETROCESO: enruta el comando por", "el protocolo de cada dispositivo", "ingesta HTTP · webhook de Grafana", "reglas R1–R7 cada 30 s (alertas y", "acciones automáticas: R1 CO₂→HVAC)"], ROJO)
caja(1040, 660, 340, 170, "Gemelos digitales", ["leen datos reales del bus", "HVAC: modelo RC + error vs medido", "tanque: balance de masa + bomba", "solar: sol + nubosidad de la API"], VIOLETA)
flecha([(972, 270), (1038, 270)], VERDE)
flecha([(972, 440), (1038, 300)], VERDE)
flecha([(972, 620), (1038, 330)], VERDE)
flecha([(972, 770), (1038, 560)], VERDE)

# capa 4: almacenamiento
caja(1450, 200, 300, 200, "InfluxDB 2.7 (TSDB)", ["bucket campus · retención 90 d", "telemetria · estado · ack", "comandos · alertas · conexion", "consultas Flux (mean/min/max)"], VERDE)
flecha([(1382, 285), (1448, 285)], VERDE)
flecha([(1382, 500), (1448, 380)], ROJO)

# capa 5: visualizacion y aplicacion
caja(1820, 200, 520, 200, "Grafana 11.6 (/grafana)", ["5 dashboards: resumen, ambiente, energía-agua,", "exterior-movilidad, retroceso-reglas", "promedio / máx / mín por rango de tiempo", "6 reglas de Grafana Alerting → webhook API", "acceso anónimo de solo lectura"], ORO, (255, 251, 240))
caja(1820, 430, 520, 170, "Front web (/) · CampusSense", ["estado en vivo de los 12 dispositivos", "panel de control: enviar comandos", "historial de comandos con ACK y RTT", "alertas y reglas (clave de control)"], ROJO, (255, 245, 245))
caja(1820, 630, 520, 120, "Caddy 2.8 (proxy inverso)", ["HTTPS automático (Let's Encrypt)", "/ → API   ·   /grafana → Grafana"], GRIS)
flecha([(1752, 300), (1818, 300)], ORO, "Flux", dt=(0, -26))
flecha([(1382, 470), (1818, 510)], ROJO, "REST /api", dt=(0, -26))

# retroceso
d.line([(1040, 600), (1005, 600), (1005, 860), (600, 860)], fill=NAR, width=5)
d.text((620, 900), "RETROCESO (bajada): MQTT campus/cmd/<id> · AMQP campus.cmd → cola cmd.<id> · STOMP /exchange/campus.cmd/<id> · CoAP POST /cmd · HTTP en la respuesta",
       font=f(17, True), fill=NAR)
d.text((620, 926), "comandos: encender · apagar · intervalo · calibrar (offset/ganancia) · reset · setpoint · modo · bomba · extractor · led · límite · velocidad · saltar  →  ACK con RTT",
       font=f(16), fill=NAR)
flecha([(600, 860), (548, 860)], NAR, ancho=5)

# capa analisis
caja(1450, 440, 300, 160, "Análisis con IA", ["exportes de InfluxDB (CSV)", "Claude (Anthropic) describe el", "comportamiento de las gráficas", "y anomalías del periodo"], (90, 60, 160))
flecha([(1600, 402), (1600, 438)], (90, 60, 160))

# servicios externos
zona(600, 975, 1775, 135, "SERVICIOS EXTERNOS", GRIS)
for i, (t, l) in enumerate([("Azure Maps Weather", "currentConditions + airQuality v1.1 (HTTPS)"), ("GPS Rutas UNAB", "gpsmobile.co REST (HTTP Basic)"),
                            ("UCI ML Repository", "Occupancy Detection · Air Quality"), ("Wokwi", "simulador ESP32 (Wi-Fi Wokwi-GUEST)"), ("GitHub", "código, manifiestos, evidencias")]):
    caja(625 + i * 348, 1000, 330, 90, t, [l], GRIS, tam=15, ttam=17, grosor=2)

# usuarios
caja(1820, 780, 520, 110, "Usuarios (navegador)", ["docente / operador: front + Grafana por HTTPS", "comandos protegidos con clave de control"], TXT)
flecha([(2080, 778), (2080, 752)], TXT)

d.text((30, 1135), "Flechas verdes: datos de subida · naranja: retroceso (comandos) · rojo: API, reglas y alertas · dorado: lectura de Grafana.  "
       "Ningún broker interno (RabbitMQ, InfluxDB, CoAP) se expone a Internet.", font=f(17), fill=GRIS)
d.text((30, 1165), "Hora del sistema UTC; dashboards en hora de Bogotá (UTC−5).", font=f(17), fill=GRIS)
img = img.crop((0, 0, W, 1200))
os.makedirs(os.path.join(RAIZ, "evidencias"), exist_ok=True)
ruta = os.path.join(RAIZ, "evidencias", "00-arquitectura.png")
img.save(ruta)
shutil.copy(ruta, os.path.join(RAIZ, "plataforma", "static", "arquitectura.png"))
print("OK", ruta)
