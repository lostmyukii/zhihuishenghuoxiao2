#!/usr/bin/env node
const assert = require("assert/strict");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "style.css"), "utf8");
const serialCore = fs.readFileSync(path.join(root, "serial-core.js"), "utf8");
const serviceWorker = fs.readFileSync(path.join(root, "sw.js"), "utf8");

["开发板离线", "USB 未连接", "WSS 未配置", "MQTT 未配置", "安心状态带", "8 路真实传感状态"].forEach((text) => assert.match(html, new RegExp(text)));
["light", "temperature", "humidity", "sound", "pir", "mq2", "water", "flame"].forEach((key) => assert.match(html, new RegExp(`data-sensor="${key}"`)));
["home", "study", "away", "energy"].forEach((mode) => assert.match(html, new RegExp(`data-mode="${mode}"`)));
assert.match(html, /GPIO12 \/ D12/);
assert.match(html, /GPIO11/);
assert.doesNotMatch(html + app, /风扇|舵机|RGB|GPIO48|8 键/);
assert.match(app, /FRESH_MS = 3500/);
assert.match(app, /HK2SerialCore\.prepareCh340Port/);
assert.match(serialCore, /dataTerminalReady: false/);
assert.match(serialCore, /requestToSend: true/);
assert.match(serialCore, /requestToSend: false/);
assert.match(html, /serial-core\.js\?v=20260712-polarity/);
assert.match(serviceWorker, /hk2-dashboard-v3-polarity/);
assert.match(app, /type: "command", actuator/);
assert.match(app, /hello/);
assert.match(app, /telemetry/);
assert.match(app, /ack/);
assert.match(css, /@media \(max-width: 390px\)/);
assert.match(css, /prefers-reduced-motion/);

console.log("dashboard contract tests passed");
