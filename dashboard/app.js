(() => {
  "use strict";

  const EXPECTED_PROJECT = "smartlife-primary-hk2";
  const EXPECTED_PROFILE = "smartlife-primary-safe-energy-home-v1";
  const FRESH_MS = 3500;
  const CLOUD_RECONNECT_MS = 1800;
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  const state = {
    serialPort: null,
    serialReader: null,
    serialWriter: null,
    serialReading: false,
    ws: null,
    cloudSocket: null,
    cloudReconnectTimer: null,
    mqttOnline: false,
    clientId: "",
    lastFrameAt: 0,
    lastTelemetryAt: 0,
    frameCount: 0,
    mode: null,
    sensors: {},
    actuators: {},
    alerts: [],
    thresholds: { light: 35, temperature: 29, sound: 70, mq2: 70 },
    energy: {},
    health: {},
    display: {},
  };

  const cloudApi = window.HK2CloudCore;
  const cloudEndpoint = cloudApi?.defaultEndpoint(window.location, window.location.search) || "";
  state.clientId = cloudApi?.clientId(() => window.crypto?.randomUUID?.()) || `hk2-${Date.now()}`;

  function timeText(date = new Date()) {
    return date.toLocaleTimeString("zh-CN", { hour12: false });
  }

  function log(message, tone = "info") {
    const list = $("#event-log");
    const item = document.createElement("li");
    item.dataset.tone = tone;
    const time = document.createElement("time");
    time.textContent = timeText();
    const text = document.createElement("span");
    text.textContent = message;
    item.append(time, text);
    list.prepend(item);
    while (list.children.length > 40) list.lastElementChild.remove();
  }

  function setChip(selector, text, status) {
    const chip = $(selector);
    chip.dataset.state = status;
    chip.innerHTML = `<i></i>${text}`;
  }

  function isBoardFresh() {
    return state.lastFrameAt > 0 && Date.now() - state.lastFrameAt < FRESH_MS;
  }

  function isTelemetryFresh() {
    return state.lastTelemetryAt > 0 && Date.now() - state.lastTelemetryAt < FRESH_MS;
  }

  function cloudOpen() {
    return Boolean(state.cloudSocket && state.cloudSocket.readyState === WebSocket.OPEN);
  }

  function formatSensor(key, value) {
    if (value === null || value === undefined || value === "" || (typeof value === "number" && !Number.isFinite(value))) return "--";
    if (["pir", "water", "flame"].includes(key)) return value ? "触发" : "正常";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    return key === "temperature" ? numeric.toFixed(1) : Math.round(numeric).toString();
  }

  function updateMeter(key, value) {
    const meter = $(`#meter-${key}`);
    if (!meter) return;
    let percent = Number(value);
    if (key === "temperature") percent = ((percent - 10) / 30) * 100;
    meter.style.width = Number.isFinite(percent) ? `${Math.max(0, Math.min(100, percent))}%` : "0%";
  }

  function updateSensorCards(sensorStates = {}) {
    ["light", "temperature", "humidity", "sound", "pir", "mq2", "water", "flame"].forEach((key) => {
      const value = state.sensors[key];
      $(`#sensor-${key}`).textContent = formatSensor(key, value);
      updateMeter(key, value);
      const card = document.querySelector(`[data-sensor="${key}"]`);
      card.dataset.state = sensorStates[key] || "normal";
      const dot = $(`#dot-${key}`);
      if (dot) dot.classList.toggle("active", Boolean(value));
    });
  }

  function updateMode() {
    const names = { home: "居家", study: "学习", away: "离家", energy: "节能" };
    $("#current-mode").textContent = names[state.mode] || "等待数据";
    $$(".mode-button").forEach((button) => button.classList.toggle("active", button.dataset.mode === state.mode));
  }

  function updateActuators() {
    $$('[data-actuator="lamp"]').forEach((button) => button.classList.toggle("active", String(Boolean(state.actuators.lamp)) === button.dataset.value));
    $$('[data-actuator="buzzer"]').forEach((button) => button.classList.toggle("active", String(Boolean(state.actuators.buzzer)) === button.dataset.value));
  }

  function updateThresholds() {
    ["light", "temperature", "sound", "mq2"].forEach((key) => {
      const input = $(`#threshold-${key}`);
      if (document.activeElement !== input && state.thresholds[key] !== undefined) input.value = state.thresholds[key];
    });
  }

  function updateSafety() {
    const presentation = HK2AlertCore.buildPresentation(state.alerts, {
      fresh: isTelemetryFresh(),
      sensors: state.sensors,
      thresholds: state.thresholds,
      actuators: state.actuators,
    });
    const ribbon = $("#safety-ribbon");
    ribbon.dataset.state = presentation.state;
    $("#safety-title").textContent = presentation.title;
    $("#safety-summary").textContent = presentation.items.length
      ? presentation.items.map((item) => `${item.title}：${item.reason}`).join(" ")
      : presentation.summary;
    $("#alert-count").textContent = isTelemetryFresh() ? String(presentation.items.length) : "--";
    updateSensorCards(presentation.sensorStates);
  }

  function updateEnergy() {
    $("#energy-score").textContent = HK2EnergyCore.formatEnergyScore(isTelemetryFresh() ? state.energy.score : null);
    $("#energy-reason").textContent = HK2EnergyCore.describeEnergyReason(isTelemetryFresh() ? state.energy.reason : null);
  }

  function updateOled() {
    const lines = Array.isArray(state.display.lines) ? state.display.lines : [];
    $("#oled-screen").textContent = isTelemetryFresh() && lines.length ? lines.join("\n") : "HK2 SAFE HOME\nWAITING DATA...";
    $("#oled-health").textContent = isTelemetryFresh() ? (state.health.oled === "ready" ? "OLED 已就绪" : "OLED 未检测") : "等待";
  }

  function render() {
    const boardFresh = isBoardFresh();
    setChip("#board-status", boardFresh ? "开发板在线" : "开发板离线", boardFresh ? "online" : "offline");
    setChip("#usb-status", state.serialPort ? "USB 已连接" : "USB 未连接", state.serialPort ? "online" : "offline");
    setChip("#mock-status", state.ws?.readyState === WebSocket.OPEN ? "Mock 已连接" : "Mock 未连接", state.ws?.readyState === WebSocket.OPEN ? "online" : "offline");
    setChip("#ws-status", cloudOpen() ? "WSS 在线" : cloudEndpoint ? "WSS 重连中" : "WSS 本地关闭", cloudOpen() ? "online" : "offline");
    setChip("#mqtt-status", state.mqttOnline ? "MQTT 在线" : cloudOpen() ? "MQTT 离线" : "MQTT 等待", state.mqttOnline ? "online" : "offline");
    $("#last-update").textContent = boardFresh ? `${timeText(new Date(state.lastFrameAt))} 更新` : "等待第一帧";
    $("#frame-count").textContent = String(state.frameCount);
    updateMode();
    updateSafety();
    updateEnergy();
    updateActuators();
    updateThresholds();
    updateOled();
  }

  function acceptIdentity(frame) {
    if (frame.project && frame.project !== EXPECTED_PROJECT) {
      log(`拒绝其他项目帧：${frame.project}`, "error");
      return false;
    }
    if (frame.profileId && frame.profileId !== EXPECTED_PROFILE) {
      log(`拒绝其他 profile：${frame.profileId}`, "error");
      return false;
    }
    return true;
  }

  function handleFrame(frame, source = "device") {
    if (!frame || typeof frame !== "object") return;
    if (!acceptIdentity(frame)) return;
    const frameAt = source === "cloud" && cloudApi ? cloudApi.frameTimestamp(frame) : Date.now();
    if (frame.type === "hello") {
      state.lastFrameAt = frameAt;
      log(`hello · ${frame.deviceName || frame.board || "N16R8"} · 固件 ${frame.firmware || "未知"}`);
    } else if (frame.type === "telemetry") {
      state.lastFrameAt = frameAt;
      state.lastTelemetryAt = state.lastFrameAt;
      state.frameCount += 1;
      state.mode = frame.mode || state.mode;
      state.sensors = { ...state.sensors, ...(frame.sensors || {}) };
      state.actuators = { ...state.actuators, ...(frame.actuators || {}) };
      state.alerts = Array.isArray(frame.alerts) ? frame.alerts : [];
      state.thresholds = { ...state.thresholds, ...(frame.thresholds || {}) };
      state.energy = frame.energy || {};
      state.health = frame.health || {};
      state.display = frame.display || {};
    } else if (frame.type === "ack") {
      log(`ack · ${frame.ok ? "成功" : "失败"} · ${frame.message || "无说明"}`, frame.ok ? "success" : "error");
      $("#voice-result").textContent = frame.message || "命令已响应";
    } else if (frame.type === "event") {
      log(`event · ${frame.message || frame.code || JSON.stringify(frame)}`);
    } else {
      log(`${source} · 收到 ${frame.type || "unknown"} 帧`);
    }
    render();
  }

  function parseLine(line, source) {
    const value = String(line || "").trim();
    if (!value) return;
    try {
      const frame = JSON.parse(value);
      handleFrame(frame, source);
      if (source === "serial") sendBoardFrameToCloud(frame);
    } catch (error) {
      log(`忽略非 JSON 数据：${value.slice(0, 70)}`, "error");
    }
  }

  async function readSerialLoop() {
    const decoder = new TextDecoder();
    let buffer = "";
    state.serialReading = true;
    try {
      while (state.serialPort?.readable && state.serialReading) {
        state.serialReader = state.serialPort.readable.getReader();
        try {
          while (state.serialReading) {
            const { value, done } = await state.serialReader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split(/\r?\n/);
            buffer = lines.pop() || "";
            lines.forEach((line) => parseLine(line, "serial"));
          }
        } finally {
          state.serialReader.releaseLock();
          state.serialReader = null;
        }
      }
    } catch (error) {
      if (state.serialReading) log(`串口读取中断：${error.message}`, "error");
    }
    if (state.serialReading) await disconnectSerial();
  }

  async function connectSerial() {
    if (!("serial" in navigator)) {
      $("#connection-help").textContent = "当前浏览器不支持 Web Serial，请改用 Chrome 或 Edge。";
      log("浏览器不支持 Web Serial", "error");
      return;
    }
    let port = null;
    try {
      await disconnectMock();
      port = await navigator.serial.requestPort();
      await port.open({ baudRate: 115200 });
      $("#connection-help").textContent = "正在释放 CH340 控制线并启动 N16R8…";
      await HK2SerialCore.prepareCh340Port(port);
      state.serialPort = port;
      state.serialWriter = port.writable.getWriter();
      state.lastFrameAt = 0;
      state.lastTelemetryAt = 0;
      state.frameCount = 0;
      $("#connection-help").textContent = "CH340 已启动，正在等待真实 hello / telemetry。";
      log("USB 串口已打开并释放 RTS/DTR，等待 hello / telemetry");
      render();
      readSerialLoop();
      setTimeout(() => {
        if (state.serialPort === port && !isBoardFresh()) {
          $("#connection-help").textContent = "已连接串口但 3.5 秒没有数据：请点击断开后重新连接，不要同时打开串口监视器。";
          log("串口已连接，但没有收到 hello / telemetry", "error");
        }
      }, FRESH_MS);
    } catch (error) {
      if (port && port !== state.serialPort) {
        try { await port.close(); } catch (_) { /* best effort */ }
      }
      log(`串口连接失败：${error.message}`, "error");
      $("#connection-help").textContent = `串口连接失败：${error.message}`;
    }
  }

  async function disconnectSerial() {
    state.serialReading = false;
    if (state.serialReader) {
      try { await state.serialReader.cancel(); } catch (_) { /* already closed */ }
    }
    if (state.serialWriter) {
      try { state.serialWriter.releaseLock(); } catch (_) { /* already released */ }
      state.serialWriter = null;
    }
    if (state.serialPort) {
      try { await state.serialPort.close(); } catch (_) { /* port may be gone */ }
      state.serialPort = null;
      log("USB 串口已断开");
    }
    render();
  }

  function mockUrl() {
    return new URLSearchParams(location.search).get("ws") || "ws://127.0.0.1:18766";
  }

  async function connectMock() {
    await disconnectSerial();
    await disconnectMock();
    try {
      const ws = new WebSocket(mockUrl());
      state.ws = ws;
      ws.addEventListener("open", () => { log(`本地 Mock 已连接：${mockUrl()}`); render(); });
      ws.addEventListener("message", (event) => parseLine(event.data, "mock"));
      ws.addEventListener("close", () => { if (state.ws === ws) state.ws = null; log("本地 Mock 已断开"); render(); });
      ws.addEventListener("error", () => log("Mock 连接失败，请先启动本地网关", "error"));
    } catch (error) {
      log(`Mock 连接失败：${error.message}`, "error");
    }
  }

  async function disconnectMock() {
    if (state.ws) {
      const ws = state.ws;
      state.ws = null;
      try { ws.close(); } catch (_) { /* already closed */ }
    }
    render();
  }

  function sendCloudPayload(payload, origin = "dashboard") {
    if (!cloudOpen() || !cloudApi) return false;
    try {
      state.cloudSocket.send(JSON.stringify(cloudApi.decoratePayload(payload, state.clientId, origin)));
      return true;
    } catch (error) {
      log(`云端发送失败：${error.message}`, "error");
      return false;
    }
  }

  function sendBoardFrameToCloud(frame) {
    if (!cloudApi || cloudApi.classifyPayload(frame) !== "board") return false;
    return sendCloudPayload(frame, "web-serial-gateway");
  }

  async function writeSerialPayload(payload) {
    if (!state.serialWriter) return false;
    const serialPayload = cloudApi ? cloudApi.stripTransportMeta(payload) : payload;
    await state.serialWriter.write(new TextEncoder().encode(`${JSON.stringify(serialPayload)}\n`));
    return true;
  }

  function scheduleCloudReconnect() {
    if (!cloudEndpoint || state.cloudReconnectTimer) return;
    state.cloudReconnectTimer = window.setTimeout(() => {
      state.cloudReconnectTimer = null;
      connectCloud();
    }, CLOUD_RECONNECT_MS);
  }

  function handleCloudPayload(payload) {
    if (!cloudApi || cloudApi.shouldIgnore(payload, state.clientId)) return;
    const kind = cloudApi.classifyPayload(payload);
    if (kind === "board") {
      handleFrame(payload, "cloud");
      return;
    }
    if (kind === "command" && state.serialWriter) {
      writeSerialPayload(payload)
        .then((written) => { if (written) log("云端命令已写入 USB，等待真实 ack"); })
        .catch((error) => log(`云端命令写入失败：${error.message}`, "error"));
      return;
    }
    if (kind === "status") {
      state.mqttOnline = payload.mqtt === "online";
      render();
    }
  }

  function connectCloud() {
    if (!cloudEndpoint || !cloudApi) return;
    if (state.cloudSocket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(state.cloudSocket.readyState)) return;
    let socket;
    try {
      socket = new WebSocket(cloudEndpoint);
    } catch (error) {
      log(`云端 WSS 连接失败：${error.message}`, "error");
      scheduleCloudReconnect();
      return;
    }
    state.cloudSocket = socket;
    socket.addEventListener("open", () => {
      sendCloudPayload({ type: "ping" });
      log("云端 WSS 已连接");
      render();
    });
    socket.addEventListener("message", (event) => {
      try { handleCloudPayload(JSON.parse(event.data)); }
      catch (_) { log("忽略非 JSON 云端数据", "error"); }
    });
    socket.addEventListener("close", () => {
      if (state.cloudSocket === socket) state.cloudSocket = null;
      state.mqttOnline = false;
      log("云端 WSS 已断开，正在重连", "error");
      render();
      scheduleCloudReconnect();
    });
    socket.addEventListener("error", () => {
      state.mqttOnline = false;
      render();
    });
  }

  async function sendCommand(command) {
    try {
      const deliveredToUsb = await writeSerialPayload(command);
      if (deliveredToUsb) {
        sendCloudPayload({ ...command, usbWritten: true }, "web-serial-gateway");
        log(`发送 USB 命令：${JSON.stringify(command)}`);
        return true;
      }
      if (state.ws?.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(command));
        log(`发送 Mock 命令：${JSON.stringify(command)}`);
        return true;
      }
      if (sendCloudPayload(command, "dashboard")) {
        log(`发送云端命令：${JSON.stringify(command)}，等待 USB 网关与真实 ack`);
        return true;
      }
      log("命令未发送：请先连接串口、本地 Mock 或云端", "error");
      return false;
    } catch (error) {
      log(`命令发送失败：${error.message}`, "error");
      return false;
    }
  }

  async function executeVoice(text) {
    const result = HK2IntentCore.resolve(text);
    $("#voice-result").textContent = result.ok ? `${result.label} · 等待设备 ack` : result.message;
    if (result.ok) await sendCommand(result.command);
  }

  function bindEvents() {
    $("#connect-serial").addEventListener("click", connectSerial);
    $("#connect-mock").addEventListener("click", connectMock);
    $("#disconnect-device").addEventListener("click", async () => { await disconnectSerial(); await disconnectMock(); });
    $$(".mode-button").forEach((button) => button.addEventListener("click", () => sendCommand({ type: "command", mode: button.dataset.mode })));
    $$('[data-actuator]').forEach((button) => button.addEventListener("click", () => sendCommand({ type: "command", actuator: { [button.dataset.actuator]: button.dataset.value === "true" } })));
    $("#save-thresholds").addEventListener("click", async () => {
      const fields = { lightThreshold: "light", temperatureThreshold: "temperature", soundThreshold: "sound", mq2Threshold: "mq2" };
      for (const [wireKey, inputKey] of Object.entries(fields)) {
        await sendCommand({ type: "command", set: { [wireKey]: Number($(`#threshold-${inputKey}`).value) } });
      }
    });
    $("#voice-form").addEventListener("submit", (event) => { event.preventDefault(); executeVoice($("#voice-input").value); });
    $("#mute-buzzer").addEventListener("click", () => sendCommand({ type: "command", set: { buzzerEnabled: false } }));
    $("#unmute-buzzer").addEventListener("click", () => sendCommand({ type: "command", set: { buzzerEnabled: true } }));
    $("#clear-log").addEventListener("click", () => { $("#event-log").innerHTML = ""; });

    const quick = $("#quick-intents");
    HK2IntentCore.quickIntents.forEach((intent) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = intent.label;
      button.addEventListener("click", () => { $("#voice-input").value = intent.label; executeVoice(intent.label); });
      quick.append(button);
    });

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.lang = "zh-CN";
      recognition.interimResults = false;
      recognition.addEventListener("result", (event) => {
        const text = event.results[0][0].transcript;
        $("#voice-input").value = text;
        executeVoice(text);
      });
      recognition.addEventListener("error", (event) => { $("#voice-result").textContent = `语音识别失败：${event.error}，请使用文字测试`; });
      $("#start-speech").addEventListener("click", () => recognition.start());
      setChip("#voice-status", "语音／文本可用", "ready");
    } else {
      $("#start-speech").disabled = true;
    }
  }

  bindEvents();
  render();
  connectCloud();
  setInterval(render, 1000);
  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) navigator.serviceWorker.register("./sw.js").catch(() => {});
})();
