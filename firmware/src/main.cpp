#include <Arduino.h>
#include <DHT.h>

namespace {

static const char PROJECT[] = "smartlife-primary-hk2";
static const char PROFILE_ID[] = "smartlife-primary-safe-energy-home-v1";
static const char BOARD_ID[] = "n16r8_esp32s3";
static const int BAUD_RATE = 115200;
static const unsigned long TELEMETRY_INTERVAL_MS = 1000;

static const uint8_t PIN_LIGHT = 1;
static const uint8_t PIN_MQ2 = 2;
static const uint8_t PIN_KEYPAD_PRIMARY = 3;
static const uint8_t PIN_SOUND = 4;
static const uint8_t PIN_PIR = 5;
static const uint8_t PIN_FLAME = 6;
static const uint8_t PIN_WATER = 8;
static const uint8_t PIN_SERVO = 9;
static const uint8_t PIN_KEYPAD_ALT = 10;
static const uint8_t PIN_FAN_PWM = 11;
static const uint8_t PIN_FAN_DIR = 12;
static const uint8_t PIN_BUZZER = 13;
static const uint8_t PIN_DHT = 14;
static const uint8_t PIN_OLED_SDA = 41;
static const uint8_t PIN_OLED_SCL = 42;
static const uint8_t PIN_RGB = 47;
static const uint8_t PIN_LAMP = 48;

enum class Mode {
  Home,
  Study,
  Away,
  Energy,
};

struct SensorState {
  int light = 0;
  int sound = 0;
  float temperature = 26.0f;
  float humidity = 55.0f;
  bool pir = false;
  int mq2 = 0;
  bool water = false;
  bool flame = false;
};

struct ActuatorState {
  bool lamp = false;
  int fan = 0;
  int curtain = 45;
  const char *rgb = "green";
  bool buzzer = false;
};

struct ThresholdState {
  int lightThreshold = 35;
  float temperatureThreshold = 29.0f;
  int soundThreshold = 70;
  int mq2Threshold = 55;
};

DHT dht(PIN_DHT, DHT11);
Mode currentMode = Mode::Home;
SensorState sensors;
ActuatorState actuators;
ThresholdState thresholds;
bool buzzerEnabled = true;
String serialLine;
unsigned long lastTelemetryAt = 0;

const char *modeName(Mode mode) {
  switch (mode) {
    case Mode::Home:
      return "home";
    case Mode::Study:
      return "study";
    case Mode::Away:
      return "away";
    case Mode::Energy:
      return "energy";
  }
  return "home";
}

int clampPercent(int value) {
  if (value < 0) {
    return 0;
  }
  if (value > 100) {
    return 100;
  }
  return value;
}

int analogPercent(uint8_t pin) {
  int raw = analogRead(pin);
  if (raw < 0) {
    raw = 0;
  }
  if (raw > 4095) {
    raw = 4095;
  }
  return (raw * 100) / 4095;
}

bool numberChar(char value) {
  return (value >= '0' && value <= '9') || value == '-' || value == '.';
}

float parseNumberAfter(const String &line, const char *key, float fallback) {
  int keyAt = line.indexOf(key);
  if (keyAt < 0) {
    return fallback;
  }

  int colonAt = line.indexOf(':', keyAt);
  if (colonAt < 0) {
    return fallback;
  }

  int start = colonAt + 1;
  while (start < line.length() && (line[start] == ' ' || line[start] == '"')) {
    start++;
  }

  int end = start;
  while (end < line.length() && numberChar(line[end])) {
    end++;
  }
  if (end == start) {
    return fallback;
  }

  return line.substring(start, end).toFloat();
}

void printBool(bool value) {
  Serial.print(value ? "true" : "false");
}

bool kitchenRisk() {
  return sensors.mq2 >= thresholds.mq2Threshold || sensors.flame;
}

bool leakRisk() {
  return sensors.water;
}

bool intrusionRisk() {
  return currentMode == Mode::Away && sensors.pir;
}

bool anyAlert() {
  return kitchenRisk() || leakRisk() || intrusionRisk();
}

const char *energyReason() {
  if (kitchenRisk()) {
    return "safety ventilation";
  }
  if (leakRisk()) {
    return "water alert";
  }
  if (intrusionRisk()) {
    return "away intrusion";
  }
  if (currentMode == Mode::Energy) {
    return "energy mode keeps lamp and fan off";
  }
  if (actuators.lamp && actuators.fan > 0) {
    return "dark and hot";
  }
  if (actuators.lamp) {
    return "dark study lamp";
  }
  if (actuators.fan > 0) {
    return "temperature ventilation";
  }
  return "collecting normal data";
}

int energyScore() {
  int score = 100;
  if (actuators.lamp) {
    score -= 12;
  }
  if (actuators.fan > 0) {
    score -= 10;
  }
  if (anyAlert()) {
    score -= 20;
  }
  if (currentMode == Mode::Energy) {
    score += 8;
  }
  return clampPercent(score);
}

void readSensors() {
  sensors.light = analogPercent(PIN_LIGHT);
  sensors.sound = analogPercent(PIN_SOUND);
  sensors.mq2 = analogPercent(PIN_MQ2);
  sensors.pir = digitalRead(PIN_PIR) == HIGH;
  sensors.water = digitalRead(PIN_WATER) == HIGH;
  sensors.flame = digitalRead(PIN_FLAME) == HIGH;

  float nextTemperature = dht.readTemperature();
  float nextHumidity = dht.readHumidity();
  if (!isnan(nextTemperature)) {
    sensors.temperature = nextTemperature;
  }
  if (!isnan(nextHumidity)) {
    sensors.humidity = nextHumidity;
  }
}

void applyAutomation() {
  bool dark = sensors.light < thresholds.lightThreshold;
  bool hot = sensors.temperature > thresholds.temperatureThreshold;

  actuators.lamp = false;
  actuators.fan = 0;
  actuators.curtain = 45;
  actuators.rgb = "green";
  actuators.buzzer = false;

  switch (currentMode) {
    case Mode::Home:
      actuators.lamp = dark && sensors.pir;
      actuators.fan = hot ? 45 : 0;
      actuators.rgb = "white";
      break;
    case Mode::Study:
      actuators.lamp = dark;
      actuators.fan = hot ? 60 : 0;
      actuators.rgb = "blue";
      break;
    case Mode::Away:
      actuators.lamp = false;
      actuators.fan = 0;
      actuators.rgb = "amber";
      break;
    case Mode::Energy:
      actuators.lamp = false;
      actuators.fan = 0;
      actuators.curtain = 20;
      actuators.rgb = "green";
      break;
  }

  if (kitchenRisk()) {
    actuators.fan = 100;
    actuators.rgb = "red";
  }
  if (leakRisk() || intrusionRisk()) {
    actuators.rgb = "red";
  }
  if (anyAlert() && buzzerEnabled) {
    actuators.buzzer = true;
  }
}

void writeActuators() {
  digitalWrite(PIN_LAMP, actuators.lamp ? HIGH : LOW);
  analogWrite(PIN_FAN_PWM, (clampPercent(actuators.fan) * 255) / 100);
  digitalWrite(PIN_FAN_DIR, actuators.fan > 0 ? HIGH : LOW);
  digitalWrite(PIN_BUZZER, actuators.buzzer ? HIGH : LOW);
}

void emitPin(const char *name, int value, bool last = false) {
  Serial.print("\"");
  Serial.print(name);
  Serial.print("\":");
  Serial.print(value);
  if (!last) {
    Serial.print(",");
  }
}

void emitHello() {
  Serial.print("{\"type\":\"hello\",\"project\":\"");
  Serial.print(PROJECT);
  Serial.print("\",\"board\":\"");
  Serial.print(BOARD_ID);
  Serial.print("\",\"profileId\":\"");
  Serial.print(PROFILE_ID);
  Serial.print("\",\"deviceName\":\"N16R8 Safe Energy Home\",\"baud\":");
  Serial.print(BAUD_RATE);
  Serial.print(",\"capabilities\":[\"webSerial\",\"mqttBridge\",\"dashboard\",\"voiceIntent\",\"energyScore\"],\"pins\":{");
  emitPin("light", PIN_LIGHT);
  emitPin("mq2", PIN_MQ2);
  emitPin("keypadPrimary", PIN_KEYPAD_PRIMARY);
  emitPin("sound", PIN_SOUND);
  emitPin("pir", PIN_PIR);
  emitPin("flame", PIN_FLAME);
  emitPin("water", PIN_WATER);
  emitPin("servo", PIN_SERVO);
  emitPin("keypadAlt", PIN_KEYPAD_ALT);
  emitPin("fanPwm", PIN_FAN_PWM);
  emitPin("fanDir", PIN_FAN_DIR);
  emitPin("buzzer", PIN_BUZZER);
  emitPin("dht", PIN_DHT);
  emitPin("oledSda", PIN_OLED_SDA);
  emitPin("oledScl", PIN_OLED_SCL);
  emitPin("rgb", PIN_RGB);
  emitPin("relayLamp", PIN_LAMP, true);
  Serial.println("}}");
}

void emitAlerts() {
  bool printed = false;
  Serial.print("\"alerts\":[");
  if (kitchenRisk()) {
    Serial.print("\"kitchenRisk\"");
    printed = true;
  }
  if (leakRisk()) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"waterLeak\"");
    printed = true;
  }
  if (intrusionRisk()) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"intrusion\"");
  }
  Serial.print("]");
}

