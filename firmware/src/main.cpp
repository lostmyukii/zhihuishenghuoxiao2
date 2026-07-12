#include <Arduino.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <Wire.h>

#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif

#ifndef ESP_ARDUINO_VERSION_MAJOR
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

namespace {

static const char PROJECT[] = "smartlife-primary-hk2";
static const char PROFILE_ID[] = "smartlife-primary-safe-energy-home-v1";
static const char BOARD_ID[] = "n16r8_esp32s3";
static const char FIRMWARE_VERSION[] = "0.2.0";
static const int BAUD_RATE = 115200;
static const unsigned long TELEMETRY_INTERVAL_MS = 1000;
static const unsigned long FAST_SENSOR_INTERVAL_MS = 200;
static const unsigned long DHT_INTERVAL_MS = 2000;
static const unsigned long DHT_STALE_MS = 6000;
static const unsigned long OLED_INTERVAL_MS = 500;
static const unsigned long MANUAL_OVERRIDE_MS = 10000;

static const uint8_t PIN_LIGHT = 1;
static const uint8_t PIN_MQ2 = 2;
static const uint8_t PIN_SOUND = 4;
static const uint8_t PIN_PIR = 5;
static const uint8_t PIN_FLAME = 11;
static const uint8_t PIN_WATER = 8;
static const uint8_t PIN_BUZZER = 13;
static const uint8_t PIN_DHT = 14;
static const uint8_t PIN_OLED_SDA = 41;
static const uint8_t PIN_OLED_SCL = 42;
static const uint8_t PIN_LAMP = 12;

static const uint8_t BUZZER_CHANNEL = 1;
static const uint8_t BUZZER_RESOLUTION = 8;
static const uint32_t BUZZER_FREQUENCY = 2200;
static const uint8_t OLED_ADDRESS = 0x3C;
static const uint8_t OLED_WIDTH = 128;
static const uint8_t OLED_HEIGHT = 64;

enum class Mode {
  Home,
  Study,
  Away,
  Energy,
};

struct SensorState {
  int lightRaw = 0;
  int light = 0;
  int soundRaw = 0;
  int sound = 0;
  int mq2Raw = 0;
  float temperature = NAN;
  float humidity = NAN;
  bool dhtValid = false;
  bool pir = false;
  int mq2 = 0;
  bool water = false;
  bool flame = false;
};

struct ActuatorState {
  bool lamp = false;
  bool buzzer = false;
};

struct ThresholdState {
  int lightThreshold = 35;
  float temperatureThreshold = 29.0f;
  int soundThreshold = 70;
  int mq2Threshold = 55;
};

DHT dht(PIN_DHT, DHT11);
Adafruit_SSD1306 oled(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
Mode currentMode = Mode::Home;
SensorState sensors;
ActuatorState actuators;
ThresholdState thresholds;
bool buzzerEnabled = true;
String serialLine;
unsigned long lastTelemetryAt = 0;
unsigned long lastFastSensorAt = 0;
unsigned long lastDhtReadAt = 0;
unsigned long lastDhtSuccessAt = 0;
unsigned long lastOledAt = 0;
unsigned long manualOverrideUntil = 0;
bool oledReady = false;

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

int analogPercentFromRaw(int raw) {
  if (raw < 0) {
    raw = 0;
  }
  if (raw > 4095) {
    raw = 4095;
  }
  return (raw * 100) / 4095;
}

void attachBuzzerPwm() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_BUZZER, BUZZER_FREQUENCY, BUZZER_RESOLUTION);
#else
  ledcSetup(BUZZER_CHANNEL, BUZZER_FREQUENCY, BUZZER_RESOLUTION);
  ledcAttachPin(PIN_BUZZER, BUZZER_CHANNEL);
#endif
}

void writeBuzzerPwm(uint32_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_BUZZER, duty);
#else
  ledcWrite(BUZZER_CHANNEL, duty);
#endif
}

void setLamp(bool on) {
  actuators.lamp = on;
  digitalWrite(PIN_LAMP, on ? HIGH : LOW);
}

