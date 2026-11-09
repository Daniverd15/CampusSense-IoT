# -*- coding: utf-8 -*-
"""Biblioteca comun de CampusSense UNAB: clase base de dispositivo + enlaces por protocolo.

Cada dispositivo sube telemetria por SU protocolo y recibe comandos de retroceso por el mismo protocolo:

  protocolo | subida (telemetria, estado, ack)              | bajada (comandos)
  ----------+-----------------------------------------------+-------------------------------------------
  MQTT      | PUBLISH campus/tele/<id>  QoS 1               | SUBSCRIBE campus/cmd/<id>  QoS 1
  AMQP      | exchange campus.tele (topic), rk tele.<id>    | cola cmd.<id> <- exchange campus.cmd (direct)
  STOMP     | SEND /exchange/campus.tele/tele.<id>          | SUBSCRIBE /exchange/campus.cmd/<id>
  CoAP      | POST CON coap://ingestor/tele                 | servidor CoAP propio: POST /cmd
  HTTP      | POST /api/ingest/<id> (X-Token)               | los comandos pendientes vuelven en la respuesta

Mensaje de subida (JSON):
  {"id", "tipo", "kind": "tele"|"estado"|"ack", "ts": epoch_ms, "seq", "v": {...}, "estado": {...}, "ack": {...}}
"""
import asyncio
import collections
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request

from registro import DISPOSITIVOS

ESTADO_DIR = os.environ.get("ESTADO_DIR", "/estado")


def log(tag, msg):
    print("%s [%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), tag, msg), flush=True)


def ahora_ms():
    return int(time.time() * 1000)


# =========================================================================== enlaces
class Enlace:
    """Interfaz: enviar(dict) y escuchar(callback(cmd_dict) -> ack_dict)."""
    protocolo = "?"

    def __init__(self, dev_id):
        self.id = dev_id
        self.on_cmd = None

    def escuchar(self, callback):
        self.on_cmd = callback

    def enviar(self, msg):
        raise NotImplementedError


class EnlaceMQTT(Enlace):
    protocolo = "mqtt"

    def __init__(self, dev_id, usuario=None, clave=None):
        super().__init__(dev_id)
        import paho.mqtt.client as mqtt
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dev-" + dev_id,
                             protocol=mqtt.MQTTv311, clean_session=False)
        self.c.username_pw_set(usuario or os.environ["MQTT_USER"], clave or os.environ["MQTT_PASS"])
        # ultima voluntad: si el nodo cae sin despedirse, el broker publica que quedo desconectado
        self.c.will_set("campus/conexion/" + dev_id, json.dumps({"id": dev_id, "conectado": False}), qos=1, retain=True)
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message
        self.c.reconnect_delay_set(1, 30)
        self.c.connect_async(os.environ.get("MQTT_HOST", "mosquitto"), int(os.environ.get("MQTT_PORT", "1883")), keepalive=60)
        self.c.loop_start()

    def _on_connect(self, cl, ud, flags, rc, props=None):
        log(self.id, "MQTT CONNACK %s -> SUBSCRIBE campus/cmd/%s qos1" % (rc, self.id))
        cl.subscribe("campus/cmd/" + self.id, qos=1)
        cl.publish("campus/conexion/" + self.id, json.dumps({"id": self.id, "conectado": True}), qos=1, retain=True)

    def _on_message(self, cl, ud, msg):
        if msg.topic == "campus/cmd/" + self.id and self.on_cmd:
            try:
                self.enviar(self.on_cmd(json.loads(msg.payload)))
            except Exception as e:
                log(self.id, "comando MQTT invalido: %s" % e)

    def enviar(self, msg):
        if msg:
            self.c.publish("campus/tele/" + self.id, json.dumps(msg), qos=1)


