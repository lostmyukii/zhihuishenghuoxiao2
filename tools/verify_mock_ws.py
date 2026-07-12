#!/usr/bin/env python3
"""Exercise the running HK2 mock gateway through a real WebSocket connection."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import time
from typing import Any, Callable, Dict


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WsClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=3)
        self.sock.settimeout(3)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self._read_until(b"\r\n\r\n")
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if b"101 Switching Protocols" not in response or expected.encode() not in response:
            raise RuntimeError("websocket handshake failed")

    def _read_until(self, marker: bytes) -> bytes:
        data = b""
        while marker not in data:
            data += self.sock.recv(4096)
        return data

    def send_json(self, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(0x80 | len(data))
        else:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(data)))
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_json(self) -> Dict[str, Any]:
        first, second = self._recv_exact(2)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        if second & 0x80:
            mask = self._recv_exact(4)
        else:
            mask = None
        data = self._recv_exact(length)
        if mask:
            data = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        if (first & 0x0F) != 0x1:
            return {}
        return json.loads(data.decode())

    def _recv_exact(self, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("websocket closed")
            data += chunk
        return data

    def wait_for(self, predicate: Callable[[Dict[str, Any]], bool], timeout: float = 4) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame = self.recv_json()
            if predicate(frame):
                return frame
        raise AssertionError("expected frame not received")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18766)
    args = parser.parse_args()
    client = WsClient(args.host, args.port)

    hello = client.wait_for(lambda frame: frame.get("type") == "hello")
    assert hello["project"] == "smartlife-primary-hk2"
    initial = client.wait_for(lambda frame: frame.get("type") == "telemetry")
    assert initial["health"]["oled"] == "ready"

    client.send_json({"type": "voiceIntent", "intent": "startStudy"})
    assert client.wait_for(lambda frame: frame.get("type") == "ack")["message"] == "mode=study"

    client.send_json({"type": "mock", "sensors": {"sound": 82, "temperature": 31}})
    client.wait_for(lambda frame: frame.get("type") == "ack" and frame.get("message") == "mock=sensors")
    study = client.wait_for(lambda frame: frame.get("type") == "telemetry" and "noise" in frame.get("alerts", []))
    assert "temperature" in study["alerts"]

    client.send_json({"type": "voiceIntent", "intent": "setAway"})
    client.wait_for(lambda frame: frame.get("type") == "ack" and frame.get("message") == "mode=away")
    client.send_json({"type": "mock", "sensors": {"pir": True, "mq2": 70, "flame": True, "water": True}})
    client.wait_for(lambda frame: frame.get("type") == "ack" and frame.get("message") == "mock=sensors")
    safety = client.wait_for(lambda frame: frame.get("type") == "telemetry" and "intrusion" in frame.get("alerts", []))
    assert {"mq2", "flame", "water", "intrusion"}.issubset(set(safety["alerts"]))
    assert safety["actuators"]["buzzer"] is True

    client.send_json({"type": "command", "actuator": {"buzzer": False}})
    client.wait_for(lambda frame: frame.get("type") == "ack")
    still_safe = client.wait_for(lambda frame: frame.get("type") == "telemetry")
    assert still_safe["actuators"]["buzzer"] is True

    client.send_json({"type": "command", "set": {"buzzerEnabled": False}})
    client.wait_for(lambda frame: frame.get("type") == "ack")
    muted = client.wait_for(lambda frame: frame.get("type") == "telemetry")
    assert muted["actuators"]["buzzer"] is False
    assert muted["health"]["buzzer"] == "muted"

    print("mock websocket verification passed: hello, study, away, safety override, explicit mute")


if __name__ == "__main__":
    main()
