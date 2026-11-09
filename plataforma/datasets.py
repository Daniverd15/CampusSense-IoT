#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dispositivos DataSet: reproducen datos medidos de datasets publicos como si fueran sensores en vivo.

  ds-ocupacion-uci  STOMP  UCI Occupancy Detection (oficina, 1 fila/min). Arranca en la fila con el mismo dia
                           de la semana y la misma hora que ahora, asi el ciclo dia/noche coincide con el reloj.
  ds-aire-uci       AMQP   UCI Air Quality (estacion urbana, 1 fila/hora). Envia una fila cada 5 min (x12),
                           alineada a la hora del dia.

Retroceso: apagar/encender (pausa), intervalo, calibrar, velocidad (filas por envio) y saltar (avanza N filas).
La fila del dataset que se esta enviando queda en el estado (campo "fila") para trazabilidad.
"""
import csv
import datetime as dt
import os
import time

from comun import Dispositivo, esperar_para_siempre, log

DIR = os.environ.get("DATASETS_DIR", "/app/datasets")


def cargar(nombre):
    with open(os.path.join(DIR, nombre), newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    for r in filas:
        r["_ts"] = dt.datetime.strptime(r.pop("ts"), "%Y-%m-%d %H:%M:%S")
    return filas


class Repeticion(Dispositivo):
    archivo, columnas, paso_alineacion = None, {}, "minuto"

    def __init__(self, dev_id):
        self.filas = cargar(self.archivo)
        self.i, self.factor = None, 1
        super().__init__(dev_id)
        if self.i is None or self.i >= len(self.filas):
            self.i = self._alinear()
        log(self.id, "%d filas de %s; empieza en fila %d (%s)" % (len(self.filas), self.archivo, self.i, self.filas[self.i]["_ts"]))

    def _alinear(self):
        ahora = dt.datetime.utcnow() - dt.timedelta(hours=5)
        for k, r in enumerate(self.filas):
            t = r["_ts"]
            if self.paso_alineacion == "minuto" and t.weekday() == ahora.weekday() and t.hour == ahora.hour and t.minute == ahora.minute:
                return k
            if self.paso_alineacion == "hora" and t.hour == ahora.hour:
                return k
        return 0

    def comando_extra(self, accion, p):
        if accion == "velocidad":
            f = int(p.get("factor", 1))
            if not 1 <= f <= 20:
                raise ValueError("factor fuera de 1..20")
            self.factor = f
            return "velocidad x%d" % f
        if accion == "saltar":
            n = int(p.get("filas", 0))
            self.i = (self.i + n) % len(self.filas)
            return "fila %d (%s)" % (self.i, self.filas[self.i]["_ts"])
        raise ValueError("accion desconocida: %s" % accion)

    def estado_extra(self):
        return {"fila": self.i if self.i is not None else -1, "velocidad": self.factor}

    def cargar_extra(self, e):
        self.i, self.factor = e.get("fila"), e.get("velocidad", 1)

    def guardar_extra(self):
        return {"fila": self.i, "velocidad": self.factor}

    def medir(self):
        r = self.filas[self.i]
        v = {dest: float(r[src]) for dest, src in self.columnas.items()}
        self.i = (self.i + self.factor) % len(self.filas)
        if self.seq % 10 == 0:
            self._guardar()
        return v


class DsOcupacion(Repeticion):
    archivo, paso_alineacion = "occupancy.csv", "minuto"
    columnas = {"temperatura": "temperatura", "humedad": "humedad", "luz": "luz", "co2": "co2",
                "humedad_ratio": "humedad_ratio", "ocupacion": "ocupacion"}

    def __init__(self):
        super().__init__("ds-ocupacion-uci")


class DsAire(Repeticion):
    archivo, paso_alineacion = "airquality.csv", "hora"
    columnas = {"co": "co_mg_m3", "nox": "nox_ppb", "no2": "no2_ug_m3", "benceno": "c6h6_ug_m3",
                "temperatura": "temperatura", "humedad": "humedad", "humedad_abs": "humedad_abs"}

    def __init__(self):
        super().__init__("ds-aire-uci")


if __name__ == "__main__":
    for d in (DsOcupacion(), DsAire()):
        d.iniciar()
    log("datasets", "2 dispositivos dataset en marcha")
    esperar_para_siempre()