class EnlaceAMQP(Enlace):
    """AMQP 0-9-1 (RabbitMQ). pika no es thread-safe: una conexion para publicar y otra para consumir."""
    protocolo = "amqp"

    def __init__(self, dev_id):
        super().__init__(dev_id)
        import pika
        self.pika = pika
        cred = pika.PlainCredentials(os.environ["AMQP_USER"], os.environ["AMQP_PASS"])
        self.params = pika.ConnectionParameters(os.environ.get("AMQP_HOST", "rabbitmq"), 5672, "/", cred, heartbeat=30,
                                                client_properties={"connection_name": "dev-" + dev_id})
        self.lock = threading.Lock()
        self.pub = None
        self.pendientes = collections.deque(maxlen=2000)   # guardar y reenviar si el broker no esta
        threading.Thread(target=self._consumir, daemon=True).start()
        threading.Thread(target=self._mantener, daemon=True).start()

    def _mantener(self):
        """pika BlockingConnection solo envia heartbeats si se atiende la conexion: sin esto RabbitMQ la cierra."""
        while True:
            time.sleep(10)
            with self.lock:
                try:
                    if self.pub is not None and self.pub.is_open:
                        self.pub.connection.process_data_events(time_limit=0)
                except Exception as e:
                    log(self.id, "AMQP keepalive: %s, se reconecta en el proximo envio" % type(e).__name__)
                    self.pub = None

    def _canal(self):
        if self.pub is None or self.pub.is_closed:
            con = self.pika.BlockingConnection(self.params)
            self.pub = con.channel()
            self.pub.exchange_declare("campus.tele", exchange_type="topic", durable=True)
            self.pub.confirm_delivery()          # publisher confirms: el broker confirma cada mensaje
        return self.pub

    def enviar(self, msg):
        with self.lock:
            if msg:
                self.pendientes.append(msg)
            for intento in range(3):
                try:
                    while self.pendientes:
                        self._canal().basic_publish("campus.tele", "tele." + self.id, json.dumps(self.pendientes[0]).encode(),
                                                    self.pika.BasicProperties(delivery_mode=2, content_type="application/json"))
                        self.pendientes.popleft()     # solo sale de la cola cuando el broker lo confirmo
                    return
                except Exception as e:
                    log(self.id, "AMQP publicar fallo (%s), reintento; %d en cola" % (type(e).__name__, len(self.pendientes)))
                    self.pub = None
                    time.sleep(2 + intento * 3)

    def _consumir(self):
        cola = "cmd." + self.id
        while True:
            try:
                con = self.pika.BlockingConnection(self.params)
                ch = con.channel()
                ch.exchange_declare("campus.cmd", exchange_type="direct", durable=True)
                ch.queue_declare(cola, durable=True, arguments={"x-message-ttl": 600000})
                ch.queue_bind(cola, "campus.cmd", routing_key=self.id)

                def cb(c, method, props, body):
                    try:
                        if self.on_cmd:
                            self.enviar(self.on_cmd(json.loads(body)))
                    except Exception as e:
                        log(self.id, "comando AMQP invalido: %s" % e)
                    c.basic_ack(method.delivery_tag)

                ch.basic_consume(cola, cb)
                log(self.id, "AMQP consumiendo comandos en cola %s (exchange campus.cmd, rk %s)" % (cola, self.id))
                ch.start_consuming()
            except Exception as e:
                log(self.id, "AMQP consumidor: %s" % type(e).__name__)
                time.sleep(5)


