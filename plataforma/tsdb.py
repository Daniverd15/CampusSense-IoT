# -*- coding: utf-8 -*-
"""Validacion + escritura en InfluxDB 2 + republicacion en el bus campus/datos/<id>.

Lo usan el ingestor (MQTT, AMQP, STOMP, CoAP) y la API (HTTP), asi todo dato pasa por las mismas reglas.

Measurements:
  telemetria  tags dispositivo,tipo,protocolo   fields = variables + seq + lat_ms
  estado      tags dispositivo,tipo,protocolo   fields = encendido, intervalo_s, offsets, estado propio
  ack         tags dispositivo,accion           fields ok, detalle, cmd_id, rtt_ms
  comandos    (lo escribe la API)  alertas (API y Grafana)
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from comun import log
from registro import DISPOSITIVOS

INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
ORG = os.environ.get("INFLUX_ORG", "unab")
BUCKET = os.environ.get("INFLUX_BUCKET", "campus")
TOKEN = os.environ.get("INFLUX_TOKEN", "")
cuenta = {"mqtt": 0, "amqp": 0, "stomp": 0, "coap": 0, "http": 0, "rechazados": 0, "fuera_rango": 0}


def _esc_tag(s):
    return str(s).replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def _campo(k, v):
    if isinstance(v, bool):
        return "%s=%s" % (k, "true" if v else "false")
    if isinstance(v, int):
        return "%s=%di" % (k, v) if k in ("seq", "lat_ms", "rtt_ms") else "%s=%s" % (k, float(v))
    if isinstance(v, float):
        return "%s=%s" % (k, v)
    return '%s="%s"' % (k, str(v).replace("\\", "\\\\").replace('"', '\\"')[:500])


def linea(medida, tags, campos, ts_ms):
    t = ",".join("%s=%s" % (k, _esc_tag(v)) for k, v in tags.items() if v not in (None, ""))
    c = ",".join(_campo(k, v) for k, v in campos.items() if v is not None)
    return "%s,%s %s %d" % (medida, t, c, ts_ms)


def escribir(lineas):
    if not lineas:
        return True
    req = urllib.request.Request("%s/api/v2/write?%s" % (INFLUX_URL, urllib.parse.urlencode(
        {"org": ORG, "bucket": BUCKET, "precision": "ms"})), data="\n".join(lineas).encode(), method="POST",
        headers={"Authorization": "Token " + TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 204
    except urllib.error.HTTPError as e:
        log("TSDB", "InfluxDB rechazo: %s %s" % (e.code, e.read()[:200]))
    except OSError as e:
        log("TSDB", "InfluxDB no responde: %s" % e)
    return False


def consulta(flux):
    """Ejecuta Flux y devuelve filas (dict) del CSV anotado."""
    import csv
    import io
    req = urllib.request.Request("%s/api/v2/query?org=%s" % (INFLUX_URL, ORG), data=json.dumps(
        {"query": flux, "type": "flux", "dialect": {"annotations": []}}).encode(), method="POST",
        headers={"Authorization": "Token " + TOKEN, "Content-Type": "application/json", "Accept": "application/csv"})
    with urllib.request.urlopen(req, timeout=20) as r:
        texto = r.read().decode()
    filas = []
    for bloque in texto.strip().split("\r\n\r\n"):
        if bloque.strip():
            filas += list(csv.DictReader(io.StringIO(bloque)))
    return filas


def procesar(m, canal, mqtt_cliente=None):
    """Valida un mensaje de subida y lo guarda. Devuelve True si quedo en la TSDB (o si es invalido y se descarta)."""
    dev = str(m.get("id", ""))
    reg = DISPOSITIVOS.get(dev)
    if not reg:
        cuenta["rechazados"] += 1
        log("RX-" + canal.upper(), "dispositivo desconocido %r: descartado" % dev)
        return True
    protocolo = reg["protocolo"] if canal == "amqp" else canal      # STOMP llega a RabbitMQ y sale por la cola AMQP
    llegada = int(time.time() * 1000)
    ts = int(m.get("ts") or llegada)
    if abs(llegada - ts) > 6 * 3600 * 1000:                          # reloj del dispositivo muy corrido
        ts = llegada
    tags = {"dispositivo": dev, "tipo": reg["tipo"], "protocolo": protocolo}
    lineas, kind = [], m.get("kind", "tele")
    if kind == "tele":
        campos = {}
        for k, x in (m.get("v") or {}).items():
            if k not in reg["variables"] or x is None:
                continue
            try:
                x = float(x)
            except (TypeError, ValueError):
                continue
            lo, hi = reg["variables"][k][1:]
            if not lo <= x <= hi:
                cuenta["fuera_rango"] += 1
                log("RX-" + canal.upper(), "%s %s=%s fuera de rango [%s, %s]: descartado" % (dev, k, x, lo, hi))
                continue
            campos[k] = x
        if not campos:
            cuenta["rechazados"] += 1
            return True
        campos["seq"] = int(m.get("seq", 0))
        campos["lat_ms"] = max(0, llegada - ts)
        lineas.append(linea("telemetria", tags, campos, ts))
    if m.get("estado"):
        est = {k: float(v) for k, v in m["estado"].items() if isinstance(v, (int, float))}
        if est:
            lineas.append(linea("estado", tags, est, ts))
    if kind == "ack" and m.get("ack"):
        a = m["ack"]
        rtt = llegada - int(a.get("enviado_ms") or llegada)
        lineas.append(linea("ack", {"dispositivo": dev, "accion": a.get("accion", "?"), "protocolo": protocolo},
                            {"ok": bool(a.get("ok")), "detalle": a.get("detalle", ""), "cmd_id": a.get("cmd_id", ""),
                             "rtt_ms": max(0, rtt) if rtt < 3600000 else None}, ts))
    if not escribir(lineas):
        return False
    cuenta[canal] = cuenta.get(canal, 0) + 1
    if mqtt_cliente is not None:
        m2 = dict(m, protocolo=protocolo, recibido_ms=llegada)
        if kind == "tele":
            mqtt_cliente.publish("campus/datos/" + dev, json.dumps(m2), qos=1, retain=True)
        elif kind == "ack":
            mqtt_cliente.publish("campus/acks/" + dev, json.dumps(m2), qos=1)
        if m.get("estado"):
            mqtt_cliente.publish("campus/estado/" + dev, json.dumps({"id": dev, "ts": ts, "estado": m["estado"]}), qos=1, retain=True)
    if kind != "tele" or m.get("seq", 0) % 20 == 1:
        log("RX-" + canal.upper(), "%s %s seq=%s lat=%dms -> InfluxDB 204" % (dev, kind, m.get("seq"), llegada - ts))
    return True
