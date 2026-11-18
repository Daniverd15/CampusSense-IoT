# Guion de sustentación · 20-nov-2026

**Duración objetivo:** 12 a 15 minutos y luego preguntas. **Equipo:** Daniel Villamizar · Tomás Urieles · David Guerrero.

## Antes de entrar (30 min antes)

1. Encender la VM si está desasignada y esperar unos 3 minutos a que levanten los contenedores:

   ```bash
   az vm start -g rg-lab4iot -n vm-lab4-iot
   ```

2. Comprobar todo de una vez. Tienen que salir 31 de 31 correctas:

   ```bash
   CONTROL_KEY=… ESP32_USER=… ESP32_PASS=… MQTT_USER=… MQTT_PASS=… python scripts/prueba_humo.py
   ```

3. Dejar abiertas cuatro pestañas:
   - el front: https://campussense-unab.northcentralus.cloudapp.azure.com
   - Grafana, en «01 Resumen»: `/grafana`
   - `/docs`
   - el repositorio en GitHub
4. Tener a mano:
   - la clave de control para el front;
   - el ESP32 listo con `./wokwi/build_y_simular.sh 600`;
   - una terminal con `scripts/demo_regla.py --con-correo`, lista para lanzarla en el minuto 0:00 (el correo de Grafana tarda unos 8 min);
   - los celulares con el correo de la UNAB abierto (las alertas llegan de «CampusSense UNAB»; si alguna cae en spam, marcarla como «no es spam» antes).
5. **Plan B (sin Internet o sin VM):**
   - el PDF del informe;
   - las capturas de `evidencias/`;
   - los registros de `mediciones/`: `prueba_humo_17nov.txt`, `demo_regla_17nov.txt`, `prueba_retroceso.json` y la sesión del ESP32.

## Guion

| Min | Quién | Qué se muestra | Qué se dice |
|---|---|---|---|
| 0:00 | Daniel | Portada del front (flujo en vivo) | El problema: el campus El Jardín no ve en un solo lugar el aire de las aulas, la energía, el agua, el clima ni el bus. CampusSense lo reúne con **12 dispositivos de 4 tipos y 5 protocolos**, en Azure con URL propia y HTTPS. |
| 1:00 | Daniel | Figura de arquitectura (informe §2 o `docs/ARQUITECTURA.md`) | Las 5 capas: dispositivos → brokers (Mosquitto, RabbitMQ, CoAP, HTTP) → ingestor → InfluxDB → API con reglas, Grafana y front, con Caddy en el borde. El bus interno normaliza los 5 protocolos. |
| 2:30 | Tomás | Front, sección Dispositivos | Un dispositivo de cada tipo: real (aula-101 por MQTT), gemelo (HVAC por CoAP), API (clima por MQTT, con respaldo Open-Meteo) y dataset (ocupación UCI por STOMP). Variables y rangos según la tabla del informe §3.1. |
| 4:00 | Tomás | Grafana, rango fijo del 8 al 14-nov | **6 días de datos, 150 035 mensajes, sin huecos.** El perfil diario del CO₂ con las clases, la marea semidiurna de la presión y la curva solar. Promedio, máximo y mínimo en cada panel. |
| 5:30 | David | Front → Retroceso: un comando por protocolo | MQTT, AMQP, STOMP, CoAP y HTTP, cada uno por su propio canal, con ACK y RTT a la vista. Benchmark: MQTT 1 ms, CoAP 4, STOMP 6, AMQP 7,5; HTTP ~28 s porque el comando viaja en la respuesta del siguiente envío. |
| 7:00 | David | **En vivo:** consola del front + celulares | David lanzó `python scripts/demo_regla.py --con-correo` en el minuto 0:00, sin que se note. Se calibró el CO₂ del aula a +1200 ppm; a los ~70 s la regla R1 mandó sola el HVAC a ventilación por CoAP, con ACK, y se muestra en la consola. Hacia el minuto 8 Grafana dispara «CO₂ alto»: llega a la API y **les llega el correo a los tres celulares** (mostrar uno). Luego el script hace el *reset* solo. Calibrar, regla, retroceso y alerta en un solo lazo. |
| 8:30 | Daniel | ESP32 en Wokwi | Firmware C++ real conectado por Internet al broker, con usuario propio y ACL. Prender el LED desde el front: ACK en ~80 ms. |
| 9:30 | Tomás | Informe §4 (análisis con IA) | Tres hallazgos: el gemelo acierta ±0,25 °C el 98,7 % del tiempo; el ozono sube hacia las 14 h por la fotoquímica; la PM2.5 subió hacia el final de la semana. La IA ayudó a leer las gráficas, y cada cifra se verificó contra los datos. |
| 11:00 | David | `mediciones/prueba_humo_17nov.txt` | Seguridad: 31 de 31 pruebas, con los puertos internos cerrados, MQTT sin acceso anónimo, ACL del ESP32 y API con clave. Resiliencia: guardar y reenviar, y el respaldo de Azure Maps cuando se bloqueó la cuenta el 15-nov. |
| 12:30 | Daniel | GitHub (README) | Se replica con `docker compose up -d --build`; todo está generado como código (tableros, informe, gráficas). Costo: ~US$0,9/día. Cierre. |