class EnlaceSTOMP(Enlace):
    protocolo = "stomp"

    def __init__(self, dev_id):
        super().__init__(dev_id)
        import stomp
        self.stomp = stomp
        self.lock = threading.Lock()
        self.con = None
        self._conectar()

    def _conectar(self):
        enl = self

        class Oyente(self.stomp.ConnectionListener):
            def on_message(self, frame):
                try:
                    if enl.on_cmd:
                        enl.enviar(enl.on_cmd(json.loads(frame.body)))
                except Exception as e:
                    log(enl.id, "comando STOMP invalido: %s" % e)

            def on_disconnected(self):
                log(enl.id, "STOMP desconectado")

        while True:
            try:
                con = self.stomp.Connection([(os.environ.get("STOMP_HOST", "rabbitmq"), 61613)], heartbeats=(20000, 20000))
                con.set_listener("cmd", Oyente())
                con.connect(os.environ["AMQP_USER"], os.environ["AMQP_PASS"], wait=True)
                con.subscribe("/exchange/campus.cmd/" + self.id, id=1, ack="auto")
                self.con = con
                log(self.id, "STOMP CONNECTED; SUBSCRIBE /exchange/campus.cmd/%s" % self.id)
                return
            except Exception as e:
                log(self.id, "STOMP conectar: %s" % type(e).__name__)
                time.sleep(5)

    def enviar(self, msg):
        if not msg:
            return
        with self.lock:
            for _ in range(3):
                try:
                    if not self.con or not self.con.is_connected():
                        self._conectar()
                    self.con.send("/exchange/campus.tele/tele." + self.id, json.dumps(msg),
                                  content_type="application/json", headers={"persistent": "true"})
                    return
                except Exception as e:
                    log(self.id, "STOMP enviar: %s" % type(e).__name__)
                    self.con = None
                    time.sleep(3)


class EnlaceCoAP(Enlace):
    """CoAP (RFC 7252): sube con POST confirmable al ingestor y expone un recurso /cmd propio."""
    protocolo = "coap"

    def __init__(self, dev_id, puerto_cmd):
        super().__init__(dev_id)
        self.destino = "coap://%s:5683/tele" % os.environ.get("COAP_HOST", "ingestor")
        self.puerto = puerto_cmd
        self.loop = asyncio.new_event_loop()
        self.listo = threading.Event()
        threading.Thread(target=self._hilo, daemon=True).start()
        self.listo.wait(20)

    def _hilo(self):
        import aiocoap
        import aiocoap.resource as resource
        asyncio.set_event_loop(self.loop)
        enl = self

        class Cmd(resource.Resource):
            async def render_post(self, req):
                try:
                    ack = enl.on_cmd(json.loads(req.payload)) if enl.on_cmd else None
                    if ack:
                        threading.Thread(target=enl.enviar, args=(ack,), daemon=True).start()
                    return aiocoap.Message(code=aiocoap.CHANGED, payload=json.dumps(ack or {}).encode())
                except Exception as e:
                    return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=str(e).encode())

        async def iniciar():
            sitio = resource.Site()
            sitio.add_resource(["cmd"], Cmd())
            await aiocoap.Context.create_server_context(sitio, bind=("0.0.0.0", self.puerto))
            self.cliente = await aiocoap.Context.create_client_context()
            log(self.id, "CoAP servidor de comandos en udp/%d recurso /cmd" % self.puerto)
            self.listo.set()

        self.loop.run_until_complete(iniciar())
        self.loop.run_forever()

    async def _post(self, cuerpo):
        import aiocoap
        req = aiocoap.Message(code=aiocoap.POST, uri=self.destino, payload=cuerpo, mtype=aiocoap.CON)
        req.opt.content_format = 50          # application/json
        r = await asyncio.wait_for(self.cliente.request(req).response, 60)
        return r.code

    def enviar(self, msg):
        if not msg:
            return
        for _ in range(3):
            try:
                cod = asyncio.run_coroutine_threadsafe(self._post(json.dumps(msg).encode()), self.loop).result(70)
                if cod.is_successful():
                    return
                log(self.id, "CoAP respuesta %s" % cod)
            except Exception as e:
                log(self.id, "CoAP POST fallo: %s" % type(e).__name__)
            time.sleep(3)


class EnlaceHTTP(Enlace):
    """HTTP REST: el dispositivo pregunta; los comandos pendientes llegan en la respuesta (como C2D en IoT Hub)."""
    protocolo = "http"

    def __init__(self, dev_id):
        super().__init__(dev_id)
        self.url = "%s/api/ingest/%s" % (os.environ.get("API_URL", "http://api:8000"), dev_id)
        self.token = os.environ["INGEST_TOKEN"]
        self.pendientes = collections.deque(maxlen=2000)   # guardar y reenviar si la API no responde
        self.lock = threading.RLock()

    def enviar(self, msg):
        with self.lock:
            if msg:
                self.pendientes.append(msg)
            while self.pendientes:
                req = urllib.request.Request(self.url, data=json.dumps(self.pendientes[0]).encode(), method="POST",
                                             headers={"Content-Type": "application/json", "X-Token": self.token})
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        resp = json.loads(r.read() or b"{}")
                except (urllib.error.URLError, OSError, ValueError) as e:
                    log(self.id, "HTTP POST fallo (%s); %d en cola, se reenvian en el proximo envio" % (e, len(self.pendientes)))
                    return
                self.pendientes.popleft()
                for cmd in resp.get("comandos", []):
                    if self.on_cmd:
                        self.enviar(self.on_cmd(cmd))


