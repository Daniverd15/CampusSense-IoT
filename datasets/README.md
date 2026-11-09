# Datasets del proyecto IoT

Dos datasets públicos del UCI Machine Learning Repository, preparados como CSV limpios.

## 1. Occupancy Detection

- **Cita:** Candanedo, L. M., & Feldheim, V. (2016). *Occupancy Detection* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5X01N
- **Licencia:** CC BY 4.0
- **Archivo:** `occupancy.csv`

**Transformaciones aplicadas**
- Se unieron `datatraining.txt`, `datatest.txt` y `datatest2.txt`.
- Se eliminó la columna de índice del archivo original y se renombraron las columnas al español (`ts, temperatura, humedad, luz, co2, humedad_ratio, ocupacion`).
- `ts` en formato `YYYY-MM-DD HH:MM:SS`; `ocupacion` como entero 0/1.
- Se ordenó por `ts` y se eliminaron timestamps duplicados (no hubo duplicados).

**Medidas**
- Filas: 20 560 (8 143 + 2 665 + 9 752 de origen, sin eliminaciones).
- Rango temporal: 2015-02-02 14:19:00 a 2015-02-18 09:19:00.
- Mínimo / máximo:
  - temperatura: 19.0 / 24.408
  - humedad: 16.745 / 39.5
  - luz: 0.0 / 1697.25
  - co2: 412.75 / 2076.5
  - humedad_ratio: 0.002674 / 0.006476
  - ocupacion: 0 / 1 (15 810 filas con 0 y 4 750 con 1)

## 2. Air Quality

- **Cita:** De Vito, S., Massera, E., Piga, M., Martinez, L., & Di Francia, G. (2008). *Air Quality* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C59K5F
- **Licencia:** CC BY 4.0
- **Archivo:** `airquality.csv`

**Transformaciones aplicadas**
- Se usó `AirQualityUCI.csv` (separador `;`, decimal con coma convertida a punto, columnas vacías finales descartadas).
- Se descartaron 114 filas sin fecha.
- Se combinaron `Date` (dd/mm/yyyy) y `Time` (HH.MM.SS) en `ts` con formato `YYYY-MM-DD HH:MM:SS`.
- Mapeo de columnas: CO(GT) → `co_mg_m3`, NOx(GT) → `nox_ppb`, NO2(GT) → `no2_ug_m3`, C6H6(GT) → `c6h6_ug_m3`, T → `temperatura`, RH → `humedad`, AH → `humedad_abs`.
- Los valores -200 (faltantes) se trataron como vacíos.
- Interpolación lineal por columna con límite de 6 valores consecutivos. Los huecos de extremos (al inicio o al final de la serie) no se extrapolaron.
- Se eliminaron las filas que aún tenían algún valor faltante tras la interpolación (1 737 filas).

**Medidas**
- Filas: 7 620.
- Rango temporal: 2004-03-10 18:00:00 a 2005-04-04 14:00:00.
- Mínimo / máximo:
  - co_mg_m3: 0.1 / 11.9
  - nox_ppb: 2.0 / 1479.0
  - no2_ug_m3: 2.0 / 333.0
  - c6h6_ug_m3: 0.2 / 63.7
  - temperatura: -1.9 / 44.6
  - humedad: 9.2 / 88.7
  - humedad_abs: 0.1847 / 2.1806

Los archivos originales se encuentran en `raw/` y no se versionan (ver `.gitignore`).
