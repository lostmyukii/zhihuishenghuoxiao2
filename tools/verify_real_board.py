#!/usr/bin/env python3
"""Verify HK2 hello/telemetry/ack directly over the CH340 serial port."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict

import serial  # type: ignore


PROJECT = "smartlife-primary-hk2"
PROFILE_ID = "smartlife-primary-safe-energy-home-v1"


def compact(frame: Dict[str, Any]) -> str:
    return json.dumps(frame, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a flashed HK2 board over UART0")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=12)
    args = parser.parse_args()

    hello: Dict[str, Any] | None = None
    telemetry: Dict[str, Any] | None = None
    acknowledgements: list[Dict[str, Any]] = []
    boot_lines = 0
    post_protocol_invalid_lines = 0
    protocol_started = False
    command_sent = False
    restored_home = False

    with serial.Serial(args.port, args.baud, timeout=0.25) as board:
        board.dtr = False
        board.rts = True
        time.sleep(0.12)
        board.rts = False
        board.reset_input_buffer()
        deadline = time.time() + args.seconds

        while time.time() < deadline:
            raw = board.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("{"):
                if protocol_started:
                    post_protocol_invalid_lines += 1
                else:
                    boot_lines += 1
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                if protocol_started:
                    post_protocol_invalid_lines += 1
                else:
                    boot_lines += 1
                continue
            protocol_started = True
            frame_type = frame.get("type")
            if frame_type == "hello":
                hello = frame
            elif frame_type == "telemetry":
                telemetry = frame
                if hello and not command_sent:
                    board.write(b'{"type":"command","mode":"study"}\n')
                    board.flush()
                    command_sent = True
            elif frame_type == "ack":
                acknowledgements.append(frame)
                if frame.get("message") == "mode=study" and not restored_home:
                    board.write(b'{"type":"command","mode":"home"}\n')
                    board.flush()
                    restored_home = True
            if (
                restored_home
                and any(frame.get("message") == "mode=home" for frame in acknowledgements)
                and telemetry
                and telemetry.get("mode") == "home"
                and (telemetry.get("health") or {}).get("dht") == "ok"
                and int((telemetry.get("health") or {}).get("uptimeMs") or 0) >= 2500
            ):
                break

    if hello is None:
        raise SystemExit("FAIL: no hello frame received after hardware reset")
    if hello.get("project") != PROJECT or hello.get("profileId") != PROFILE_ID:
        raise SystemExit(f"FAIL: unexpected identity: {compact(hello)}")
    pins = hello.get("pins") or {}
    if pins.get("flame") != 11 or pins.get("lamp") != 12:
        raise SystemExit(f"FAIL: unexpected GPIO contract: {pins}")
    if telemetry is None:
        raise SystemExit("FAIL: no telemetry frame received")
    required_sensors = {"light", "sound", "temperature", "humidity", "pir", "mq2", "water", "flame"}
    if not required_sensors.issubset(telemetry.get("sensors") or {}):
        raise SystemExit("FAIL: telemetry sensors are incomplete")
    if not any(frame.get("message") == "mode=study" for frame in acknowledgements):
        raise SystemExit(f"FAIL: no study ack: {acknowledgements}")
    if not any(frame.get("message") == "mode=home" for frame in acknowledgements):
        raise SystemExit(f"FAIL: no home restore ack: {acknowledgements}")

    print(f"hello OK: firmware={hello.get('firmware')} pins={pins}")
    print(f"telemetry OK: {compact(telemetry)}")
    print(f"ack OK: {[frame.get('message') for frame in acknowledgements]}")
    print(f"serial cleanliness: boot_lines={boot_lines} post_protocol_invalid_lines={post_protocol_invalid_lines}")


if __name__ == "__main__":
    main()
