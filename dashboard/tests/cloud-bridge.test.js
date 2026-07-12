#!/usr/bin/env node
const assert = require("assert/strict");
const cloud = require("../cloud-core.js");

assert.equal(
  cloud.defaultEndpoint(
    { protocol: "https:", hostname: "hongkongxiao2.ilelezhan.cn", host: "hongkongxiao2.ilelezhan.cn" },
    "",
  ),
  "wss://hongkongxiao2.ilelezhan.cn/smartlife-primary-hk2-ws",
);
assert.equal(cloud.defaultEndpoint({ protocol: "http:", hostname: "127.0.0.1", host: "127.0.0.1:19167" }, ""), "");
assert.equal(
  cloud.defaultEndpoint(
    { protocol: "http:", hostname: "127.0.0.1", host: "127.0.0.1:19167" },
    "?cloudWs=ws%3A%2F%2F127.0.0.1%3A19366",
  ),
  "ws://127.0.0.1:19366",
);
assert.equal(cloud.defaultEndpoint({ protocol: "https:", hostname: "example.test", host: "example.test" }, "?cloud=off"), "");

assert.equal(cloud.classifyPayload({ type: "telemetry" }), "board");
assert.equal(cloud.classifyPayload({ type: "command" }), "command");
assert.equal(cloud.classifyPayload({ type: "relayStatus" }), "status");
assert.equal(cloud.classifyPayload({ type: "demo" }), "unknown");

const decorated = cloud.decoratePayload(
  { type: "telemetry", sensors: {} },
  "client-1",
  "web-serial-gateway",
  123456,
);
assert.equal(decorated.project, "smartlife-primary-hk2");
assert.equal(decorated.profileId, "smartlife-primary-safe-energy-home-v1");
assert.equal(decorated.origin, "web-serial-gateway");
assert.equal(decorated.originClientId, "client-1");
assert.equal(decorated.originSentAt, 123456);
assert.equal(cloud.shouldIgnore(decorated, "client-1"), true);
assert.equal(cloud.shouldIgnore(decorated, "client-2"), false);
assert.equal(cloud.frameTimestamp({ originSentAt: 1000 }, 2000), 1000);
assert.equal(cloud.frameTimestamp({}, 2000), 2000);

assert.deepEqual(
  cloud.stripTransportMeta({
    type: "command",
    mode: "energy",
    project: "smartlife-primary-hk2",
    profileId: "smartlife-primary-safe-energy-home-v1",
    origin: "dashboard",
    originClientId: "client-1",
    originSentAt: 123456,
    mqttTopic: "smartlife/primary/hk2/n16r8/command",
    _internal: true,
  }),
  {
    type: "command",
    mode: "energy",
    project: "smartlife-primary-hk2",
    profileId: "smartlife-primary-safe-energy-home-v1",
  },
);

console.log("HK2 cloud bridge tests passed");
