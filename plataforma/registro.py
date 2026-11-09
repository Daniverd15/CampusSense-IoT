# -*- coding: utf-8 -*-
"""Registro unico de dispositivos de CampusSense UNAB.

Lo usan los dispositivos, el ingestor, la API, el front, el generador de dashboards y el informe:
un solo lugar define id, tipo, protocolo, variables (unidad y rango fisico) e intervalo.
"""

# variable: (unidad, minimo, maximo)  -> el ingestor descarta valores fuera del rango fisico
DISPOSITIVOS = {
    # ------------------------------------------------------------------ REALES
    "aula-101": {
        "nombre": "Nodo ambiental Aula 101", "tipo": "real", "protocolo": "mqtt", "intervalo": 15,
        "ubicacion": "Edificio L, aula 101",
        "hardware": "ESP32 + SCD41 (CO2/T/HR) + INMP441 (ruido) + BH1750 (luz) + PIR/conteo",
        "variables": {"temperatura": ("°C", 10, 40), "humedad": ("%", 10, 100), "co2": ("ppm", 350, 5000),
                      "ruido": ("dBA", 25, 110), "ocupacion": ("personas", 0, 60), "luz": ("lux", 0, 2000)},
    },
    "lab-quimica": {
        "nombre": "Nodo calidad de aire Lab. Química", "tipo": "real", "protocolo": "mqtt", "intervalo": 20,
        "ubicacion": "Edificio de laboratorios, piso 2",
        "hardware": "ESP32 + SHT31 (T/HR) + PMS5003 (PM2.5) + SGP40 (VOC) + relé extractor",
        "variables": {"temperatura": ("°C", 10, 40), "humedad": ("%", 10, 100), "pm25": ("µg/m³", 0, 500),
                      "voc": ("ppb", 0, 5000), "extractor": ("on/off", 0, 1)},
    },
    "medidor-bloque-a": {
        "nombre": "Medidor de energía Bloque A", "tipo": "real", "protocolo": "amqp", "intervalo": 30,
        "ubicacion": "Tablero general Bloque A",
        "hardware": "Medidor trifásico Modbus (PZEM-004T x3) + gateway Raspberry Pi",
        "variables": {"voltaje": ("V", 100, 140), "corriente": ("A", 0, 600), "potencia": ("kW", 0, 80),
                      "fp": ("", 0.5, 1.0), "frecuencia": ("Hz", 59, 61), "energia": ("kWh", 0, 1e7)},
    },
    "esp32-wokwi": {
        "nombre": "ESP32 de demostración (Wokwi)", "tipo": "real", "protocolo": "mqtt", "intervalo": 10,
        "ubicacion": "Simulador Wokwi (firmware real Arduino/ESP32)",
        "hardware": "ESP32 DevKit + DHT22 + LDR + potenciómetro + LED",
        "variables": {"temperatura": ("°C", -40, 80), "humedad": ("%", 0, 100), "luz": ("lux", 0, 100000),
                      "potenciometro": ("%", 0, 100), "led": ("on/off", 0, 1)},
    },
    # ------------------------------------------------------------------ GEMELOS DIGITALES
    "twin-hvac-aula101": {
        "nombre": "Gemelo digital HVAC Aula 101", "tipo": "twin", "protocolo": "coap", "intervalo": 30,
        "ubicacion": "Modelo térmico del Aula 101 (lee aula-101 y api-clima-unab)",
        "hardware": "Modelo RC de 1er orden + controlador PI del aire acondicionado",
        "variables": {"temp_modelo": ("°C", 10, 40), "temp_suministro": ("°C", 8, 35), "setpoint": ("°C", 16, 30),
                      "potencia": ("kW", 0, 10), "modo": ("0 apagado, 1 auto, 2 ventilación, 3 eco", 0, 3),
                      "error_modelo": ("°C", -15, 15)},
    },
    "twin-tanque-agua": {
        "nombre": "Gemelo digital tanque elevado", "tipo": "twin", "protocolo": "coap", "intervalo": 30,
        "ubicacion": "Tanque elevado 20 m³ (balance de masa)",
        "hardware": "Modelo de balance de masa + control de bomba por histéresis",
        "variables": {"nivel": ("%", 0, 100), "volumen": ("m³", 0, 20), "caudal_entrada": ("L/min", 0, 400),
                      "caudal_salida": ("L/min", 0, 400), "bomba": ("on/off", 0, 1), "presion": ("bar", 0, 5)},
    },
    "twin-panel-solar": {
        "nombre": "Gemelo digital planta solar 12 kWp", "tipo": "twin", "protocolo": "http", "intervalo": 30,
        "ubicacion": "Cubierta Bloque A (lee nubosidad de api-clima-unab)",
        "hardware": "Modelo cielo despejado + nubosidad + temperatura de celda",
        "variables": {"irradiancia": ("W/m²", 0, 1400), "potencia": ("kW", 0, 15), "temp_panel": ("°C", 0, 85),
                      "energia_dia": ("kWh", 0, 150), "inversor": ("on/off", 0, 1)},
    },
    # ------------------------------------------------------------------ API
    "api-clima-unab": {
        "nombre": "Clima actual UNAB (Azure Maps Weather)", "tipo": "api", "protocolo": "mqtt", "intervalo": 600,
        "ubicacion": "7.1170, -73.1053 (campus El Jardín)",
        "hardware": "Azure Maps Weather - Current Conditions v1.1 (HTTPS -> MQTT)",
        "variables": {"temperatura": ("°C", -10, 50), "sensacion": ("°C", -20, 60), "humedad": ("%", 0, 100),
                      "punto_rocio": ("°C", -20, 40), "presion": ("hPa", 900, 1100), "viento": ("km/h", 0, 200),
                      "rafaga": ("km/h", 0, 250), "uv": ("índice", 0, 16), "nubosidad": ("%", 0, 100),
                      "visibilidad": ("km", 0, 100), "precipitacion": ("mm/h", 0, 200)},
    },
    "api-aire-unab": {
        "nombre": "Calidad del aire UNAB (Azure Maps Air Quality)", "tipo": "api", "protocolo": "mqtt", "intervalo": 900,
        "ubicacion": "7.1170, -73.1053",
        "hardware": "Azure Maps Weather - Air Quality v1.1 (HTTPS -> MQTT)",
        "variables": {"indice_global": ("índice", 0, 500), "pm25": ("µg/m³", 0, 1000), "pm10": ("µg/m³", 0, 1000),
                      "no2": ("µg/m³", 0, 2000), "o3": ("µg/m³", 0, 2000), "co": ("µg/m³", 0, 50000),
                      "so2": ("µg/m³", 0, 2000)},
    },
    "api-bus-ruta1": {
        "nombre": "Bus UNAB Ruta 1 (GPS)", "tipo": "api", "protocolo": "mqtt", "intervalo": 60,
        "ubicacion": "Rutas UNAB (gpsmobile.co)",
        "hardware": "API REST del rastreador GPS del bus (HTTP Basic -> MQTT)",
        "variables": {"lat": ("°", 6.5, 7.6), "lon": ("°", -73.6, -72.6), "velocidad": ("km/h", 0, 140),
                      "encendido": ("on/off", 0, 1), "bateria_ext": ("V", 0, 40), "bateria_int": ("V", 0, 6),
                      "distancia_campus": ("km", 0, 100)},
    },
    # ------------------------------------------------------------------ DATASET
    "ds-ocupacion-uci": {
        "nombre": "Oficina - UCI Occupancy Detection", "tipo": "dataset", "protocolo": "stomp", "intervalo": 60,
        "ubicacion": "Repetición del dataset UCI (Candanedo 2016), 1 fila/min alineada a la hora del día",
        "hardware": "Dataset UCI 357 (20 560 filas a 1 min)",
        "variables": {"temperatura": ("°C", 10, 40), "humedad": ("%", 0, 100), "luz": ("lux", 0, 2000),
                      "co2": ("ppm", 300, 3000), "humedad_ratio": ("kg/kg", 0, 0.02), "ocupacion": ("0/1", 0, 1)},
    },
    "ds-aire-uci": {
        "nombre": "Estación urbana - UCI Air Quality", "tipo": "dataset", "protocolo": "amqp", "intervalo": 300,
        "ubicacion": "Repetición del dataset UCI (De Vito 2008), 1 fila horaria cada 5 min (x12)",
        "hardware": "Dataset UCI 360 (7 620 filas horarias)",
        "variables": {"co": ("mg/m³", 0, 20), "nox": ("ppb", 0, 2000), "no2": ("µg/m³", 0, 500),
                      "benceno": ("µg/m³", 0, 100), "temperatura": ("°C", -10, 50), "humedad": ("%", 0, 100),
                      "humedad_abs": ("g/m³", 0, 5)},
    },
}

