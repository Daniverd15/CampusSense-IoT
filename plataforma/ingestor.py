#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingestor de CampusSense: un proceso, cuatro adaptadores de entrada -> InfluxDB + bus campus/datos.

  MQTT   suscriptor paho a campus/tele/+ (QoS 1, sesion persistente)       <- Mosquitto
         y campus/conexion/+ (ultima voluntad: el broker avisa si un nodo cae)
  AMQP   cola durable ingestor.tele <- exchange campus.tele, rk tele.#    <- RabbitMQ
         (aqui llegan tambien los mensajes STOMP: RabbitMQ traduce STOMP -> AMQP)
  CoAP   servidor aiocoap udp/5683, recurso POST /tele (mensajes CON)     <- gemelos
  (HTTP lo atiende la API en /api/ingest/<id>)

Un mensaje solo se confirma (PUBACK implicito tras escribir, basic.ack, 2.04) cuando InfluxDB lo acepto.
Cada dato aceptado se republica retenido en campus/datos/<id>: de ahi leen los gemelos, la API y las reglas.
"""
import asyncio
import json
import os
import threading
import time

import aiocoap
import aiocoap.resource as resource
import paho.mqtt.client as mqtt
import pika

import tsdb
from comun import log

pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingestor-pub", protocol=mqtt.MQTTv311)
pub.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
pub.connect_async(os.environ.get("MQTT_HOST", "mosquitto"), 1883, 60)
pub.loop_start()


# --------------------------------------------------------------------------- MQTT
def adaptador_mqtt():
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ingestor", protocol=mqtt.MQTTv311,
                    clean_session=False, manual_ack=True)
    c.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])

    def on_connect(cl, ud, flags, rc, props=None):
        log("MQTT", "CONNACK %s; SUBSCRIBE campus/tele/+ y campus/conexion/+ qos1" % rc)
        cl.subscribe([("campus/tele/+", 1), ("campus/conexion/+", 1)])

    def on_message(cl, ud, msg):
        ok = True
        try:
            m = json.loads(msg.payload)
            if msg.topic.startswith("campus/conexion/"):
                dev = msg.topic.split("/")[-1]
                tsdb.escribir([tsdb.linea("conexion", {"dispositivo": dev}, {"conectado": 1.0 if m.get("conectado") else 0.0},
                                          int(time.time() * 1000))])
                log("MQTT", "conexion %s -> %s" % (dev, m.get("conectado")))
            else:
                ok = tsdb.procesar(m, "mqtt", pub)
        except (ValueError, TypeError, AttributeError) as e:
            tsdb.cuenta["rechazados"] += 1
            log("MQTT", "mensaje invalido en %s: %s" % (msg.topic, e))
        if ok:
            cl.ack(msg.mid, msg.qos)
        else:
            time.sleep(2)
            cl.disconnect()                      # sin ack: el broker lo reentrega al reconectar

    c.on_connect, c.on_message = on_connect, on_message
    while True:
        try:
            c.connect(os.environ.get("MQTT_HOST", "mosquitto"), 1883, 45)
            c.loop_forever()
        except Exception as e:
            log("MQTT", "ERROR %s: %s" % (type(e).__name__, e))
        time.sleep(3)


# --------------------------------------------------------------------------- AMQP (+ STOMP)
def adaptador_amqp():
    cred = pika.PlainCredentials(os.environ["AMQP_USER"], os.environ["AMQP_PASS"])
    params = pika.ConnectionParameters(os.environ.get("AMQP_HOST", "rabbitmq"), 5672, "/", cred, heartbeat=30,
                                       client_properties={"connection_name": "ingestor"})

    def on_message(ch, method, props, body):
        try:
            ok = tsdb.procesar(json.loads(body), "amqp", pub)
        except (ValueError, TypeError, AttributeError) as e:
            tsdb.cuenta["rechazados"] += 1
            log("AMQP", "mensaje invalido rk=%s: %s" % (method.routing_key, e))
            ch.basic_reject(method.delivery_tag, requeue=False)
            return
        if ok:
            ch.basic_ack(method.delivery_tag)
        else:
            time.sleep(2)
            ch.basic_nack(method.delivery_tag, requeue=True)

    while True:
        try:
            con = pika.BlockingConnection(params)
            ch = con.channel()
            ch.exchange_declare("campus.tele", exchange_type="topic", durable=True)
            ch.exchange_declare("campus.cmd", exchange_type="direct", durable=True)
            ch.queue_declare("ingestor.tele", durable=True)
            ch.queue_bind("ingestor.tele", "campus.tele", routing_key="tele.#")
            ch.basic_qos(prefetch_count=50)
            ch.basic_consume("ingestor.tele", on_message)
            log("AMQP", "consumiendo cola durable ingestor.tele (exchange campus.tele, rk tele.#)")
            ch.start_consuming()
        except Exception as e:
            log("AMQP", "ERROR %s: %s" % (type(e).__name__, e))
            time.sleep(5)


# --------------------------------------------------------------------------- CoAP
class Tele(resource.Resource):
    async def render_post(self, req):
        try:
            m = json.loads(req.payload)
        except ValueError:
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=b"json invalido")
        ok = await asyncio.get_running_loop().run_in_executor(None, tsdb.procesar, m, "coap", pub)
        return aiocoap.Message(code=aiocoap.CHANGED if ok else aiocoap.SERVICE_UNAVAILABLE)


async def adaptador_coap():
    sitio = resource.Site()
    sitio.add_resource(["tele"], Tele())
    await aiocoap.Context.create_server_context(sitio, bind=("0.0.0.0", 5683))
    log("CoAP", "servidor escuchando en udp/5683, recurso POST /tele")
    while True:
        await asyncio.sleep(300)
        log("STATS", json.dumps(tsdb.cuenta))


if __name__ == "__main__":
    threading.Thread(target=adaptador_mqtt, daemon=True).start()
    threading.Thread(target=adaptador_amqp, daemon=True).start()
    asyncio.run(adaptador_coap())
