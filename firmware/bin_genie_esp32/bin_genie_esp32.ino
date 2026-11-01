/*
 * BIN-GENIE ESP32 firmware  v1.0.0
 * Speaks the same line protocol as the dashboard simulator.
 * Flash with Arduino-ESP32. Board: ESP32 Dev Module. 115200 baud.
 */

#include <ESP32Servo.h>

const char* FIRMWARE = "1.0.0";

const int PIN_SERVO = 18;
const int PIN_STEP  = 19;
const int PIN_DIR   = 21;
const int PIN_IR    = 32;   // active LOW = object present
const int PIN_MOIST = 34;   // analog
const int PIN_METAL = 35;   // HIGH = metal
const int LED_PM    = 25;
const int LED_PA    = 26;
const int LED_GL    = 27;
const int LED_RS    = 14;

const int STEPS_PER_REV = 200 * 8; // 1.8° motor, 8× microstep
const int STEP_US = 800;

Servo flap;
int discDeg = 0;

struct Bay {
  const char* key;
  int deg;
  int led;
};

Bay bays[] = {
  {"plastic_metal", 0,   LED_PM},
  {"paper",         90,  LED_PA},
  {"glass",         180, LED_GL},
  {"residual",      270, LED_RS},
};

void setup() {
  Serial.begin(115200);
  pinMode(PIN_STEP, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_IR, INPUT_PULLUP);
  pinMode(PIN_METAL, INPUT_PULLDOWN);
  pinMode(LED_PM, OUTPUT);
  pinMode(LED_PA, OUTPUT);
  pinMode(LED_GL, OUTPUT);
  pinMode(LED_RS, OUTPUT);
  flap.setPeriodHertz(50);
  flap.attach(PIN_SERVO, 500, 2400);
  flap.write(0);
  allLeds(LOW);
  Serial.println("PONG firmware=1.0.0 mode=live");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length()) handle(line);
  }
}

void handle(String cmd) {
  if (cmd == "PING") {
    Serial.println("PONG firmware=1.0.0 mode=live");
    return;
  }
  if (cmd == "STATUS") {
    emitSensors();
    emitFill();
    return;
  }
  if (cmd == "RESET") {
    rotateTo(0);
    flap.write(0);
    allLeds(LOW);
    Serial.println("SORT_OK bin=home t_ms=0 disc=0 flap=0");
    return;
  }
  if (cmd.startsWith("SORT ")) {
    String key = cmd.substring(5);
    key.trim();
    unsigned long t0 = millis();
    Bay* b = findBay(key);
    if (!b) {
      Serial.println("SORT_ERR reason=unknown_bin");
      return;
    }
    rotateTo(b->deg);
    allLeds(LOW);
    digitalWrite(b->led, HIGH);
    flap.write(18);
    delay(400);
    flap.write(0);
    unsigned long dt = millis() - t0;
    Serial.print("SORT_OK bin=");
    Serial.print(b->key);
    Serial.print(" t_ms=");
    Serial.print(dt);
    Serial.print(" disc=");
    Serial.print(b->deg);
    Serial.println(" flap=18");
    return;
  }
  Serial.println("SORT_ERR reason=unknown_cmd");
}

Bay* findBay(String key) {
  for (int i = 0; i < 4; i++) {
    if (key == bays[i].key) return &bays[i];
  }
  return nullptr;
}

void emitSensors() {
  int ir = digitalRead(PIN_IR) == LOW ? 1 : 0;
  float moist = analogRead(PIN_MOIST) / 4095.0f;
  int metal = digitalRead(PIN_METAL) == HIGH ? 1 : 0;
  Serial.print("SENSORS ir=");
  Serial.print(ir);
  Serial.print(" moist=");
  Serial.print(moist, 2);
  Serial.print(" metal=");
  Serial.println(metal);
}

void emitFill() {
  // Fill is owned by the host (vision + SQLite). Device only reports sensors.
  Serial.println("FILL host_owned=1");
}

void rotateTo(int target) {
  int delta = target - discDeg;
  while (delta > 180) delta -= 360;
  while (delta < -180) delta += 360;
  digitalWrite(PIN_DIR, delta >= 0 ? HIGH : LOW);
  int steps = abs(delta) * (STEPS_PER_REV / 360);
  for (int i = 0; i < steps; i++) {
    digitalWrite(PIN_STEP, HIGH);
    delayMicroseconds(STEP_US);
    digitalWrite(PIN_STEP, LOW);
    delayMicroseconds(STEP_US);
  }
  discDeg = target;
}

void allLeds(int v) {
  digitalWrite(LED_PM, v);
  digitalWrite(LED_PA, v);
  digitalWrite(LED_GL, v);
  digitalWrite(LED_RS, v);
}