void emitTelemetry() {
  Serial.print("{\"type\":\"telemetry\",\"mode\":\"");
  Serial.print(modeName(currentMode));
  Serial.print("\",\"sensors\":{\"light\":");
  Serial.print(sensors.light);
  Serial.print(",\"sound\":");
  Serial.print(sensors.sound);
  Serial.print(",\"temperature\":");
  Serial.print(sensors.temperature, 1);
  Serial.print(",\"humidity\":");
  Serial.print(sensors.humidity, 1);
  Serial.print(",\"pir\":");
  printBool(sensors.pir);
  Serial.print(",\"mq2\":");
  Serial.print(sensors.mq2);
  Serial.print(",\"water\":");
  printBool(sensors.water);
  Serial.print(",\"flame\":");
  printBool(sensors.flame);
  Serial.print("},\"actuators\":{\"lamp\":");
  printBool(actuators.lamp);
  Serial.print(",\"fan\":");
  Serial.print(actuators.fan);
  Serial.print(",\"curtain\":");
  Serial.print(actuators.curtain);
  Serial.print(",\"rgb\":\"");
  Serial.print(actuators.rgb);
  Serial.print("\",\"buzzer\":");
  printBool(actuators.buzzer);
  Serial.print("},");
  emitAlerts();
  Serial.print(",\"energy\":{\"score\":");
  Serial.print(energyScore());
  Serial.print(",\"reason\":\"");
  Serial.print(energyReason());
  Serial.print("\"},\"health\":{\"profileId\":\"");
  Serial.print(PROFILE_ID);
  Serial.print("\",\"thresholdFocus\":\"lightThreshold\",\"buzzer\":\"");
  Serial.print(buzzerEnabled ? "enabled" : "muted");
  Serial.print("\",\"uptimeMs\":");
  Serial.print(millis());
  Serial.println("}}");
}

