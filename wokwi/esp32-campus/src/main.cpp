// CampusSense UNAB - dispositivo real ESP32 (simulado en Wokwi con firmware Arduino real)
//
// Sensores: DHT22 (temperatura, humedad), LDR (luz), potenciometro (%). Actuador: LED.
// Sube por MQTT 3.1.1 al broker propio (Mosquitto en la VM de Azure) y recibe comandos de retroceso
// por el mismo protocolo: encender, apagar, intervalo, calibrar, reset, led.
//
//   subida : campus/tele/esp32-wokwi    {"id","tipo","kind":"tele","ts","seq","v":{...},"estado":{...}}
//   bajada : campus/cmd/esp32-wokwi     {"cmd_id","accion","params":{...},"ts"}
//   LWT    : campus/conexion/esp32-wokwi (retenido) -> el broker avisa si el ESP32 cae sin despedirse
//
// Las credenciales entran por -D al compilar (MQTT_HOST, MQTT_USER, MQTT_PASS): no estan en el codigo.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#ifndef MQTT_HOST
#define MQTT_HOST "campussense-unab.northcentralus.cloudapp.azure.com"
#endif
#ifndef MQTT_USER
#define MQTT_USER "esp32"
#endif
#ifndef MQTT_PASS
#define MQTT_PASS "cambiar"
#endif

const char *ID = "esp32-wokwi";
const char *T_TELE = "campus/tele/esp32-wokwi";
const char *T_CMD = "campus/cmd/esp32-wokwi";
const char *T_CONEXION = "campus/conexion/esp32-wokwi";
const int PIN_DHT = 15, PIN_POT = 34, PIN_LDR = 35, PIN_LED = 13;

DHT dht(PIN_DHT, DHT22);
WiFiClient red;
PubSubClient mqtt(red);

bool encendido = true;
uint32_t intervaloS = 10;
uint32_t seq = 0;
bool led = false;
// calibracion por variable: indice 0 temperatura, 1 humedad, 2 luz, 3 potenciometro
const char *VARS[] = {"temperatura", "humedad", "luz", "potenciometro"};
float offs[4] = {0, 0, 0, 0}, gan[4] = {1, 1, 1, 1};
unsigned long ultimoEnvio = 0, ultimoLatido = 0;

uint64_t ahoraMs() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return (uint64_t)tv.tv_sec * 1000ULL + tv.tv_usec / 1000;
}

void llenarEstado(JsonObject e) {
  e["encendido"] = encendido ? 1 : 0;
  e["intervalo_s"] = intervaloS;
  e["led"] = led ? 1 : 0;
  for (int i = 0; i < 4; i++) {
    if (offs[i] != 0 || gan[i] != 1) {
      e[String("offset_") + VARS[i]] = offs[i];
      e[String("ganancia_") + VARS[i]] = gan[i];
    }
  }
}

void publicar(JsonDocument &doc) {
  char buf[640];
  size_t n = serializeJson(doc, buf);
  bool ok = mqtt.publish(T_TELE, (const uint8_t *)buf, n, false);
  Serial.printf("[MQTT] PUBLISH %s (%u B) %s\n", T_TELE, (unsigned)n, ok ? "ok" : "FALLO");
}

float luxLDR() {
  // modulo fotorresistor de Wokwi: divisor con 10 kOhm, GAMMA 0.7, RL10 50 kOhm
  float v = analogRead(PIN_LDR) / 4095.0 * 3.3;
  if (v >= 3.29) return 0;
  float r = 2000.0 * v / (1 - v / 5.0);
  return pow(50 * 1e3 * pow(10, 0.7) / r, 1 / 0.7);
}

void medirYEnviar() {
  float vals[4] = {dht.readTemperature(), dht.readHumidity(), luxLDR(), analogRead(PIN_POT) / 4095.0f * 100.0f};
  StaticJsonDocument<640> doc;
  doc["id"] = ID;
  doc["tipo"] = "real";
  doc["kind"] = "tele";
  doc["ts"] = ahoraMs();
  doc["seq"] = ++seq;
  JsonObject v = doc.createNestedObject("v");
  for (int i = 0; i < 4; i++) {
    if (!isnan(vals[i])) v[VARS[i]] = roundf((vals[i] * gan[i] + offs[i]) * 100) / 100.0;
  }
  v["led"] = led ? 1 : 0;
  llenarEstado(doc.createNestedObject("estado"));
  publicar(doc);
}