def crear_enlace(dev_id, **kw):
    p = DISPOSITIVOS[dev_id]["protocolo"]
    return {"mqtt": EnlaceMQTT, "amqp": EnlaceAMQP, "stomp": EnlaceSTOMP,
            "coap": EnlaceCoAP, "http": EnlaceHTTP}[p](dev_id, **kw)


# =========================================================================== bus de datos
class BusDatos:
    """Lee el ultimo valor de otros dispositivos desde campus/datos/<id> (retained, lo publica el ingestor).

    Asi un gemelo digital usa datos reales (aula-101, api-clima) venga de donde venga su protocolo.
    """

    def __init__(self, nombre, ids):
        import paho.mqtt.client as mqtt
        self.ult = {}
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="bus-" + nombre, protocol=mqtt.MQTTv311)
        c.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
        c.on_connect = lambda cl, ud, fl, rc, pr=None: [cl.subscribe("campus/datos/" + i, qos=1) for i in ids]

        def on_message(cl, ud, msg):
            try:
                m = json.loads(msg.payload)
                self.ult[m["id"]] = m
            except ValueError:
                pass

        c.on_message = on_message
        c.connect_async(os.environ.get("MQTT_HOST", "mosquitto"), 1883, 60)
        c.loop_start()
        self.c = c

    def valor(self, dev_id, var, defecto=None, max_edad_s=3600):
        m = self.ult.get(dev_id)
        if not m or var not in m.get("v", {}):
            return defecto
        if time.time() - m.get("ts", 0) / 1000 > max_edad_s:
            return defecto
        return m["v"][var]