void emitAck(bool ok, const String &message) {
  Serial.print("{\"type\":\"ack\",\"ok\":");
  printBool(ok);
  Serial.print(",\"message\":\"");
  Serial.print(message);
  Serial.println("\"}");
}

bool setModeFromCommand(const String &line, const char *token, Mode mode, String &message) {
  if (line.indexOf(token) < 0) {
    return false;
  }
  currentMode = mode;
  message = "mode=";
  message += modeName(mode);
  return true;
}

void handleCommandLine(String line) {
  line.trim();
  if (line.length() == 0) {
    return;
  }

  bool handled = false;
  String message = "unknown";

  handled = setModeFromCommand(line, "\"mode\":\"home\"", Mode::Home, message) || handled;
  handled = setModeFromCommand(line, "\"mode\":\"study\"", Mode::Study, message) || handled;
  handled = setModeFromCommand(line, "\"mode\":\"away\"", Mode::Away, message) || handled;
  handled = setModeFromCommand(line, "\"mode\":\"energy\"", Mode::Energy, message) || handled;

  if (line.indexOf("\"intent\":\"startStudy\"") >= 0) {
    currentMode = Mode::Study;
    message = "mode=study";
    handled = true;
  } else if (line.indexOf("\"intent\":\"setAway\"") >= 0) {
    currentMode = Mode::Away;
    message = "mode=away";
    handled = true;
  } else if (line.indexOf("\"intent\":\"setEnergy\"") >= 0) {
    currentMode = Mode::Energy;
    message = "mode=energy";
    handled = true;
  } else if (line.indexOf("\"intent\":\"querySafety\"") >= 0) {
    message = anyAlert() ? "safety=alert" : "safety=normal";
    handled = true;
  } else if (line.indexOf("\"intent\":\"muteBuzzer\"") >= 0) {
    buzzerEnabled = false;
    message = "buzzerEnabled=false";
    handled = true;
  }

  if (line.indexOf("lightThreshold") >= 0) {
    thresholds.lightThreshold = clampPercent((int)parseNumberAfter(line, "lightThreshold", thresholds.lightThreshold));
    message = "lightThreshold=" + String(thresholds.lightThreshold);
    handled = true;
  }
  if (line.indexOf("temperatureThreshold") >= 0) {
    thresholds.temperatureThreshold = parseNumberAfter(line, "temperatureThreshold", thresholds.temperatureThreshold);
    message = "temperatureThreshold=" + String(thresholds.temperatureThreshold, 1);
    handled = true;
  }
  if (line.indexOf("buzzerEnabled") >= 0) {
    buzzerEnabled = line.indexOf("false") < 0;
    message = buzzerEnabled ? "buzzerEnabled=true" : "buzzerEnabled=false";
    handled = true;
  }

  readSensors();
  applyAutomation();
  writeActuators();
  emitAck(handled, message);
}

void setupPins() {
  analogReadResolution(12);
  pinMode(PIN_LIGHT, INPUT);
  pinMode(PIN_SOUND, INPUT);
  pinMode(PIN_MQ2, INPUT);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_WATER, INPUT);
  pinMode(PIN_FLAME, INPUT);

  pinMode(PIN_LAMP, OUTPUT);
  pinMode(PIN_FAN_PWM, OUTPUT);
  pinMode(PIN_FAN_DIR, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  digitalWrite(PIN_LAMP, LOW);
  analogWrite(PIN_FAN_PWM, 0);
  digitalWrite(PIN_FAN_DIR, LOW);
  digitalWrite(PIN_BUZZER, LOW);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  setupPins();
  dht.begin();
  delay(300);
  readSensors();
  applyAutomation();
  writeActuators();
  emitHello();
  emitTelemetry();
}

void loop() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') {
      continue;
    }
    if (ch == '\n') {
      handleCommandLine(serialLine);
      serialLine = "";
    } else if (serialLine.length() < 512) {
      serialLine += ch;
    }
  }

  unsigned long now = millis();
  if (now - lastTelemetryAt >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryAt = now;
    readSensors();
    applyAutomation();
    writeActuators();
    emitTelemetry();
  }
}