# comandos de retroceso que acepta todo dispositivo; los gemelos y algunos reales agregan los suyos
COMANDOS_COMUNES = {
    "encender": "Reanuda el envío de telemetría",
    "apagar": "Detiene la telemetría (solo queda un latido de estado cada 60 s)",
    "intervalo": "Cambia el periodo de muestreo: {\"segundos\": N}",
    "calibrar": "Offset y ganancia por variable: {\"variable\": \"temperatura\", \"offset\": -0.5, \"ganancia\": 1.0}",
    "reset": "Vuelve a la configuración de fábrica (intervalo y calibración)",
}
COMANDOS_EXTRA = {
    "lab-quimica": {"extractor": "Fuerza el extractor: {\"estado\": \"on\"|\"off\"|\"auto\"}"},
    "esp32-wokwi": {"led": "Enciende o apaga el LED: {\"estado\": \"on\"|\"off\"}"},
    "twin-hvac-aula101": {"setpoint": "Temperatura objetivo: {\"valor\": 16..30}",
                          "modo": "{\"valor\": \"apagado\"|\"auto\"|\"ventilacion\"|\"eco\"}"},
    "twin-tanque-agua": {"bomba": "{\"estado\": \"on\"|\"off\"|\"auto\"}", "consumo": "Multiplica la demanda: {\"factor\": 0.5..3}"},
    "twin-panel-solar": {"limite": "Límite de potencia del inversor: {\"kw\": 0..12}"},
    "ds-ocupacion-uci": {"velocidad": "Filas por intervalo: {\"factor\": 1..20}", "saltar": "Avanza N filas: {\"filas\": N}"},
    "ds-aire-uci": {"velocidad": "Filas por intervalo: {\"factor\": 1..20}", "saltar": "Avanza N filas: {\"filas\": N}"},
}

CAMPUS = (7.117030, -73.105338)   # UNAB, campus El Jardín (Bucaramanga)


def comandos(dev_id):
    c = dict(COMANDOS_COMUNES)
    c.update(COMANDOS_EXTRA.get(dev_id, {}))
    return c
