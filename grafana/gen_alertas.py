#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera grafana/provisioning/alerting/alertas.yml: reglas de Grafana Alerting + punto de contacto webhook.

Las alertas de Grafana llegan a la API (/api/alertas/grafana) y quedan junto a las del motor de reglas,
en InfluxDB (measurement alertas) y en el front. El token se toma de la variable de entorno INGEST_TOKEN.
Uso: python grafana/gen_alertas.py
"""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))


def flux_ventana(dev, campo):
    return ('from(bucket: "campus")\n'
            '  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            '  |> filter(fn: (r) => r._measurement == "telemetria" and r.dispositivo == "%s" and r._field == "%s")\n'
            '  |> keep(columns: ["_time", "_value", "dispositivo"])' % (dev, campo))


SIN_DATOS = ('from(bucket: "campus")\n'
             '  |> range(start: -3d)\n'
             '  |> filter(fn: (r) => r._measurement == "telemetria" and r._field == "seq" and r.dispositivo != "esp32-wokwi")\n'
             '  |> group(columns: ["dispositivo"])\n'
             '  |> last()\n'
             '  |> map(fn: (r) => ({r with _value: float(v: uint(v: now()) - uint(v: r._time)) / 1000000000.0}))\n'
             '  |> keep(columns: ["_time", "_value", "dispositivo"])')

# uid, titulo, flux, ventana_s, reductor, operador, umbral, for, severidad, resumen
REGLAS = [
    ("co2-aula", "CO2 alto Aula 101", flux_ventana("aula-101", "co2"), 300, "mean", "gt", 1000, "5m", "warning",
     "CO2 promedio 5 min en Aula 101: {{ printf \"%.0f\" $values.B.Value }} ppm (umbral 1000)"),
    ("temp-aula", "Temperatura alta Aula 101", flux_ventana("aula-101", "temperatura"), 600, "mean", "gt", 28, "10m", "warning",
     "Temperatura promedio 10 min en Aula 101: {{ printf \"%.1f\" $values.B.Value }} °C (umbral 28)"),
    ("tanque-bajo", "Tanque de agua bajo", flux_ventana("twin-tanque-agua", "nivel"), 120, "last", "lt", 20, "1m", "critical",
     "Nivel del tanque: {{ printf \"%.1f\" $values.B.Value }} % (umbral 20)"),
    ("pm25-lab", "PM2.5 alto Lab. Química", flux_ventana("lab-quimica", "pm25"), 300, "mean", "gt", 35, "5m", "warning",
     "PM2.5 promedio 5 min en Lab. Química: {{ printf \"%.1f\" $values.B.Value }} µg/m³ (umbral 35)"),
    ("aire-exterior", "Calidad del aire exterior mala", flux_ventana("api-aire-unab", "indice_global"), 3600, "last", "gt", 100, "0s", "warning",
     "Índice global de calidad del aire: {{ printf \"%.0f\" $values.B.Value }} (umbral 100)"),
    ("sin-datos", "Dispositivo sin datos", SIN_DATOS, 600, "last", "gt", 2700, "2m", "critical",
     "{{ $labels.dispositivo }} lleva {{ printf \"%.0f\" $values.B.Value }} s sin telemetría"),
]


def regla(uid, titulo, flux, ventana, red, op, umbral, para, sev, resumen):
    q = "\n".join("                " + l for l in flux.splitlines())
    return f"""      - uid: {uid}
        title: {titulo}
        condition: C
        data:
          - refId: A
            relativeTimeRange: {{from: {ventana}, to: 0}}
            datasourceUid: influx-campus
            model:
              refId: A
              intervalMs: 15000
              maxDataPoints: 500
              query: |
{q}
          - refId: B
            datasourceUid: __expr__
            model: {{refId: B, type: reduce, expression: A, reducer: {red}, settings: {{mode: dropNN}}}}
          - refId: C
            datasourceUid: __expr__
            model:
              refId: C
              type: threshold
              expression: B
              conditions:
                - evaluator: {{type: {op}, params: [{umbral}]}}
        for: {para}
        noDataState: OK
        execErrState: OK
        labels:
          severity: {sev}
          regla: {uid}
        annotations:
          summary: '{resumen}'
"""


def main():
    cuerpo = "".join(regla(*r) for r in REGLAS)
    yml = f"""# Generado por grafana/gen_alertas.py - Grafana Alerting aprovisionado (queda versionado en el repo).
apiVersion: 1

contactPoints:
  - orgId: 1
    name: api-campussense
    receivers:
      - uid: webhook-api
        type: webhook
        disableResolveMessage: false
        settings:
          url: http://api:8000/api/alertas/grafana?token=$INGEST_TOKEN
          httpMethod: POST

policies:
  - orgId: 1
    receiver: api-campussense
    group_by: [alertname, dispositivo]
    group_wait: 30s
    group_interval: 2m
    repeat_interval: 4h

groups:
  - orgId: 1
    name: umbrales-campus
    folder: Alertas CampusSense
    interval: 1m
    rules:
{cuerpo}"""
    ruta = os.path.join(AQUI, "provisioning", "alerting", "alertas.yml")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(yml)
    print("OK", ruta, len(REGLAS), "reglas")


if __name__ == "__main__":
    main()
