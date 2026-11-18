#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera Informe_CampusSense_UNAB.docx (proyecto final IoT) con python-docx.
Uso: python informe/build_informe.py   (luego Word -> PDF con C:/azv/work/to_pdf.ps1)
Todas las cifras salen de mediciones/export (ventana oficial) y mediciones/prueba_retroceso.json.
"""
import csv
import json
import os
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(RAIZ, "plataforma"))
from registro import DISPOSITIVOS, comandos  # noqa: E402

EV, GR, EXP = os.path.join(RAIZ, "evidencias"), os.path.join(RAIZ, "informe", "graficas"), os.path.join(RAIZ, "mediciones", "export")
SALIDA = os.path.join(RAIZ, "Informe_CampusSense_UNAB.docx")
EST = json.load(open(os.path.join(EXP, "estadisticas.json"), encoding="utf-8"))
PRO = json.load(open(os.path.join(EXP, "protocolos.json"), encoding="utf-8"))
RET = json.load(open(os.path.join(RAIZ, "mediciones", "prueba_retroceso.json"), encoding="utf-8"))["resultados"]

MORADO, NOCHE, NARANJA, GRIS, TEXTO = RGBColor(0x6D, 0x2C, 0xA0), RGBColor(0x3B, 0x15, 0x61), RGBColor(0xC9, 0x7C, 0x00), RGBColor(0x5F, 0x56, 0x6C), RGBColor(0x1D, 0x14, 0x28)
FUENTE = "Calibri"
URL = "https://campussense-unab.northcentralus.cloudapp.azure.com"
REPO = "https://github.com/Daniverd15/CampusSense-IoT"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.0)
sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
ANCHO = 21.0 - 4.0
st = doc.styles["Normal"]
st.font.name = FUENTE
st.element.rPr.rFonts.set(qn("w:eastAsia"), FUENTE)
st.font.size = Pt(10)
st.font.color.rgb = TEXTO
st.paragraph_format.space_after = Pt(4)
st.paragraph_format.line_spacing = 1.12
for nivel, tam, color in ((1, 16, MORADO), (2, 12.5, NOCHE), (3, 11, MORADO)):
    h = doc.styles["Heading %d" % nivel]
    h.font.name, h.font.size, h.font.bold, h.font.color.rgb = FUENTE, Pt(tam), True, color
    h.element.rPr.rFonts.set(qn("w:eastAsia"), FUENTE)
    h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(14 if nivel == 1 else 9), Pt(5)
    h.paragraph_format.keep_with_next = True


def runs(p, texto, negrita=False, tam=None, color=None, cursiva=False):
    for tok in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)", texto):
        if not tok:
            continue
        neg, cur, cod = negrita, cursiva, False
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            tok, neg = tok[2:-2], True
        elif tok.startswith("`") and tok.endswith("`") and len(tok) > 2:
            tok, cod = tok[1:-1], True
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            tok, cur = tok[1:-1], True
        r = p.add_run(tok)
        r.bold, r.italic = neg, cur
        if cod:
            r.font.name = "Consolas"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
            r.font.color.rgb = NOCHE
        if tam:
            r.font.size = Pt(tam - 0.8 if cod else tam)
        if color is not None and not cod:
            r.font.color.rgb = color
    return p


def P(texto="", tam=None, color=None, negrita=False, alinear=None, antes=None, despues=None, cursiva=False):
    p = doc.add_paragraph()
    if alinear is not None:
        p.alignment = alinear
    if antes is not None:
        p.paragraph_format.space_before = Pt(antes)
    if despues is not None:
        p.paragraph_format.space_after = Pt(despues)
    if texto:
        runs(p, texto, negrita, tam, color, cursiva)
    return p


def H(texto, nivel=1):
    return doc.add_heading(texto, level=nivel)


def V(texto, tam=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    runs(p, texto, tam=tam)
    return p


def sombra(c, hexcolor):
    tcPr = c._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    for k, v in (("val", "clear"), ("color", "auto"), ("fill", hexcolor)):
        sh.set(qn("w:" + k), v)
    tcPr.append(sh)


def bordes(t, color="D2C7DF"):
    b = OxmlElement("w:tblBorders")
    for k in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + k)
        for a, v in (("val", "single"), ("sz", "4"), ("space", "0"), ("color", color)):
            e.set(qn("w:" + a), v)
        b.append(e)
    t._tbl.tblPr.append(b)


def T(filas, anchos, tam=8.5, cab=True, zebra=True, primera_negrita=True):
    t = doc.add_table(rows=len(filas), cols=len(anchos))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bordes(t)
    for i, fila in enumerate(filas):
        for j, txt in enumerate(fila):
            c = t.cell(i, j)
            c.width = Cm(anchos[j])
            c.text = ""
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            es_cab = cab and i == 0
            runs(p, str(txt), negrita=es_cab or (primera_negrita and j == 0), tam=tam, color=RGBColor(255, 255, 255) if es_cab else None)
            if es_cab:
                sombra(c, "6D2CA0")
            elif zebra and i % 2 == 0:
                sombra(c, "F3F0F7")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


num_fig = [0]


def F(ruta, ancho, pie):
    num_fig[0] += 1
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(ruta, width=Cm(ancho))
    q = doc.add_paragraph()
    q.alignment = WD_ALIGN_PARAGRAPH.CENTER
    runs(q, "**Figura %d.** %s" % (num_fig[0], pie), tam=8.5, color=GRIS, cursiva=True)
    return num_fig[0]


def campo(p, instr):
    r = p.add_run()
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = "(actualizar con F9)"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    for e in (f1, it, f2, t, f3):
        r._r.append(e)


def salto():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def f(x, d=None):
    if d is None:
        a = abs(x)
        d = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 1 else 3
    return ("{:,.%df}" % d).format(x).replace(",", "X").replace(".", ",").replace("X", ".")


def s(dev, var, k="mean", d=None):
    return f(EST[dev][var][k], d)


def n(x):
    return "{:,}".format(int(x)).replace(",", ".")


cont = {d: int(max(v["count"] for v in EST[d].values())) for d in EST}
total = sum(cont.values())
alert_fire = {}
for r in csv.DictReader(open(os.path.join(EXP, "alertas.csv"), encoding="utf-8")):
    if r["estado"] == "firing":
        alert_fire[(r["regla"], r["origen"])] = alert_fire.get((r["regla"], r["origen"]), 0) + 1
reglas_cmd = {}
for r in csv.DictReader(open(os.path.join(EXP, "reglas.csv"), encoding="utf-8")):
    reglas_cmd[r["origen"]] = reglas_cmd.get(r["origen"], 0) + 1

# ====================================================================== pie de pagina con numero
for sc in doc.sections:
    fp = sc.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    runs(fp, "CampusSense UNAB · Proyecto final IoT · página ", tam=8, color=GRIS)
    campo(fp, "PAGE")

# ====================================================================== PORTADA
P("UNIVERSIDAD AUTÓNOMA DE BUCARAMANGA · IoT + Cloud + Sistemas Distribuidos", tam=9.5, color=MORADO, negrita=True, despues=2)
P("Parcial 2 · Proyecto final · IoT a la medida", tam=11, color=GRIS, despues=26)
P("CampusSense UNAB", tam=34, color=MORADO, negrita=True, despues=2)
P("Plataforma IoT propia para el campus El Jardín: 12 dispositivos, 5 protocolos, retroceso en cada dispositivo, reglas automáticas y 6 días de datos en Azure",
  tam=13.5, color=NOCHE, despues=18)
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(os.path.join(EV, "00-arquitectura.png"), width=Cm(ANCHO))
P("", despues=10)
T([["", ""],
   ["Integrantes", "Daniel Villamizar · Tomás Urieles · David Guerrero"],
   ["Plataforma en vivo", URL],
   ["Grafana", URL + "/grafana"],
   ["Repositorio", REPO],
   ["Ventana oficial de datos", "8-nov-2026 23:19 → 14-nov-2026 23:19 (hora de Bogotá): 6 días, %s mensajes" % n(total)],
   ["Fecha", "17 de noviembre de 2026 · sustentación: 20 de noviembre de 2026"]],
  [4.2, ANCHO - 4.2], tam=9.5, cab=False)
salto()

# ====================================================================== CONTENIDO
P("Contenido", tam=16, color=MORADO, negrita=True)
campo(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
salto()

# ====================================================================== RESUMEN Y CUMPLIMIENTO
H("Resumen ejecutivo")
P("CampusSense UNAB es una plataforma IoT construida y desplegada por el grupo, sin servicios IoT comerciales, en una máquina virtual de "
  "Azure con dominio propio y HTTPS. Reúne **12 dispositivos de cuatro familias** —3 nodos de campo emulados en Python y un ESP32 con firmware "
  "real en Wokwi, 3 gemelos digitales, 3 fuentes de API reales y 2 datasets públicos— que envían datos por **MQTT, AMQP, STOMP, CoAP y HTTP**. "
  "Cada dispositivo **recibe comandos de vuelta por su mismo protocolo** (encender, apagar, cambiar intervalo, calibrar, setpoint, modo…) y confirma con un ACK.")
P("Durante la ventana oficial de 6 días se guardaron **%s mensajes sin un solo hueco**: el mayor intervalo entre datos de cada dispositivo coincide con su "
  "periodo de envío. El motor de reglas actuó solo **%d veces** (R1 cambió el aire acondicionado a ventilación %d veces cuando el CO₂ del aula pasó de "
  "1000 ppm), y Grafana y el motor dispararon **%d alertas**. En la prueba formal de retroceso, **95 de 95 comandos** recibieron ACK, con medianas de 1 a 8 ms "
  "en MQTT, CoAP, STOMP y AMQP, 81 ms para el ESP32 por Internet y unos 28 s para HTTP por su naturaleza de sondeo."
  % (n(total), reglas_cmd.get("regla R1", 0) + reglas_cmd.get("regla R2", 0), reglas_cmd.get("regla R1", 0) // 2, sum(alert_fire.values())))
H("Cumplimiento del enunciado", 2)
T([["Requisito", "Cómo se cumple", "Dónde"],
   ["Elementos IoT: sensores, datos y variables, protocolos, plataforma, visualización", "12 dispositivos, 72 variables con rango físico, 5 protocolos, brokers propios, InfluxDB, Grafana y front", "§2, §3"],
   ["4 a 6 días de datos", "6 días exactos (8 nov 23:19 → 14 nov 23:19), %s mensajes, sin huecos" % n(total), "§3.4, §4"],
   ["≥10 dispositivos en Real, Digital Twin, API, DataSet con su protocolo", "4 reales, 3 gemelos, 3 API y 2 datasets; cada uno con su protocolo", "§3.1"],
   ["Retroceso: modificar, apagar, ajustar, calibrar", "Comandos por el mismo protocolo de cada dispositivo, con ACK y RTT; reglas que actúan solas", "§3.2, §5"],
   ["Nube con URL propia e infraestructura propia", "VM de Azure, Docker Compose de 11 servicios, DNS propio y HTTPS (Let's Encrypt)", "§3.3"],
   ["Arquitectura de referencia propia", "Diagrama por capas con subida, retroceso, servicios y fuentes externas", "§2"],
   ["Sensores en tabla con variables y rangos", "Tabla de dispositivos y anexo A con todas las variables", "§3.1, anexo A"],
   ["Comunicación: bróker y protocolo (envío y recepción)", "Tabla de subida y bajada por protocolo, formato de mensaje y medición", "§3.2"],
   ["Visualización y procesamiento: promedio, máx, mín, alertas, reglas, ajuste de tiempo", "5 tableros de Grafana, análisis del periodo en el front, 6 alertas de Grafana y 7 reglas", "§3.4"],
   ["Análisis de gráficas con IA", "Análisis por dispositivo y transversal, generado con IA sobre los datos exportados y revisado por el grupo", "§4"],
   ["Referencias, GitHub, URL", "Referencias en formato APA, repositorio público y plataforma en línea", "§7, portada"]],
  [5.0, 9.3, 2.7], tam=8.3)

# ====================================================================== 1. DESCRIPCION Y CONTEXTO
H("1. Descripción y contexto")
P("**Escenario.** El campus El Jardín de la UNAB (Bucaramanga, 7,117° N, −73,105° O, ~1.000 m s. n. m.) concentra aulas, laboratorios, oficinas, "
  "una red de agua con tanque elevado, el consumo eléctrico de varios bloques y la movilidad de las rutas de buses institucionales. Hoy cada uno de esos "
  "frentes se vigila por separado, o no se vigila. CampusSense propone una sola plataforma que mida, guarde, analice y actúe sobre ellos.")
P("**Problema.** Un aula llena eleva el CO₂ por encima de 1000 ppm, lo que se asocia con somnolencia y menor rendimiento; un laboratorio genera picos de "
  "partículas y compuestos volátiles durante las prácticas; la demanda eléctrica del bloque llega a picos que encarecen la factura; el tanque de agua debe "
  "mantenerse entre niveles seguros; y el clima exterior y la calidad del aire cambian durante el día. Sin datos continuos ni capacidad de responder, todo se decide tarde.")
P("**Objetivo general.** Diseñar, desplegar y operar una plataforma IoT a la medida que integre dispositivos heterogéneos, cinco protocolos de comunicación y "
  "comandos de retroceso, con visualización, procesamiento y reglas automáticas, y que funcione en la nube con URL propia durante al menos 4 días de toma.")
P("**Objetivos específicos.**")
for t in ["Integrar al menos 10 dispositivos de las cuatro familias pedidas (real, gemelo digital, API y dataset), cada uno con su protocolo.",
          "Implementar el retroceso por el mismo protocolo de cada dispositivo, con confirmación (ACK) y medición del tiempo de ida y vuelta.",
          "Guardar todo en una base de series de tiempo y visualizarlo con promedio, mínimo y máximo en el rango que elija el usuario.",
          "Automatizar respuestas: reglas que disparan alertas y comandos sin intervención humana.",
          "Desplegar en Azure con dominio propio y HTTPS, y documentar honestamente qué es real, qué es modelado y qué es repetido."]:
    V(t)
P("**Alcance y honestidad del montaje.** No se usa hardware físico (lo permite el enunciado). Los nodos «reales» de campo son firmware emulado en Python "
  "que reproduce el comportamiento del hardware descrito con modelos físicos sencillos; el ESP32 corre firmware Arduino real en el simulador Wokwi; los "
  "gemelos digitales son modelos alimentados con datos del bus; las API son datos **reales** externos; los datasets son mediciones reales públicas, repetidas "
  "en tiempo real. Cada tarjeta del front y cada sección de este informe lo rotula.")

# ====================================================================== 2. ARQUITECTURA
H("2. Arquitectura de referencia IoT propia")
F(os.path.join(EV, "00-arquitectura.png"), ANCHO, "Arquitectura de referencia de CampusSense UNAB: dispositivos, protocolos, brokers, procesamiento, almacenamiento y visualización en Azure.")
T([["Capa", "Componentes", "Función"],
   ["1. Dispositivos (percepción)", "12 dispositivos: 3 nodos Python, ESP32 Wokwi, 3 gemelos, 3 API, 2 datasets", "Miden o modelan variables y aceptan comandos"],
   ["2. Comunicación (transporte)", "MQTT 3.1.1, AMQP 0-9-1, STOMP 1.2, CoAP (UDP), HTTP REST", "Subida de telemetría, estado y ACK; bajada de comandos"],
   ["3. Brokers y endpoints", "Mosquitto 2.0, RabbitMQ 3.13 (AMQP + STOMP), servidor CoAP, endpoint HTTP", "Reciben, encolan y enrutan mensajes"],
   ["4. Procesamiento", "Ingestor Python, API FastAPI, motor de reglas, gemelos digitales", "Valida rangos, escribe, republica en el bus, enruta comandos y actúa"],
   ["5. Almacenamiento", "InfluxDB 2.7, bucket `campus`, retención 90 días", "Series de tiempo: telemetría, estado, ACK, comandos, alertas"],
   ["6. Aplicación y visualización", "Grafana 11.6 (5 tableros, 6 alertas) y front propio en tiempo real (SSE)", "Ver, analizar por rango y enviar comandos"],
   ["7. Infraestructura y seguridad", "VM Azure B2als_v2, Docker Compose, Caddy (HTTPS), NSG, DNS propio", "Despliegue, cifrado, aislamiento, claves fuera del repo"]],
  [3.7, 7.3, 6.0], tam=8.3)
P("**Flujo de subida.** Cada dispositivo publica por su protocolo un mensaje JSON `{id, tipo, kind, ts, seq, v:{variables}, estado:{…}}`. El ingestor (MQTT, AMQP "
  "con STOMP y CoAP) o la API (HTTP) valida cada variable contra su rango físico, escribe en InfluxDB con la marca de tiempo del dispositivo, solo entonces "
  "confirma al broker o al emisor, y republica el dato retenido en `campus/datos/<id>`, un bus interno del que leen los gemelos, la API, el motor de reglas y el front.")
P("**Flujo de retroceso.** Un comando sale del front o del motor de reglas hacia la API, que lo registra y lo envía por el protocolo del dispositivo: MQTT "
  "`campus/cmd/<id>`, AMQP a la cola `cmd.<id>`, STOMP a `/exchange/campus.cmd/<id>`, CoAP `POST /cmd` al gemelo o, en HTTP, dentro de la respuesta al siguiente POST. "
  "El dispositivo aplica el cambio, guarda su estado en disco y responde un ACK que vuelve por su canal de subida y queda en InfluxDB con su tiempo de ida y vuelta.")
P("**Relación con la arquitectura del docente.** Se respetan sus bloques —*real device python.py*, *api*, *digital twin*, *dataset* → *broker messaging* → "
  "*front / back / database* → *Grafana* y *analysis*— y se amplían con varios brokers, un bus interno, un motor de reglas, retroceso por protocolo y despliegue con HTTPS.")

P("**Decisiones de diseño.** Cada pieza se eligió frente a una alternativa concreta:", tam=9.6)
T([["Decisión", "Alternativa", "Por qué"],
   ["Una VM con Docker Compose", "AKS (Lab 6)", "AKS consumió rápido los créditos de estudiante y chocó con las cuotas; para 12 dispositivos alcanza una VM de 4 GB (≈ US$0,9/día) y se replica con un comando"],
   ["InfluxDB 2.7", "PostgreSQL / TimescaleDB", "Base de series de tiempo nativa: `aggregateWindow` da promedio, máximo y mínimo por ventana, y Grafana la consulta directo"],
   ["Mosquitto + RabbitMQ", "Un solo broker", "Cada protocolo con su broker de referencia; RabbitMQ cubre AMQP y STOMP con el mismo intercambio"],
   ["Bus interno retenido", "Que cada consumidor lea cada broker", "Los 5 protocolos se normalizan en un formato; un cliente nuevo recibe el último valor al conectarse"],
   ["ACK con `cmd_id`", "Comandos sin confirmación", "El retroceso se puede demostrar y medir, y la interfaz muestra si el equipo obedeció"],
   ["HTTP con comandos en la respuesta", "Que la plataforma llame al equipo", "Un equipo HTTP real suele estar detrás de NAT; a cambio, la latencia es el intervalo de envío"],
   ["Reglas en la API y alertas en Grafana", "Solo Grafana", "Las reglas que actúan necesitan enviar comandos con memoria e histéresis; Grafana queda como capa visual y avisa por webhook y por correo"],
   ["Respaldo Open-Meteo", "Depender solo de Azure Maps", "Cuando la cuenta de Azure Maps se bloqueó (15-nov), los dispositivos de clima y aire siguieron midiendo sin intervención"]],
  [3.9, 3.6, 9.5], tam=8.2)

# ====================================================================== 3. TECNOLOGIAS
H("3. Tecnologías seleccionadas")
H("3.1 Sensores y dispositivos", 2)
P("La Tabla siguiente resume los 12 dispositivos con su familia, protocolo, origen, variables con rango físico aceptado e intervalo. El ingestor descarta "
  "cualquier valor fuera de ese rango. El detalle de cada variable con unidades y estadísticas de la ventana está en el Anexo A.")
filas = [["Dispositivo", "Familia · protocolo", "Origen del dato", "Variables (rango físico)", "Intervalo"]]
ORIG = {"real": "emulado en Python", "twin": "modelo en la nube", "api": "dato externo real", "dataset": "dataset UCI repetido"}
for d, r in DISPOSITIVOS.items():
    var = ", ".join("%s %s–%s %s" % (k.replace("_", " "), f(v[1], 0) if abs(v[1]) >= 1 or v[1] == 0 else v[1], f(v[2], 0) if abs(v[2]) >= 10 else v[2], v[0] if len(v[0]) < 9 else "")
                    for k, v in r["variables"].items())
    filas.append(["`%s`\n%s" % (d, r["nombre"]), "%s · %s" % ({"real": "Real", "twin": "Gemelo", "api": "API", "dataset": "Dataset"}[r["tipo"]], r["protocolo"].upper()),
                  "firmware real · Wokwi" if d == "esp32-wokwi" else ORIG[r["tipo"]], var, "%d s" % r["intervalo"] if r["intervalo"] < 120 else "%d min" % (r["intervalo"] // 60)])
T(filas, [3.6, 2.3, 2.3, 7.4, 1.4], tam=7.4)
P("**Escenario de cada elemento.**", antes=2)
ESC = {
    "aula-101": "Aula de clase de 180 m³ en el Edificio L. Un ESP32 con SCD41, INMP441 y BH1750 mediría CO₂, temperatura, humedad, ruido, luz y la ocupación. El modelo usa un balance de CO₂ (≈100 ppm/h por persona) con la ventilación que ordena el gemelo HVAC y la temperatura exterior real de la API.",
    "lab-quimica": "Laboratorio de química con prácticas de 8 a 12 y de 14 a 18 h. Mide PM2.5, VOC, temperatura y humedad, y controla un extractor en automático (enciende con VOC > 450 ppb o PM2.5 > 35 µg/m³).",
    "medidor-bloque-a": "Medidor trifásico del tablero general del Bloque A (PZEM-004T + gateway). La demanda sigue el horario académico, suma la potencia del HVAC y resta la generación solar.",
    "esp32-wokwi": "ESP32 DevKit con DHT22, LDR, potenciómetro y LED, con firmware Arduino real en Wokwi, conectado por Internet al broker con un usuario MQTT restringido por ACL. Funciona en sesiones de demostración.",
    "twin-hvac-aula101": "Gemelo del aire acondicionado del Aula 101: modelo térmico RC de primer orden más controlador, alimentado con la temperatura y la ocupación medidas y la temperatura exterior. Publica su predicción y el error contra lo medido.",
    "twin-tanque-agua": "Gemelo del tanque elevado de 20 m³: balance de masa con demanda según el horario del campus y bomba de 230 L/min por histéresis (enciende bajo 35 %, apaga sobre 90 %).",
    "twin-panel-solar": "Gemelo de una planta fotovoltaica de 12 kWp en la cubierta del Bloque A: posición del sol, nubosidad real de la API y temperatura de celda; usa HTTP para mostrar el patrón de sondeo.",
    "api-clima-unab": "Condiciones actuales en el campus desde Azure Maps Weather (clave del docente). Desde el 15-nov, cuando la cuenta del docente fue desactivada, el dispositivo pasa solo a Open-Meteo como respaldo.",
    "api-aire-unab": "Calidad del aire en el campus desde Azure Maps Air Quality (índice global y seis contaminantes), con el mismo respaldo automático.",
    "api-bus-ruta1": "Bus de la Ruta 1 de Rutas UNAB desde la API REST de su rastreador GPS (HTTP Basic). Solo se guardan posición, velocidad, encendido y baterías; no se guardan datos personales.",
    "ds-ocupacion-uci": "Oficina del dataset UCI Occupancy Detection (Candanedo y Feldheim, 2016), repetido a una fila por minuto y alineado al día de la semana y la hora actuales.",
    "ds-aire-uci": "Estación urbana del dataset UCI Air Quality (De Vito et al., 2008), con una fila horaria cada 5 min (×12) alineada a la hora del día.",
}
for d in DISPOSITIVOS:
    V("**%s** — %s" % (d, ESC[d]), tam=9.3)

H("3.2 Comunicación: brokers y protocolos de envío y recepción", 2)
P("Se usan dos brokers y dos endpoints propios. **Mosquitto** atiende MQTT con usuario y contraseña, ACL por dispositivo, sesión persistente y última voluntad. "
  "**RabbitMQ** atiende AMQP 0-9-1 y, con su plugin, STOMP 1.2: ambos protocolos llegan al mismo exchange `campus.tele`, lo que demuestra la interoperabilidad "
  "del broker. El **ingestor** expone un servidor CoAP en UDP 5683 y la **API** un endpoint HTTP con token.")
T([["Protocolo", "Envío (subida)", "Recepción (retroceso)", "Garantía"],
   ["MQTT 3.1.1", "`PUBLISH campus/tele/<id>` QoS 1", "`SUBSCRIBE campus/cmd/<id>` QoS 1", "PUBACK, sesión persistente, LWT"],
   ["AMQP 0-9-1", "exchange `campus.tele` (topic), rk `tele.<id>`", "exchange `campus.cmd` (direct) → cola durable `cmd.<id>`", "publisher confirms, colas durables"],
   ["STOMP 1.2", "`SEND /exchange/campus.tele/tele.<id>`", "`SUBSCRIBE /exchange/campus.cmd/<id>`", "persistente en RabbitMQ"],
   ["CoAP (RFC 7252)", "`POST` confirmable a `coap://ingestor/tele`", "cada gemelo expone `POST /cmd`", "mensajes CON; respuesta 2.04 = ACK"],
   ["HTTP REST", "`POST /api/ingest/<id>` + `X-Token`", "comandos dentro de la respuesta al siguiente POST", "códigos HTTP; guardar y reenviar"]],
  [2.4, 4.9, 5.6, 4.1], tam=8.2)
P("**Formato del mensaje (subida).** `{\"id\":\"aula-101\", \"tipo\":\"real\", \"kind\":\"tele\", \"ts\":1794302400000, \"seq\":812, \"v\":{\"co2\":918, \"temperatura\":25.4, …}, "
  "\"estado\":{\"encendido\":1, \"intervalo_s\":15}}`. **Comando (bajada):** `{\"cmd_id\":\"7a31cd749828\", \"accion\":\"calibrar\", \"params\":{\"variable\":\"temperatura\", \"offset\":-0.3}, "
  "\"origen\":\"manual\", \"ts\":…}`. **ACK:** `{\"kind\":\"ack\", \"ack\":{\"cmd_id\", \"accion\", \"ok\", \"detalle\", \"enviado_ms\"}, \"estado\":{…}}`.")
P("**Robustez.** El ingestor solo confirma un mensaje después de escribirlo en InfluxDB. Los enlaces AMQP y HTTP guardan y reenvían lo que no pudieron enviar (probado reiniciando la API: "
  "ningún dato perdido). Un hilo mantiene los *heartbeats* de AMQP, y cada dispositivo guarda en disco su estado, de modo que un reinicio no borra lo que se le ordenó.")
T([["Protocolo", "Mensajes (6 días)", "Latencia media de subida", "ACK de la prueba", "RTT mediana", "RTT p95"]] +
  [[{"mqtt": "MQTT", "amqp": "AMQP", "stomp": "STOMP", "coap": "CoAP", "http": "HTTP"}[p], n(PRO[p]["mensajes"]), "%s ms" % f(PRO[p]["latencia_mean_ms"], 1),
    "%d/%d" % (RET[p]["ack_ok"], RET[p]["comandos"]), ("%s s" % f(RET[p]["rtt_mediana_ms"] / 1000, 1)) if RET[p]["rtt_mediana_ms"] >= 1000 else "%s ms" % f(RET[p]["rtt_mediana_ms"], 1),
    ("%s s" % f(RET[p]["rtt_p95_ms"] / 1000, 1)) if RET[p]["rtt_p95_ms"] >= 1000 else "%s ms" % f(RET[p]["rtt_p95_ms"], 0)] for p in ("mqtt", "amqp", "stomp", "coap", "http")] +
  [["MQTT por Internet (ESP32)", "21 + sesión 17-nov", "reloj del simulador*", "%d/%d" % (RET["mqtt-internet"]["ack_ok"], RET["mqtt-internet"]["comandos"]),
    "%s ms" % f(RET["mqtt-internet"]["rtt_mediana_ms"], 0), "%s ms" % f(RET["mqtt-internet"]["rtt_p95_ms"], 0)]],
  [4.0, 2.6, 3.0, 2.3, 2.4, 2.7], tam=8.2)
P("*El reloj del ESP32 en Wokwi corre más lento que el real: su «latencia» aparente (~10 s) es deriva del simulador y se excluye del promedio de MQTT. "
  "Latencia de subida = llegada a InfluxDB − marca de tiempo del dispositivo. RTT = ACK recibido − comando enviado.", tam=8.5, color=GRIS, cursiva=True)
F(os.path.join(GR, "g23_protocolos.png"), ANCHO, "Retroceso (95 comandos: 20 por protocolo, 5 por HTTP y 10 al ESP32 por Internet) y latencia de subida por protocolo en la ventana.")
P("**Lectura.** Los cuatro protocolos con conexión o datagrama propio (MQTT, CoAP, STOMP, AMQP) devuelven el ACK en milisegundos dentro de la nube; "
  "AMQP y STOMP pagan unos ms de enrutamiento en RabbitMQ y de la conexión por comando. El ESP32 añade el viaje por Internet desde el simulador (81 ms). "
  "HTTP es el único protocolo en que el servidor no puede iniciar la conversación: el comando espera la siguiente consulta del dispositivo (≤ 30 s), igual que el C2D por HTTP de Azure IoT Hub.")

H("3.3 Nube, infraestructura y servicios utilizados", 2)
T([["Recurso", "Detalle"],
   ["Máquina virtual", "Azure Standard_B2als_v2 (2 vCPU AMD, 4 GB RAM), Ubuntu 22.04, región North Central US, suscripción Azure for Students"],
   ["Red y dominio", "IP pública estática con etiqueta DNS propia `campussense-unab.northcentralus.cloudapp.azure.com`; NSG abierto solo en 22 (llave SSH), 80/443 y 1883"],
   ["HTTPS", "Caddy 2.8 como proxy inverso, certificado Let's Encrypt automático; HTTP redirige a HTTPS"],
   ["Orquestación", "Docker Compose con 11 contenedores, `restart: unless-stopped`, límites de memoria y volúmenes persistentes"],
   ["Servicios externos", "Azure Maps Weather (clima y aire, clave del docente), Open-Meteo (respaldo sin clave), API GPS de Rutas UNAB, UCI ML Repository, Wokwi, GitHub"],
   ["Costo", "≈ US$ 0,90 por día de VM (precio de lista de B2als_v2) más disco e IP; ≈ US$ 9 por los ~10 días de operación, de los créditos de estudiante (estimación, no factura)"]],
  [3.2, 13.8], tam=8.5)
T([["Contenedor", "Imagen", "Función"],
   ["mosquitto", "eclipse-mosquitto 2.0.20", "Broker MQTT con usuarios y ACL generados desde .env"],
   ["rabbitmq", "rabbitmq 3.13 + STOMP", "Broker AMQP 0-9-1 y STOMP 1.2"],
   ["influxdb", "influxdb 2.7", "Base de series de tiempo"],
   ["ingestor", "campus-plataforma", "Adaptadores MQTT, AMQP (+STOMP) y CoAP hacia InfluxDB"],
   ["api", "campus-plataforma", "FastAPI: registro, retroceso, ingesta HTTP, reglas, SSE y front"],
   ["dev-reales / dev-gemelos / dev-apis / dev-datasets", "campus-plataforma", "Los 11 dispositivos que corren en la nube (el ESP32 corre en Wokwi)"],
   ["grafana", "grafana-oss 11.6", "5 tableros y 6 reglas de alerta aprovisionados desde el repositorio"],
   ["caddy", "caddy 2.8", "Entrada web con HTTPS: `/` → API y front, `/grafana` → Grafana"]],
  [5.2, 3.6, 8.2], tam=8.3)
P("**Seguridad.** Ninguna clave está en el repositorio: todo va en `.env`, ignorado por git. RabbitMQ, InfluxDB y CoAP solo escuchan dentro de la red de Docker. "
  "El usuario MQTT del ESP32 solo puede publicar en sus propios tópicos, y enviar comandos desde el front exige una clave de control. Del GPS no se guardan nombres ni datos de la SIM.")

H("3.4 Visualización y procesamiento de los datos", 2)
P("**Procesamiento en la ingesta.** El ingestor valida cada variable contra su rango físico (Tabla §3.1), escribe con la marca de tiempo del dispositivo para que una reentrega "
  "no duplique el dato, calcula la latencia de subida y republica en el bus. InfluxDB guarda seis *measurements*: `telemetria`, `estado`, `ack`, `comandos`, `alertas` y `conexion`.")
P("**Promedio, máximo y mínimo con ajuste de tiempo.** Hay tres caminos:")
for t in ["Cada tablero de Grafana tiene paneles *promedio / máx / mín del rango* y leyendas con mín, promedio, máx y último. Todo se recalcula al mover el selector de tiempo, y la agregación se adapta con `v.windowPeriod`.",
          "El front tiene la sección *Análisis del periodo*: elige dispositivo y rango (ventana oficial, 1 h, 24 h, 6 d o todo) y calcula en InfluxDB mínimo, promedio, máximo y número de muestras por variable, con una barra que ubica el periodo en el rango físico.",
          "El panel de cada dispositivo grafica de 1 h a 6 días con mínimo, promedio y máximo por variable."]:
    V(t)
P("**Alertas y reglas.** Hay dos niveles complementarios. **Grafana Alerting** tiene 6 reglas aprovisionadas (CO₂ aula > 1000 ppm 5 min, temperatura aula > 28 °C 10 min, tanque < 20 %, "
  "PM2.5 laboratorio > 35 µg/m³ 5 min, índice de aire exterior > 100 y dispositivo sin datos) que notifican a la API por *webhook* y por **correo electrónico** a los tres integrantes, con Brevo SMTP (`smtp-relay.brevo.com:587` y STARTTLS obligatorio). El **motor de reglas** de la API evalúa cada 30 s y, además de alertar, **actúa**:")
filas = [["Regla", "Condición", "Acción automática", "Disparos en la ventana"]]
for rid, cond, acc, clave in [("R1", "CO₂ aula-101 (prom. 5 min) > 1000 ppm; libera < 750", "HVAC → ventilación; al liberar → auto", ("R1 CO2 alto", "reglas")),
                              ("R2", "Demanda Bloque A (prom. 5 min) > 30 kW; libera < 24", "HVAC → eco si estaba en auto (R1 tiene prioridad)", ("R2 Demanda alta", "reglas")),
                              ("R3", "Nivel del tanque < 20 %; libera > 30 %", "Alerta crítica; bomba forzada en off → auto", ("R3 Tanque bajo", "reglas")),
                              ("R4", "PM2.5 lab (prom. 5 min) > 35 µg/m³; libera < 25", "Alerta; extractor forzado en off → auto", ("R4 PM2.5 laboratorio", "reglas")),
                              ("R5", "Índice global exterior > 100 o PM2.5 > 37,5", "Alerta", ("R5 Aire exterior", "reglas")),
                              ("R6", "Encendido y sin telemetría > máx(3×intervalo, 180 s)", "Alerta crítica", ("R6 Sin datos", "reglas")),
                              ("R7", "Velocidad del bus > 60 km/h", "Alerta", ("R7 Velocidad bus", "reglas"))]:
    filas.append([rid, cond, acc, str(alert_fire.get(clave, 0))])
T(filas, [1.2, 6.2, 6.4, 3.2], tam=8.2)
P("R1 generó %d comandos automáticos (%d a ventilación y %d de vuelta a auto) y R2 %d a eco. R3, R6 y R7 no se dispararon: el tanque nunca bajó de 34,8 %%, ningún dispositivo dejó de "
  "transmitir y el bus no pasó de 43 km/h. R5 se disparó una vez el 14-nov por un evento real de calidad del aire."
  % (reglas_cmd.get("regla R1", 0), reglas_cmd.get("regla R1", 0) // 2, reglas_cmd.get("regla R1", 0) // 2, reglas_cmd.get("regla R2", 0)))
F(os.path.join(GR, "g24_alertas.png"), ANCHO, "Alertas disparadas durante la ventana: motor de reglas (naranja) y Grafana Alerting (morado).")
for img, pie in [("10-grafana-resumen.png", "Grafana · tablero 1, resumen: dispositivos en línea, mensajes, alertas y comandos de la ventana oficial."),
                 ("11-grafana-ambiente.png", "Grafana · tablero 2, ambiente interior: promedio, máximo y mínimo del rango y series del Aula 101, el laboratorio, el ESP32 y la oficina UCI."),
                 ("12-grafana-energia-agua.png", "Grafana · tablero 3, energía, HVAC y agua: red vs solar, gemelo HVAC (modelo vs medido) y tanque."),
                 ("13-grafana-exterior.png", "Grafana · tablero 4, exterior y movilidad: clima y aire de Azure Maps, estación UCI y recorrido del bus en el mapa."),
                 ("14-grafana-retroceso.png", "Grafana · tablero 5, retroceso, reglas y protocolos: estado encendido, intervalos, RTT de ACK, latencia y línea de tiempo de alertas.")]:
    F(os.path.join(EV, img), ANCHO * (0.92 if "resumen" in img else 0.82), pie)
P("**Front propio (centro de control).** La URL principal abre un panel en tiempo real por *Server-Sent Events*: el flujo de cada mensaje se anima por su protocolo, cada "
  "dispositivo muestra su origen, sus valores y su estado, y el panel lateral permite ver gráficas y enviar comandos con confirmación del ACK.")
for img, pie in [("20-front-portada.jpg", "Front · portada: flujo de datos en vivo, avance de la toma (6 días completada) e indicadores."),
                 ("22-front-analisis-ventana-oficial.jpg", "Front · análisis del periodo: mínimo, promedio y máximo de la ventana oficial calculados en InfluxDB."),
                 ("27-front-panel-controles.jpg", "Front · panel del gemelo HVAC: controles visuales de retroceso (encendido, intervalo, calibración, setpoint, modo).")]:
    F(os.path.join(EV, img), ANCHO * 0.9, pie)

# ====================================================================== 4. ANALISIS CON IA
H("4. Análisis de gráficas y comportamiento (con IA)")
P("**Método.** Los datos de la ventana oficial se exportaron de InfluxDB (promedios de 10 min por variable y estadísticas sobre los datos crudos). "
  "El análisis de esta sección lo redactó un asistente de IA (Claude, de Anthropic) a partir de esas gráficas y cifras, y el grupo lo revisó contra el "
  "funcionamiento conocido de cada modelo y fuente. Todas las cifras se pueden verificar en `mediciones/export/` del repositorio. En todas las figuras la línea "
  "naranja es el promedio de la ventana y la hora es la de Bogotá. El 8-nov 23:19 fue domingo por la noche; la ventana cubre de lunes a sábado.", tam=9.6)
F(os.path.join(GR, "g01_mensajes.png"), ANCHO, "Mensajes guardados por dispositivo en la ventana oficial (%s en total)." % n(total))

ANALISIS = {
    "aula-101": [
        "El CO₂ dibuja seis jornadas idénticas en forma: línea base de ~420 ppm de noche y subidas en cada bloque de clase entre las 7:00 y las 21:30 (sábado solo hasta las 13:00). "
        "El promedio de la ventana es %s ppm y el máximo %s ppm. Cuando el promedio de 5 min pasa de 1000 ppm, R1 manda ventilación y el CO₂ cae; con el aula llena "
        "(más de 35 personas) la ventilación solo logra sostenerlo cerca de 1000 ppm, lo que indica que para ese aforo haría falta más caudal de aire." % (s("aula-101", "co2", d=0), s("aula-101", "co2", "max", 0)),
        "La temperatura (%s–%s °C, promedio %s °C) sube por la tarde y con el aula llena; las alertas de Grafana «Temperatura alta» (> 28 °C) aparecen al final de la tarde, "
        "cuando el aire pasa a ventilación y entra aire exterior caliente. La humedad (%s–%s %%) baja mientras el aire enfría y sube de noche. El ruido (%s–%s dBA) y "
        "la luz (0–%s lux) siguen la ocupación (promedio %s personas, máximo %s): son los dos indicadores más directos de que hay clase." % (
            s("aula-101", "temperatura", "min", 1), s("aula-101", "temperatura", "max", 1), s("aula-101", "temperatura", d=1), s("aula-101", "humedad", "min", 0), s("aula-101", "humedad", "max", 0),
            s("aula-101", "ruido", "min", 0), s("aula-101", "ruido", "max", 0), s("aula-101", "luz", "max", 0), s("aula-101", "ocupacion", d=0), s("aula-101", "ocupacion", "max", 0))],
    "lab-quimica": [
        "El PM2.5 tiene picos de hasta %s µg/m³ y los VOC de hasta %s ppb durante las prácticas (8–12 y 14–18 h, lunes a viernes). El promedio de PM2.5 (%s µg/m³) queda justo en el umbral de 35, "
        "porque los picos son muy altos aunque breves; fuera de práctica la base es de 10–15 µg/m³, ligada al aire exterior." % (s("lab-quimica", "pm25", "max", 0), s("lab-quimica", "voc", "max", 0), s("lab-quimica", "pm25", d=1)),
        "El extractor automático estuvo encendido el %s %% del tiempo y cada encendido corta la subida en minutos. R4 y la alerta de Grafana se disparan en los mismos tramos, lo que confirma "
        "que los dos niveles de alerta coinciden. Temperatura (%s–%s °C) y humedad (%s–%s %%) son estables: el laboratorio está climatizado." % (
            f(EST["lab-quimica"]["extractor"]["mean"] * 100, 0), s("lab-quimica", "temperatura", "min", 1), s("lab-quimica", "temperatura", "max", 1), s("lab-quimica", "humedad", "min", 0), s("lab-quimica", "humedad", "max", 0))],
    "medidor-bloque-a": [
        "La potencia de red va de %s a %s kW (promedio %s kW) con un perfil laboral claro: base nocturna de ~7 kW, subida desde las 6:00, una pequeña baja al mediodía y caída después de las 22:00. "
        "La baja del mediodía coincide con el máximo de la planta solar, que descuenta su generación de la red. R2 (> 30 kW) se disparó 10 veces, en los picos de la mañana y del final de la tarde." % (
            s("medidor-bloque-a", "potencia", "min", 1), s("medidor-bloque-a", "potencia", "max", 1), s("medidor-bloque-a", "potencia", d=1)),
        "El voltaje (%s–%s V) cae cuando sube la carga, una caída de unos 0,06 V por kW, y el factor de potencia (%s–%s) mejora con la carga. La energía acumulada creció %s kWh en 6 días "
        "(≈ %s kWh por día)." % (s("medidor-bloque-a", "voltaje", "min", 1), s("medidor-bloque-a", "voltaje", "max", 1), s("medidor-bloque-a", "fp", "min", 2), s("medidor-bloque-a", "fp", "max", 2),
                                 f(EST["medidor-bloque-a"]["energia"]["max"] - EST["medidor-bloque-a"]["energia"]["min"], 0), f((EST["medidor-bloque-a"]["energia"]["max"] - EST["medidor-bloque-a"]["energia"]["min"]) / 6, 0))],
    "twin-hvac-aula101": [
        "El gemelo predice la temperatura del aula con un error medio de %s °C y una desviación de %s °C (ver §4.2): sigue cada subida y bajada del día. El modo pasó de auto (1) a ventilación (2) "
        "por R1 y a eco (3) por R2; la potencia (promedio %s kW, máximo %s kW) solo aparece cuando hay que enfriar." % (s("twin-hvac-aula101", "error_modelo", d=3), s("twin-hvac-aula101", "error_modelo", "stddev", 2),
                                                                                                    s("twin-hvac-aula101", "potencia", d=2), s("twin-hvac-aula101", "potencia", "max", 1)),
        "El único error grande (%s °C) ocurrió el 10-nov hacia las 21:40, al final de la última clase, cuando el aula cambió más rápido de lo que el modelo esperaba; el observador corrigió el estado en menos de una hora. "
        "Ese es justo el uso de un gemelo: un error que crece señala que el aula real se comporta distinto al modelo." % s("twin-hvac-aula101", "error_modelo", "min", 2)],
    "twin-tanque-agua": [
        "El nivel oscila entre %s y %s %% (promedio %s %%): la bomba de 230 L/min enciende bajo 35 %% y apaga sobre 90 %%, y estuvo encendida el %s %% del tiempo. El consumo (promedio %s L/min) tiene dos "
        "picos diarios, hacia las 10:00 y las 15:30, de hasta %s L/min, y de noche baja a ~9 L/min; por eso el nivel solo desciende lento en la madrugada." % (
            s("twin-tanque-agua", "nivel", "min", 1), s("twin-tanque-agua", "nivel", "max", 1), s("twin-tanque-agua", "nivel", d=1), f(EST["twin-tanque-agua"]["bomba"]["mean"] * 100, 0),
            s("twin-tanque-agua", "caudal_salida", d=0), s("twin-tanque-agua", "caudal_salida", "max", 0)),
        "El nivel nunca bajó de 34,8 %%, así que R3 (< 20 %%) no se disparó: con el consumo observado, el tanque y la bomba están bien dimensionados. La presión (%s–%s bar) sigue al nivel." % (
            s("twin-tanque-agua", "presion", "min", 2), s("twin-tanque-agua", "presion", "max", 2))],
    "twin-panel-solar": [
        "La irradiancia llega a %s W/m² al mediodía y la potencia a %s kW de 12 kWp: la diferencia se debe a la temperatura de celda (hasta %s °C) y a la nubosidad real que entrega la API. "
        "La energía diaria bajó de 71,7 kWh (9 y 10-nov) a 63,0 kWh (14-nov) a medida que aumentó la nubosidad durante la semana." % (s("twin-panel-solar", "irradiancia", "max", 0), s("twin-panel-solar", "potencia", "max", 1), s("twin-panel-solar", "temp_panel", "max", 0)),
        "Con un promedio de %s kW, la planta generó unos 60 kWh por día, alrededor del 13 %% de lo que consume el Bloque A, y su efecto se ve en la baja de la demanda de red al mediodía." % s("twin-panel-solar", "potencia", d=2)],
    "api-clima-unab": [
        "La temperatura exterior real fue de %s a %s °C (promedio %s °C) con máximos a primera hora de la tarde; la sensación térmica llegó a %s °C por la humedad (promedio %s %%). "
        "La nubosidad (promedio %s %%) subió hacia el final de la semana y explica la caída gradual de la energía solar diaria (de 71,7 a 63,0 kWh); el índice UV llegó a %s al mediodía y hubo lluvias de hasta %s mm/h." % (
            s("api-clima-unab", "temperatura", "min", 1), s("api-clima-unab", "temperatura", "max", 1), s("api-clima-unab", "temperatura", d=1), s("api-clima-unab", "sensacion", "max", 1),
            s("api-clima-unab", "humedad", d=0), s("api-clima-unab", "nubosidad", d=0), s("api-clima-unab", "uv", "max", 0), s("api-clima-unab", "precipitacion", "max", 1)),
        "La presión (%s–%s hPa) muestra dos máximos (hacia las 9–10 h y las 22–23 h) y dos mínimos (hacia las 3–4 h y las 16 h) por día: es la marea atmosférica semidiurna, típica del trópico, y su aparición confirma que la fuente es real." % (
            s("api-clima-unab", "presion", "min", 0), s("api-clima-unab", "presion", "max", 0))],
    "api-aire-unab": [
        "El índice global de calidad del aire varió entre %s y %s (promedio %s). El ozono tiene un pico diario hacia las 14:00 (hasta %s µg/m³) por la fotoquímica con el sol fuerte, y el PM2.5 (%s–%s µg/m³) "
        "sube a lo largo de la semana. El 14-nov, hacia las 9:40, el índice pasó de 100, se disparó R5 y también la alerta de Grafana: un evento real que la plataforma detectó." % (
            s("api-aire-unab", "indice_global", "min", 0), s("api-aire-unab", "indice_global", "max", 0), s("api-aire-unab", "indice_global", d=0), s("api-aire-unab", "o3", "max", 0),
            s("api-aire-unab", "pm25", "min", 1), s("api-aire-unab", "pm25", "max", 1))],
    "api-bus-ruta1": [
        "El bus circuló en las franjas de la mañana y la tarde de los días hábiles: estuvo encendido el %s %% del tiempo, con velocidad máxima de %s km/h y promedio de %s km/h, porque pasa mucho "
        "tiempo detenido en paradas. Nunca se alejó más de %s km del campus, lo que coincide con un recorrido corto por El Jardín y Cabecera, y su batería externa (%s–%s V) sube a ~28 V con el motor en marcha." % (
            f(EST["api-bus-ruta1"]["encendido"]["mean"] * 100, 0), s("api-bus-ruta1", "velocidad", "max", 0), s("api-bus-ruta1", "velocidad", d=1), s("api-bus-ruta1", "distancia_campus", "max", 1),
            s("api-bus-ruta1", "bateria_ext", "min", 1), s("api-bus-ruta1", "bateria_ext", "max", 1))],
    "ds-ocupacion-uci": [
        "La oficina del dataset estuvo ocupada el %s %% del tiempo, en horario de oficina. En esos tramos el CO₂ sube hasta %s ppm y la luz hasta %s lux; los días sin ocupación (fin de semana del dataset) "
        "quedan planos. Como el dataset es de febrero en Bélgica, su temperatura (%s–%s °C) y su humedad (%s–%s %%) son más bajas que las de Bucaramanga, y así se rotula." % (
            f(EST["ds-ocupacion-uci"]["ocupacion"]["mean"] * 100, 0), s("ds-ocupacion-uci", "co2", "max", 0), s("ds-ocupacion-uci", "luz", "max", 0), s("ds-ocupacion-uci", "temperatura", "min", 1),
            s("ds-ocupacion-uci", "temperatura", "max", 1), s("ds-ocupacion-uci", "humedad", "min", 0), s("ds-ocupacion-uci", "humedad", "max", 0))],
    "ds-aire-uci": [
        "La estación urbana repite su día cada 2 horas reales por la compresión ×12, así que los picos de tráfico de la mañana y la tarde aparecen como oscilaciones rápidas. El NO₂ (%s–%s µg/m³), los NOx (hasta %s ppb) "
        "y el benceno (hasta %s µg/m³) suben y bajan juntos, la firma típica de las emisiones vehiculares." % (
            s("ds-aire-uci", "no2", "min", 0), s("ds-aire-uci", "no2", "max", 0), s("ds-aire-uci", "nox", "max", 0), s("ds-aire-uci", "benceno", "max", 1))],
}
H("4.1 Análisis por dispositivo", 2)
for d, reg in DISPOSITIVOS.items():
    ruta = os.path.join(GR, "dev_%s.png" % d)
    if d == "esp32-wokwi" or not os.path.exists(ruta):
        continue
    H("%s · %s (%s)" % (reg["nombre"], d, reg["protocolo"].upper()), 3)
    F(ruta, ANCHO, "%s: cada variable en la ventana de 6 días con mínimo, promedio y máximo." % reg["nombre"])
    for parr in ANALISIS[d]:
        P(parr, tam=9.6)
H("ESP32 de demostración · esp32-wokwi (MQTT por Internet)", 3)
P("El ESP32 corre firmware Arduino real en el simulador Wokwi, que no puede quedar encendido 6 días sin un computador abierto. Por eso se usa en sesiones: una el 9-nov "
  "(21 mensajes dentro de la ventana) y otra el 17-nov con 10 comandos (LED, intervalo, calibración, apagar, encender y reset), todos con ACK y una mediana de 81 ms por Internet. "
  "Sus valores son constantes porque los sensores del simulador se fijan en el diagrama (DHT22 en 24,5 °C y 62 %); el aporte de este dispositivo es demostrar el camino completo "
  "con firmware real y un usuario MQTT limitado por ACL. Los logs están en `mediciones/esp32_wokwi_*`.", tam=9.6)

H("4.2 Análisis transversal", 2)
F(os.path.join(GR, "g21_lazo_r1.png"), ANCHO, "Lazo cerrado del 10-nov: el CO₂ del aula, la ocupación, los comandos de R1 y el modo resultante del gemelo HVAC.")
P("**Lazo cerrado.** La Figura muestra la cadena completa sin intervención humana: un nodo real (MQTT) mide el CO₂, el motor de reglas decide, el comando viaja por CoAP "
  "hasta el gemelo HVAC, el gemelo cambia de modo, y el modelo del aula (que lee ese modo por el bus) ventila y baja el CO₂. Cuando la clase termina y el CO₂ cae de 750 ppm, R1 "
  "devuelve el aire a auto. La histéresis (1000/750 ppm) evita que el sistema oscile.", tam=9.6)
F(os.path.join(GR, "g22_gemelo.png"), ANCHO, "Gemelo digital HVAC: temperatura medida vs predicha el 11-nov y distribución del error en 6 días.")
P("**Gemelo digital.** El 98,7 % de los errores (promedios de 10 min) está dentro de ±0,25 °C y el 95 % entre −0,09 y +0,16 °C. La cola hacia los negativos corresponde al 10-nov hacia las 21:40; si el error se sostuviera, "
  "sería la señal para recalibrar el modelo o revisar el aula real.", tam=9.6)
F(os.path.join(GR, "g20_perfiles.png"), ANCHO, "Perfiles por hora del día (promedio de los 6 días): aula, energía, tanque y clima.")
P("**Patrones diarios.** Los perfiles promedian los 6 días por hora y dejan ver la rutina del campus: el CO₂ sigue a la ocupación con un retraso de minutos; la generación "
  "solar recorta la demanda justo cuando más se consume; el tanque baja con los dos picos de consumo y se recupera con la bomba; y la temperatura exterior y la nubosidad marcan "
  "lo que pasa adentro. Ninguna variable se mueve sola: los dispositivos se afectan entre sí a través del bus, como pasaría en un campus real.", tam=9.6)

# ====================================================================== 5. RETROCESO Y PRUEBAS
H("5. Retroceso, pruebas y resiliencia")
P("**Comandos disponibles.** Todos los dispositivos aceptan " + ", ".join("`%s`" % c for c in ("encender", "apagar", "intervalo", "calibrar", "reset")) + ". Además: "
  "`setpoint` y `modo` (HVAC), `bomba` y `consumo` (tanque), `limite` (solar), `extractor` (laboratorio), `led` (ESP32), `velocidad` y `saltar` (datasets). "
  "La calibración aplica `valor = medido × ganancia + offset` en el propio dispositivo, y el estado reportado incluye cada offset y ganancia vigentes.")
T([["Prueba", "Resultado"],
   ["Prueba formal de retroceso (17-nov)", "95/95 comandos con ACK: MQTT 20/20 (mediana 1 ms), CoAP 20/20 (4 ms), STOMP 20/20 (6 ms), AMQP 20/20 (7,5 ms), HTTP 5/5 (27,9 s), ESP32 10/10 (81 ms)"],
   ["Comandos y reglas en la ventana", "%d comandos registrados: %d automáticos por regla y el resto manuales; todos con ACK" % (sum(reglas_cmd.values()), reglas_cmd.get("regla R1", 0) + reglas_cmd.get("regla R2", 0))],
   ["Guardar y reenviar (HTTP)", "Se reinició la API mientras la planta solar enviaba: el mensaje fallido quedó en cola y se guardó después; la serie no tiene hueco"],
   ["Heartbeats AMQP", "Se corrigió el cierre de conexión cada 5 min; desde el arreglo, 0 cortes en RabbitMQ y la latencia media de AMQP bajó a 3,5 ms"],
   ["Carrera del ACK", "Un ACK de 8 ms llegaba antes de que la API registrara el comando; se corrigió registrando antes de enviar (de 94/95 a 95/95)"],
   ["Caída de la API del docente (15-nov)", "La cuenta de Azure Maps del docente quedó desactivada (`AccountLocked`); R6 y Grafana alertaron, y se agregó respaldo automático a Open-Meteo, que reintenta Azure Maps cada 6 h"],
   ["Disponibilidad", "11 contenedores sin reinicios durante la toma; 0 huecos en los 6 días"],
   ["Alertas por correo (17-nov)", "Se calibró el CO₂ del aula-101 a +1200 ppm. A los ~8 min la regla de Grafana «CO2 alto Aula 101» llegó a la API por webhook, y Brevo registró el correo «[CampusSense UNAB] FIRING · CO2 alto Aula 101» como entregado a los 3 integrantes"],
   ["Reinicio de la VM completa (17-nov)", "Sin intervención: HTTPS a los 38 s y los 11 dispositivos con datos nuevos a los 47 s; intervalos, calibraciones, historial y memoria de las reglas intactos (R1 devolvió el HVAC a auto)"]],
  [4.6, 12.4], tam=8.4)
F(os.path.join(EV, "23-front-retroceso.jpg"), ANCHO * 0.9, "Front · retroceso: camino y tiempo de ida y vuelta por protocolo e historial de comandos con su ACK.")
P("**Lazo cerrado de extremo a extremo (17-nov).** `scripts/demo_regla.py` une calibración, regla y retroceso en una sola prueba contra la URL pública. Primero se "
  "calibra el CO₂ del aula-101 con un offset de +1200 ppm por MQTT (ACK en 1 ms). A los 70 s el promedio de 5 min superó 1000 ppm, y la regla R1 mandó sola el "
  "gemelo HVAC a ventilación por CoAP (ACK en 36 ms). Después se hizo un *reset* de fábrica, y a los 301 s el promedio bajó de 750 ppm: R1 devolvió el HVAC a auto (ACK en 24 ms). "
  "El registro completo está en `mediciones/demo_regla_17nov.txt`, y es la demostración que se hará en vivo en la sustentación.", tam=9.6)
P("**Pruebas de funcionamiento y seguridad desde Internet.** `scripts/prueba_humo.py` se ejecuta desde cualquier PC y comprueba lo que debe funcionar y lo que "
  "debe estar bloqueado. Resultado del 17-nov: **31 de 31 correctas** (`mediciones/prueba_humo_17nov.txt`).", tam=9.6)
T([["Grupo", "Qué se comprobó", "Resultado"],
   ["Nube", "DNS, certificado TLS de Let's Encrypt, redirección de HTTP a HTTPS", "OK (308 a HTTPS)"],
   ["Servicios", "Front, `/api/salud`, `/docs`, Grafana, 12 dispositivos registrados y 11 en línea, resumen de la ventana", "OK"],
   ["Puertos", "Abiertos: 443 y 1883. Cerrados: 5672, 61613, 15672, 8086, 3000, 8000 y 8081", "9 de 9"],
   ["MQTT", "Anónimo y clave falsa rechazados (CONNACK 5). El ESP32 suscrito a `campus/#` no recibe nada, no ve los comandos de otro equipo y no puede suplantar al aula-101", "7 de 7"],
   ["API y Grafana", "Comando sin clave o con clave falsa, ingesta y webhook sin token: 401. Grafana anónimo no puede crear tableros: 403", "5 de 5"],
   ["Datos (mínimo privilegio)", "Grafana lee InfluxDB con un token de solo lectura del bucket `campus`: leer 200; escribir o borrar 403", "OK"],
   ["Retroceso", "Comando MQTT real al aula-101 desde Internet", "ACK en 2 ms; ida y vuelta completa en 1,2 s"]],
  [2.6, 10.6, 3.8], tam=8.3)
P("El webhook de alertas de Grafana manda su token en la cabecera `Authorization: Bearer` y no en la URL, para que no quede registrado en los logs de acceso; se probó con una alerta real de CO₂ que llegó a la API. ", tam=9.0, cursiva=True)
P("Mosquitto 2 concede cualquier suscripción y aplica la ACL al entregar cada mensaje. Por eso la prueba de la ACL no mira la respuesta a la suscripción: "
  "cuenta los mensajes que realmente llegan, y los compara con un usuario de la plataforma que en el mismo lapso sí recibe 35.", tam=9.0, cursiva=True)

# ====================================================================== 6. CONCLUSIONES
H("6. Resultados, conclusiones y trabajo futuro")
for t in ["Se construyó una plataforma IoT completa y propia —dispositivos, brokers, ingesta, base de series de tiempo, reglas, API, front y Grafana— y se operó 6 días en Azure con "
          "URL propia y HTTPS, sin huecos y con %s mensajes." % n(total),
          "El retroceso funciona en los cinco protocolos, cada uno por su canal natural. Las mediciones muestran el costo de cada patrón: milisegundos donde el servidor puede "
          "empujar el comando (MQTT, AMQP, STOMP, CoAP) y decenas de segundos donde el dispositivo debe preguntar (HTTP).",
          "Las reglas cierran el lazo: el CO₂ del aula disparó 43 veces la ventilación del gemelo HVAC, que lo devolvió a valores seguros, salvo en clases a plena capacidad, "
          "donde el análisis recomienda más caudal de aire.",
          "El gemelo digital predijo la temperatura del aula con un error medio de 0,01 °C, lo que permite usarlo para detectar comportamientos anómalos del aula real.",
          "La plataforma resistió fallas reales: la caída de la API del docente y reinicios de la propia API, gracias al respaldo automático, a guardar y reenviar y a las alertas de dispositivo sin datos."]:
    V(t)
P("**Limitaciones.** No hay hardware físico; el ESP32 opera por sesiones; HTTP usa sondeo; MQTT para dispositivos externos va sin TLS (con usuario y ACL), y la VM es un único punto de falla.", tam=9.6)
P("**Trabajo futuro.** Usar MQTT sobre TLS (8883) y certificados por dispositivo; desplegar en Kubernetes con réplicas, como se hizo en el Lab 6; integrar sensores físicos en el aula; "
  "agregar detección de anomalías con aprendizaje automático sobre el error del gemelo; y llevar la medición de retroceso a dispositivos en redes móviles.", tam=9.6)

# ====================================================================== 7. REFERENCIAS
H("7. Referencias")
REFS = [
    "Banks, A., Briggs, E., Borgendale, K., & Gupta, R. (Eds.). (2019). *MQTT Version 5.0*. OASIS Standard. https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html",
    "Banks, A., & Gupta, R. (Eds.). (2014). *MQTT Version 3.1.1*. OASIS Standard. https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html",
    "AMQP Working Group. (2008). *AMQP 0-9-1 Specification*. https://www.rabbitmq.com/resources/specs/amqp0-9-1.pdf",
    "STOMP. (2012). *STOMP Protocol Specification, Version 1.2*. https://stomp.github.io/stomp-specification-1.2.html",
    "Shelby, Z., Hartke, K., & Bormann, C. (2014). *The Constrained Application Protocol (CoAP)* (RFC 7252). IETF. https://doi.org/10.17487/RFC7252",
    "Fielding, R., Nottingham, M., & Reschke, J. (Eds.). (2022). *HTTP Semantics* (RFC 9110). IETF. https://doi.org/10.17487/RFC9110",
    "ISO/IEC. (2018). *ISO/IEC 30141:2018 Internet of Things (IoT) — Reference Architecture*. International Organization for Standardization.",
    "Microsoft. (2025). *Azure Maps Weather service REST API (2025-01-01)*. https://learn.microsoft.com/es-es/rest/api/maps/weather",
    "Open-Meteo. (2026). *Weather Forecast API and Air Quality API*. https://open-meteo.com/en/docs",
    "Candanedo, L. M., & Feldheim, V. (2016). Accurate occupancy detection of an office room from light, temperature, humidity and CO2 measurements using statistical learning models. *Energy and Buildings, 112*, 28–39. Dataset: UCI Machine Learning Repository. https://doi.org/10.24432/C5X01N",
    "De Vito, S., Massera, E., Piga, M., Martinotto, L., & Di Francia, G. (2008). On field calibration of an electronic nose for benzene estimation in an urban pollution monitoring scenario. *Sensors and Actuators B: Chemical, 129*(2), 750–757. Dataset: UCI Machine Learning Repository. https://doi.org/10.24432/C59K5F",
    "InfluxData. (2026). *InfluxDB OSS v2 documentation* y *Flux language*. https://docs.influxdata.com/influxdb/v2/",
    "Grafana Labs. (2026). *Grafana documentation: dashboards, provisioning and Grafana Alerting*. https://grafana.com/docs/grafana/latest/",
    "Eclipse Foundation. (2026). *Eclipse Mosquitto* y *Eclipse Paho MQTT Python client*. https://mosquitto.org/ · https://eclipse.dev/paho/",
    "Broadcom. (2026). *RabbitMQ documentation: AMQP 0-9-1, STOMP plugin, publisher confirms*. https://www.rabbitmq.com/docs",
    "Amsüss, C., & Wasilak, M. (2026). *aiocoap: The Python CoAP library*. https://aiocoap.readthedocs.io/",
    "Ramírez, S. (2026). *FastAPI documentation*. https://fastapi.tiangolo.com/",
    "Caddy. (2026). *Caddy 2 documentation: automatic HTTPS*. https://caddyserver.com/docs/ · Let's Encrypt. https://letsencrypt.org/",
    "Docker Inc. (2026). *Docker Compose documentation*. https://docs.docker.com/compose/",
    "Wokwi. (2026). *Wokwi ESP32 simulator and wokwi-cli*. https://docs.wokwi.com/",
    "Microsoft. (2026). *Azure Virtual Machines: Bsv2-series*. https://learn.microsoft.com/azure/virtual-machines/sizes/general-purpose/bsv2-series",
    "Anthropic. (2026). *Claude* [modelo de lenguaje usado como asistente para el análisis de gráficas y la redacción técnica]. https://www.anthropic.com/claude",
]
for r in REFS:
    p = P(r, tam=9)
    p.paragraph_format.left_indent = Cm(0.8)
    p.paragraph_format.first_line_indent = Cm(-0.8)

# ====================================================================== ANEXOS
salto()
H("Anexo A. Estadísticas de la ventana oficial por variable")
P("Calculadas en InfluxDB sobre los datos crudos del 9-nov 04:19 UTC al 15-nov 04:19 UTC (8-nov 23:19 a 14-nov 23:19 en Bogotá).", tam=9)
filas = [["Dispositivo", "Variable (unidad)", "Rango físico", "Mínimo", "Promedio", "Máximo", "Desv.", "Muestras"]]
for d, reg in DISPOSITIVOS.items():
    for v, (u, lo, hi) in reg["variables"].items():
        e = EST.get(d, {}).get(v)
        if not e:
            continue
        filas.append([d, "%s (%s)" % (v.replace("_", " "), u if len(u) < 14 else "código"), "%s – %s" % (f(lo) if lo else "0", f(hi)), f(e["min"]), f(e["mean"]), f(e["max"]),
                      f(e.get("stddev", 0)), n(e["count"])])
T(filas, [3.0, 3.6, 2.4, 1.6, 1.7, 1.6, 1.4, 1.7], tam=7.2, primera_negrita=False)

H("Anexo B. Cómo reproducir y verificar")
for t in ["`git clone %s && cd CampusSense-IoT && cp .env.example .env` (cambiar todas las claves) y `docker compose up -d --build`." % REPO,
          "Validar los paneles de Grafana: `python3 grafana/verificar_paneles.py` (en la VM). Resumen de la toma: `python3 scripts/resumen_toma.py`.",
          "Exportar la ventana: `python3 scripts/exportar_toma.py` y regenerar las gráficas de este informe con `python informe/graficas.py`.",
          "Prueba de retroceso: `CONTROL_KEY=… python scripts/prueba_retroceso.py`. ESP32: `./wokwi/build_y_simular.sh 600`.",
          "Funcionamiento y seguridad: `python scripts/prueba_humo.py`. Lazo en vivo: `CONTROL_KEY=… python scripts/demo_regla.py`.",
          "Evidencias: `evidencias/` (capturas de Grafana y del front), `mediciones/` (exportes, logs del ESP32, prueba de retroceso), `informe/graficas/`."]:
    V(t, tam=9.3)

H("Anexo C. Declaración de uso de inteligencia artificial")
P("El grupo usó un asistente de IA (Claude, de Anthropic) para apoyar la programación de la plataforma, la generación de gráficas y la redacción del análisis de la sección 4. "
  "Todas las cifras provienen de los datos medidos y exportados de InfluxDB, y el grupo verificó el análisis contra el comportamiento conocido de cada modelo y fuente. "
  "Las decisiones de diseño, el despliegue y la sustentación son responsabilidad del grupo.", tam=9.6)

doc.save(SALIDA)
print("OK", SALIDA, "figuras:", num_fig[0])
