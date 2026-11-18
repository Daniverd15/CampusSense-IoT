# Bitácora del proyecto

Registro de lo hecho, las decisiones y los problemas encontrados, con su solución. Las horas son de Bogotá (UTC−5).
El detalle técnico de cada decisión está en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md#4-decisiones-de-diseño).

---

## 2026-11-08 · Construcción y arranque de la toma

**Hecho**
- Lectura del enunciado y de los insumos del docente: el diagrama `ArquitecturaIoTCapstoneFinal.excalidraw` y la colección Postman (Azure Maps y GPS del bus de la UNAB).
- Diseño del escenario: el campus El Jardín, con un aula, un laboratorio, un bloque, el tanque, el panel solar, el clima y el bus.
- 12 dispositivos de 4 tipos sobre una clase base común (`plataforma/comun.py`), con un enlace por protocolo y el retroceso por el mismo canal.
- Pila Docker de 11 contenedores en la VM del Lab 4/5, redimensionada a `Standard_B2als_v2` (4 GB). El stack del Lab 5 se bajó con sus volúmenes intactos.
- Motor de reglas R1–R7 y 5 tableros de Grafana generados como código (`grafana/gen_dashboards.py`).
- **Arranque de la toma oficial a las 23:19.**

**Decisiones**
- VM con Compose en lugar de AKS: el Lab 6 mostró lo rápido que AKS consume los créditos de estudiante.
- InfluxDB como base de series de tiempo; RabbitMQ para cubrir AMQP y STOMP con un solo broker.

## 2026-11-09 · Publicación, front y ESP32

**Hecho**
- NSG con 80/443 y 1883; etiqueta DNS `campussense-unab`; HTTPS de Let's Encrypt con Caddy. Repositorio público `Daniverd15/CampusSense-IoT`.
- Primera sesión del ESP32 en Wokwi por Internet: 6 comandos con ACK y RTT de 105 a 140 ms (`mediciones/esp32_wokwi_sesion1.txt`).
- Front de centro de control: flujo en vivo por SSE, panel por dispositivo, mapa del bus y consola de retroceso.
- Rediseño con la identidad UNAB y el método Impeccable (`PRODUCT.md`, `DESIGN.md`).

**Problemas y soluciones**
- RabbitMQ cerraba la conexión de publicación entre envíos, porque se perdían los heartbeats. Se agregó un hilo que atiende `process_data_events`.
- Se perdían mensajes AMQP y HTTP cuando el receptor se reiniciaba. Se agregó guardar y reenviar: una cola de hasta 2000 mensajes.
- El reloj del ESP32 simulado deriva unos 10 s, así que su latencia aparente no es real. Se excluye del promedio de latencia MQTT.
- Grafana no muestra bien sus tableros por el túnel SSH, porque su `root_url` es el dominio. Los paneles se validan con `grafana/verificar_paneles.py` dentro de la VM.

## 2026-11-12 · Cuarto día de datos

- Se cumplió el mínimo del enunciado (4 días) a las 23:19. Se revisaron los huecos con `scripts/resumen_toma.py` y no había ninguno.

## 2026-11-14 · Cierre de la ventana oficial

- A las 23:19 se completaron los 6 días. **150 035 mensajes de 12 dispositivos, sin huecos.**
- La plataforma se dejó tomando datos para la demostración en vivo. El informe y Grafana usan el rango fijo de la toma oficial.

## 2026-11-15 · Incidente: Azure Maps bloqueado

- Hacia las 16:00, Azure Maps empezó a responder `401 AccountLocked` con la clave del docente. Las otras claves de la colección Postman dan `InvalidKey`.
- La ventana oficial no se vio afectada, porque ya había terminado.

## 2026-11-17 · Cierre del proyecto

**Hecho**
- **Respaldo automático Open-Meteo** para `api-clima-unab` y `api-aire-unab`: el estado del dispositivo marca la fuente (`fuente: 1`) y cada 6 h se reintenta Azure Maps.
- Exportación de la ventana oficial a `mediciones/export/`: series, estadísticas, reglas, alertas y perfil horario.
- Prueba formal de retroceso en los 6 caminos (`mediciones/prueba_retroceso.json`). Solo se mandaron comandos que no cambian nada, como volver a poner el intervalo de fábrica.
- Segunda sesión del ESP32: 10 de 10 ACK, con un RTT mediano de 81 ms.
- Informe de 33 páginas generado como código (`informe/build_informe.py`). Antes de cerrarlo se comprobó cada cifra del análisis contra los datos.
- Prueba de humo y seguridad desde Internet (`scripts/prueba_humo.py`): **31 de 31 correctas** (`mediciones/prueba_humo_17nov.txt`).
- Documentación: arquitectura con decisiones, bitácora, evidencias y guion de sustentación.

