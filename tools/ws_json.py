#!/usr/bin/env python3
"""Small dependency-free JSON WebSocket relay for the HK2 local gateway."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
from typing import Any, Dict, Optional, Set


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PROTOCOL_TOPIC_PREFIX = "smartlife/primary/hk2/n16r8"


def json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def topic_for_frame(frame: Dict[str, Any], prefix: str = PROTOCOL_TOPIC_PREFIX) -> str:
    frame_type = str(frame.get("type") or "event")
    suffix = frame_type if frame_type in {"hello", "telemetry", "health", "command", "config", "voiceIntent"} else "event"
    return f"{prefix.rstrip('/')}/{suffix}"


def is_protocol_frame(frame: Dict[str, Any]) -> bool:
    return frame.get("type") in {"hello", "telemetry", "ack", "command", "config", "voiceIntent", "ping"}


class WebSocketPeer:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    @classmethod
    async def accept(cls, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> "WebSocketPeer":
        request = await reader.readuntil(b"\r\n\r\n")
        headers = _parse_headers(request.decode("utf-8", errors="replace"))
        key = headers.get("sec-websocket-key")
        if not key:
            raise ConnectionError("missing Sec-WebSocket-Key")
        accept_key = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()
        writer.write((
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
        ).encode("ascii"))
        await writer.drain()
        return cls(reader, writer)

    async def recv_text(self) -> Optional[str]:
        byte_one, byte_two = await self.reader.readexactly(2)
        opcode = byte_one & 0x0F
        masked = bool(byte_two & 0x80)
        length = byte_two & 0x7F
        if length == 126:
            length = struct.unpack("!H", await self.reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
        mask = await self.reader.readexactly(4) if masked else b""
        payload = await self.reader.readexactly(length) if length else b""
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        if opcode == 0x8:
            return None
        if opcode == 0x9:
            await self.send_frame(payload, 0xA)
            return ""
        return payload.decode("utf-8", errors="replace") if opcode == 0x1 else ""

    async def send_text(self, text: str) -> None:
        await self.send_frame(text.encode("utf-8"), 0x1)

    async def send_frame(self, payload: bytes, opcode: int) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length <= 0xFFFF:
            header.extend([126])
            header.extend(struct.pack("!H", length))
        else:
            header.extend([127])
            header.extend(struct.pack("!Q", length))
        self.writer.write(bytes(header) + payload)
        await self.writer.drain()


class JsonRelayServer:
    def __init__(self, host: str, port: int, *, name: str) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.incoming: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.peers: Set[WebSocketPeer] = set()
        self.retained: Dict[str, str] = {}
        self.server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def broadcast_json(self, payload: Dict[str, Any], *, retain: bool = False) -> None:
        text = json_dumps(payload)
        if retain:
            self.retained[str(payload.get("type") or "event")] = text
        stale = []
        for peer in list(self.peers):
            try:
                await peer.send_text(text)
            except Exception:
                stale.append(peer)
        for peer in stale:
            self.peers.discard(peer)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer: Optional[WebSocketPeer] = None
        try:
            peer = await WebSocketPeer.accept(reader, writer)
            self.peers.add(peer)
            for text in self.retained.values():
                await peer.send_text(text)
            while True:
                text = await peer.recv_text()
                if text is None:
                    break
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {"type": "raw", "text": text}
                await self.incoming.put(payload)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            if peer is not None:
                self.peers.discard(peer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


def _parse_headers(request: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in request.split("\r\n")[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers
