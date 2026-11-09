#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dispositivos API: consultan un servicio externo por HTTPS/HTTP y publican por MQTT (puente API -> broker).

  api-clima-unab  Azure Maps Weather  GET /weather/currentConditions/json  v1.1   cada 10 min
  api-aire-unab   Azure Maps Weather  GET /weather/airQuality/current/json v1.1   cada 15 min
  api-bus-ruta1   GPS Rutas UNAB      GET http://gpsmobile.co:4000/api/DetalleVehiculo/...  (HTTP Basic)  cada 60 s

El retroceso tambien aplica: "apagar" deja de consultar la API (ahorra cuota), "intervalo" cambia la
frecuencia de consulta y "calibrar" corrige el dato antes de publicarlo.
Las claves vienen de variables de entorno; no estan en el repositorio. Del GPS solo se guardan
posicion, velocidad y baterias (no nombres de conductores ni datos de la SIM).
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from comun import Dispositivo, esperar_para_siempre, log
from registro import CAMPUS

AZ = "https://atlas.microsoft.com/weather/%s/json"


def http_json(url, auth=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "CampusSense-UNAB/1.0"})
    if auth:
        import base64
        req.add_header("Authorization", "Basic " + base64.b64encode(("%s:%s" % auth).encode()).decode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def azure_maps(recurso):
    q = urllib.parse.urlencode({"api-version": "1.1", "query": "%.6f,%.6f" % CAMPUS, "language": "es-MX",
                                "subscription-key": os.environ["AZMAPS_KEY"]})
    return http_json(AZ % recurso + "?" + q)


class ApiBase(Dispositivo):
    intervalo_min = 60

    def medir(self):
        try:
            return self.consultar()
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as e:
            log(self.id, "API sin respuesta valida: %s" % e)
            return None


class ApiClima(ApiBase):
    intervalo_min = 300

    def __init__(self):
        super().__init__("api-clima-unab")

    def consultar(self):
        r = azure_maps("currentConditions")["results"][0]
        val = _get
        return {"temperatura": val(r, "temperature", "value"), "sensacion": val(r, "realFeelTemperature", "value"),
                "humedad": r.get("relativeHumidity"), "punto_rocio": val(r, "dewPoint", "value"),
                "presion": val(r, "pressure", "value"), "viento": val(r, "wind", "speed", "value"),
                "rafaga": val(r, "windGust", "speed", "value"), "uv": r.get("uvIndex"), "nubosidad": r.get("cloudCover"),
                "visibilidad": val(r, "visibility", "value"),
                "precipitacion": val(r, "precipitationSummary", "pastHour", "value")}


class ApiAire(ApiBase):
    intervalo_min = 300
    MAPA = {"PM2.5": "pm25", "PM10": "pm10", "NO2": "no2", "O3": "o3", "CO": "co", "SO2": "so2"}

    def __init__(self):
        super().__init__("api-aire-unab")

    def consultar(self):
        r = azure_maps("airQuality/current")["results"][0]
        v = {"indice_global": r.get("globalIndex")}
        for p in r.get("pollutants", []):
            k = self.MAPA.get(str(p.get("type", "")).upper().replace(" ", ""))
            if k:
                v[k] = _get(p, "concentration", "value")
        return v


class ApiBus(ApiBase):
    def __init__(self):
        self.url = os.environ.get("GPS_URL", "http://gpsmobile.co:4000/api/DetalleVehiculo/97141/96365")
        super().__init__("api-bus-ruta1")

    def consultar(self):
        r = http_json(self.url, auth=(os.environ["GPS_USER"], os.environ["GPS_PASS"]))
        veh = r["response"]["veh"]
        info = str(veh.get("Info", ""))
        bat = lambda k: float(re.search(k + r":([\d,\.]+)V", info).group(1).replace(",", ".")) if re.search(k + r":([\d,\.]+)V", info) else None
        lat, lon, vel = float(veh["Lt"]), float(veh["Lg"]), float(veh.get("Vel", 0))
        return {"lat": round(lat, 6), "lon": round(lon, 6), "velocidad": vel,
                "encendido": 1 if (vel > 0 or str(veh.get("Std")) == "1") else 0,
                "bateria_ext": bat("BatExt"), "bateria_int": bat("BatInt"),
                "distancia_campus": round(haversine(lat, lon, *CAMPUS), 3)}


def _get(d, *k):
    for x in k:
        if not isinstance(d, dict) or x not in d:
            return None
        d = d[x]
    return d


def haversine(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


if __name__ == "__main__":
    for d in (ApiClima(), ApiAire(), ApiBus()):
        d.iniciar()
        time.sleep(2)
    log("apis", "3 dispositivos API en marcha")
    esperar_para_siempre()
