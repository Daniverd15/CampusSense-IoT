#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API de CampusSense (FastAPI): back-end de la plataforma.

  GET  /api/dispositivos                 registro + ultimo dato + estado + en linea
  GET  /api/dispositivos/{id}            detalle
  POST /api/dispositivos/{id}/comando    RETROCESO (requiere X-Clave): se enruta por el protocolo del dispositivo
  POST /api/ingest/{id}                  subida HTTP (X-Token); la respuesta lleva los comandos pendientes
  GET  /api/comandos  /api/alertas       historial
  GET  /api/resumen/{id}?horas=24        promedio, minimo y maximo por variable (Flux sobre InfluxDB)
  POST /api/alertas/grafana              webhook de Grafana Alerting
  GET  /api/salud                        estado de la plataforma

Ademas corre el motor de reglas (cada 30 s), que dispara alertas y acciones automaticas de retroceso.
"""
import collections
import json
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import tsdb
from comun import log
from registro import DISPOSITIVOS, comandos

CLAVE = os.environ["CONTROL_KEY"]
TOKEN_INGEST = os.environ["INGEST_TOKEN"]
COAP_CMD = {"twin-hvac-aula101": "coap://dev-gemelos:5701/cmd", "twin-tanque-agua": "coap://dev-gemelos:5702/cmd"}
INICIO = time.time()

ult = {}                                       # id -> ultimo mensaje de telemetria
est = {}                                       # id -> ultimo estado
conexion = {}                                  # id -> conectado (ultima voluntad MQTT)
ventanas = collections.defaultdict(lambda: collections.deque(maxlen=200))   # (id, var) -> [(t, valor)]
pendientes_http = collections.defaultdict(list)
historial_cmd = collections.deque(maxlen=300)
historial_alertas = collections.deque(maxlen=300)
lock = threading.Lock()

# --------------------------------------------------------------------------- MQTT (bus de la plataforma)
bus = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="api", protocol=mqtt.MQTTv311)
bus.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])


def _on_connect(cl, ud, fl, rc, pr=None):
    cl.subscribe([("campus/datos/+", 1), ("campus/estado/+", 1), ("campus/acks/+", 1), ("campus/conexion/+", 1)])
    log("API", "bus MQTT conectado")


def _on_message(cl, ud, msg):
    try:
        m = json.loads(msg.payload)
    except ValueError:
        return
    dev = msg.topic.split("/")[-1]
    with lock:
        if msg.topic.startswith("campus/datos/"):
            ult[dev] = m
            t = m.get("ts", 0) / 1000
            for k, v in (m.get("v") or {}).items():
                ventanas[(dev, k)].append((t, v))
        elif msg.topic.startswith("campus/estado/"):
            est[dev] = m.get("estado", {})
        elif msg.topic.startswith("campus/conexion/"):
            conexion[dev] = bool(m.get("conectado"))
        elif msg.topic.startswith("campus/acks/"):
            a = m.get("ack", {})
            for c in historial_cmd:
                if c["cmd_id"] == a.get("cmd_id"):
                    c["ack"] = {"ok": a.get("ok"), "detalle": a.get("detalle"),
                                "rtt_ms": m.get("recibido_ms", 0) - (c["ts"] or 0)}


bus.on_connect, bus.on_message = _on_connect, _on_message
bus.connect_async(os.environ.get("MQTT_HOST", "mosquitto"), 1883, 60)
bus.loop_start()


# --------------------------------------------------------------------------- envio de comandos por protocolo
def _enviar_amqp(dev, cuerpo):
    import pika
    cred = pika.PlainCredentials(os.environ["AMQP_USER"], os.environ["AMQP_PASS"])
    con = pika.BlockingConnection(pika.ConnectionParameters(os.environ.get("AMQP_HOST", "rabbitmq"), 5672, "/", cred,
                                                            client_properties={"connection_name": "api-cmd"}))
    try:
        ch = con.channel()
        ch.exchange_declare("campus.cmd", exchange_type="direct", durable=True)
        ch.confirm_delivery()
        ch.basic_publish("campus.cmd", dev, cuerpo.encode(), pika.BasicProperties(delivery_mode=2, content_type="application/json"))
    finally:
        con.close()


def _enviar_stomp(dev, cuerpo):
    import stomp
    c = stomp.Connection([(os.environ.get("STOMP_HOST", "rabbitmq"), 61613)])
    c.connect(os.environ["AMQP_USER"], os.environ["AMQP_PASS"], wait=True)
    try:
        c.send("/exchange/campus.cmd/" + dev, cuerpo, content_type="application/json")
    finally:
        c.disconnect()


def _enviar_coap(dev, cuerpo):
    import asyncio
    import aiocoap

    async def post():
        ctx = await aiocoap.Context.create_client_context()
        try:
            req = aiocoap.Message(code=aiocoap.POST, uri=COAP_CMD[dev], payload=cuerpo.encode(), mtype=aiocoap.CON)
            r = await asyncio.wait_for(ctx.request(req).response, 20)
            return str(r.code), r.payload.decode(errors="replace")
        finally:
            await ctx.shutdown()

    return asyncio.run(post())


def enviar_comando(dev, accion, params, origen="manual"):
    if dev not in DISPOSITIVOS:
        raise HTTPException(404, "dispositivo desconocido")
    if accion not in comandos(dev):
        raise HTTPException(400, "accion no soportada por %s: %s" % (dev, accion))
    proto = DISPOSITIVOS[dev]["protocolo"]
    cmd = {"cmd_id": uuid.uuid4().hex[:12], "accion": accion, "params": params or {}, "origen": origen,
           "ts": int(time.time() * 1000)}
    cuerpo = json.dumps(cmd)
    respuesta = None
    if proto == "mqtt":
        info = bus.publish("campus/cmd/" + dev, cuerpo, qos=1)
        info.wait_for_publish(5)
        via = "MQTT PUBLISH campus/cmd/%s QoS1" % dev
    elif proto == "amqp":
        _enviar_amqp(dev, cuerpo)
        via = "AMQP basic.publish exchange campus.cmd rk %s (confirmado)" % dev
    elif proto == "stomp":
        _enviar_stomp(dev, cuerpo)
        via = "STOMP SEND /exchange/campus.cmd/%s" % dev
    elif proto == "coap":
        codigo, respuesta = _enviar_coap(dev, cuerpo)
        via = "CoAP POST CON %s -> %s" % (COAP_CMD[dev], codigo)
    else:
        with lock:
            pendientes_http[dev].append(cmd)
        via = "HTTP: en cola, viaja en la respuesta al proximo POST del dispositivo"
    registro = dict(cmd, dispositivo=dev, protocolo=proto, via=via, ack=None)
    if respuesta:
        try:
            a = json.loads(respuesta).get("ack", {})
            registro["ack"] = {"ok": a.get("ok"), "detalle": a.get("detalle"), "rtt_ms": int(time.time() * 1000) - cmd["ts"]}
        except ValueError:
            pass
    with lock:
        historial_cmd.appendleft(registro)
    tsdb.escribir([tsdb.linea("comandos", {"dispositivo": dev, "accion": accion, "origen": origen, "protocolo": proto},
                              {"cmd_id": cmd["cmd_id"], "params": json.dumps(params or {}), "via": via}, cmd["ts"])])
    log("CMD", "%s -> %s %s (%s) via %s" % (origen, dev, accion, json.dumps(params or {}), via))
    return registro


# --------------------------------------------------------------------------- alertas
activas = {}           # clave -> dict de alerta activa


def alerta(clave, regla, dev, severidad, mensaje, valor, activa, origen="reglas"):
    ahora = int(time.time() * 1000)
    if activa and clave in activas:
        return False
    if not activa and clave not in activas:
        return False
    estado = "firing" if activa else "resolved"
    a = {"ts": ahora, "regla": regla, "dispositivo": dev, "severidad": severidad, "estado": estado,
         "mensaje": mensaje, "valor": valor, "origen": origen}
    if activa:
        activas[clave] = a
    else:
        activas.pop(clave, None)
    with lock:
        historial_alertas.appendleft(a)
    tsdb.escribir([tsdb.linea("alertas", {"regla": regla, "dispositivo": dev, "severidad": severidad, "origen": origen},
                              {"estado": estado, "activa": 1.0 if activa else 0.0, "mensaje": mensaje,
                               "valor": float(valor) if isinstance(valor, (int, float)) else None}, ahora)])
    log("ALERTA", "%s %s %s: %s (%s)" % (estado.upper(), regla, dev, mensaje, valor))
    return True


# --------------------------------------------------------------------------- motor de reglas
def promedio(dev, var, minutos=5):
    with lock:
        datos = [v for t, v in ventanas[(dev, var)] if t >= time.time() - minutos * 60]
    return sum(datos) / len(datos) if datos else None


def ultimo(dev, var):
    m = ult.get(dev)
    return (m or {}).get("v", {}).get(var)


REGLAS = [
    {"id": "R1", "nombre": "CO2 alto en Aula 101 -> HVAC en ventilación",
     "condicion": "promedio 5 min de aula-101.co2 > 1000 ppm (se libera < 750 ppm)",
     "accion": "twin-hvac-aula101 modo=ventilacion; al liberar modo=auto"},
    {"id": "R2", "nombre": "Demanda alta Bloque A -> HVAC en eco",
     "condicion": "promedio 5 min de medidor-bloque-a.potencia > 30 kW (se libera < 24 kW)",
     "accion": "twin-hvac-aula101 modo=eco si estaba en auto; al liberar modo=auto"},
    {"id": "R3", "nombre": "Tanque de agua bajo",
     "condicion": "twin-tanque-agua.nivel < 20 % (se libera > 30 %)",
     "accion": "alerta crítica; si la bomba está forzada en off, la pone en auto"},
    {"id": "R4", "nombre": "PM2.5 alto en Lab. Química",
     "condicion": "promedio 5 min de lab-quimica.pm25 > 35 µg/m³ (se libera < 25)",
     "accion": "alerta; si el extractor está forzado en off, lo pone en auto"},
    {"id": "R5", "nombre": "Calidad del aire exterior",
     "condicion": "api-aire-unab.indice_global > 100 o pm25 > 37.5 µg/m³", "accion": "alerta"},
    {"id": "R6", "nombre": "Dispositivo sin datos",
     "condicion": "encendido y sin telemetría por más de max(3 x intervalo, 180 s)", "accion": "alerta"},
    {"id": "R7", "nombre": "Exceso de velocidad del bus",
     "condicion": "api-bus-ruta1.velocidad > 60 km/h", "accion": "alerta"},
]
memoria = {"R1": False, "R2": False}


def _modo_hvac():
    return int((est.get("twin-hvac-aula101") or {}).get("modo", ultimo("twin-hvac-aula101", "modo") or 1))


def evaluar():
    co2 = promedio("aula-101", "co2")
    if co2 is not None:
        if co2 > 1000 and not memoria["R1"]:
            memoria["R1"] = True
            alerta("R1", "R1 CO2 alto", "aula-101", "warning", "CO2 promedio 5 min %.0f ppm: HVAC a ventilacion" % co2, co2, True)
            enviar_comando("twin-hvac-aula101", "modo", {"valor": "ventilacion"}, "regla R1")
        elif co2 < 750 and memoria["R1"]:
            memoria["R1"] = False
            alerta("R1", "R1 CO2 alto", "aula-101", "warning", "CO2 normalizado (%.0f ppm): HVAC a auto" % co2, co2, False)
            enviar_comando("twin-hvac-aula101", "modo", {"valor": "auto"}, "regla R1")
    p = promedio("medidor-bloque-a", "potencia")
    if p is not None:
        if p > 30 and not memoria["R2"]:
            memoria["R2"] = True
            alerta("R2", "R2 Demanda alta", "medidor-bloque-a", "warning", "Demanda %.1f kW: HVAC a eco" % p, p, True)
            if _modo_hvac() == 1 and not memoria["R1"]:
                enviar_comando("twin-hvac-aula101", "modo", {"valor": "eco"}, "regla R2")
        elif p < 24 and memoria["R2"]:
            memoria["R2"] = False
            alerta("R2", "R2 Demanda alta", "medidor-bloque-a", "warning", "Demanda normal (%.1f kW)" % p, p, False)
            if _modo_hvac() == 3 and not memoria["R1"]:
                enviar_comando("twin-hvac-aula101", "modo", {"valor": "auto"}, "regla R2")
    nivel = ultimo("twin-tanque-agua", "nivel")
    if nivel is not None:
        if nivel < 20 and alerta("R3", "R3 Tanque bajo", "twin-tanque-agua", "critical", "Nivel %.1f %%" % nivel, nivel, True):
            if (est.get("twin-tanque-agua") or {}).get("bomba_modo") == 2:
                enviar_comando("twin-tanque-agua", "bomba", {"estado": "auto"}, "regla R3")
        elif nivel > 30:
            alerta("R3", "R3 Tanque bajo", "twin-tanque-agua", "critical", "Nivel recuperado %.1f %%" % nivel, nivel, False)
    pm = promedio("lab-quimica", "pm25")
    if pm is not None:
        if pm > 35 and alerta("R4", "R4 PM2.5 laboratorio", "lab-quimica", "warning", "PM2.5 promedio %.1f" % pm, pm, True):
            if (est.get("lab-quimica") or {}).get("extractor_modo") == 2:
                enviar_comando("lab-quimica", "extractor", {"estado": "auto"}, "regla R4")
        elif pm < 25:
            alerta("R4", "R4 PM2.5 laboratorio", "lab-quimica", "warning", "PM2.5 normal %.1f" % pm, pm, False)
    idx, pm_ext = ultimo("api-aire-unab", "indice_global"), ultimo("api-aire-unab", "pm25")
    if idx is not None:
        malo = idx > 100 or (pm_ext or 0) > 37.5
        alerta("R5", "R5 Aire exterior", "api-aire-unab", "warning", "Indice %.0f, PM2.5 %s" % (idx, pm_ext), idx, malo)
    for dev, reg in DISPOSITIVOS.items():
        if dev == "esp32-wokwi":
            continue                                   # se usa por sesiones de demostracion
        e = est.get(dev) or {}
        m = ult.get(dev)
        if not m or not e.get("encendido", 1):
            alerta("R6:" + dev, "R6 Sin datos", dev, "critical", "volvio", 0, False)
            continue
        edad = time.time() - m.get("ts", 0) / 1000
        limite = max(3 * float(e.get("intervalo_s", reg["intervalo"])), 180)
        alerta("R6:" + dev, "R6 Sin datos", dev, "critical",
               ("sin telemetria hace %.0f s" % edad) if edad > limite else "telemetria restablecida", round(edad), edad > limite)
    vel = ultimo("api-bus-ruta1", "velocidad")
    if vel is not None:
        alerta("R7", "R7 Velocidad bus", "api-bus-ruta1", "warning", "Velocidad %.0f km/h" % vel, vel, vel > 60)


def motor_reglas():
    time.sleep(90)                                      # deja llenar las ventanas tras un reinicio
    m = _modo_hvac()
    memoria["R1"] = m == 2
    log("REGLAS", "motor de reglas activo (%d reglas)" % len(REGLAS))
    while True:
        try:
            evaluar()
        except Exception as e:
            log("REGLAS", "ERROR %s: %s" % (type(e).__name__, e))
        time.sleep(30)


threading.Thread(target=motor_reglas, daemon=True).start()

# --------------------------------------------------------------------------- HTTP
app = FastAPI(title="CampusSense UNAB API", version="1.0",
              description="Back-end de la plataforma IoT CampusSense UNAB (IoT a la medida).")


def _vista(dev):
    reg = DISPOSITIVOS[dev]
    m = ult.get(dev) or {}
    e = est.get(dev) or {}
    edad = time.time() - m.get("ts", 0) / 1000 if m else None
    limite = max(3 * float(e.get("intervalo_s", reg["intervalo"])), 180)
    return {"id": dev, "nombre": reg["nombre"], "tipo": reg["tipo"], "protocolo": reg["protocolo"],
            "ubicacion": reg["ubicacion"], "hardware": reg["hardware"], "intervalo_fabrica": reg["intervalo"],
            "variables": {k: {"unidad": u, "min": lo, "max": hi} for k, (u, lo, hi) in reg["variables"].items()},
            "comandos": comandos(dev), "ultimo": m.get("v"), "ts": m.get("ts"), "seq": m.get("seq"),
            "edad_s": round(edad, 1) if edad is not None else None, "estado": e,
            "en_linea": bool(m) and edad is not None and edad <= limite and bool(e.get("encendido", 1)),
            "conectado_mqtt": conexion.get(dev)}


@app.get("/api/dispositivos")
def dispositivos():
    return [_vista(d) for d in DISPOSITIVOS]


@app.get("/api/dispositivos/{dev}")
def dispositivo(dev: str):
    if dev not in DISPOSITIVOS:
        raise HTTPException(404, "dispositivo desconocido")
    return _vista(dev)


@app.post("/api/dispositivos/{dev}/comando")
async def comando(dev: str, request: Request, x_clave: str = Header(default="")):
    if x_clave != CLAVE:
        raise HTTPException(401, "clave de control invalida")
    cuerpo = await request.json()
    import starlette.concurrency
    return await starlette.concurrency.run_in_threadpool(enviar_comando, dev, str(cuerpo.get("accion", "")),
                                                         cuerpo.get("params") or {}, "manual")


@app.post("/api/ingest/{dev}")
async def ingest(dev: str, request: Request, x_token: str = Header(default="")):
    if x_token != TOKEN_INGEST:
        raise HTTPException(401, "token invalido")
    m = await request.json()
    if m.get("id") != dev:
        raise HTTPException(400, "id no coincide")
    import starlette.concurrency
    ok = await starlette.concurrency.run_in_threadpool(tsdb.procesar, m, "http", bus)
    if not ok:
        raise HTTPException(503, "TSDB no disponible")
    with lock:
        cmds, pendientes_http[dev] = pendientes_http[dev], []
    return {"ok": True, "comandos": cmds}


@app.get("/api/comandos")
def lista_comandos(n: int = 50):
    with lock:
        return list(historial_cmd)[:n]


@app.get("/api/alertas")
def lista_alertas(n: int = 50):
    with lock:
        return {"activas": list(activas.values()), "historial": list(historial_alertas)[:n]}


@app.get("/api/reglas")
def reglas():
    return {"reglas": REGLAS, "memoria": memoria}


@app.post("/api/alertas/grafana")
async def webhook_grafana(request: Request, token: str = ""):
    if token != TOKEN_INGEST:
        raise HTTPException(401, "token invalido")
    cuerpo = await request.json()
    for a in cuerpo.get("alerts", []):
        lab, ann = a.get("labels", {}), a.get("annotations", {})
        nombre = lab.get("alertname", "grafana")
        clave = "G:" + nombre + ":" + lab.get("dispositivo", "")
        alerta(clave, nombre, lab.get("dispositivo", "-"), lab.get("severity", "warning"),
               ann.get("summary", nombre), None, a.get("status") == "firing", origen="grafana")
    return {"ok": True}


@app.get("/api/resumen/{dev}")
def resumen(dev: str, horas: float = 24):
    if dev not in DISPOSITIVOS:
        raise HTTPException(404, "dispositivo desconocido")
    horas = max(0.1, min(horas, 24 * 14))
    base = 'from(bucket:"%s") |> range(start:-%dm) |> filter(fn:(r)=> r._measurement=="telemetria" and r.dispositivo=="%s" and r._field!="seq" and r._field!="lat_ms")' % (
        tsdb.BUCKET, int(horas * 60), dev)
    out = {}
    for fn in ("mean", "min", "max", "count"):
        for r in tsdb.consulta(base + " |> group(columns:[\"_field\"]) |> %s()" % fn):
            out.setdefault(r["_field"], {})[fn] = round(float(r["_value"]), 3)
    return {"dispositivo": dev, "horas": horas, "variables": out}


@app.get("/api/salud")
def salud():
    return {"ok": True, "inicio": INICIO, "uptime_s": round(time.time() - INICIO), "dispositivos": len(DISPOSITIVOS),
            "en_linea": sum(1 for d in DISPOSITIVOS if _vista(d)["en_linea"]), "alertas_activas": len(activas),
            "ingesta_http": tsdb.cuenta.get("http", 0)}


STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def inicio():
    return FileResponse(os.path.join(STATIC, "index.html"))
