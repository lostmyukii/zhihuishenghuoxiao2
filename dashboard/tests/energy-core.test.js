#!/usr/bin/env node
const assert = require("assert/strict");
const { describeEnergyReason, formatEnergyScore } = require("../energy-core.js");

assert.equal(describeEnergyReason("empty-room-light-off"), "房间无人，学习灯保持关闭");
assert.equal(describeEnergyReason("daylight-light-off"), "自然光充足，学习灯保持关闭");
assert.equal(describeEnergyReason("occupied-dark-light-on"), "有人且光线暗，允许学习灯亮起");
assert.equal(describeEnergyReason("safety-alert-active"), "安全告警优先，暂不评价普通节能动作");
assert.equal(formatEnergyScore(88.2), "88 分");
assert.equal(formatEnergyScore(null), "-- 分");
assert.equal(formatEnergyScore(101), "-- 分");

console.log("energy core tests passed");