**Problemas y soluciones**
- Carrera del ACK: 1 de 95 comandos AMQP quedó sin ACK, porque el ACK llegaba antes de que la API registrara el comando. Ahora se registra antes de enviar, y en la repetición fueron 95 de 95.
- Las anotaciones de comandos automáticos tapaban las gráficas de Grafana. Se separaron en tres capas: manuales (visible), reglas y alertas (ocultas por defecto).
- El mapa de Grafana pedía una clave de CARTO, así que se cambió a OpenStreetMap. Además se agregó `aggregateWindow` para no dibujar decenas de miles de puntos.
- Las series binarias (extractor, ocupación, bomba) ocupaban todo el panel. Se fijó su escala entre 0 y 4.
- Un despliegue de la API con la constante de la ventana debajo de su primer uso causó un `SyntaxError`, y la API estuvo caída unos 2 minutos. Guardar y reenviar evitó perder datos. Desde entonces se valida antes de desplegar.
- El front mostraba "8,53 días" y solo los últimos 80 comandos. Ahora muestra "6 días · completada" y el total real desde el 8-nov.
- Las primeras pruebas de ACL dieron un falso fallo: Mosquitto 2 concede la suscripción y aplica la ACL al entregar cada mensaje. La prueba se cambió para contar los mensajes que realmente llegan.

## 2026-11-17 (noche) · Endurecimiento tras comparar con otro proyecto del curso

**Hecho**
- Revisión del repositorio de laboratorios de un compañero: su Lab 5 usaba un token de solo lectura para Grafana y tenía una prueba de reinicio de la VM. Adoptamos las dos ideas.
- **Grafana con token de solo lectura** (`scripts/crear_token_grafana.sh`). Leer da 200; escribir o borrar da 403; no puede ver otros tokens. Antes usaba el token de administrador, aunque el comentario del datasource decía que solo leía.
- **Prueba de reinicio de la VM** (`scripts/prueba_reinicio.py`). Sin intervención, HTTPS volvió a los 38 s y los 11 dispositivos enviaron datos a los 47 s. Se conservaron los intervalos, el historial y la memoria de R1, que devolvió el HVAC a auto.
- Prueba de humo repetida al final: 31 de 31.

**Problemas y soluciones**
- El log de acceso de la API imprimía el token de ingesta, porque Grafana lo mandaba en la URL del webhook (`?token=`). Ahora va en la cabecera `Authorization: Bearer`. Se probó de punta a punta con una alerta real de Grafana, que llegó a los 512 s.
- La primera versión de la prueba de reinicio daba «en línea a los 39 s» con los valores retenidos de antes. Se corrigió para medir el primer dato con marca de tiempo posterior al reinicio.
- La prueba de permisos daba 401 en todo porque `cut -d= -f2` cortaba el `==` final del token. Se cambió por `cut -d= -f2-`.

## 2026-11-17 (noche) · Alertas por correo

- Se creó una cuenta gratuita de Brevo con una clave SMTP («campussense», vence en nov-2027). Daniel verificó su correo y su teléfono, y el remitente quedó verificado.
- Las alertas de Grafana ahora tienen dos receptores en el mismo punto de contacto: el webhook a la API, como antes, y un correo a los tres integrantes. La clave y los destinatarios viven solo en el `.env`.
- Prueba: el correo de prueba se entregó a los 3. Además se hizo una alerta real de CO₂ (calibrar +1200 ppm): Grafana la disparó a las 22:14, la API la recibió a las 22:15 y Brevo entregó el correo a los 3 el mismo minuto (`mediciones/alertas_email_17nov.txt`).
- `scripts/demo_regla.py --con-correo` mantiene el CO₂ alto hasta que Grafana dispara, para que en la sustentación el correo llegue en vivo.

## Pendiente

- [ ] Sustentación el 20-nov con la demostración en vivo (ver [SUSTENTACION.md](SUSTENTACION.md)).
- [ ] Desasignar la VM después de la sustentación (`az vm deallocate -g rg-lab4iot -n vm-lab4-iot`).
