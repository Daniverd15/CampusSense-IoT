#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemelos digitales: modelos que corren en la nube alimentados con datos reales del bus.

  twin-hvac-aula101  CoAP  modelo termico RC del aula + controlador del aire acondicionado.
                           Entradas: temperatura y ocupacion medidas (aula-101), temperatura exterior (api-clima).
                           Salida clave: error_modelo = medido - predicho (si crece, algo cambio en el aula real).
  twin-tanque-agua   CoAP  balance de masa de un tanque elevado de 20 m3 con bomba por histeresis.
  twin-panel-solar   HTTP  planta de 12 kWp: posicion del sol + nubosidad real (api-clima) + temperatura de celda.
"""
import math
import random
import time

from comun import BusDatos, Dispositivo, EnlaceCoAP, esperar_para_siempre, log, ruido
from dispositivos_reales import hora_local, temp_exterior_modelo
from registro import CAMPUS

MODOS = {"apagado": 0, "auto": 1, "ventilacion": 2, "eco": 3}


class GemeloHVAC(Dispositivo):
    def __init__(self, bus):
        self.bus = bus
        self.modo, self.setpoint, self.Tm = 1, 23.0, None
        self.t_prev = time.time()
        super().__init__("twin-hvac-aula101", EnlaceCoAP("twin-hvac-aula101", 5701))

    def comando_extra(self, accion, p):
        if accion == "setpoint":
            v = float(p.get("valor"))
            if not 16 <= v <= 30:
                raise ValueError("setpoint fuera de 16..30 °C")
            self.setpoint = v
            return "setpoint=%.1f °C" % v
        if accion == "modo":
            m = str(p.get("valor", "")).lower()
            if m not in MODOS:
                raise ValueError("modo debe ser apagado, auto, ventilacion o eco")
            self.modo = MODOS[m]
            return "modo=%s" % m
        raise ValueError("accion desconocida: %s" % accion)

    def cargar_extra(self, e):
        self.modo, self.setpoint = e.get("modo", 1), e.get("setpoint", 23.0)

    def guardar_extra(self):
        return {"modo": self.modo, "setpoint": self.setpoint}

    def medir(self):
        dt_h = min(time.time() - self.t_prev, 600) / 3600
        self.t_prev = time.time()
        _, h = hora_local()
        t_med = self.bus.valor("aula-101", "temperatura", None, max_edad_s=300)
        occ = self.bus.valor("aula-101", "ocupacion", 0, max_edad_s=300)
        t_ext = self.bus.valor("api-clima-unab", "temperatura", temp_exterior_modelo(h))
        if self.Tm is None:
            self.Tm = t_med if t_med is not None else 24.0
        enfria = self.modo in (1, 3) and (occ > 2 or 6 <= h <= 21)
        sp = self.setpoint + (2 if self.modo == 3 else 0)
        # modelo del gemelo (parametros identificados, no iguales a la realidad): tau 3.2 h, 0.045 °C/h/persona
        dT = (t_ext - self.Tm) / 3.2 + occ * 0.045 - (1.5 * (self.Tm - sp) if enfria and self.Tm > sp else 0)
        self.Tm += dT * dt_h
        error = 0.0
        if t_med is not None:
            error = t_med - self.Tm
            self.Tm += error * min(1, dt_h * 0.5)          # observador: corrige el estado lentamente
        if enfria and t_med is not None and t_med > sp:
            pot = min(5.5, 0.9 + 1.4 * (t_med - sp)) * (0.6 if self.modo == 3 else 1.0)
            t_sum = max(10.0, sp - 8)
        else:
            pot, t_sum = (0.35 if self.modo == 2 else 0.0), (t_med if t_med is not None else self.Tm)
        if self.modo == 2:
            pot += 0.6                                        # ventiladores al maximo
        return {"temp_modelo": round(self.Tm, 2), "temp_suministro": round(t_sum + ruido(0.1), 2),
                "setpoint": self.setpoint, "potencia": round(max(0, pot + ruido(0.05)), 3), "modo": self.modo,
                "error_modelo": round(error, 3)}


class GemeloTanque(Dispositivo):
    CAP_L, Q_BOMBA = 20000.0, 230.0

    def __init__(self):
        self.L, self.bomba, self.modo_bomba, self.factor = 14000.0, 0, "auto", 1.0
        self.t_prev = time.time()
        super().__init__("twin-tanque-agua", EnlaceCoAP("twin-tanque-agua", 5702))

    def comando_extra(self, accion, p):
        if accion == "bomba":
            e = str(p.get("estado", "")).lower()
            if e not in ("on", "off", "auto"):
                raise ValueError("estado debe ser on, off o auto")
            self.modo_bomba = e
            return "bomba %s" % e
        if accion == "consumo":
            f = float(p.get("factor", 1))
            if not 0.5 <= f <= 3:
                raise ValueError("factor fuera de 0.5..3")
            self.factor = f
            return "demanda x%.2f" % f
        raise ValueError("accion desconocida: %s" % accion)

    def estado_extra(self):
        return {"bomba_modo": {"auto": 0, "on": 1, "off": 2}[self.modo_bomba], "factor_consumo": self.factor}

    def cargar_extra(self, e):
        self.L, self.modo_bomba, self.factor = e.get("litros", 14000.0), e.get("modo_bomba", "auto"), e.get("factor", 1.0)

    def guardar_extra(self):
        return {"litros": self.L, "modo_bomba": self.modo_bomba, "factor": self.factor}

    def medir(self):
        dt_min = min(time.time() - self.t_prev, 600) / 60
        self.t_prev = time.time()
        dia, h = hora_local()
        if dia < 5 and 6.5 <= h <= 21.5:
            q_out = 45 + 55 * math.exp(-((h - 10) / 1.6) ** 2) + 48 * math.exp(-((h - 15.5) / 1.8) ** 2)
        elif dia == 5 and 6.5 <= h <= 13.5:
            q_out = 40
        else:
            q_out = 9
        q_out = max(0, q_out * self.factor * random.uniform(0.85, 1.15))
        nivel = self.L / self.CAP_L * 100
        if self.modo_bomba == "auto":
            self.bomba = 1 if nivel < 35 else (0 if nivel > 90 else self.bomba)
        else:
            self.bomba = 1 if self.modo_bomba == "on" else 0
        q_in = self.Q_BOMBA * random.uniform(0.97, 1.02) if self.bomba else 0.0
        self.L = max(0.0, min(self.CAP_L, self.L + (q_in - q_out) * dt_min))
        nivel = self.L / self.CAP_L * 100
        if self.seq % 10 == 0:
            self._guardar()
        return {"nivel": round(nivel, 2), "volumen": round(self.L / 1000, 3), "caudal_entrada": round(q_in, 1),
                "caudal_salida": round(q_out, 1), "bomba": self.bomba,
                "presion": round((15 + nivel / 100 * 4) * 0.0981 + ruido(0.005), 3)}


def elevacion_solar(lat, lon):
    """Elevacion del sol en grados (aproximacion de Cooper + ecuacion del tiempo)."""
    t = time.gmtime()
    n = t.tm_yday
    decl = 23.45 * math.sin(math.radians(360 / 365 * (284 + n)))
    b = math.radians(360 / 365 * (n - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)       # minutos
    solar = t.tm_hour + t.tm_min / 60 + t.tm_sec / 3600 + lon / 15 + eot / 60
    w = math.radians(15 * (solar - 12))
    la, de = math.radians(lat), math.radians(decl)
    return math.degrees(math.asin(math.sin(la) * math.sin(de) + math.cos(la) * math.cos(de) * math.cos(w)))


class GemeloSolar(Dispositivo):
    KWP = 12.0

    def __init__(self, bus):
        self.bus = bus
        self.limite, self.inversor, self.energia, self.dia = 12.0, 1, 0.0, None
        self.nube_local = 0.0
        self.t_prev = time.time()
        super().__init__("twin-panel-solar")      # enlace HTTP

    def comando_extra(self, accion, p):
        if accion == "limite":
            kw = float(p.get("kw"))
            if not 0 <= kw <= 12:
                raise ValueError("kw fuera de 0..12")
            self.limite = kw
            return "limite=%.1f kW" % kw
        raise ValueError("accion desconocida: %s" % accion)

    def manejar(self, cmd):
        # apagar/encender tambien desconecta/conecta el inversor (la planta sigue reportando irradiancia)
        if cmd.get("accion") in ("apagar", "encender"):
            self.inversor = 1 if cmd["accion"] == "encender" else 0
            cmd = dict(cmd, accion="encender")
            ack = super().manejar(cmd)
            ack["ack"]["accion"] = "inversor_" + ("on" if self.inversor else "off")
            ack["ack"]["detalle"] = "inversor %s" % ("conectado" if self.inversor else "desconectado")
            ack["estado"] = self.estado()
            return ack
        return super().manejar(cmd)

    def estado_extra(self):
        return {"limite_kw": self.limite, "inversor": self.inversor}

    def cargar_extra(self, e):
        self.limite, self.inversor, self.energia = e.get("limite", 12.0), e.get("inversor", 1), e.get("energia", 0.0)
        self.dia = e.get("dia")

    def guardar_extra(self):
        return {"limite": self.limite, "inversor": self.inversor, "energia": self.energia, "dia": self.dia}

    def medir(self):
        dt_h = min(time.time() - self.t_prev, 600) / 3600
        self.t_prev = time.time()
        dia_local = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 5 * 3600))
        if dia_local != self.dia:
            self.dia, self.energia = dia_local, 0.0
        elev = elevacion_solar(*CAMPUS)
        ghi_cs = 1098 * math.sin(math.radians(elev)) ** 1.15 if elev > 0 else 0.0
        nub = self.bus.valor("api-clima-unab", "nubosidad", 50.0) / 100
        self.nube_local = max(-0.25, min(0.25, self.nube_local * 0.8 + ruido(0.08)))  # nubes que pasan
        irr = ghi_cs * (1 - 0.75 * min(1.0, max(0.0, nub + self.nube_local)) ** 3.4)
        t_amb = self.bus.valor("api-clima-unab", "temperatura", 25.0)
        tp = t_amb + irr / 800 * 25
        p = self.KWP * irr / 1000 * (1 - 0.004 * (tp - 25)) * 0.96 if self.inversor else 0.0
        p = max(0.0, min(p, self.limite))
        self.energia += p * dt_h
        if self.seq % 10 == 0:
            self._guardar()
        return {"irradiancia": round(max(0, irr + ruido(3 if irr > 0 else 0)), 1), "potencia": round(p, 3),
                "temp_panel": round(tp, 2), "energia_dia": round(self.energia, 3), "inversor": self.inversor}


if __name__ == "__main__":
    bus = BusDatos("gemelos", ["aula-101", "api-clima-unab"])
    time.sleep(3)
    for d in (GemeloHVAC(bus), GemeloTanque(), GemeloSolar(bus)):
        d.iniciar()
    log("gemelos", "3 gemelos digitales en marcha")
    esperar_para_siempre()
