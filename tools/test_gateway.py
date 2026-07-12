#!/usr/bin/env python3
import unittest

from n16r8_gateway import MockBoardState, PROFILE_ID, PROJECT, prepare_serial_board
from ws_json import PROTOCOL_TOPIC_PREFIX, is_protocol_frame, topic_for_frame


class GatewayContractTest(unittest.TestCase):
    def test_real_serial_prepare_releases_ch340_reset_lines(self):
        class FakeSerial:
            dtr = True
            rts = False
            reset_calls = 0

            def reset_input_buffer(self):
                self.reset_calls += 1

        board = FakeSerial()
        prepare_serial_board(board, reset_delay=0)
        self.assertFalse(board.dtr)
        self.assertFalse(board.rts)
        self.assertEqual(board.reset_calls, 1)

    def test_identity_and_topic_are_hk2(self):
        board = MockBoardState()
        hello = board.hello()
        self.assertEqual(hello["project"], PROJECT)
        self.assertEqual(hello["profileId"], PROFILE_ID)
        self.assertEqual(PROTOCOL_TOPIC_PREFIX, "smartlife/primary/hk2/n16r8")
        self.assertEqual(topic_for_frame({"type": "ack"}), f"{PROTOCOL_TOPIC_PREFIX}/event")
        self.assertTrue(is_protocol_frame({"type": "telemetry"}))

    def test_hardware_scope_and_gpio_contract(self):
        pins = MockBoardState().hello()["pins"]
        self.assertEqual(pins["flame"], 11)
        self.assertEqual(pins["lamp"], 12)
        self.assertEqual(pins["buzzer"], 13)
        self.assertNotIn("keypad", pins)
        self.assertNotIn("fan", pins)
        self.assertNotIn("servo", pins)
        self.assertNotIn("rgb", pins)

    def test_mode_and_energy_rules(self):
        board = MockBoardState()
        board.sensors.update({"light": 20, "pir": True})
        board.apply_command({"type": "command", "mode": "energy"})
        telemetry = board.telemetry()
        self.assertEqual(telemetry["mode"], "energy")
        self.assertTrue(telemetry["actuators"]["lamp"])
        self.assertEqual(telemetry["energy"]["reason"], "occupied-dark-light-on")

        board.sensors["pir"] = False
        telemetry = board.telemetry()
        self.assertFalse(telemetry["actuators"]["lamp"])
        self.assertEqual(telemetry["energy"]["reason"], "empty-room-light-off")

    def test_study_reminders_and_away_intrusion(self):
        board = MockBoardState()
        board.apply_command({"type": "command", "mode": "study"})
        board.sensors.update({"sound": 80, "temperature": 31})
        self.assertEqual(board.telemetry()["alerts"], ["noise", "temperature"])

        board.apply_command({"type": "command", "mode": "away"})
        board.sensors.update({"sound": 20, "temperature": 27, "pir": True})
        telemetry = board.telemetry()
        self.assertIn("intrusion", telemetry["alerts"])
        self.assertTrue(telemetry["actuators"]["buzzer"])
        self.assertFalse(telemetry["actuators"]["lamp"])

    def test_all_safety_sensors_and_explicit_mute(self):
        board = MockBoardState()
        board.sensors.update({"mq2": 70, "flame": True, "water": True})
        telemetry = board.telemetry()
        self.assertEqual(telemetry["alerts"], ["mq2", "flame", "water"])
        self.assertTrue(telemetry["actuators"]["buzzer"])

        board.apply_command({"type": "command", "actuator": {"buzzer": False}})
        self.assertTrue(board.telemetry()["actuators"]["buzzer"])

        board.apply_command({"type": "command", "set": {"buzzerEnabled": False}})
        telemetry = board.telemetry()
        self.assertFalse(telemetry["actuators"]["buzzer"])
        self.assertEqual(telemetry["health"]["buzzer"], "muted")

    def test_voice_whitelist_and_thresholds(self):
        board = MockBoardState()
        ack = board.apply_command({"type": "voiceIntent", "intent": "startStudy"})
        self.assertEqual(ack["message"], "mode=study")
        ack = board.apply_command({"type": "voiceIntent", "intent": "setAway"})
        self.assertEqual(ack["message"], "mode=away")
        ack = board.apply_command({"type": "command", "set": {"lightThreshold": 28, "mq2Threshold": 60}})
        self.assertTrue(ack["ok"])
        self.assertEqual(board.thresholds["light"], 28)
        self.assertEqual(board.thresholds["mq2"], 60)

    def test_telemetry_has_dashboard_contract(self):
        telemetry = MockBoardState().telemetry()
        self.assertEqual(len(telemetry["display"]["lines"]), 7)
        self.assertEqual(telemetry["health"]["oled"], "ready")
        self.assertIn("lightRaw", telemetry["sensors"])
        self.assertIn("thresholds", telemetry)
        self.assertNotIn("mqtt", telemetry["health"])


if __name__ == "__main__":
    unittest.main()
