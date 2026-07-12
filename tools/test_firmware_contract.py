import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_SOURCE = ROOT / "firmware" / "src" / "main.cpp"
PLATFORMIO_INI = ROOT / "firmware" / "platformio.ini"
SYNC_FILES = [
    ROOT / "AGENTS.md",
    ROOT / "设计方案.md",
    ROOT / "开发文档.md",
    ROOT / "assets" / "n16r8-hk2-wiring-diagram.svg",
]


class FirmwareContractTest(unittest.TestCase):
    def read_source(self):
        self.assertTrue(
            FIRMWARE_SOURCE.exists(),
            "firmware/src/main.cpp must exist for the Stage 2 firmware skeleton",
        )
        return FIRMWARE_SOURCE.read_text(encoding="utf-8")

    def read_platformio(self):
        self.assertTrue(
            PLATFORMIO_INI.exists(),
            "firmware/platformio.ini must exist for repeatable N16R8 builds",
        )
        return PLATFORMIO_INI.read_text(encoding="utf-8")

    def test_platformio_targets_esp32_s3_and_serial_speed(self):
        config = self.read_platformio()

        self.assertIn("framework = arduino", config)
        self.assertIn("monitor_speed = 115200", config)
        self.assertRegex(config, r"board\s*=\s*esp32-s3-devkitc-1")
        self.assertIn("board_build.arduino.memory_type = qio_opi", config)
        self.assertIn("board_build.partitions = default_16MB.csv", config)
        self.assertIn("board_upload.flash_size = 16MB", config)
        self.assertIn("-D BOARD_HAS_PSRAM", config)
        self.assertIn("-D ARDUINO_USB_CDC_ON_BOOT=0", config)

    def test_serial_protocol_identity_matches_docs(self):
        source = self.read_source()
        protocol_text = source.replace(r"\"", '"')

        expected_literals = [
            "smartlife-primary-hk2",
            "smartlife-primary-safe-energy-home-v1",
            "n16r8_esp32s3",
            "Serial.begin(115200)",
            '"type":"hello"',
            '"type":"telemetry"',
            '"type":"ack"',
        ]
        for literal in expected_literals:
            with self.subTest(literal=literal):
                self.assertIn(literal, protocol_text)

    def test_core_gpio_contract_is_frozen_in_firmware(self):
        source = self.read_source()

        expected_pins = {
            "PIN_LIGHT": 1,
            "PIN_MQ2": 2,
            "PIN_SOUND": 4,
            "PIN_PIR": 5,
            "PIN_FLAME": 11,
            "PIN_WATER": 8,
            "PIN_BUZZER": 13,
            "PIN_DHT": 14,
            "PIN_OLED_SDA": 41,
            "PIN_OLED_SCL": 42,
            "PIN_LAMP": 12,
        }
        for name, value in expected_pins.items():
            with self.subTest(pin=name):
                self.assertRegex(
                    source,
                    rf"\b{name}\s*=\s*{value}\b",
                    f"{name} must stay aligned with AGENTS.md and 开发文档.md",
                )

    def test_flame_sensor_uses_real_board_gpio11_active_high(self):
        source = self.read_source()

        self.assertIn("FLAME_ACTIVE_LEVEL = HIGH", source)
        self.assertIn("pinMode(PIN_FLAME, INPUT_PULLDOWN)", source)
        self.assertIn("digitalRead(PIN_FLAME) == FLAME_ACTIVE_LEVEL", source)

    def test_water_sensor_uses_real_board_gpio8_active_low(self):
        source = self.read_source()

        self.assertIn("WATER_ACTIVE_LEVEL = LOW", source)
        self.assertIn("pinMode(PIN_WATER, INPUT_PULLUP)", source)
        self.assertIn("digitalRead(PIN_WATER) == WATER_ACTIVE_LEVEL", source)

    def test_removed_actuators_are_absent_from_firmware_contract(self):
        source = self.read_source()

        removed_tokens = [
            "PIN_FAN_PWM",
            "PIN_FAN_DIR",
            "PIN_SERVO",
            "PIN_RGB",
            "PIN_KEYPAD",
            'emitPin("fanPwm"',
            'emitPin("fanDir"',
            'emitPin("servo"',
            'emitPin("rgb"',
            'Serial.print(",\\\"fan\\\":"',
            'Serial.print(",\\\"curtain\\\":"',
            'Serial.print(",\\\"rgb\\\":"',
        ]
        for token in removed_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_stable_sampling_and_oled_are_present(self):
        source = self.read_source()
        config = self.read_platformio()

        for dependency in [
            "adafruit/DHT sensor library@1.4.6",
            "adafruit/Adafruit GFX Library@1.12.1",
            "adafruit/Adafruit SSD1306@2.5.13",
        ]:
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, config)

        for token in [
            "FAST_SENSOR_INTERVAL_MS = 200",
            "DHT_INTERVAL_MS = 2000",
            "DHT_STALE_MS = 6000",
            "readFastSensors",
            "readDhtSensor",
            "sensors.dhtValid",
            "Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL)",
            "oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS, false, false)",
            "renderOled",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, source)

    def test_protocol_handlers_and_modes_exist(self):
        source = self.read_source()
        protocol_text = source.replace(r'\"', '"')

        for symbol in [
            "emitHello",
            "emitTelemetry",
            "emitAck",
            "handleCommandLine",
            "applyAutomation",
            "readFastSensors",
            "readDhtSensor",
        ]:
            with self.subTest(symbol=symbol):
                self.assertRegex(source, rf"\b{symbol}\b")

        for token in [
            '"home"',
            '"study"',
            '"away"',
            '"energy"',
            "lightThreshold",
            "temperatureThreshold",
            "soundThreshold",
            "mq2Threshold",
            "buzzerEnabled",
            '"actuator"',
            "MANUAL_OVERRIDE_MS = 10000",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, protocol_text)

    def test_safety_alerts_override_manual_buzzer_off(self):
        source = self.read_source()
        protocol_text = source.replace(r'\"', '"')

        self.assertIn("if (anyAlert())", source)
        self.assertIn("setBuzzer(buzzerEnabled)", source)
        self.assertIn("if (!anyAlert() || requested) setBuzzer(requested)", source)
        for alert in ['"mq2"', '"flame"', '"water"', '"intrusion"']:
            with self.subTest(alert=alert):
                self.assertIn(alert, protocol_text)

    def test_telemetry_contains_real_health_and_no_keypad_fields(self):
        source = self.read_source()

        for token in [
            "lightRaw",
            "soundRaw",
            "mq2Raw",
            "emitFloatOrNull",
            "relaySafety",
            "lowVoltageOnly",
            "emitDisplay",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, source)

        self.assertNotIn("thresholdFocus", source)
        self.assertNotIn("keypad", source.lower())

    def test_gpio_contract_is_synced_across_docs_and_wiring_asset(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in SYNC_FILES)

        self.assertIn("GPIO12", combined)
        self.assertIn("GPIO11", combined)
        self.assertNotIn("GPIO48", combined)
        self.assertNotIn("GPIO3 或 GPIO10", combined)
        self.assertNotIn("GPIO3/GPIO10", combined)


if __name__ == "__main__":
    unittest.main()
