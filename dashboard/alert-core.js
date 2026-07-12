(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.HK2AlertCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  const ALARM_CODES = new Set(["mq2", "flame", "water", "intrusion"]);
  const REMINDER_CODES = new Set(["noise", "temperature"]);

  const meta = {
    mq2: { title: "烟雾／燃气风险", source: "MQ-2 · GPIO2", sensorKey: "mq2" },
    flame: { title: "火源信号异常", source: "火焰 DO · GPIO11 · HIGH 触发", sensorKey: "flame" },
    water: { title: "检测到漏水", source: "水滴 · GPIO8 · LOW 触发", sensorKey: "water" },
    intrusion: { title: "离家人体报警", source: "PIR · GPIO5", sensorKey: "pir" },
    noise: { title: "学习噪声提醒", source: "声音 · GPIO4", sensorKey: "sound" },
    temperature: { title: "学习温度提醒", source: "DHT11 · GPIO14", sensorKey: "temperature" },
  };

  function normalizeAlerts(alerts) {
    if (!Array.isArray(alerts)) return [];
    return [...new Set(alerts.map((item) => String(item || "").trim()).filter(Boolean))];
  }

  function thresholdReason(code, sensors, thresholds) {
    if (code === "mq2" && Number.isFinite(Number(sensors.mq2))) {
      return `当前 ${Number(sensors.mq2).toFixed(0)}%，安全阈值 ${Number(thresholds.mq2 ?? 70).toFixed(0)}%。`;
    }
    if (code === "noise" && Number.isFinite(Number(sensors.sound))) {
      return `当前 ${Number(sensors.sound).toFixed(0)}%，提醒阈值 ${Number(thresholds.sound ?? 70).toFixed(0)}%。`;
    }
    if (code === "temperature" && Number.isFinite(Number(sensors.temperature))) {
      return `当前 ${Number(sensors.temperature).toFixed(1)}°C，提醒阈值 ${Number(thresholds.temperature ?? 29).toFixed(1)}°C。`;
    }
    if (code === "flame") return "火焰模块 DO/SIG 出现高电平，请人工确认；演示不用明火。";
    if (code === "water") return "水滴模块已触发，请检查厨卫区域。";
    if (code === "intrusion") return "离家模式下，玄关检测到人体活动。";
    return "设备上报了需要处理的状态。";
  }

  function describeAlert(code, context = {}) {
    const normalized = String(code || "unknown");
    const item = meta[normalized] || {
      title: "设备异常提醒",
      source: "N16R8 实时数据",
      sensorKey: "",
    };
    return {
      code: normalized,
      title: item.title,
      source: item.source,
      sensorKey: item.sensorKey,
      severity: ALARM_CODES.has(normalized) ? "alarm" : REMINDER_CODES.has(normalized) ? "reminder" : "alarm",
      reason: thresholdReason(normalized, context.sensors || {}, context.thresholds || {}),
    };
  }

  function buildPresentation(alerts, context = {}) {
    if (!context.fresh) {
      return {
        state: "idle",
        title: "等待 N16R8 实时数据",
        summary: "连接开发板或本地 mock 后，这里才显示真实状态",
        items: [],
        sensorStates: {},
      };
    }

    const items = normalizeAlerts(alerts).map((code) => describeAlert(code, context));
    const alarms = items.filter((item) => item.severity === "alarm");
    const reminders = items.filter((item) => item.severity === "reminder");
    const sensorStates = Object.fromEntries(items.filter((item) => item.sensorKey).map((item) => [item.sensorKey, item.severity]));

    if (alarms.length) {
      return {
        state: "alarm",
        title: `检测到 ${alarms.length} 项安全报警`,
        summary: alarms.map((item) => item.title).join("、"),
        items,
        sensorStates,
      };
    }
    if (reminders.length) {
      return {
        state: "reminder",
        title: `检测到 ${reminders.length} 项学习提醒`,
        summary: reminders.map((item) => item.title).join("、"),
        items,
        sensorStates,
      };
    }
    return {
      state: "normal",
      title: "安心状态正常",
      summary: "烟雾、漏水、火焰与离家安防均无报警",
      items: [],
      sensorStates: {},
    };
  }

  return { ALARM_CODES, REMINDER_CODES, normalizeAlerts, describeAlert, buildPresentation };
});
