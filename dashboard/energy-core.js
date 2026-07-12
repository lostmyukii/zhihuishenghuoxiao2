(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.HK2EnergyCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  const labels = {
    "safety-alert-active": "安全告警优先，暂不评价普通节能动作",
    "empty-room-light-off": "房间无人，学习灯保持关闭",
    "daylight-light-off": "自然光充足，学习灯保持关闭",
    "occupied-dark-light-on": "有人且光线暗，允许学习灯亮起",
    "study-mode-comfort": "学习模式按需照明并监测舒适度",
    "away-mode-guarding": "离家模式关闭学习灯并守护玄关",
    "home-mode-active": "居家模式按光照与人体状态控制学习灯",
  };

  function describeEnergyReason(reason) {
    const key = String(reason || "").trim();
    return labels[key] || (key ? "N16R8 正在执行当前模式规则" : "等待实时节能原因");
  }

  function formatEnergyScore(score) {
    if (score === null || score === undefined || score === "") return "-- 分";
    const numeric = Number(score);
    return Number.isFinite(numeric) && numeric >= 0 && numeric <= 100 ? `${Math.round(numeric)} 分` : "-- 分";
  }

  return { describeEnergyReason, formatEnergyScore };
});
