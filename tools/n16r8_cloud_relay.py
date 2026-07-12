#!/usr/bin/env python3
"""MQTT-backed WebSocket relay for the HK2 N16R8 SmartLife dashboard."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

from ws_json import JsonRelayServer, PROTOCOL_TOPIC_PREFIX, json_dumps, topic_for_frame

try:
    import paho.mqtt.client as mqtt  # type: ignore
except ImportError:  # pragma: no cover - checked when starting the service
    mqtt = None


PROJECT = "smartlife-primary-hk2"
PROFILE_ID = "smartlife-primary-safe-energy-home-v1"
BOARD_FRAME_TYPES = {"hello", "telemetry", "health", "event", "ack"}
COMMAND_TYPES = {"command", "config", "voiceIntent"}
ALLOWED_TYPES = BOARD_FRAME_TYPES | COMMAND_TYPES | {"ping"}
RETAINED_TYPES = {"hello", "telemetry", "health"}


def mqtt_connect_succeeded(reason_code: Any) -> bool:
    is_failure = getattr(reason_code, "is_failure", None)
    if isinstance(is_failure, bool):
        return not is_failure
    try:
        return int(reason_code) == 0
    except (TypeError, ValueError):
        return str(reason_code).strip().lower() == "success"


def normalize_frame(frame: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(frame, dict) or frame.get("type") not in ALLOWED_TYPES:
        return None
    if frame.get("project") not in {None, "", PROJECT}:
        return None
    if frame.get("profileId") not in {None, "", PROFILE_ID}:
        return None
    outgoing = dict(frame)
    outgoing["project"] = PROJECT
    outgoing["profileId"] = PROFILE_ID
    return outgoing


def mqtt_route_for_frame(
    frame: Any,
    topic_prefix: str = PROTOCOL_TOPIC_PREFIX,
) -> Optional[Tuple[str, str, bool]]:
    outgoing = normalize_frame(frame)
    if not outgoing or outgoing.get("type") == "ping":
        return None
    return (
        topic_for_frame(outgoing, topic_prefix),
        json_dumps(outgoing),
        outgoing.get("type") in RETAINED_TYPES,
    )


def browser_frame_from_mqtt(topic: str, raw_payload: Any, topic_prefix: str) -> Optional[Dict[str, Any]]:
    if not topic.startswith(f"{topic_prefix.rstrip('/')}/"):
        return None
    try:
        payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return None
    outgoing = normalize_frame(payload)
    if not outgoing:
        return None
    outgoing["mqttTopic"] = topic
    outgoing["relayedAt"] = int(time.time() * 1000)
    return outgoing


class MqttBridge:
    def __init__(self, args: argparse.Namespace, relay: JsonRelayServer, loop: asyncio.AbstractEventLoop) -> None:
        if mqtt is None:
            raise RuntimeError("paho-mqtt is required for the cloud relay")
        self.args = args
        self.relay = relay
        self.loop = loop
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.mqtt_client_id)
        if args.mqtt_username:
            self.client.username_pw_set(args.mqtt_username, args.mqtt_password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def status_payload(self) -> Dict[str, Any]:
        return {
            "type": "relayStatus",
            "project": PROJECT,
            "profileId": PROFILE_ID,
            "name": "smartlife-primary-hk2-relay",
            "mqtt": "online" if self.connected else "offline",
        }

    def _broadcast_status(self) -> None:
        asyncio.run_coroutine_threadsafe(self.relay.broadcast_json(self.status_payload()), self.loop)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = mqtt_connect_succeeded(reason_code)
        if self.connected:
            client.subscribe(f"{self.args.topic_prefix.rstrip('/')}/#")
        self._broadcast_status()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = False
        self._broadcast_status()

    def _on_message(self, client, userdata, message) -> None:
        payload = browser_frame_from_mqtt(
            message.topic,
            message.payload.decode("utf-8", errors="replace"),
            self.args.topic_prefix,
        )
        if not payload:
            return
        retain = payload.get("type") in RETAINED_TYPES
        asyncio.run_coroutine_threadsafe(self.relay.broadcast_json(payload, retain=retain), self.loop)

    def start(self) -> None:
        self.client.connect_async(self.args.mqtt_host, self.args.mqtt_port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic: str, message: str, retain: bool) -> bool:
        if not self.connected:
            return False
        info = self.client.publish(topic, message, qos=0, retain=retain)
        return info.rc == mqtt.MQTT_ERR_SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N16R8 SmartLife HK2 MQTT/WebSocket relay")
    parser.add_argument("--host", default=os.getenv("HK2_RELAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HK2_RELAY_PORT", "19366")))
    parser.add_argument("--mqtt-host", default=os.getenv("HK2_MQTT_HOST", "127.0.0.1"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("HK2_MQTT_PORT", "19383")))
    parser.add_argument("--mqtt-username", default=os.getenv("HK2_MQTT_USERNAME", ""))
    parser.add_argument("--mqtt-password", default=os.getenv("HK2_MQTT_PASSWORD", ""))
    parser.add_argument("--mqtt-client-id", default=os.getenv("HK2_MQTT_CLIENT_ID", "smartlife-primary-hk2-relay"))
    parser.add_argument("--topic-prefix", default=os.getenv("HK2_TOPIC_PREFIX", PROTOCOL_TOPIC_PREFIX))
    return parser


async def run(args: argparse.Namespace) -> None:
    relay = JsonRelayServer(args.host, args.port, name="smartlife-primary-hk2-relay", broadcast_incoming=False)
    await relay.start()
    bridge = MqttBridge(args, relay, asyncio.get_running_loop())
    bridge.start()
    print(f"relay listening on ws://{args.host}:{args.port}")
    print(f"mqtt connecting to {args.mqtt_host}:{args.mqtt_port} prefix={args.topic_prefix}")

    try:
        while True:
            frame = await relay.incoming.get()
            if frame.get("type") == "ping":
                await relay.broadcast_json(bridge.status_payload())
                continue
            route = mqtt_route_for_frame(frame, args.topic_prefix)
            if not route:
                continue
            topic, message, retain = route
            if not bridge.publish(topic, message, retain):
                fallback = normalize_frame(frame)
                if fallback:
                    fallback["relayFallback"] = True
                    await relay.broadcast_json(fallback, retain=retain)
    finally:
        bridge.stop()


def main() -> None:
    try:
        asyncio.run(run(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("relay stopped")


if __name__ == "__main__":
    main()
