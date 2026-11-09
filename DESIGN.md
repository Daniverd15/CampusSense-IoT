# Design — CampusSense UNAB (front `/`)

Método: el mismo del proyecto CDE Conecta (Hackatón UNAB 2026), que trabaja con *Impeccable*: producto en `PRODUCT.md`,
contrato de dirección por superficie, construcción y revisión de acabado documentada aquí.

## Surface brief: centro de control (`plataforma/static/index.html`)

Modo: Demostrar. Audiencia: docente y compañeros de IoT en la sustentación, y el operador del campus. Acción: ver la plataforma
trabajando, abrir un dispositivo, enviarle un comando y comprobar la respuesta. Prueba: datos en vivo de la API, rotulados según su origen.

### Direction contract

THESIS: la portada es la plataforma trabajando, no una promesa. El primer viewport es el diagrama de flujo con paquetes reales
moviéndose por su protocolo. Se rechazan el hero de titular, subtítulo, dos botones y tres tarjetas, el texto en degradado, la grilla
decorativa de fondo, los brillos y los emoji como iconos.

OWN-WORLD: identidad UNAB. Poppins para texto, JetBrains Mono para todo número y todo identificador técnico. Morado institucional
#6D2CA0 (noche #3B1561) como color de marca y de la UI activa; naranja UNAB #F59C00 reservado al retroceso (un comando bajando
siempre es naranja). Cuatro familias con color propio: real azul, gemelo morado, API verde azulado, dataset magenta. Superficies
sobre una escala gris teñida de morado; en oscuro la escala se invierte (#0F0B15 → #17111F).

STORY: (1) el campus transmitiendo ahora, con el avance de la toma de 4 a 6 días; (2) las cuatro familias y de dónde sale cada dato;
(3) análisis del periodo: promedio, mínimo y máximo con ajuste de tiempo; (4) retroceso: los cinco caminos y cada comando con su ACK;
(5) mapa y consola; (6) protocolos medidos; (7) reglas y alertas; (8) arquitectura.

FIRST VIEWPORT: izquierda, el titular «El campus UNAB, transmitiendo ahora.», una frase, la barra de la toma de datos con la marca
de 4 días y el botón «Hablarle a un dispositivo». Derecha, el flujo en vivo con un ticker del último mensaje
(«aula-101 → MQTT → ingestor → InfluxDB · co2 430 ppm · 1 ms»). Debajo, una franja de cuatro indicadores (no tarjetas sueltas).

FORM: secciones numeradas 01–06 con cabecera a la izquierda; dispositivos agrupados por familia con una línea de color y una frase
honesta sobre su origen; panel lateral por dispositivo con gráficas y controles visuales.

FINISH: revisión de acabado abajo, con veredicto.

## Tokens

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--marca` | #6D2CA0 | #B98AE6 | marca, botón primario, filtros activos, foco |
| `--marca-2` | #3B1561 | #E3CFF7 | hover del primario |
| `--cmd` | #C97C00 (texto AA sobre blanco) | #FFB21F | retroceso: paquetes, rutas de comando, origen «regla» |
| `--real` / `--twin` / `--api` / `--dataset` | #2563EB / #7B35B3 / #0B8574 / #BE185D | #79ABFF / #C697F0 / #3FD0B8 / #F478AC | familias |
| `--ok` / `--mal` / `--aviso` | #15803D / #C2253A / #B45309 | #5AD48A / #FF7B8A / #F5B54A | estados |
| `--bg` / `--panel` / `--panel-2` | #F6F4F9 / #FFF / #F3F0F7 | #0F0B15 / #17111F / #1F1829 | superficies |
| radio | 14 px tarjetas, 11–12 px controles | | |

El logotipo es un cuadrado morado con un punto naranja (el sensor) y dos ondas (la transmisión); el mismo dibujo sirve de favicon.

## Componentes

- **Flujo (SVG):** seis columnas (dispositivos, protocolo, broker, procesamiento, base de datos, visualización). Cada mensaje del
  stream SSE anima un punto del color de su familia por su ruta real; HTTP entra por la API, CoAP por el ingestor; STOMP y AMQP comparten RabbitMQ.
  Los comandos bajan desde «API y reglas» en naranja. Cada nodo de protocolo muestra mensajes por minuto.
- **Tarjeta de dispositivo:** nombre, id, estado (en línea, apagado por comando, fuera de sesión), etiqueta de origen
  (emulado en Python, firmware real · Wokwi, modelo en la nube, dato externo real, dataset UCI repetido), valor principal en mono con
  sparkline de 6 h y cuatro variables secundarias. Binarias como ON/OFF; el modo del HVAC por nombre.
- **Análisis del periodo:** tabla de mínimo, promedio y máximo por variable calculada en InfluxDB (`/api/resumen`), con una barra
  que ubica el periodo dentro del rango físico que acepta el ingestor.
- **Panel lateral:** gráficas de 1 h a 6 días (Chart.js, eje ajustado a los datos, escalonadas para binarias) y controles de retroceso
  (interruptor, deslizadores, segmentos) que confirman con el ACK y su tiempo de ida y vuelta.
- **Toasts:** iconos SVG, borde del color del tipo (aceptado, rechazado, comando, alerta).

## Movimiento

Solo el que cuenta algo: paquetes del flujo, latido del nodo que recibe, destello del valor que cambió, pulso del marcador en el mapa.
Con `prefers-reduced-motion` no hay paquetes ni animaciones.

## Finish review (9-nov-2026)

| Revisión | Resultado |
|---|---|
| Primer viewport muestra el producto trabajando | Sí: flujo en vivo + ticker con el último mensaje real |
| Sin clichés (texto en degradado, grilla de fondo, brillos, emoji, hero de 3 tarjetas) | Quitados en esta versión |
| Identidad UNAB (Poppins, morado, naranja como acento) | Sí; el naranja solo marca el retroceso |
| Honestidad de origen | Cada tarjeta, el panel y los popups del mapa dicen si el dato es emulado, modelado, externo o de dataset; la ubicación del mapa se rotula como ilustrativa |
| Cifras inventadas | Ninguna: todo número sale de la API; sin dato se muestra «–» o «sin datos» |
| Requisitos del enunciado visibles | 12 dispositivos en 4 familias, 5 protocolos, retroceso con ACK, promedio/mín/máx con ajuste de tiempo, alertas y reglas, toma de 4 a 6 días, URL propia |
| Claro y oscuro | Ambos revisados en el navegador |
| Celular (375 px) | Sin scroll horizontal; el flujo se desplaza dentro de su marco |
| Accesibilidad | Foco visible, enlace «Saltar a los dispositivos», `aria-pressed` en filtros, `role="switch"` en interruptores, panel con `aria-modal`, Escape cierra y devuelve el foco |
| Hallazgo durante la revisión | La latencia MQTT promedio daba 441 ms por el ESP32 de Wokwi (10,7 s): su reloj simulado va más lento que el real. Se excluye del promedio y la tarjeta MQTT lo dice |

**Veredicto:** listo para la sustentación.

Limitaciones que siguen abiertas:
- Grafana conserva su tema propio; no lleva la identidad UNAB.
- El envío de comandos desde el formulario lo debe probar el grupo con la clave de control. En la revisión se probó por la API y el front reflejó el comando y el ACK en vivo.
