#!/usr/bin/env node
const assert = require("assert/strict");
const { normalizeAlerts, describeAlert, buildPresentation } = require("../alert-core.js");

assert.deepEqual(normalizeAlerts(["mq2", " mq2 ", "flame", ""]), ["mq2", "flame"]);
assert.equal(describeAlert("flame").source, "火焰 DO · GPIO11 · HIGH 触发");
assert.equal(describeAlert("water").source, "水滴 · GPIO8 · LOW 触发");
assert.equal(describeAlert("intrusion").source, "PIR · GPIO5");
assert.match(describeAlert("mq2", { sensors: { mq2: 62 }, thresholds: { mq2: 55 } }).reason, /62%/);

const alarm = buildPresentation(["mq2", "flame"], { fresh: true });
assert.equal(alarm.state, "alarm");
assert.equal(alarm.items.length, 2);
assert.equal(alarm.title, "检测到 2 项安全报警");

const reminder = buildPresentation(["noise"], { fresh: true });
assert.equal(reminder.state, "reminder");
assert.equal(reminder.sensorStates.sound, "reminder");

const normal = buildPresentation([], { fresh: true });
assert.equal(normal.state, "normal");

const offline = buildPresentation(["mq2"], { fresh: false });
assert.equal(offline.state, "idle");
assert.equal(offline.items.length, 0);

console.log("alert core tests passed");
