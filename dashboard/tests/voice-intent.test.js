#!/usr/bin/env node
const assert = require("assert/strict");
const { normalize, resolve, quickIntents } = require("../intent-core.js");

assert.equal(normalize(" 开启节能！ "), "开启节能");
assert.equal(quickIntents.length, 6);

const cases = [
  ["开始学习", "startStudy"],
  ["我回家了", "setHome"],
  ["我要出门", "setAway"],
  ["开启节能模式", "setEnergy"],
  ["家里安全吗", "querySafety"],
  ["查询温度", "queryComfort"],
  ["静音安全蜂鸣器", "muteBuzzer"],
  ["恢复安全蜂鸣器", "unmuteBuzzer"],
];
cases.forEach(([text, intent]) => {
  const result = resolve(text);
  assert.equal(result.ok, true);
  assert.equal(result.command.type, "voiceIntent");
  assert.equal(result.command.intent, intent);
});

assert.equal(resolve("打开燃气并持续加热").ok, false);
assert.equal(resolve(" ").ok, false);

console.log("voice intent tests passed");
