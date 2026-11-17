# Evidencias

Todas las capturas son de la plataforma desplegada (`campussense-unab.northcentralus.cloudapp.azure.com`). No muestran claves ni contraseñas.
Las gráficas de Grafana usan el rango fijo de la toma oficial: del 8-nov 23:19 al 14-nov 23:19, hora de Bogotá.

| Archivo | Qué se ve | Requisito |
|---|---|---|
| `00-arquitectura.png` | Arquitectura de referencia propia (5 capas, 12 dispositivos, 5 protocolos) | Arquitectura |
| `10-grafana-resumen.png` | Tablero 01: mensajes por dispositivo y protocolo, en línea, alertas | Visualización, 4 a 6 días |
| `11-grafana-ambiente.png` | Tablero 02: CO₂, temperatura, humedad, ruido y PM2.5 del aula y el laboratorio | Visualización |
| `12-grafana-energia-agua.png` | Tablero 03: medidor del Bloque A, panel solar, tanque y HVAC | Visualización, gemelos |
| `13-grafana-exterior.png` | Tablero 04: clima, calidad del aire, mapa del bus y datasets | APIs y datasets |
| `14-grafana-retroceso.png` | Tablero 05: comandos, ACK, RTT por protocolo y acciones de las reglas | Retroceso |
| `20-front-portada.jpg` | Centro de control: flujo en vivo dispositivo → broker → plataforma | Front, URL propia |
| `21-front-dispositivos.jpg` | Las 4 familias con su protocolo y su origen | Dispositivos |
| `22-front-analisis-ventana-oficial.jpg` | Promedio, máximo y mínimo de la ventana oficial | Procesamiento |
| `23-front-retroceso.jpg` | Caminos de retroceso por protocolo | Retroceso |
| `24-front-mapa-consola.jpg` | Mapa del bus y consola de comandos con ACK | API GPS, retroceso |
| `25-front-protocolos-reglas.jpg` | Métricas por protocolo y reglas R1–R7 | Reglas y alertas |
| `26-front-panel-graficas.jpg` | Panel de un dispositivo: series y estadísticas | Visualización |
| `27-front-panel-controles.jpg` | Panel de un dispositivo: encender, apagar, intervalo y calibrar | Retroceso |

## Registros de pruebas (`../mediciones/`)

| Archivo | Qué prueba |
|---|---|
| `export/` | Datos de la toma oficial: series CSV, `estadisticas.json`, `reglas.csv`, `alertas.csv`, `perfil_horario.csv` |
| `prueba_retroceso.json` | 95 comandos en 6 caminos, todos con ACK, y el RTT de cada protocolo |
| `prueba_humo_17nov.txt` | 31 de 31 pruebas de funcionamiento y seguridad desde Internet |
| `demo_regla_17nov.txt` | Lazo cerrado en vivo: calibrar → R1 → HVAC por CoAP → ACK → vuelta a auto |
| `esp32_wokwi_sesion1.txt`, `esp32_wokwi_sesion2_17nov.txt` | ESP32 en Wokwi conectado por Internet, con los comandos y su ACK |
