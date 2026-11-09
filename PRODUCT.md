# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (front propio servido por FastAPI en https://campussense-unab.northcentralus.cloudapp.azure.com) + Grafana en /grafana

## Users

Docente y compañeros del curso IoT + Cloud + Sistemas Distribuidos de la UNAB que evalúan el proyecto final, y el operador
del campus que vigila ambiente, energía, agua y movilidad. En la sustentación el grupo maneja la plataforma en vivo frente al docente.

## Product Purpose

CampusSense reúne en una sola plataforma propia 12 dispositivos de cuatro familias (real, gemelo digital, API y dataset) que hablan
cinco protocolos, y permite hablarles de vuelta (retroceso). Éxito: el evaluador ve llegar cada dato, entiende el camino que recorrió,
envía un comando y ve la respuesta del dispositivo en menos de un segundo, y encuentra promedio, máximo y mínimo de cualquier variable en el rango que elija.

## Positioning

IoT a la medida, no una plataforma comercial: brokers, ingesta, base de series de tiempo, reglas y front escritos y desplegados por el grupo
en una VM de Azure con URL propia y HTTPS. Cada dispositivo recibe comandos por su mismo protocolo.

## Capabilities and Constraints

- 12 dispositivos: 3 nodos de campo emulados en Python (sin hardware), 1 ESP32 con firmware real en el simulador Wokwi (solo en sesiones),
  3 gemelos digitales, 3 fuentes de API reales (Azure Maps clima y aire, GPS de Rutas UNAB) y 2 datasets públicos UCI repetidos.
- Front sin framework (HTML, CSS, JS) + Chart.js + Leaflet; tiempo real por Server-Sent Events.
- Interfaz en español de Colombia. Comandos protegidos con clave de control.

## Brand Commitments

Proyecto de la UNAB: Poppins, morado institucional (#6D2CA0, noche #3B1561) y naranja (#F59C00) como acento, reservado al retroceso
(comandos que bajan al dispositivo). Cuatro familias con color propio: real azul, gemelo morado, API verde azulado, dataset magenta.
Modo claro y oscuro obligatorios.

## Evidence on Hand

Toma continua desde el 8-nov-2026 23:19 (hora de Bogotá). Retroceso medido en los 5 protocolos (ACK: STOMP ~15 ms, AMQP ~20 ms,
CoAP ~27 ms, MQTT ~90 ms incluido el ESP32 por Internet, HTTP ~18 s por sondeo). Sin cifras inventadas: todo número del front sale de la API.

## Product Principles

- Lo primero que se ve es la plataforma trabajando, no una promesa.
- Decir qué es real y qué es emulado, modelado o repetido.
- Cada número sale de la API en vivo; si no hay dato, se dice.
- El comando es protagonista: cada uno muestra por dónde viajó y qué respondió el dispositivo.

## Accessibility & Inclusion

Contraste AA en claro y oscuro, foco visible, movimiento reducido respetado (sin paquetes animados), funciona en celular sin scroll horizontal.