# =========================================================================== dispositivo base
class Dispositivo:
    """Ciclo comun: medir -> calibrar -> enviar; atiende comandos de retroceso y persiste su estado."""

    def __init__(self, dev_id, enlace=None):
        self.id = dev_id
        self.cfg = DISPOSITIVOS[dev_id]
        self.intervalo_fabrica = self.cfg["intervalo"]
        self.intervalo = self.intervalo_fabrica
        self.encendido = True
        self.cal = {}              # variable -> [offset, ganancia]
        self.seq = 0
        self.despertar = threading.Event()
        self.ruta_estado = os.path.join(ESTADO_DIR, dev_id + ".json")
        self._cargar()
        self.enlace = enlace or crear_enlace(dev_id)
        self.enlace.escuchar(self.manejar)

    # ---------------------------------------------------------------- estado persistente
    def _cargar(self):
        try:
            with open(self.ruta_estado) as f:
                e = json.load(f)
            self.encendido = e.get("encendido", True)
            self.intervalo = e.get("intervalo", self.intervalo)
            self.cal = e.get("cal", {})
            self.cargar_extra(e.get("extra", {}))
            log(self.id, "estado restaurado: encendido=%s intervalo=%s cal=%s" % (self.encendido, self.intervalo, self.cal))
        except (OSError, ValueError):
            pass

    def _guardar(self):
        try:
            os.makedirs(ESTADO_DIR, exist_ok=True)
            with open(self.ruta_estado, "w") as f:
                json.dump({"encendido": self.encendido, "intervalo": self.intervalo, "cal": self.cal,
                           "extra": self.guardar_extra()}, f)
        except OSError as e:
            log(self.id, "no se pudo guardar el estado: %s" % e)

    # ---------------------------------------------------------------- para sobrescribir
    def medir(self):
        raise NotImplementedError

    def comando_extra(self, accion, params):
        raise ValueError("accion desconocida: %s" % accion)

    def estado_extra(self):
        return {}

    def cargar_extra(self, e):
        pass

    def guardar_extra(self):
        return {}

    # ---------------------------------------------------------------- retroceso
    def manejar(self, cmd):
        accion = str(cmd.get("accion", "")).lower()
        p = cmd.get("params") or {}
        ok, detalle = True, ""
        try:
            if accion == "encender":
                self.encendido, detalle = True, "telemetria reanudada"
            elif accion == "apagar":
                self.encendido, detalle = False, "telemetria detenida"
            elif accion == "intervalo":
                s = int(p.get("segundos", 0))
                minimo = getattr(self, "intervalo_min", 5)
                if not minimo <= s <= 3600:
                    raise ValueError("segundos debe estar entre %d y 3600" % minimo)
                self.intervalo, detalle = s, "intervalo=%ds" % s
            elif accion == "calibrar":
                var = p.get("variable")
                if var not in self.cfg["variables"]:
                    raise ValueError("variable desconocida: %s" % var)
                self.cal[var] = [float(p.get("offset", 0.0)), float(p.get("ganancia", 1.0))]
                detalle = "%s: offset=%s ganancia=%s" % (var, self.cal[var][0], self.cal[var][1])
            elif accion == "reset":
                self.intervalo, self.cal, self.encendido = self.intervalo_fabrica, {}, True
                detalle = "configuracion de fabrica"
            else:
                detalle = self.comando_extra(accion, p) or "ok"
        except (ValueError, TypeError) as e:
            ok, detalle = False, str(e)
        self._guardar()
        log(self.id, "COMANDO %s %s -> %s %s" % (accion, json.dumps(p), "OK" if ok else "ERROR", detalle))
        self.despertar.set()       # aplica el cambio ya, sin esperar el intervalo
        return {"id": self.id, "tipo": self.cfg["tipo"], "kind": "ack", "ts": ahora_ms(),
                "ack": {"cmd_id": cmd.get("cmd_id", ""), "accion": accion, "ok": ok, "detalle": detalle,
                        "enviado_ms": cmd.get("ts", 0)},
                "estado": self.estado()}

    def estado(self):
        e = {"encendido": 1 if self.encendido else 0, "intervalo_s": self.intervalo}
        for var, (off, gan) in self.cal.items():
            e["offset_" + var] = off
            e["ganancia_" + var] = gan
        e.update(self.estado_extra())
        return e

    def calibrar(self, v):
        out = {}
        for k, x in v.items():
            if x is None:
                continue
            off, gan = self.cal.get(k, (0.0, 1.0))
            out[k] = round(float(x) * gan + off, 4)
        return out

    # ---------------------------------------------------------------- ciclo
    def ciclo(self):
        ultimo_latido = 0
        while True:
            self.despertar.clear()
            try:
                if self.encendido:
                    v = self.medir()
                    if v:
                        self.seq += 1
                        self.enlace.enviar({"id": self.id, "tipo": self.cfg["tipo"], "kind": "tele", "ts": ahora_ms(),
                                            "seq": self.seq, "v": self.calibrar(v), "estado": self.estado()})
                elif time.time() - ultimo_latido >= 60:
                    ultimo_latido = time.time()
                    self.enlace.enviar({"id": self.id, "tipo": self.cfg["tipo"], "kind": "estado", "ts": ahora_ms(),
                                        "estado": self.estado()})
            except Exception as e:
                log(self.id, "ERROR en ciclo: %s: %s" % (type(e).__name__, e))
            self.despertar.wait(self.intervalo if self.encendido else 60)

    def iniciar(self):
        threading.Thread(target=self.ciclo, name=self.id, daemon=True).start()
        log(self.id, "iniciado (%s, %s, cada %ss)" % (self.cfg["tipo"], self.enlace.protocolo, self.intervalo))
        return self


def ruido(sigma):
    return random.gauss(0, sigma)


def esperar_para_siempre():
    while True:
        time.sleep(3600)