void setBuzzer(bool on) {
  actuators.buzzer = on;
  writeBuzzerPwm(on ? 128 : 0);
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

bool temperatureReminder() {
  return currentMode == Mode::Study && sensors.dhtValid &&
         sensors.temperature > thresholds.temperatureThreshold;
}

bool noiseReminder() {
  return currentMode == Mode::Study && sensors.sound > thresholds.soundThreshold;
}

bool anyAlert() {
  return kitchenRisk() || leakRisk() || intrusionRisk();
}

bool anyReminder() {
  return noiseReminder() || temperatureReminder();
}

String highestStatusCode() {
  if (sensors.mq2 >= thresholds.mq2Threshold) return "MQ2";
  if (sensors.flame) return "FLAME";
  if (sensors.water) return "WATER";
  if (intrusionRisk()) return "INTRUSION";
  if (noiseReminder()) return "NOISE";
  if (temperatureReminder()) return "TEMP";
  return "NORMAL";
}

String displayLine(uint8_t index) {
  switch (index) {
    case 0:
      return "HK2 SAFE HOME";
    case 1:
      return String("MODE:") + modeName(currentMode);
    case 2:
      return String("L:") + sensors.light + " MQ:" + sensors.mq2;
    case 3:
      return String("T:") + (sensors.dhtValid ? String(sensors.temperature, 1) : "--") + " H:" +
             (sensors.dhtValid ? String(sensors.humidity, 0) : "--");
    case 4:
      return String("P:") + (sensors.pir ? "1" : "0") + " W:" + (sensors.water ? "1" : "0") +
             " F:" + (sensors.flame ? "1" : "0");
    case 5:
      return String("LAMP:") + (actuators.lamp ? "ON" : "OFF") + " BZ:" +
             (actuators.buzzer ? "ON" : "OFF");
    case 6:
      return String("STATE:") + highestStatusCode();
  }
  return "";
}

void renderOled() {
  if (!oledReady) return;
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  for (uint8_t row = 0; row < 7; row++) {
    oled.setCursor(0, row * 9);
    oled.print(displayLine(row));
  }
  oled.display();
}

const char *energyReason() {
  if (anyAlert()) {
    return "safety-alert-active";
  }
  if (currentMode == Mode::Energy) {
    if (!sensors.pir) {
      return "empty-room-light-off";
    }
    if (sensors.light >= thresholds.lightThreshold) {
      return "daylight-light-off";
    }
    return "occupied-dark-light-on";
  }
  if (currentMode == Mode::Study) {
    return "study-mode-comfort";
  }
  return currentMode == Mode::Away ? "away-mode-guarding" : "home-mode-active";
}

int energyScore() {
  int score = 100;
  if (actuators.lamp) {
    score -= 12;
  }
  if (anyAlert()) {
    score -= 20;
  }
  if (currentMode == Mode::Energy) {
    score += 8;
  }
  return clampPercent(score);
}

void readFastSensors() {
  sensors.lightRaw = analogRead(PIN_LIGHT);
  sensors.soundRaw = analogRead(PIN_SOUND);
  sensors.mq2Raw = analogRead(PIN_MQ2);
  sensors.light = analogPercentFromRaw(sensors.lightRaw);
  sensors.sound = analogPercentFromRaw(sensors.soundRaw);
  sensors.mq2 = analogPercentFromRaw(sensors.mq2Raw);
  sensors.pir = digitalRead(PIN_PIR) == HIGH;
  sensors.water = digitalRead(PIN_WATER) == HIGH;
  sensors.flame = digitalRead(PIN_FLAME) == LOW;
}

void readDhtSensor(unsigned long now) {
  float nextTemperature = dht.readTemperature();
  float nextHumidity = dht.readHumidity();
  if (!isnan(nextTemperature) && !isnan(nextHumidity)) {
    sensors.temperature = nextTemperature;
    sensors.humidity = nextHumidity;
    sensors.dhtValid = true;
    lastDhtSuccessAt = now;
    return;
  }

  if (lastDhtSuccessAt == 0 || now - lastDhtSuccessAt >= DHT_STALE_MS) {
    sensors.dhtValid = false;
  }
}

void applyAutomation() {
  bool dark = sensors.light < thresholds.lightThreshold;

  if (anyAlert()) {
    setBuzzer(buzzerEnabled);
  } else if (manualOverrideUntil > millis()) {
    return;
  }

  bool automaticLamp = false;
  bool automaticBuzzer = false;

  switch (currentMode) {
    case Mode::Home:
      automaticLamp = dark && sensors.pir;
      break;
    case Mode::Study:
      automaticLamp = dark;
      automaticBuzzer = anyReminder();
      break;
    case Mode::Away:
      automaticLamp = false;
      break;
    case Mode::Energy:
      automaticLamp = dark && sensors.pir;
      break;
  }

  setLamp(automaticLamp);
  if (!anyAlert()) {
    setBuzzer(automaticBuzzer && buzzerEnabled);
  }
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
  Serial.print("\",\"firmware\":\"");
  Serial.print(FIRMWARE_VERSION);
  Serial.print("\",\"deviceName\":\"N16R8 Safe Energy Home HK2\",\"baud\":");
  Serial.print(BAUD_RATE);
  Serial.print(",\"capabilities\":[\"webSerial\",\"dashboard\",\"voiceIntent\",\"energyScore\",\"oled\"],\"pins\":{");
  emitPin("light", PIN_LIGHT);
  emitPin("mq2", PIN_MQ2);
  emitPin("sound", PIN_SOUND);
  emitPin("pir", PIN_PIR);
  emitPin("flame", PIN_FLAME);
  emitPin("water", PIN_WATER);
  emitPin("lamp", PIN_LAMP);
  emitPin("buzzer", PIN_BUZZER);
  emitPin("dht", PIN_DHT);
  emitPin("oledSda", PIN_OLED_SDA);
  emitPin("oledScl", PIN_OLED_SCL, true);
  Serial.println("}}");
}

void emitAlerts() {
  bool printed = false;
  Serial.print("\"alerts\":[");
  if (sensors.mq2 >= thresholds.mq2Threshold) {
    Serial.print("\"mq2\"");
    printed = true;
  }
  if (sensors.flame) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"flame\"");
    printed = true;
  }
  if (leakRisk()) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"water\"");
    printed = true;
  }
  if (intrusionRisk()) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"intrusion\"");
    printed = true;
  }
  if (noiseReminder()) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"noise\"");
    printed = true;
  }
  if (temperatureReminder()) {
    if (printed) {
      Serial.print(",");
    }
    Serial.print("\"temperature\"");
  }
  Serial.print("]");
}

