#!/usr/bin/env node
const assert = require("assert/strict");
const { RESET_HOLD_MS, BOOT_WAIT_MS, prepareCh340Port } = require("../serial-core.js");

const signals = [];
const waits = [];
const fakePort = {
  async setSignals(value) { signals.push(value); },
};

(async () => {
  const result = await prepareCh340Port(fakePort, async (ms) => waits.push(ms));
  assert.deepEqual(signals, [
    { dataTerminalReady: false, requestToSend: true },
    { dataTerminalReady: false, requestToSend: false },
  ]);
  assert.deepEqual(waits, [RESET_HOLD_MS, BOOT_WAIT_MS]);
  assert.deepEqual(result, { resetHoldMs: 120, bootWaitMs: 450 });
  await assert.rejects(() => prepareCh340Port({}), /不能设置 CH340 控制线/);
  console.log("serial core tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
