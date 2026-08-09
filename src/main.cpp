/*
 * ============================================================
 *  AEGIS IDEA 3 - Secure MQTT Lockdown Controller (Full Version)
 * ============================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <mbedtls/md.h>
#include <ArduinoJson.h>
#include <time.h>

// ========== ตั้งค่า ==========
const char* WIFI_SSID     = "iPhone Music";
const char* WIFI_PASSWORD = "Mew050871";

const char* MQTT_BROKER = "172.20.10.2";
const int   MQTT_PORT   = 1883;

const char* HMAC_SECRET = "AEGIS-DEMO-SHARED-SECRET-change-me";

// ========== Topics ==========
const char* TOPIC_COMMAND   = "aegis/lockdown/cmd";
const char* TOPIC_ACK       = "aegis/lockdown/ack";
const char* TOPIC_HEARTBEAT = "aegis/heartbeat";
const char* TOPIC_STATUS    = "aegis/status";

// ========== Hardware ==========
const int RELAY_IN  = 27;
const int LED_GREEN = 32;
const int LED_RED   = 33;
const int RELAY_RELEASE = HIGH;
const int RELAY_TRIGGER = LOW;

// ========== Security ==========
const unsigned long DEADMAN_TIMEOUT_MS = 60000;
const int NONCE_HISTORY_SIZE = 20;
const int MAX_COMMAND_AGE_SEC = 30;

// ========== LED Blink (ไฟแดงกระพริบตอน Lockdown) ==========
const unsigned long LED_BLINK_INTERVAL_MS = 300;

unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL_MS = 5000;

// ========== State ==========
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
bool isLockedDown = false;
unsigned long lastHeartbeatMs = 0;
bool deadmanTriggered = false;
String usedNonces[NONCE_HISTORY_SIZE];
int nonceIndex = 0;
unsigned long lastBlinkMs = 0;
bool ledRedBlinkState = false;

// ========== ฟังก์ชันประกาศล่วงหน้า ==========
String computeHMAC(const String& m, const char* key);
bool isNonceUsed(const String& n);
void recordNonce(const String& n);
void publishStatus(const String& state, const String& reason);
void setLockdown(bool lock, const String& reason);
void sendAck(const String& result, const String& detail);
void onMqttMessage(char* topic, byte* payload, unsigned int length);
void connectWiFi();
void syncTimeNTP();
void connectMQTT();
void checkDeadman();
void updateLedBlink();

String computeHMAC(const String& m, const char* key) {
  byte r[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)key, strlen(key));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)m.c_str(), m.length());
  mbedtls_md_hmac_finish(&ctx, r);
  mbedtls_md_free(&ctx);
  String hex = "";
  for (int i = 0; i < 32; i++) { char b[3]; sprintf(b, "%02x", r[i]); hex += b; }
  return hex;
}

bool isNonceUsed(const String& n) {
  for (int i = 0; i < NONCE_HISTORY_SIZE; i++) if (usedNonces[i] == n) return true;
  return false;
}
void recordNonce(const String& n) {
  usedNonces[nonceIndex] = n;
  nonceIndex = (nonceIndex + 1) % NONCE_HISTORY_SIZE;
}

void publishStatus(const String& state, const String& reason) {
  JsonDocument doc;
  doc["state"] = state;
  doc["reason"] = reason;
  doc["rssi"] = WiFi.RSSI();
  doc["heap"] = ESP.getFreeHeap();
  String out; serializeJson(doc, out);
  mqtt.publish(TOPIC_STATUS, out.c_str());
}


void setLockdown(bool lock, const String& reason) {
  isLockedDown = lock;
  digitalWrite(RELAY_IN, lock ? RELAY_TRIGGER : RELAY_RELEASE);
  digitalWrite(LED_GREEN, lock ? LOW : HIGH);
  if (lock) {
    // เริ่มกระพริบไฟแดงทันที (สถานะกระพริบคุมต่อใน updateLedBlink() ผ่าน loop())
    ledRedBlinkState = true;
    digitalWrite(LED_RED, HIGH);
    lastBlinkMs = millis();
  } else {
    digitalWrite(LED_RED, LOW);
  }
  Serial.println();
  if (lock) {
    Serial.println("################################################");
    Serial.println("#  [ LOCKDOWN ]  ตัด uplink !!");
    Serial.print("#  เหตุผล: "); Serial.println(reason);
    Serial.println("################################################");
  } else {
    Serial.println("------------------------------------------------");
    Serial.println("|  [ NORMAL ]  uplink ONLINE");
    Serial.print("|  เหตุผล: "); Serial.println(reason);
    Serial.println("------------------------------------------------");
  }
  publishStatus(lock ? "LOCKDOWN" : "NORMAL", reason);
}

void sendAck(const String& result, const String& detail) {
  JsonDocument doc;
  doc["ack"] = result;
  doc["detail"] = detail;
  String out; serializeJson(doc, out);
  mqtt.publish(TOPIC_ACK, out.c_str());
  Serial.print("  -> ACK: "); Serial.println(out);
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) message += (char)payload[i];
  String t = String(topic);

  if (t != TOPIC_COMMAND && t != TOPIC_HEARTBEAT) return;

  Serial.println();
  Serial.print("=== ได้รับข้อความจาก: "); Serial.print(t); Serial.println(" ===");
  Serial.println(message);

  JsonDocument doc;
  if (deserializeJson(doc, message)) { 
    Serial.println("[ปฏิเสธ] JSON ผิดรูปแบบ"); 
    if (t == TOPIC_COMMAND) sendAck("BAD_JSON","parse"); 
    return; 
  }

  String cmd = doc["cmd"] | "";
  String hb = doc["hb"] | "";
  String nonce = doc["nonce"] | "";
  unsigned long ts = doc["ts"] | 0UL;
  String signature = doc["sig"] | "";

  if ((cmd == "" && hb == "") || nonce == "" || ts == 0 || signature == "") { 
    Serial.println("[ปฏิเสธ] ข้อมูลไม่ครบถ้วน"); 
    if (t == TOPIC_COMMAND) sendAck("BAD_FORMAT","missing"); 
    return; 
  }

  // 1. ตรวจสอบ Timestamp Window (NTP Sync)
  time_t now = time(nullptr);
  if (abs((long)(now - ts)) > MAX_COMMAND_AGE_SEC) { 
    Serial.println("[ปฏิเสธ] !! STALE COMMAND !! คำสั่งหมดอายุแล้ว"); 
    if (t == TOPIC_COMMAND) sendAck("STALE","timestamp out of window"); 
    return; 
  }

  // 2. ตรวจสอบ Nonce (Replay Attack)
  if (isNonceUsed(nonce)) { 
    Serial.println("[ปฏิเสธ] !! REPLAY ATTACK !!"); 
    if (t == TOPIC_COMMAND) sendAck("REPLAY","nonce reused"); 
    return; 
  }

  // 3. ตรวจสอบ HMAC
  String payloadToSign = (cmd != "") ? (cmd + "|" + nonce + "|" + String(ts)) : (hb + "|" + nonce + "|" + String(ts));
  String expectedSig = computeHMAC(payloadToSign, HMAC_SECRET);
  if (expectedSig != signature) { 
    Serial.println("[ปฏิเสธ] !! HMAC ไม่ตรง !! ลายเซ็นปลอม"); 
    if (t == TOPIC_COMMAND) sendAck("BAD_HMAC","sig mismatch"); 
    return; 
  }

  // ผ่านการตรวจสอบทั้งหมด!
  recordNonce(nonce);
  Serial.println("[ผ่าน] ลายเซ็น HMAC ถูกต้อง + ภายในเวลา 30s + Nonce ใหม่");

  if (t == TOPIC_HEARTBEAT) {
    lastHeartbeatMs = millis();
    if (deadmanTriggered) { 
      deadmanTriggered = false; 
      setLockdown(false, "Heartbeat ยืนยันตัวตนสำเร็จ กลับมาแล้ว"); 
    }
    Serial.println("[HEARTBEAT] อัปเดตตัวจับเวลาเรียบร้อย");
  } 
  else if (t == TOPIC_COMMAND) {
    if (cmd == "CUT_UPLINK") { setLockdown(true, "verified"); sendAck("OK","uplink cut"); }
    else if (cmd == "RESTORE_UPLINK") { setLockdown(false, "verified"); sendAck("OK","uplink restored"); }
    else { Serial.println("[ปฏิเสธ] cmd ไม่รู้จัก"); sendAck("UNKNOWN_CMD", cmd); }
  }
}

void connectWiFi() {
  Serial.print("เชื่อมต่อ WiFi: "); Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println();
  Serial.print("WiFi OK! IP: "); Serial.println(WiFi.localIP());
}

void syncTimeNTP() {
  Serial.print("กำลังดึงเวลามาตรฐานจาก NTP...");
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  struct tm timeinfo;
  while (!getLocalTime(&timeinfo, 5000)) { 
    Serial.print("."); 
    delay(1000); 
  }
  Serial.println(" สำเร็จ!");
  Serial.println(&timeinfo, "เวลาปัจจุบัน: %A, %d %B %Y %H:%M:%S");
}

void connectMQTT() {
  // ลองต่อใหม่แค่ทุก 5 วิ ไม่วนติดแหง็ก
  if (millis() - lastReconnectAttempt < RECONNECT_INTERVAL_MS) return;
  lastReconnectAttempt = millis();

  Serial.print("เชื่อมต่อ MQTT broker...");
  String clientId = "AEGIS-ESP32-" + String(random(0xffff), HEX);
  if (mqtt.connect(clientId.c_str())) {
    Serial.println(" สำเร็จ!");
    mqtt.subscribe(TOPIC_COMMAND);
    mqtt.subscribe(TOPIC_HEARTBEAT);
    Serial.print("  subscribe: "); Serial.println(TOPIC_COMMAND);
    Serial.print("  subscribe: "); Serial.println(TOPIC_HEARTBEAT);
    publishStatus("ONLINE", "Boot completed");
  } else {
    Serial.print(" fail rc="); Serial.print(mqtt.state());
    Serial.println(" จะลองใหม่ใน 5 วิ");
  }
}

void checkDeadman() {
  if (lastHeartbeatMs == 0) return;
  if (millis() - lastHeartbeatMs > DEADMAN_TIMEOUT_MS && !deadmanTriggered) {
    deadmanTriggered = true;
    setLockdown(true, "DEAD MAN'S SWITCH - ขาดสัญญาณ Heartbeat 60 วิ!");
  }
}

void updateLedBlink() {
  if (!isLockedDown) return;  // ปกติไฟแดงดับนิ่ง ไม่ต้องกระพริบ
  unsigned long now = millis();
  if (now - lastBlinkMs >= LED_BLINK_INTERVAL_MS) {
    lastBlinkMs = now;
    ledRedBlinkState = !ledRedBlinkState;
    digitalWrite(LED_RED, ledRedBlinkState ? HIGH : LOW);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(RELAY_IN, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  digitalWrite(RELAY_IN, RELAY_RELEASE);
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_RED, LOW);
  
  Serial.println();
  Serial.println("================================================");
  Serial.println("  AEGIS IDEA 3 - Secure MQTT Lockdown (Full)");
  Serial.println("================================================");
  
  connectWiFi();
  syncTimeNTP();
  
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  connectMQTT();
  
  Serial.println("พร้อมรับคำสั่ง (เขียวติด = ปกติ)");
  Serial.println("================================================");
}

void loop() {
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();
  checkDeadman();
  updateLedBlink();
  delay(10);
}