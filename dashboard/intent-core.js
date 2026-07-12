(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.HK2IntentCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  const rules = [
    { intent: "startStudy", label: "开始学习", patterns: ["开始学习", "学习模式", "我要学习"] },
    { intent: "setHome", label: "回到居家", patterns: ["回到居家", "居家模式", "我回家了"] },
    { intent: "setAway", label: "我要出门", patterns: ["我要出门", "离家模式", "家里没人"] },
    { intent: "setEnergy", label: "开启节能", patterns: ["开启节能", "节能模式", "省电模式"] },
    { intent: "querySafety", label: "家里安全吗", patterns: ["家里安全吗", "查询安全", "有没有危险"] },
    { intent: "queryComfort", label: "房间热不热", patterns: ["房间热不热", "查询温度", "温湿度"] },
    { intent: "muteBuzzer", label: "静音安全蜂鸣器", patterns: ["静音安全蜂鸣器", "关闭安全声音"] },
    { intent: "unmuteBuzzer", label: "恢复安全蜂鸣器", patterns: ["恢复安全蜂鸣器", "开启安全声音"] },
  ];

  function normalize(text) {
    return String(text || "").trim().replace(/[，。！？、,.!?\s]/g, "").toLowerCase();
  }

  function resolve(text) {
    const original = String(text || "").trim();
    const value = normalize(original);
    if (!value) return { ok: false, message: "请输入要测试的语音文字" };
    const rule = rules.find((item) => item.patterns.some((pattern) => value.includes(normalize(pattern))));
    if (!rule) return { ok: false, message: "未匹配到安全白名单意图", text: original };
    return {
      ok: true,
      intent: rule.intent,
      label: rule.label,
      text: original,
      command: { type: "voiceIntent", intent: rule.intent, text: original, source: "dashboard" },
    };
  }

  return { rules, quickIntents: rules.slice(0, 6), normalize, resolve };
});
