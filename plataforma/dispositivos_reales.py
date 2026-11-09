#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dispositivos "reales" (real device python.py): firmware de nodo de campo emulado en Python.

Cada clase reproduce lo que mediria el hardware descrito en registro.py con un modelo fisico
sencillo (balance de CO2, inercia termica, perfil de carga) y ruido de sensor. Los nodos se afectan
entre si a traves del bus de datos: el modo del gemelo HVAC cambia la ventilacion del aula,
la potencia del HVAC y la planta solar cambian la demanda del medidor.

  aula-101          MQTT   temperatura, humedad, co2, ruido, ocupacion, luz
  lab-quimica       MQTT   temperatura, humedad, pm25, voc, extractor
  medidor-bloque-a  AMQP   voltaje, corriente, potencia, fp, frecuencia, energia
"""
import math
import random
import time

from comun import BusDatos, Dispositivo, esperar_para_siempre, log, ruido


def hora_local():
    """Hora de Bogota (UTC-5, sin horario de verano): (dia_semana 0=lunes, hora decimal)."""
    t = time.gmtime(time.time() - 5 * 3600)
    return t.tm_wday, t.tm_hour + t.tm_min / 60 + t.tm_sec / 3600


def temp_exterior_modelo(h):
    """Ciclo diario de Bucaramanga (min ~19 °C a las 5 h, max ~29 °C a las 14 h) si no hay dato de la API."""
    return 24 + 5 * math.sin((h - 8) / 24 * 2 * math.pi)


def luz_dia(h):
    return max(0.0, math.sin((h - 6) / 12 * math.pi)) if 6 <= h <= 18 else 0.0


class Aula101(Dispositivo):
    VOL = 180.0                              # m3
    ACH = {0: 0.6, 1: 3.0, 2: 7.0, 3: 1.8}   # renovaciones/h segun modo HVAC (apagado, auto, ventilacion, eco)

    def __init__(self, bus):
        self.bus = bus
        self.T, self.C, self.occ, self.objetivo = 24.0, 450.0, 0.0, 0
        self.bloque = None
        self.t_prev = time.time()
        super().__init__("aula-101")

    def _ocupacion_objetivo(self, dia, h):
        horario = (dia < 5 and (7 <= h < 12 or 14 <= h < 21.5)) or (dia == 5 and 7 <= h < 13)
        if not horario:
            return random.choice([0, 0, 0, 1, 2]) if 6 <= h <= 22 else 0
        bloque = (dia, int((h - 7) // 2))
        if bloque != self.bloque:            # cada bloque de 2 h: hay clase o no, y cuantos asisten
            self.bloque = bloque
            self.objetivo = random.randint(18, 42) if random.random() < 0.8 else random.randint(0, 4)
        if (h - 7) % 2 > 1.83:               # cambio de clase: el salon se vacia unos minutos
            return random.randint(0, 3)
        return self.objetivo

    def medir(self):
        dt_h = min(time.time() - self.t_prev, 600) / 3600
        self.t_prev = time.time()
        dia, h = hora_local()
        self.occ += (self._ocupacion_objetivo(dia, h) - self.occ) * min(1, dt_h * 12)
        modo = int(self.bus.valor("twin-hvac-aula101", "modo", 1))
        setpoint = self.bus.valor("twin-hvac-aula101", "setpoint", 23.0)
        t_ext = self.bus.valor("api-clima-unab", "temperatura", temp_exterior_modelo(h))
        hr_ext = self.bus.valor("api-clima-unab", "humedad", 75.0)
        ach = self.ACH.get(modo, 3.0)
        # CO2: cada persona ~18 L/h -> +100 ppm/h en 180 m3; la ventilacion lleva hacia 420 ppm
        self.C += (self.occ * 0.018 / self.VOL * 1e6 - ach * (self.C - 420)) * dt_h
        # temperatura: intercambio con exterior + gente (~100 W) + enfriamiento del HVAC hacia el setpoint
        enfria = modo in (1, 3) and (self.occ > 2 or 6 <= h <= 21)
        sp = setpoint + (2 if modo == 3 else 0)
        dT = (t_ext - self.T) / 3.0 + self.occ * 0.05 - (1.6 * (self.T - sp) if enfria and self.T > sp else 0)
        self.T += dT * dt_h
        hum = hr_ext * (0.72 if enfria else 0.92) + self.occ * 0.15
        luz = 650 * luz_dia(h) * 0.5 + (480 if self.occ > 2 else 0)
        return {"temperatura": round(self.T + ruido(0.08), 2), "humedad": round(min(98, max(25, hum + ruido(0.6))), 1),
                "co2": round(max(400, self.C + ruido(12))), "ruido": round(34 + 13 * math.log10(1 + self.occ) + ruido(1.5), 1),
                "ocupacion": int(round(self.occ)), "luz": round(max(0, luz + ruido(15)))}


class LabQuimica(Dispositivo):
    def __init__(self, bus):
        self.bus = bus
        self.pm, self.voc, self.modo_extractor, self.extractor = 10.0, 120.0, "auto", 0
        self.evento = 0.0
        self.t_prev = time.time()
        super().__init__("lab-quimica")

    def comando_extra(self, accion, p):
        if accion == "extractor":
            e = str(p.get("estado", "")).lower()
            if e not in ("on", "off", "auto"):
                raise ValueError("estado debe ser on, off o auto")
            self.modo_extractor = e
            return "extractor %s" % e
        raise ValueError("accion desconocida: %s" % accion)

    def estado_extra(self):
        return {"extractor_modo": {"auto": 0, "on": 1, "off": 2}[self.modo_extractor]}

    def cargar_extra(self, e):
        self.modo_extractor = e.get("modo_extractor", "auto")

    def guardar_extra(self):
        return {"modo_extractor": self.modo_extractor}

    def medir(self):
        dt_h = min(time.time() - self.t_prev, 600) / 3600
        self.t_prev = time.time()
        dia, h = hora_local()
        practica = dia < 5 and (8 <= h < 12 or 14 <= h < 18)
        if practica and random.random() < 0.025:          # un experimento libera particulas y solventes
            self.evento = random.uniform(0.5, 1.0)
        self.evento *= math.exp(-dt_h * 6)
        pm_ext = self.bus.valor("api-aire-unab", "pm25", 12.0)
        if self.modo_extractor == "auto":
            self.extractor = 1 if (self.voc > 450 or self.pm > 35) else (0 if self.voc < 250 and self.pm < 20 else self.extractor)
        else:
            self.extractor = 1 if self.modo_extractor == "on" else 0
        k = 8.0 if self.extractor else 1.5                  # renovaciones/h
        self.pm += (pm_ext * 0.6 + self.evento * 260 - self.pm) * min(1, k * dt_h) + (self.evento * 40 * dt_h)
        self.voc += ((90 + (60 if practica else 0) + self.evento * 1500) - self.voc) * min(1, k * dt_h)
        return {"temperatura": round(22.5 + (1.2 if practica else -0.6) + ruido(0.1), 2),
                "humedad": round(52 + 4 * math.sin(h / 24 * 2 * math.pi) + ruido(0.7), 1),
                "pm25": round(max(0, self.pm + ruido(1.2)), 1), "voc": round(max(0, self.voc + ruido(8))),
                "extractor": self.extractor}


class MedidorBloqueA(Dispositivo):
    def __init__(self, bus):
        self.bus = bus
        self.energia = 182400.0              # lectura acumulada del medidor al instalarlo (kWh)
        self.t_prev = time.time()
        super().__init__("medidor-bloque-a")

    def cargar_extra(self, e):
        self.energia = e.get("energia", self.energia)

    def guardar_extra(self):
        return {"energia": self.energia}

    def medir(self):
        dt_h = min(time.time() - self.t_prev, 600) / 3600
        self.t_prev = time.time()
        dia, h = hora_local()
        laborable = dia < 5 or (dia == 5 and h < 13)
        perfil = 0.0
        if laborable:
            perfil = max(0.0, min(1.0, (h - 6) / 2)) * max(0.0, min(1.0, (22 - h) / 2)) * (0.85 if 12 <= h < 14 else 1.0)
        carga = 7.5 + 26 * perfil + self.bus.valor("twin-hvac-aula101", "potencia", 0.0) + ruido(0.8)
        solar = self.bus.valor("twin-panel-solar", "potencia", 0.0)
        p = max(0.5, carga - solar)          # potencia tomada de la red (la solar descuenta)
        fp = min(0.99, 0.88 + 0.08 * perfil + ruido(0.005))
        v = 120.5 - 0.06 * p + ruido(0.3)
        i = p * 1000 / (3 * v * fp)          # corriente por fase (trifasico 208/120 V)
        self.energia += p * dt_h
        if self.seq % 10 == 0:
            self._guardar()
        return {"voltaje": round(v, 2), "corriente": round(i, 2), "potencia": round(p, 3), "fp": round(fp, 3),
                "frecuencia": round(60 + ruido(0.012), 3), "energia": round(self.energia, 2)}


if __name__ == "__main__":
    bus = BusDatos("reales", ["twin-hvac-aula101", "api-clima-unab", "api-aire-unab", "twin-panel-solar"])
    time.sleep(3)
    for d in (Aula101(bus), LabQuimica(bus), MedidorBloqueA(bus)):
        d.iniciar()
    log("reales", "3 dispositivos reales en marcha")
    esperar_para_siempre()
