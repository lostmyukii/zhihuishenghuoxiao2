(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.HK2SerialCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  const RESET_HOLD_MS = 120;
  const BOOT_WAIT_MS = 450;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function prepareCh340Port(port, wait = sleep) {
    if (!port || typeof port.setSignals !== "function") {
      throw new Error("当前浏览器不能设置 CH340 控制线");
    }

    await port.setSignals({ dataTerminalReady: false, requestToSend: true });
    await wait(RESET_HOLD_MS);
    await port.setSignals({ dataTerminalReady: false, requestToSend: false });
    await wait(BOOT_WAIT_MS);

    return { resetHoldMs: RESET_HOLD_MS, bootWaitMs: BOOT_WAIT_MS };
  }

  return { RESET_HOLD_MS, BOOT_WAIT_MS, prepareCh340Port };
});