## Preguntas probables

- **¿Por qué una VM y no Kubernetes?**
  - En el Lab 6 AKS consumió los créditos y chocó con las cuotas de la suscripción de estudiante.
  - Para 12 dispositivos alcanza una VM de 4 GB; el `docker-compose.yml` se podría llevar a AKS sin cambiar el código.
- **¿Los dispositivos "reales" son reales?**
  - Son simulaciones con física y horarios plausibles, más el ESP32 con firmware real en Wokwi; el enunciado permite simular.
  - Lo que sí es real: las APIs (clima, aire y el GPS del bus), los datasets UCI, los protocolos, la nube y el retroceso.
- **¿Qué pasa si se cae un broker o la API?**
  - MQTT: QoS 1 con sesión persistente.
  - AMQP y HTTP: guardar y reenviar (cola de 2000 mensajes).
  - El estado de cada dispositivo vive en un volumen.
  - Se probó reiniciando la API: no se perdieron datos.
- **¿Qué pasa si se reinicia la VM?**
  - Se probó: todo vuelve solo.
  - HTTPS a los 38 s y los 11 dispositivos con datos nuevos a los 47 s.
  - Se conservan los intervalos, las calibraciones, el historial y la memoria de las reglas.
  - Evidencia: `mediciones/prueba_reinicio_17nov.txt`.
- **¿Cómo se enteran de una alerta?** Grafana avisa por dos caminos: el webhook a la API (aparece en el front) y un correo a los tres por Brevo SMTP con STARTTLS. Se repite como máximo cada 4 h para no saturar (`mediciones/alertas_email_17nov.txt`).
- **¿Grafana puede dañar los datos?** No: lee InfluxDB con un token de solo lectura, y escribir o borrar con él da 403 (`mediciones/endurecimiento_17nov.txt`).
- **¿Cómo se ajusta el tiempo?**
  - Cada mensaje trae `ts` en milisegundos UTC y `seq`; InfluxDB guarda en UTC y Grafana muestra en hora de Bogotá.
  - `aggregateWindow` agrega en ventanas según el rango.
  - El reloj del ESP32 deriva unos 10 s, así que se excluye del promedio de latencia.
- **¿Por qué el RTT de HTTP es tan alto?** HTTP no tiene canal de bajada: el comando espera al siguiente envío del dispositivo (30 s). Es la misma idea que los mensajes de la nube al dispositivo de IoT Hub.
- **¿Para qué sirve la IA?**
  - Se usó para interpretar las gráficas y redactar las hipótesis de cada patrón.
  - Las cifras salen de `mediciones/export/` y se comprobaron una por una (declaración en el anexo C del informe).
- **¿Qué mejorarían?**
  - MQTT con TLS (8883) y un certificado por equipo.
  - Detección de anomalías sobre el error del gemelo.
  - Alta de dispositivos sin tocar código.
  - Tener un nodo físico real.
