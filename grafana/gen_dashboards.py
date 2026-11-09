#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera los 5 dashboards aprovisionados de CampusSense en grafana/dashboards/.

  01-resumen        estado de los 12 dispositivos, mensajes por protocolo, alertas y comandos
  02-ambiente       Aula 101, Lab. Química, ESP32 y dataset de oficina
  03-energia-agua   medidor, planta solar, gemelo HVAC (modelo vs medido) y tanque
  04-exterior       clima y aire de Azure Maps, dataset urbano y bus GPS (mapa)
  05-retroceso      comandos (anotaciones), estado encendido/intervalo, RTT de ACK y latencia por protocolo

Todos los paneles de series muestran min / promedio / max / ultimo del rango elegido en el selector de tiempo
(el "ajuste de tiempo": la agregacion se adapta con v.windowPeriod).
Uso: python grafana/gen_dashboards.py
"""
import json
import os

DS = {"type": "influxdb", "uid": "influx-campus"}
B = "campus"
AQUI = os.path.dirname(os.path.abspath(__file__))
LEYENDA = {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["min", "mean", "max", "lastNotNull"]},
           "tooltip": {"mode": "multi", "sort": "none"}}
COL = ["#1f6feb", "#e8590c", "#2f9e44", "#9c36b5", "#c92a2a", "#0c8599", "#f08c00", "#5c7cfa"]


def serie(dev, campo, nombre, fn="mean", medida="telemetria"):
    return ('from(bucket: "%s")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            '  |> filter(fn: (r) => r._measurement == "%s" and r.dispositivo == "%s" and r._field == "%s")\n'
            '  |> aggregateWindow(every: v.windowPeriod, fn: %s, createEmpty: false)\n'
            '  |> set(key: "serie", value: "%s")\n  |> keep(columns: ["_time", "_value", "serie"])' % (B, medida, dev, campo, fn, nombre))


def total(dev, campo, nombre, fn):
    """Una sola cifra del rango completo: mean / max / min."""
    return ('from(bucket: "%s")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            '  |> filter(fn: (r) => r._measurement == "telemetria" and r.dispositivo == "%s" and r._field == "%s")\n'
            '  |> group()\n  |> %s()\n  |> set(key: "serie", value: "%s")\n  |> keep(columns: ["_value", "serie"])' % (B, dev, campo, fn, nombre))


class Tablero:
    def __init__(self, uid, titulo, texto, tags):
        self.uid, self.titulo, self.texto, self.tags = uid, titulo, texto, tags
        self.paneles, self.y, self.id = [], 0, 1
        self.anotaciones = []
        if texto:
            self.add({"type": "text", "title": "", "transparent": True, "options": {"mode": "markdown", "content": texto}}, 24, 3)

    def add(self, p, w, h, x=None):
        if x is None:
            x = getattr(self, "_x", 0)
            if x + w > 24:
                x, self.y = 0, self.y + getattr(self, "_h", 0)
                self._h = 0
        p.update({"id": self.id, "gridPos": {"x": x, "y": self.y, "w": w, "h": h}})
        self.id += 1
        self.paneles.append(p)
        self._x, self._h = x + w, max(getattr(self, "_h", 0), h)
        if self._x >= 24:
            self._x, self.y, self._h = 0, self.y + self._h, 0
        return p

    def fila(self, titulo):
        if getattr(self, "_x", 0):
            self._x, self.y, self._h = 0, self.y + self._h, 0
        self.add({"type": "row", "title": titulo, "collapsed": False, "panels": []}, 24, 1)

    def ts(self, titulo, consultas, unidad="", w=12, h=8, desc="", umbrales=None, extra_def=None, step=False, minimo=None):
        cfg = {"drawStyle": "line", "lineWidth": 1.5, "fillOpacity": 6, "showPoints": "never", "spanNulls": 3600000,
               "lineInterpolation": "stepAfter" if step else "linear"}
        d = {"unit": unidad, "custom": cfg, "displayName": "${__field.labels.serie}", "color": {"mode": "palette-classic"}}
        if minimo is not None:
            d["min"] = minimo
        if umbrales:
            d["thresholds"] = {"mode": "absolute", "steps": [{"color": "transparent", "value": None}] +
                               [{"color": c, "value": v} for v, c in umbrales]}
            cfg["thresholdsStyle"] = {"mode": "dashed"}
        if extra_def:
            d.update(extra_def)
        return self.add({"type": "timeseries", "title": titulo, "description": desc, "datasource": DS,
                         "targets": [{"refId": chr(65 + i), "datasource": DS, "query": q} for i, q in enumerate(consultas)],
                         "fieldConfig": {"defaults": d, "overrides": []}, "options": LEYENDA}, w, h)

    def stat(self, titulo, consultas, unidad="", w=4, h=4, desc="", decimales=1, color="#0f766e", pasos=None):
        d = {"unit": unidad, "decimals": decimales, "displayName": "${__field.labels.serie}",
             "color": {"mode": "fixed", "fixedColor": color} if not pasos else {"mode": "thresholds"}}
        if pasos:
            d["thresholds"] = {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in pasos]}
        return self.add({"type": "stat", "title": titulo, "description": desc, "datasource": DS,
                         "targets": [{"refId": chr(65 + i), "datasource": DS, "query": q} for i, q in enumerate(consultas)],
                         "fieldConfig": {"defaults": d, "overrides": []},
                         "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                                     "colorMode": "value", "graphMode": "none", "textMode": "value_and_name",
                                     "orientation": "horizontal", "justifyMode": "auto"}}, w, h)

    def resumen(self, dev, campo, nombre, unidad, w=6, h=4, decimales=1):
        """Promedio, maximo y minimo del rango seleccionado para una variable."""
        return self.stat("%s — promedio / máx / mín del rango" % nombre,
                         [total(dev, campo, "promedio", "mean"), total(dev, campo, "máximo", "max"), total(dev, campo, "mínimo", "min")],
                         unidad, w, h, "Calculado sobre todo el rango elegido en el selector de tiempo.", decimales)

    def tabla(self, titulo, consulta, w=12, h=8, desc="", transform=None, overrides=None):
        return self.add({"type": "table", "title": titulo, "description": desc, "datasource": DS,
                         "targets": [{"refId": "A", "datasource": DS, "query": consulta}],
                         "fieldConfig": {"defaults": {}, "overrides": overrides or []},
                         "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
                         "transformations": transform or []}, w, h)

    def json(self):
        return {"uid": self.uid, "title": self.titulo, "tags": self.tags, "timezone": "America/Bogota",
                "schemaVersion": 39, "version": 1, "editable": False, "refresh": "1m", "graphTooltip": 1,
                "time": {"from": "now-24h", "to": "now"},
                "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m"]},
                "annotations": {"list": self.anotaciones}, "templating": {"list": []},
                "links": [{"title": "CampusSense", "type": "dashboards", "tags": ["campussense"], "asDropdown": True}],
                "panels": self.paneles}


ANOT_CMD = {"name": "Comandos (retroceso)", "datasource": DS, "enable": True, "iconColor": "#e8590c",
            "target": {"refId": "Anno", "query": 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                       '  |> filter(fn: (r) => r._measurement == "comandos" and r._field == "params")\n'
                       '  |> map(fn: (r) => ({_time: r._time, text: r.dispositivo + ": " + r.accion + " " + r._value + " (" + r.origen + ")"}))'}}
ANOT_ALERTA = {"name": "Alertas", "datasource": DS, "enable": True, "iconColor": "#c92a2a",
               "target": {"refId": "Alr", "query": 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                          '  |> filter(fn: (r) => r._measurement == "alertas" and r._field == "mensaje")\n'
                          '  |> map(fn: (r) => ({_time: r._time, text: r.regla + " [" + r.dispositivo + "]: " + r._value}))'}}

tableros = []

# =============================================================================== 01 resumen
t = Tablero("campus-resumen", "CampusSense · 1. Resumen de la plataforma",
            "## CampusSense UNAB — IoT a la medida\n12 dispositivos (**4 reales · 3 gemelos digitales · 3 API · 2 dataset**) por **MQTT, AMQP, STOMP, CoAP y HTTP** "
            "→ Mosquitto / RabbitMQ → ingestor y API → **InfluxDB** → Grafana. El retroceso (comandos) usa el mismo protocolo de cada dispositivo. Hora de Bogotá.",
            ["campussense"])
t.anotaciones = [ANOT_CMD, ANOT_ALERTA]
t.stat("Dispositivos con datos (últimos 10 min)", ['from(bucket: "campus")\n  |> range(start: -10m)\n  |> filter(fn: (r) => r._measurement == "telemetria" and r._field == "seq")\n  |> group(columns: ["dispositivo"])\n  |> last()\n  |> group()\n  |> count()\n  |> set(key: "serie", value: "en línea")'],
       "none", 6, 4, "Dispositivos distintos que enviaron telemetría en los últimos 10 minutos (12 posibles; el ESP32 de Wokwi solo en sesiones).", 0,
       pasos=[(None, "#c92a2a"), (9, "#f08c00"), (11, "#2f9e44")])
t.stat("Mensajes en el rango", ['from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r._measurement == "telemetria" and r._field == "seq")\n  |> group()\n  |> count()\n  |> set(key: "serie", value: "telemetría")'],
       "short", 6, 4, "Mensajes de telemetría guardados en InfluxDB en el rango elegido.", 0)
t.stat("Alertas activas", ['from(bucket: "campus")\n  |> range(start: -30d)\n  |> filter(fn: (r) => r._measurement == "alertas" and r._field == "activa")\n  |> group(columns: ["regla", "dispositivo"])\n  |> last()\n  |> group()\n  |> sum()\n  |> set(key: "serie", value: "activas")'],
       "none", 6, 4, "Última transición de cada regla: 1 = disparada, 0 = resuelta.", 0, pasos=[(None, "#2f9e44"), (1, "#c92a2a")])
t.stat("Comandos en el rango", ['from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r._measurement == "comandos" and r._field == "cmd_id")\n  |> group()\n  |> count()\n  |> set(key: "serie", value: "comandos")'],
       "none", 6, 4, "Comandos de retroceso enviados (manuales y automáticos por regla).", 0, color="#e8590c")
t.tabla("Estado de los dispositivos (último mensaje)",
        'from(bucket: "campus")\n  |> range(start: -7d)\n  |> filter(fn: (r) => r._measurement == "telemetria" and r._field == "lat_ms")\n'
        '  |> group(columns: ["dispositivo", "tipo", "protocolo"])\n  |> last()\n  |> map(fn: (r) => ({dispositivo: r.dispositivo, tipo: r.tipo, protocolo: r.protocolo, ultimo: r._time, latencia_ms: r._value,\n'
        '       hace_s: (uint(v: now()) - uint(v: r._time)) / uint(v: 1000000000)}))\n  |> group()\n  |> sort(columns: ["tipo", "dispositivo"])',
        12, 10, "Último mensaje de cada dispositivo, su protocolo y la latencia dispositivo → InfluxDB.",
        overrides=[{"matcher": {"id": "byName", "options": "hace_s"}, "properties": [
            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}}, {"id": "unit", "value": "s"},
            {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 180}, {"color": "red", "value": 1200}]}}]},
            {"matcher": {"id": "byName", "options": "ultimo"}, "properties": [{"id": "unit", "value": "dateTimeAsLocal"}]}])
t.ts("Mensajes por minuto según protocolo", ['from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r._measurement == "telemetria" and r._field == "seq")\n'
                                             '  |> group(columns: ["protocolo"])\n  |> aggregateWindow(every: v.windowPeriod, fn: count, createEmpty: true)\n'
                                             '  |> map(fn: (r) => ({r with _value: float(v: r._value) * 60000000000.0 / float(v: int(v: v.windowPeriod))}))\n'
                                             '  |> map(fn: (r) => ({r with serie: r.protocolo}))\n  |> keep(columns: ["_time", "_value", "serie"])'],
     "short", 12, 10, "Caudal de mensajes por protocolo. Un hueco cae a 0.")
t.tabla("Últimas alertas", 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r._measurement == "alertas")\n'
        '  |> pivot(rowKey: ["_time", "regla", "dispositivo", "severidad", "origen"], columnKey: ["_field"], valueColumn: "_value")\n  |> group()\n'
        '  |> keep(columns: ["_time", "regla", "dispositivo", "severidad", "estado", "mensaje", "origen"])\n  |> sort(columns: ["_time"], desc: true)\n  |> limit(n: 50)', 12, 9,
        "Disparos y resoluciones del motor de reglas (origen=reglas) y de Grafana Alerting (origen=grafana).")
t.tabla("Últimos comandos de retroceso", 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r._measurement == "comandos")\n'
        '  |> pivot(rowKey: ["_time", "dispositivo", "accion", "origen", "protocolo"], columnKey: ["_field"], valueColumn: "_value")\n  |> group()\n'
        '  |> keep(columns: ["_time", "dispositivo", "accion", "params", "origen", "protocolo"])\n  |> sort(columns: ["_time"], desc: true)\n  |> limit(n: 50)', 12, 9,
        "Cada comando queda registrado con su origen (manual desde el front o regla automática) y el protocolo por el que viajó.")
tableros.append(("01-resumen.json", t))

# =============================================================================== 02 ambiente
t = Tablero("campus-ambiente", "CampusSense · 2. Ambiente interior",
            "**Aula 101** (real, MQTT) · **Lab. Química** (real, MQTT) · **ESP32 Wokwi** (real, MQTT por Internet) · **Oficina UCI** (dataset, STOMP). "
            "Umbrales: CO₂ 1000 ppm (regla R1 → HVAC a ventilación), PM2.5 35 µg/m³ (R4).", ["campussense"])
t.anotaciones = [ANOT_CMD, ANOT_ALERTA]
t.fila("Aula 101 — nodo ambiental (aula-101)")
t.resumen("aula-101", "co2", "CO₂ Aula 101", "ppm", 8, 4, 0)
t.resumen("aula-101", "temperatura", "Temperatura Aula 101", "celsius", 8, 4, 1)
t.resumen("aula-101", "ocupacion", "Ocupación Aula 101", "none", 8, 4, 0)
t.ts("CO₂ y ocupación", [serie("aula-101", "co2", "CO₂ (ppm)"), serie("aula-101", "ocupacion", "ocupación (personas)")], "", 12, 8,
     "El CO₂ sube con la gente y baja cuando el gemelo HVAC pasa a ventilación (anotaciones naranjas).", umbrales=[(1000, "red")],
     extra_def={}, minimo=0)
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "ocupación (personas)"},
                                              "properties": [{"id": "custom.axisPlacement", "value": "right"}, {"id": "custom.drawStyle", "value": "bars"},
                                                             {"id": "custom.fillOpacity", "value": 30}]}]
t.ts("Temperatura y humedad", [serie("aula-101", "temperatura", "temperatura (°C)"), serie("aula-101", "humedad", "humedad (%)")], "", 12, 8)
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "humedad (%)"}, "properties": [{"id": "custom.axisPlacement", "value": "right"}]}]
t.ts("Ruido", [serie("aula-101", "ruido", "ruido")], "dB", 12, 6)
t.ts("Iluminación", [serie("aula-101", "luz", "luz")], "lux", 12, 6)
t.fila("Laboratorio de Química (lab-quimica)")
t.resumen("lab-quimica", "pm25", "PM2.5 Lab. Química", "conμgm3", 12, 4, 1)
t.resumen("lab-quimica", "voc", "VOC Lab. Química", "ppb", 12, 4, 0)
t.ts("PM2.5 y VOC (con extractor)", [serie("lab-quimica", "pm25", "PM2.5 (µg/m³)"), serie("lab-quimica", "voc", "VOC (ppb)"),
                                     serie("lab-quimica", "extractor", "extractor (0/1)", "max")], "", 16, 8, umbrales=[(35, "red")])
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "VOC (ppb)"}, "properties": [{"id": "custom.axisPlacement", "value": "right"}]},
                                             {"matcher": {"id": "byName", "options": "extractor (0/1)"}, "properties": [{"id": "custom.drawStyle", "value": "bars"}, {"id": "custom.fillOpacity", "value": 20}, {"id": "custom.axisPlacement", "value": "hidden"}]}]
t.ts("Temperatura y humedad del laboratorio", [serie("lab-quimica", "temperatura", "temperatura (°C)"), serie("lab-quimica", "humedad", "humedad (%)")], "", 8, 8)
t.fila("ESP32 de demostración (Wokwi) y oficina del dataset UCI")
t.ts("ESP32 Wokwi: DHT22 y LDR", [serie("esp32-wokwi", "temperatura", "temperatura (°C)"), serie("esp32-wokwi", "humedad", "humedad (%)"),
                                  serie("esp32-wokwi", "potenciometro", "potenciómetro (%)"), serie("esp32-wokwi", "led", "LED", "max")], "", 12, 8,
     "Firmware real de ESP32 corriendo en el simulador Wokwi, conectado por Internet al broker MQTT. Solo transmite durante las sesiones de demostración.")
t.ts("Oficina UCI: CO₂, luz y ocupación", [serie("ds-ocupacion-uci", "co2", "CO₂ (ppm)"), serie("ds-ocupacion-uci", "luz", "luz (lux)"),
                                           serie("ds-ocupacion-uci", "ocupacion", "ocupación (0/1)", "max")], "", 12, 8,
     "Dataset UCI Occupancy Detection repetido a 1 fila/min, alineado al día de la semana y la hora actuales.")
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "ocupación (0/1)"}, "properties": [{"id": "custom.axisPlacement", "value": "hidden"}, {"id": "custom.drawStyle", "value": "bars"}, {"id": "custom.fillOpacity", "value": 25}]}]
tableros.append(("02-ambiente.json", t))

# =============================================================================== 03 energia y agua
t = Tablero("campus-energia", "CampusSense · 3. Energía, HVAC y agua",
            "**Medidor Bloque A** (real, AMQP) · **Planta solar 12 kWp** (gemelo, HTTP) · **HVAC Aula 101** (gemelo, CoAP) · **Tanque 20 m³** (gemelo, CoAP). "
            "La potencia de red = carga − solar. Regla R2: demanda > 30 kW → HVAC a eco.", ["campussense"])
t.anotaciones = [ANOT_CMD, ANOT_ALERTA]
t.fila("Energía")
t.resumen("medidor-bloque-a", "potencia", "Potencia de red Bloque A", "kwatt", 8, 4, 2)
t.resumen("twin-panel-solar", "potencia", "Potencia solar", "kwatt", 8, 4, 2)
t.resumen("twin-panel-solar", "irradiancia", "Irradiancia", "Wm2", 8, 4, 0)
t.ts("Potencia de red vs generación solar vs HVAC", [serie("medidor-bloque-a", "potencia", "red Bloque A (kW)"), serie("twin-panel-solar", "potencia", "solar (kW)"),
                                                     serie("twin-hvac-aula101", "potencia", "HVAC Aula 101 (kW)")], "kwatt", 16, 8, umbrales=[(30, "red")], minimo=0)
t.ts("Energía solar del día", [serie("twin-panel-solar", "energia_dia", "energía del día", "last")], "kwatth", 8, 8, minimo=0)
t.ts("Irradiancia y temperatura de panel", [serie("twin-panel-solar", "irradiancia", "irradiancia (W/m²)"), serie("twin-panel-solar", "temp_panel", "temp. panel (°C)")], "", 12, 7)
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "temp. panel (°C)"}, "properties": [{"id": "custom.axisPlacement", "value": "right"}]}]
t.ts("Voltaje y factor de potencia", [serie("medidor-bloque-a", "voltaje", "voltaje (V)"), serie("medidor-bloque-a", "fp", "factor de potencia")], "", 12, 7)
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "factor de potencia"}, "properties": [{"id": "custom.axisPlacement", "value": "right"}]}]
t.fila("Gemelo digital HVAC — modelo vs aula real")
t.ts("Temperatura medida (aula-101) vs predicha por el gemelo", [serie("aula-101", "temperatura", "medida (aula-101)"), serie("twin-hvac-aula101", "temp_modelo", "modelo del gemelo"),
                                                               serie("twin-hvac-aula101", "setpoint", "setpoint", "last")], "celsius", 12, 8,
     "Un gemelo digital sirve si predice bien: la diferencia (error del modelo) debería quedarse cerca de 0.")
t.ts("Error del modelo y modo del HVAC", [serie("twin-hvac-aula101", "error_modelo", "error medido − modelo (°C)"), serie("twin-hvac-aula101", "modo", "modo (0 apag. 1 auto 2 vent. 3 eco)", "last")], "", 12, 8, step=False)
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "modo (0 apag. 1 auto 2 vent. 3 eco)"}, "properties": [{"id": "custom.axisPlacement", "value": "right"}, {"id": "custom.lineInterpolation", "value": "stepAfter"}]}]
t.fila("Gemelo digital tanque de agua")
t.resumen("twin-tanque-agua", "nivel", "Nivel del tanque", "percent", 8, 4, 1)
t.ts("Nivel y bomba", [serie("twin-tanque-agua", "nivel", "nivel (%)"), serie("twin-tanque-agua", "bomba", "bomba (0/1)", "max")], "", 16, 8, umbrales=[(20, "red")], minimo=0)
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "bomba (0/1)"}, "properties": [{"id": "custom.axisPlacement", "value": "hidden"}, {"id": "custom.drawStyle", "value": "bars"}, {"id": "custom.fillOpacity", "value": 20}]}]
t.ts("Caudales de entrada y salida", [serie("twin-tanque-agua", "caudal_entrada", "entrada (bomba)"), serie("twin-tanque-agua", "caudal_salida", "salida (consumo)")], "", 24, 7)
tableros.append(("03-energia-agua.json", t))

# =============================================================================== 04 exterior y movilidad
t = Tablero("campus-exterior", "CampusSense · 4. Exterior y movilidad",
            "**Clima y calidad del aire** de Azure Maps (API, HTTPS → MQTT) · **Estación urbana UCI** (dataset, AMQP) · **Bus UNAB Ruta 1** (API GPS, HTTP → MQTT).", ["campussense"])
t.anotaciones = [ANOT_CMD, ANOT_ALERTA]
t.fila("Clima en el campus (api-clima-unab)")
t.resumen("api-clima-unab", "temperatura", "Temperatura exterior", "celsius", 8, 4, 1)
t.resumen("api-clima-unab", "humedad", "Humedad exterior", "percent", 8, 4, 0)
t.resumen("api-clima-unab", "nubosidad", "Nubosidad", "percent", 8, 4, 0)
t.ts("Temperatura, sensación y punto de rocío", [serie("api-clima-unab", "temperatura", "temperatura"), serie("api-clima-unab", "sensacion", "sensación térmica"),
                                                serie("api-clima-unab", "punto_rocio", "punto de rocío")], "celsius", 12, 8)
t.ts("Humedad y nubosidad", [serie("api-clima-unab", "humedad", "humedad"), serie("api-clima-unab", "nubosidad", "nubosidad")], "percent", 12, 8)
t.ts("Viento y ráfagas", [serie("api-clima-unab", "viento", "viento"), serie("api-clima-unab", "rafaga", "ráfaga")], "velocitykmh", 8, 7)
t.ts("Presión", [serie("api-clima-unab", "presion", "presión")], "pressurehpa", 8, 7)
t.ts("UV y lluvia última hora", [serie("api-clima-unab", "uv", "índice UV", "max"), serie("api-clima-unab", "precipitacion", "lluvia (mm/h)", "max")], "", 8, 7)
t.fila("Calidad del aire")
t.resumen("api-aire-unab", "indice_global", "Índice global de calidad del aire", "none", 8, 4, 0)
t.ts("Índice global (Azure Maps)", [serie("api-aire-unab", "indice_global", "índice global")], "none", 16, 7, umbrales=[(100, "red")])
t.ts("Contaminantes en el campus (µg/m³)", [serie("api-aire-unab", "pm25", "PM2.5"), serie("api-aire-unab", "pm10", "PM10"), serie("api-aire-unab", "no2", "NO₂"),
                                           serie("api-aire-unab", "o3", "O₃"), serie("api-aire-unab", "so2", "SO₂")], "conμgm3", 12, 8)
t.ts("Estación urbana UCI (dataset): NO₂, NOx y benceno", [serie("ds-aire-uci", "no2", "NO₂ (µg/m³)"), serie("ds-aire-uci", "nox", "NOx (ppb)"),
                                                         serie("ds-aire-uci", "benceno", "benceno (µg/m³)")], "", 12, 8,
     "Dataset UCI Air Quality: 1 fila horaria cada 5 min (x12). La forma del día urbano (picos de tráfico) se comprime 12 veces.")
t.fila("Bus UNAB Ruta 1 (api-bus-ruta1)")
t.add({"type": "geomap", "title": "Recorrido del bus (últimas posiciones)", "datasource": DS,
       "targets": [{"refId": "A", "datasource": DS, "query": 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                    '  |> filter(fn: (r) => r._measurement == "telemetria" and r.dispositivo == "api-bus-ruta1" and (r._field == "lat" or r._field == "lon" or r._field == "velocidad"))\n'
                    '  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")\n  |> keep(columns: ["_time", "lat", "lon", "velocidad"])\n  |> group()'}],
       "fieldConfig": {"defaults": {"color": {"mode": "continuous-GrYlRd"}, "unit": "velocitykmh"}, "overrides": []},
       "options": {"view": {"id": "coords", "lat": 7.115, "lon": -73.11, "zoom": 13},
                   "controls": {"showZoom": True, "mouseWheelZoom": False},
                   "basemap": {"type": "default", "name": "Mapa"},
                   "layers": [{"type": "markers", "name": "posiciones", "location": {"mode": "coords", "latitude": "lat", "longitude": "lon"},
                               "config": {"size": {"fixed": 5}, "color": {"field": "velocidad", "fixed": "dark-green"}, "showLegend": True}}]}}, 12, 10)
t.ts("Velocidad y distancia al campus", [serie("api-bus-ruta1", "velocidad", "velocidad (km/h)", "max"), serie("api-bus-ruta1", "distancia_campus", "distancia al campus (km)")], "", 12, 10,
     umbrales=[(60, "red")])
t.paneles[-1]["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": "distancia al campus (km)"}, "properties": [{"id": "custom.axisPlacement", "value": "right"}]}]
tableros.append(("04-exterior.json", t))

# =============================================================================== 05 retroceso y reglas
t = Tablero("campus-retroceso", "CampusSense · 5. Retroceso, reglas y protocolos",
            "**Retroceso:** cada comando (encender, apagar, intervalo, calibrar, setpoint, modo…) se ve como anotación naranja y cambia el estado que reporta el dispositivo. "
            "**Reglas:** el motor de la API actúa solo (R1–R7). **Protocolos:** latencia de subida y tiempo de ida y vuelta del ACK de cada comando.", ["campussense"])
t.anotaciones = [ANOT_CMD, ANOT_ALERTA]


def estado_q(campo, nombre_por_disp=True):
    return ('from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            '  |> filter(fn: (r) => r._measurement == "estado" and r._field == "%s")\n'
            '  |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)\n'
            '  |> map(fn: (r) => ({r with serie: r.dispositivo}))\n  |> keep(columns: ["_time", "_value", "serie"])' % campo)


t.add({"type": "state-timeline", "title": "Encendido / apagado por comando (estado reportado)", "datasource": DS,
       "targets": [{"refId": "A", "datasource": DS, "query": estado_q("encendido")}],
       "fieldConfig": {"defaults": {"displayName": "${__field.labels.serie}", "color": {"mode": "thresholds"},
                                    "thresholds": {"mode": "absolute", "steps": [{"color": "#c92a2a", "value": None}, {"color": "#2f9e44", "value": 1}]},
                                    "mappings": [{"type": "value", "options": {"0": {"text": "apagado"}, "1": {"text": "encendido"}}}]}, "overrides": []},
       "options": {"showValue": "never", "rowHeight": 0.8, "mergeValues": True, "legend": {"showLegend": False}}}, 24, 9)
t.ts("Intervalo de muestreo reportado (s)", [estado_q("intervalo_s")], "s", 12, 8, "Cambia cuando se envía el comando «intervalo».", step=True)
t.ts("Modo del HVAC (gemelo) — acciones de R1/R2", [serie("twin-hvac-aula101", "modo", "modo (0 apag. 1 auto 2 vent. 3 eco)", "last")], "none", 12, 8, step=True, minimo=0)
t.add({"type": "barchart", "title": "Tiempo de ida y vuelta del ACK por protocolo (promedio del rango)", "datasource": DS,
       "targets": [{"refId": "A", "datasource": DS, "query": 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                    '  |> filter(fn: (r) => r._measurement == "ack" and r._field == "rtt_ms")\n  |> group(columns: ["protocolo"])\n  |> mean()\n'
                    '  |> group()\n  |> keep(columns: ["protocolo", "_value"])\n  |> rename(columns: {_value: "RTT ms"})'}],
       "fieldConfig": {"defaults": {"unit": "ms", "color": {"mode": "fixed", "fixedColor": "#e8590c"}}, "overrides": []},
       "options": {"orientation": "horizontal", "showValue": "always", "xField": "protocolo", "legend": {"showLegend": False}}}, 12, 8)
t.add({"type": "barchart", "title": "Latencia de subida dispositivo → InfluxDB por protocolo (promedio del rango)", "datasource": DS,
       "targets": [{"refId": "A", "datasource": DS, "query": 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
                    '  |> filter(fn: (r) => r._measurement == "telemetria" and r._field == "lat_ms")\n  |> group(columns: ["protocolo"])\n  |> mean()\n'
                    '  |> group()\n  |> keep(columns: ["protocolo", "_value"])\n  |> rename(columns: {_value: "latencia ms"})'}],
       "fieldConfig": {"defaults": {"unit": "ms", "color": {"mode": "fixed", "fixedColor": "#1f6feb"}}, "overrides": []},
       "options": {"orientation": "horizontal", "showValue": "always", "xField": "protocolo", "legend": {"showLegend": False}}}, 12, 8)
t.add({"type": "state-timeline", "title": "Reglas y alertas (1 = disparada)", "datasource": DS,
       "targets": [{"refId": "A", "datasource": DS, "query": 'from(bucket: "campus")\n  |> range(start: -30d, stop: v.timeRangeStop)\n'
                    '  |> filter(fn: (r) => r._measurement == "alertas" and r._field == "activa")\n  |> map(fn: (r) => ({r with serie: r.regla + " · " + r.dispositivo}))\n'
                    '  |> keep(columns: ["_time", "_value", "serie"])'}],
       "fieldConfig": {"defaults": {"displayName": "${__field.labels.serie}", "color": {"mode": "thresholds"},
                                    "thresholds": {"mode": "absolute", "steps": [{"color": "#2f9e44", "value": None}, {"color": "#c92a2a", "value": 1}]},
                                    "mappings": [{"type": "value", "options": {"0": {"text": "normal"}, "1": {"text": "disparada"}}}]}, "overrides": []},
       "options": {"showValue": "never", "rowHeight": 0.8, "mergeValues": True, "legend": {"showLegend": False}}}, 24, 9)
t.tabla("ACK de comandos (respuesta de los dispositivos)", 'from(bucket: "campus")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r._measurement == "ack")\n'
        '  |> pivot(rowKey: ["_time", "dispositivo", "accion", "protocolo"], columnKey: ["_field"], valueColumn: "_value")\n  |> group()\n'
        '  |> keep(columns: ["_time", "dispositivo", "protocolo", "accion", "ok", "detalle", "rtt_ms"])\n  |> sort(columns: ["_time"], desc: true)\n  |> limit(n: 60)', 24, 9)
tableros.append(("05-retroceso.json", t))

if __name__ == "__main__":
    os.makedirs(os.path.join(AQUI, "dashboards"), exist_ok=True)
    for nombre, tb in tableros:
        with open(os.path.join(AQUI, "dashboards", nombre), "w", encoding="utf-8", newline="\n") as f:
            json.dump(tb.json(), f, ensure_ascii=False, indent=1)
        print("OK", nombre, len(tb.paneles), "paneles")
