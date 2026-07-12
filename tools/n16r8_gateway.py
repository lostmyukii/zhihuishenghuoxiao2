#!/usr/bin/env python3
"""Local serial/WebSocket gateway and deterministic mock board for HK2."""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import time
from typing import Any, Dict, Iterable, Optional

from ws_json import JsonRelayServer, json_dumps

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover
    serial = None


PROJECT = "smartlife-primary-hk2"
PROFILE_ID = "smartlife-primary-safe-energy-home-v1"
MODES = {"home", "study", "away", "energy"}


class MockBoardState:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.mode = "home"
        self.sensors: Dict[str, Any] = {
            "light": 48,
            "sound": 24,
            "temperature": 27.2,
            "humidity": 55.0,
            "pir": False,
            "mq2": 18,
            "water": False,
            "flame": False,
        }
        self.thresholds = {"light": 35, "temperature": 29.0, "sound": 70, "mq2": 70}
        self.buzzer_enabled = True
        self.manual: Dict[str, Any] = {}
        self.manual_until = 0.0

    def hello(self) -> Dict[str, Any]:
        return {
            "type": "hello",
            "project": PROJECT,
            "board": "n16r8_esp32s3",
            "profileId": PROFILE_ID,
            "firmware": "mock-0.2.2",
            "deviceName": "N16R8 Safe Energy Home HK2 Mock",
            "baud": 115200,
            "capabilities": ["webSerial", "dashboard", "voiceIntent", "energyScore", "oled"],
            "pins": {
                "light": 1,
                "mq2": 2,
                "sound": 4,
                "pir": 5,
                "water": 8,
                "flame": 11,
                "lamp": 12,
                "buzzer": 13,
                "dht": 14,
                "oledSda": 41,
                "oledScl": 42,
            },
        }

    def alerts(self) -> list[str]:
        values: list[str] = []
        if self.sensors["mq2"] >= self.thresholds["mq2"]:
            values.append("mq2")
        if self.sensors["flame"]:
            values.append("flame")
        if self.sensors["water"]:
            values.append("water")
        if self.mode == "away" and self.sensors["pir"]:
            values.append("intrusion")
        if self.mode == "study" and self.sensors["sound"] > self.thresholds["sound"]:
            values.append("noise")
        if self.mode == "study" and self.sensors["temperature"] > self.thresholds["temperature"]:
            values.append("temperature")
        return values

    def actuators(self) -> Dict[str, bool]:
        alerts = self.alerts()
        safety = any(code in {"mq2", "flame", "water", "intrusion"} for code in alerts)
        dark = self.sensors["light"] < self.thresholds["light"]
        lamp = dark if self.mode == "study" else dark and self.sensors["pir"] if self.mode in {"home", "energy"} else False
        buzzer = bool(alerts) and self.buzzer_enabled
        if not safety and time.time() < self.manual_until:
            lamp = bool(self.manual.get("lamp", lamp))
            buzzer = bool(self.manual.get("buzzer", buzzer)) and self.buzzer_enabled
        return {"lamp": lamp, "buzzer": buzzer}

    def energy(self, actuators: Dict[str, bool], alerts: list[str]) -> Dict[str, Any]:
        score = 100 - (12 if actuators["lamp"] else 0) - (20 if any(code in {"mq2", "flame", "water", "intrusion"} for code in alerts) else 0)
        if self.mode == "energy":
            score = min(100, score + 8)
        if any(code in {"mq2", "flame", "water", "intrusion"} for code in alerts):
            reason = "safety-alert-active"
        elif self.mode == "energy" and not self.sensors["pir"]:
            reason = "empty-room-light-off"
        elif self.mode == "energy" and self.sensors["light"] >= self.thresholds["light"]:
            reason = "daylight-light-off"
        elif self.mode == "energy":
            reason = "occupied-dark-light-on"
        elif self.mode == "study":
            reason = "study-mode-comfort"
        elif self.mode == "away":
            reason = "away-mode-guarding"
        else:
            reason = "home-mode-active"
        return {"score": max(0, score), "reason": reason}

    def telemetry(self) -> Dict[str, Any]:
        elapsed = int((time.time() - self.started_at) * 1000)
        alerts = self.alerts()
        actuators = self.actuators()
        status = alerts[0].upper() if alerts else "NORMAL"
        lines = [
            "HK2 SAFE HOME",
            f"MODE:{self.mode}",
            f"L:{self.sensors['light']} MQ:{self.sensors['mq2']}",
            f"T:{self.sensors['temperature']:.1f} H:{self.sensors['humidity']:.0f}",
            f"P:{int(self.sensors['pir'])} W:{int(self.sensors['water'])} F:{int(self.sensors['flame'])}",
            f"LAMP:{'ON' if actuators['lamp'] else 'OFF'} BZ:{'ON' if actuators['buzzer'] else 'OFF'}",
            f"STATE:{status}",
        ]
        sensor_frame = dict(self.sensors)
        sensor_frame.update({
            "lightRaw": round(self.sensors["light"] * 4095 / 100),
            "soundRaw": round(self.sensors["sound"] * 4095 / 100),
            "mq2Raw": round(self.sensors["mq2"] * 4095 / 100),
        })
        return {
            "type": "telemetry",
            "ts": elapsed,
            "mode": self.mode,
            "sensors": sensor_frame,
            "actuators": actuators,
            "alerts": alerts,
            "thresholds": dict(self.thresholds),
            "energy": self.energy(actuators, alerts),
            "display": {"lines": lines},
            "health": {
                "profileId": PROFILE_ID,
                "dht": "ok",
                "mq2": "ready",
                "oled": "ready",
                "buzzer": "enabled" if self.buzzer_enabled else "muted",
                "relaySafety": "lowVoltageOnly",
                "uptimeMs": elapsed,
            },
        }

    def apply_command(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        if frame.get("type") == "ping":
            return {"type": "ack", "ok": True, "message": "pong"}
        if frame.get("type") == "mock":
            self.sensors.update({key: value for key, value in (frame.get("sensors") or {}).items() if key in self.sensors})
            return {"type": "ack", "ok": True, "message": "mock=sensors"}
        mode = frame.get("mode")
        if mode in MODES:
            self.mode = mode
            self.manual_until = 0
            return {"type": "ack", "ok": True, "message": f"mode={mode}"}
        if frame.get("type") == "voiceIntent":
            intent_modes = {"startStudy": "study", "setHome": "home", "returnHome": "home", "setAway": "away", "setEnergy": "energy"}
            intent = frame.get("intent")
            if intent in intent_modes:
                self.mode = intent_modes[intent]
                self.manual_until = 0
                return {"type": "ack", "ok": True, "message": f"mode={self.mode}"}
            if intent == "querySafety":
                return {"type": "ack", "ok": True, "message": "safety=alert" if any(code in {"mq2", "flame", "water", "intrusion"} for code in self.alerts()) else "safety=normal"}
            if intent == "queryComfort":
                return {"type": "ack", "ok": True, "message": f"comfort={self.sensors['temperature']:.1f}C,{self.sensors['humidity']:.0f}%"}
            if intent == "muteBuzzer":
                self.buzzer_enabled = False
                return {"type": "ack", "ok": True, "message": "buzzerEnabled=false"}
            if intent == "unmuteBuzzer":
                self.buzzer_enabled = True
                return {"type": "ack", "ok": True, "message": "buzzerEnabled=true"}
        settings = frame.get("set") or {}
        field_map = {"lightThreshold": "light", "temperatureThreshold": "temperature", "soundThreshold": "sound", "mq2Threshold": "mq2"}
        changed = []
        for field, key in field_map.items():
            if field in settings:
                self.thresholds[key] = float(settings[field]) if key == "temperature" else int(settings[field])
                changed.append(field)
        if "buzzerEnabled" in settings:
            self.buzzer_enabled = bool(settings["buzzerEnabled"])
            changed.append("buzzerEnabled")
        if changed:
            return {"type": "ack", "ok": True, "message": f"set={','.join(changed)}"}
        if "actuator" in frame:
            self.manual.update({key: bool(value) for key, value in (frame.get("actuator") or {}).items() if key in {"lamp", "buzzer"}})
            self.manual_until = time.time() + 10
            return {"type": "ack", "ok": True, "message": "actuator=temporary-10s"}
        return {"type": "ack", "ok": False, "message": "unknown-command"}


def candidate_serial_ports() -> Iterable[str]:
    for pattern in ["/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.usbmodem*", "/dev/tty.usbserial*", "/dev/tty.wchusbserial*"]:
        yield from sorted(glob.glob(pattern))


def choose_serial_port(requested: Optional[str]) -> str:
    if requested:
        return requested
    try:
        return next(iter(candidate_serial_ports()))
    except StopIteration as exc:
        raise RuntimeError("no serial port found; pass --serial-port or use --mock-board") from exc


def prepare_serial_board(board: Any, reset_delay: float = 0.12) -> None:
    """Release CH340 control lines and hard-reset into the normal application."""
    board.dtr = False
    board.rts = True
    time.sleep(reset_delay)
    board.rts = False
    board.reset_input_buffer()


async def mock_board_loop(relay: JsonRelayServer) -> None:
    board = MockBoardState()
    await relay.broadcast_json(board.hello(), retain=True)

    async def consume_commands() -> None:
        while True:
            frame = await relay.incoming.get()
            if frame.get("type") in {"command", "voiceIntent", "ping", "mock"}:
                await relay.broadcast_json(board.apply_command(frame))

    asyncio.create_task(consume_commands())
    while True:
        await relay.broadcast_json(board.telemetry(), retain=True)
        await asyncio.sleep(1)


async def serial_read_loop(relay: JsonRelayServer, board: Any) -> None:
    while True:
        raw = await asyncio.to_thread(board.readline)
        if not raw:
            await asyncio.sleep(0.02)
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("{"):
            continue
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:
            continue
        await relay.broadcast_json(frame, retain=frame.get("type") in {"hello", "telemetry", "health"})


async def serial_command_loop(relay: JsonRelayServer, board: Any) -> None:
    while True:
        frame = await relay.incoming.get()
        if frame.get("type") not in {"command", "voiceIntent", "ping"}:
            continue
        await asyncio.to_thread(board.write, (json_dumps(frame) + "\n").encode("utf-8"))
        await asyncio.to_thread(board.flush)


async def run_gateway(args: argparse.Namespace) -> None:
    relay = JsonRelayServer(args.ws_host, args.ws_port, name="smartlife-primary-hk2-local")
    await relay.start()
    print(f"gateway websocket listening on ws://{args.ws_host}:{args.ws_port}")
    if args.mock_board:
        print("mock board enabled")
        await mock_board_loop(relay)
        return
    if serial is None:
        raise RuntimeError("pyserial is not installed; use --mock-board or install pyserial")
    port_name = choose_serial_port(args.serial_port)
    board = serial.Serial(port_name, args.baud, timeout=0.1)
    prepare_serial_board(board)
    print(f"serial connected: {port_name} baud={args.baud}")
    await asyncio.gather(serial_read_loop(relay, board), serial_command_loop(relay, board))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HK2 N16R8 local serial/WebSocket gateway")
    parser.add_argument("--mock-board", action="store_true")
    parser.add_argument("--serial-port")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=18766)
    return parser


def main() -> None:
    try:
        asyncio.run(run_gateway(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("gateway stopped")


if __name__ == "__main__":
    main()