void emitFloatOrNull(float value, bool valid, uint8_t decimals) {
  if (!valid || isnan(value)) {
    Serial.print("null");
    return;
  }
  Serial.print(value, decimals);
}

void emitDisplay() {
  Serial.print("\"display\":{\"lines\":[");
  for (uint8_t index = 0; index < 7; index++) {
    if (index > 0) Serial.print(",");
    Serial.print("\"");
    Serial.print(displayLine(index));
    Serial.print("\"");
  }
  Serial.print("]}");
}

void emitTelemetry() {
  Serial.print("{\"type\":\"telemetry\",\"ts\":");
  Serial.print(millis());
  Serial.print(",\"mode\":\"");
  Serial.print(modeName(currentMode));
  Serial.print("\",\"sensors\":{\"light\":");
  Serial.print(sensors.light);
  Serial.print(",\"lightRaw\":");
  Serial.print(sensors.lightRaw);
  Serial.print(",\"sound\":");
  Serial.print(sensors.sound);
  Serial.print(",\"soundRaw\":");
  Serial.print(sensors.soundRaw);
  Serial.print(",\"temperature\":");
  emitFloatOrNull(sensors.temperature, sensors.dhtValid, 1);
  Serial.print(",\"humidity\":");
  emitFloatOrNull(sensors.humidity, sensors.dhtValid, 1);
  Serial.print(",\"pir\":");
  printBool(sensors.pir);
  Serial.print(",\"mq2\":");
  Serial.print(sensors.mq2);
  Serial.print(",\"mq2Raw\":");
  Serial.print(sensors.mq2Raw);
  Serial.print(",\"water\":");
  printBool(sensors.water);
  Serial.print(",\"flame\":");
  printBool(sensors.flame);
  Serial.print("},\"actuators\":{\"lamp\":");
  printBool(actuators.lamp);
  Serial.print(",\"buzzer\":");
  printBool(actuators.buzzer);
  Serial.print("},");
  emitAlerts();
  Serial.print(",\"thresholds\":{\"light\":");
  Serial.print(thresholds.lightThreshold);
  Serial.print(",\"temperature\":");
  Serial.print(thresholds.temperatureThreshold, 1);
  Serial.print(",\"sound\":");
  Serial.print(thresholds.soundThreshold);
  Serial.print(",\"mq2\":");
  Serial.print(thresholds.mq2Threshold);
  Serial.print("}");
  Serial.print(",\"energy\":{\"score\":");
  Serial.print(energyScore());
  Serial.print(",\"reason\":\"");
  Serial.print(energyReason());
  Serial.print("\"},");
  emitDisplay();
  Serial.print(",\"health\":{\"profileId\":\"");
  Serial.print(PROFILE_ID);
  Serial.print("\",\"dht\":\"");
  Serial.print(sensors.dhtValid ? "ok" : "missing");
  Serial.print("\",\"oled\":\"");
  Serial.print(oledReady ? "ready" : "missing");
  Serial.print("\",\"buzzer\":\"");
  Serial.print(buzzerEnabled ? "enabled" : "muted");
  Serial.print("\",\"relaySafety\":\"lowVoltageOnly\"");
  Serial.print(",\"uptimeMs\":");
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
  manualOverrideUntil = 0;
  message = "mode=";
  message += modeName(mode);
  return true;
}

