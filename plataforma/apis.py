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


OPEN_METEO = "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f&current=%s&timezone=UTC"
OPEN_METEO_AIRE = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=%.4f&longitude=%.4f&current=%s"
REINTENTO_PRINCIPAL_S = 6 * 3600


class ApiBase(Dispositivo):
    """Fuente principal + respaldo: si la principal falla, se usa el respaldo y se reintenta la principal cada 6 h.
    El estado reporta fuente=0 (principal) o fuente=1 (respaldo), asi cada dato queda trazado a su origen."""
    intervalo_min = 60
    fuentes = ("principal",)

    def __init__(self, dev_id):
        self.fuente, self.falla_principal = 0, 0.0
        super().__init__(dev_id)

    def estado_extra(self):
        return {"fuente": self.fuente} if len(self.fuentes) > 1 else {}

    def medir(self):
        errores = (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError)
        if len(self.fuentes) == 1 or time.time() - self.falla_principal > REINTENTO_PRINCIPAL_S:
            try:
                v = self.consultar()
                if self.fuente != 0:
                    log(self.id, "fuente principal (%s) disponible otra vez" % self.fuentes[0])
                self.fuente = 0
                return v
            except errores as e:
                log(self.id, "fuente principal (%s) sin respuesta valida: %s" % (self.fuentes[0], e))
                if len(self.fuentes) == 1:
                    return None
                self.falla_principal = time.time()
        try:
            v = self.respaldo()
            if self.fuente != 1:
                log(self.id, "usando la fuente de respaldo (%s)" % self.fuentes[1])
            self.fuente = 1
            return v
        except errores as e:
            log(self.id, "respaldo (%s) sin respuesta valida: %s" % (self.fuentes[1], e))
            return None


class ApiClima(ApiBase):
    intervalo_min = 300
    fuentes = ("Azure Maps Weather", "Open-Meteo")

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

    def respaldo(self):
        campos = "temperature_2m,relative_humidity_2m,apparent_temperature,dew_point_2m,pressure_msl,wind_speed_10m,wind_gusts_10m,cloud_cover,precipitation,uv_index,visibility"
        c = http_json(OPEN_METEO % (CAMPUS[0], CAMPUS[1], campos))["current"]
        return {"temperatura": c.get("temperature_2m"), "sensacion": c.get("apparent_temperature"), "humedad": c.get("relative_humidity_2m"),
                "punto_rocio": c.get("dew_point_2m"), "presion": c.get("pressure_msl"), "viento": c.get("wind_speed_10m"),
                "rafaga": c.get("wind_gusts_10m"), "uv": c.get("uv_index"), "nubosidad": c.get("cloud_cover"),
                "visibilidad": round(c["visibility"] / 1000, 2) if c.get("visibility") is not None else None,
                "precipitacion": c.get("precipitation")}


class ApiAire(ApiBase):
    intervalo_min = 300
    fuentes = ("Azure Maps Air Quality", "Open-Meteo Air Quality")
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

    def respaldo(self):
        # el indice del respaldo es el US AQI (Open-Meteo), escala parecida pero no identica al globalIndex de Azure Maps
        c = http_json(OPEN_METEO_AIRE % (CAMPUS[0], CAMPUS[1], "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,carbon_monoxide,sulphur_dioxide"))["current"]
        return {"indice_global": c.get("us_aqi"), "pm25": c.get("pm2_5"), "pm10": c.get("pm10"), "no2": c.get("nitrogen_dioxide"),
                "o3": c.get("ozone"), "co": c.get("carbon_monoxide"), "so2": c.get("sulphur_dioxide")}


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
