import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_SOURCE = ROOT / "firmware" / "src" / "main.cpp"
PLATFORMIO_INI = ROOT / "firmware" / "platformio.ini"


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
            "PIN_SOUND": 4,
            "PIN_PIR": 5,
            "PIN_FAN_PWM": 11,
            "PIN_FAN_DIR": 12,
            "PIN_BUZZER": 13,
            "PIN_DHT": 14,
            "PIN_OLED_SDA": 41,
            "PIN_OLED_SCL": 42,
            "PIN_RGB": 47,
            "PIN_LAMP": 48,
        }
        for name, value in expected_pins.items():
            with self.subTest(pin=name):
                self.assertRegex(
                    source,
                    rf"\b{name}\s*=\s*{value}\b",
                    f"{name} must stay aligned with AGENTS.md and 开发文档.md",
                )

    def test_stage_two_modes_and_handlers_exist(self):
        source = self.read_source()

        for symbol in [
            "emitHello",
            "emitTelemetry",
            "emitAck",
            "handleCommandLine",
            "applyAutomation",
            "readSensors",
            "writeActuators",
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
            "buzzerEnabled",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