bool parseBoolAfter(const String &line, const char *key, bool fallback) {
  int keyAt = line.indexOf(key);
  if (keyAt < 0) return fallback;
  int colonAt = line.indexOf(':', keyAt);
  if (colonAt < 0) return fallback;
  int falseAt = line.indexOf("false", colonAt);
  int trueAt = line.indexOf("true", colonAt);
  if (falseAt >= 0 && (trueAt < 0 || falseAt < trueAt)) return false;
  if (trueAt >= 0) return true;
  return fallback;
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
    manualOverrideUntil = 0;
    message = "mode=study";
    handled = true;
  } else if (line.indexOf("\"intent\":\"setHome\"") >= 0 ||
             line.indexOf("\"intent\":\"returnHome\"") >= 0) {
    currentMode = Mode::Home;
    manualOverrideUntil = 0;
    message = "mode=home";
    handled = true;
  } else if (line.indexOf("\"intent\":\"setAway\"") >= 0) {
    currentMode = Mode::Away;
    manualOverrideUntil = 0;
    message = "mode=away";
    handled = true;
  } else if (line.indexOf("\"intent\":\"setEnergy\"") >= 0) {
    currentMode = Mode::Energy;
    manualOverrideUntil = 0;
    message = "mode=energy";
    handled = true;
  } else if (line.indexOf("\"intent\":\"querySafety\"") >= 0) {
    message = anyAlert() ? "safety=alert" : "safety=normal";
    handled = true;
  } else if (line.indexOf("\"intent\":\"queryComfort\"") >= 0) {
    message = sensors.dhtValid
                  ? "comfort=" + String(sensors.temperature, 1) + "C," + String(sensors.humidity, 0) + "%"
                  : "comfort=dht-missing";
    handled = true;
  } else if (line.indexOf("\"intent\":\"muteBuzzer\"") >= 0) {
    buzzerEnabled = false;
    message = "buzzerEnabled=false";
    handled = true;
  } else if (line.indexOf("\"intent\":\"unmuteBuzzer\"") >= 0) {
    buzzerEnabled = true;
    message = "buzzerEnabled=true";
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
  if (line.indexOf("soundThreshold") >= 0) {
    thresholds.soundThreshold = clampPercent((int)parseNumberAfter(line, "soundThreshold", thresholds.soundThreshold));
    message = "soundThreshold=" + String(thresholds.soundThreshold);
    handled = true;
  }
  if (line.indexOf("mq2Threshold") >= 0) {
    thresholds.mq2Threshold = clampPercent((int)parseNumberAfter(line, "mq2Threshold", thresholds.mq2Threshold));
    message = "mq2Threshold=" + String(thresholds.mq2Threshold);
    handled = true;
  }
  if (line.indexOf("buzzerEnabled") >= 0) {
    buzzerEnabled = parseBoolAfter(line, "buzzerEnabled", buzzerEnabled);
    message = buzzerEnabled ? "buzzerEnabled=true" : "buzzerEnabled=false";
    handled = true;
  }

  if (line.indexOf("\"actuator\"") >= 0) {
    manualOverrideUntil = millis() + MANUAL_OVERRIDE_MS;
    if (line.indexOf("\"lamp\"") >= 0) {
      setLamp(parseBoolAfter(line, "\"lamp\"", actuators.lamp));
      message = String("lamp=") + (actuators.lamp ? "true" : "false");
      handled = true;
    }
    if (line.indexOf("\"buzzer\"") >= 0) {
      bool requested = parseBoolAfter(line, "\"buzzer\"", actuators.buzzer);
      if (!anyAlert() || requested) setBuzzer(requested);
      message = String("buzzer=") + (actuators.buzzer ? "true" : "false");
      handled = true;
    }
  }

  readFastSensors();
  applyAutomation();
  renderOled();
  emitAck(handled, message);
}

void setupPins() {
  analogReadResolution(12);
  pinMode(PIN_LIGHT, INPUT);
  pinMode(PIN_SOUND, INPUT);
  pinMode(PIN_MQ2, INPUT);
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_WATER, INPUT);
  pinMode(PIN_FLAME, INPUT_PULLUP);

  pinMode(PIN_LAMP, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  setupPins();
  attachBuzzerPwm();
  setLamp(false);
  setBuzzer(false);
  Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
  oledReady = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS, false, false);
  dht.begin();
  delay(300);
  readFastSensors();
  readDhtSensor(millis());
  applyAutomation();
  renderOled();
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
  if (now - lastFastSensorAt >= FAST_SENSOR_INTERVAL_MS) {
    lastFastSensorAt = now;
    readFastSensors();
    applyAutomation();
  }
  if (now - lastDhtReadAt >= DHT_INTERVAL_MS) {
    lastDhtReadAt = now;
    readDhtSensor(now);
    applyAutomation();
  }
  if (now - lastOledAt >= OLED_INTERVAL_MS) {
    lastOledAt = now;
    renderOled();
  }
  if (now - lastTelemetryAt >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryAt = now;
    emitTelemetry();
  }
}