void enviarAck(const char *cmdId, const char *accion, bool ok, const String &detalle, uint64_t enviado) {
  StaticJsonDocument<640> doc;
  doc["id"] = ID;
  doc["tipo"] = "real";
  doc["kind"] = "ack";
  doc["ts"] = ahoraMs();
  JsonObject a = doc.createNestedObject("ack");
  a["cmd_id"] = cmdId;
  a["accion"] = accion;
  a["ok"] = ok;
  a["detalle"] = detalle;
  a["enviado_ms"] = enviado;
  llenarEstado(doc.createNestedObject("estado"));
  publicar(doc);
}

void alRecibir(char *topico, byte *payload, unsigned int len) {
  StaticJsonDocument<512> cmd;
  if (deserializeJson(cmd, payload, len)) {
    Serial.println("[CMD] JSON invalido");
    return;
  }
  const char *accion = cmd["accion"] | "";
  JsonObject p = cmd["params"];
  bool ok = true;
  String detalle = "ok";
  if (!strcmp(accion, "encender")) {
    encendido = true; detalle = "telemetria reanudada";
  } else if (!strcmp(accion, "apagar")) {
    encendido = false; detalle = "telemetria detenida";
  } else if (!strcmp(accion, "intervalo")) {
    int s = p["segundos"] | 0;
    if (s >= 5 && s <= 3600) { intervaloS = s; detalle = "intervalo=" + String(s) + "s"; }
    else { ok = false; detalle = "segundos debe estar entre 5 y 3600"; }
  } else if (!strcmp(accion, "calibrar")) {
    const char *var = p["variable"] | "";
    int k = -1;
    for (int i = 0; i < 4; i++) if (!strcmp(var, VARS[i])) k = i;
    if (k < 0) { ok = false; detalle = String("variable desconocida: ") + var; }
    else { offs[k] = p["offset"] | 0.0f; gan[k] = p["ganancia"] | 1.0f; detalle = String(var) + ": offset=" + offs[k] + " ganancia=" + gan[k]; }
  } else if (!strcmp(accion, "reset")) {
    encendido = true; intervaloS = 10;
    for (int i = 0; i < 4; i++) { offs[i] = 0; gan[i] = 1; }
    detalle = "configuracion de fabrica";
  } else if (!strcmp(accion, "led")) {
    const char *e = p["estado"] | "";
    led = !strcmp(e, "on");
    digitalWrite(PIN_LED, led ? HIGH : LOW);
    detalle = String("LED ") + (led ? "encendido" : "apagado");
  } else {
    ok = false; detalle = String("accion desconocida: ") + accion;
  }
  Serial.printf("[CMD] %s -> %s %s\n", accion, ok ? "OK" : "ERROR", detalle.c_str());
  enviarAck(cmd["cmd_id"] | "", accion, ok, detalle, cmd["ts"] | 0ULL);
  ultimoEnvio = 0;   // aplica el cambio de inmediato
}

void conectarMQTT() {
  while (!mqtt.connected()) {
    Serial.printf("[MQTT] conectando a %s:1883 como %s ... ", MQTT_HOST, MQTT_USER);
    if (mqtt.connect(ID, MQTT_USER, MQTT_PASS, T_CONEXION, 1, true, "{\"id\":\"esp32-wokwi\",\"conectado\":false}")) {
      Serial.println("CONNACK ok");
      mqtt.publish(T_CONEXION, "{\"id\":\"esp32-wokwi\",\"conectado\":true}", true);
      mqtt.subscribe(T_CMD, 1);
      Serial.printf("[MQTT] SUBSCRIBE %s qos1\n", T_CMD);
    } else {
      Serial.printf("fallo rc=%d, reintento en 3 s\n", mqtt.state());
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  dht.begin();
  WiFi.begin("Wokwi-GUEST", "", 6);
  Serial.print("[WiFi] conectando");
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.printf(" ok, IP %s\n", WiFi.localIP().toString().c_str());
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  while (time(nullptr) < 1700000000) delay(200);
  Serial.println("[NTP] hora sincronizada");
  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setBufferSize(768);
  mqtt.setKeepAlive(30);
  mqtt.setCallback(alRecibir);
}

void loop() {
  if (!mqtt.connected()) conectarMQTT();
  mqtt.loop();
  unsigned long ahora = millis();
  if (encendido && (ultimoEnvio == 0 || ahora - ultimoEnvio >= intervaloS * 1000UL)) {
    ultimoEnvio = ahora;
    medirYEnviar();
  } else if (!encendido && ahora - ultimoLatido >= 60000UL) {
    ultimoLatido = ahora;
    StaticJsonDocument<256> doc;
    doc["id"] = ID; doc["tipo"] = "real"; doc["kind"] = "estado"; doc["ts"] = ahoraMs();
    llenarEstado(doc.createNestedObject("estado"));
    publicar(doc);
  }
  delay(20);
}
