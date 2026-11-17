#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Une capturas de pantalla tomadas con desplazamiento conocido en una sola imagen de página completa.
Cada captura se pega en su posición (scrollY); las posteriores pisan a las anteriores salvo la barra fija superior.
Uso: python informe/unir_capturas.py
"""
import os

from PIL import Image

T = r"C:\Users\danie\.claude\projects\C--Users-danie-Documents-ParcialInfra\e3f57186-9ace-4cf5-af26-deaac821ab9d\tool-results"
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BARRA = 104          # alto de la barra fija de Grafana (controles) que se repite en cada captura
PAGINAS = {
    "10-grafana-resumen.png": [("eevlz8", 0), ("ojme7n", 210)],
    "11-grafana-ambiente.png": [("h2foe8", 0), ("whu0zg", 780), ("i55tea", 894)],
    "12-grafana-energia-agua.png": [("69kvwx", 0), ("95p7cm", 780), ("x93dfe", 1046)],
    "13-grafana-exterior.png": [("f2qfjd", 0), ("wmvwo3", 780), ("g6j669", 1122)],
    "14-grafana-retroceso.png": [("mv86gy", 0), ("jptrdz", 780), ("ykq4qo", 970)],
}


def ruta(sufijo):
    for f in os.listdir(T):
        if f.endswith(sufijo + ".jpg") and "claude-in-chrome" in f:
            return os.path.join(T, f)
    raise FileNotFoundError(sufijo)


for nombre, tramos in PAGINAS.items():
    imgs = [(Image.open(ruta(s)).convert("RGB"), y) for s, y in tramos]
    w, h = imgs[0][0].size
    alto = tramos[-1][1] + h
    lienzo = Image.new("RGB", (w, alto), "white")
    for i, (im, y) in enumerate(imgs):
        if i == 0:
            lienzo.paste(im, (0, y))
        else:
            lienzo.paste(im.crop((0, BARRA, w, h)), (0, y + BARRA))
    lienzo.save(os.path.join(RAIZ, "evidencias", nombre), optimize=True)
    print("OK", nombre, lienzo.size)
