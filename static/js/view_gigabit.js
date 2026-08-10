/* view_gigabit.js — 千兆质差小区看板 */
(function (R) {
  "use strict";
  const view = {
    id: "gigabit",
    title: "千兆质差小区",
    async init() {
      await this.load();
    },
    async load() {
      const res = await fetch("/api/data/gigabit").then((r) => r.json());
      const box = document.getElementById("v-gigabit");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      const kpis = (res.kpis || []).map(R.kpiCard).join("");
      const cells = res.cells || [];
      const rows = cells
        .map(
          (c) =>
            `<tr class="border-b"><td class="py-1">${c.cell}</td><td class="py-1">${c.latency}</td><td class="py-1">${c.jitter}</td><td class="py-1 ${R.statusColor(
              c.status
            )}">${c.low_speed_users}</td><td class="py-1" style="color:var(--ink-3)">${c.repair_status ||
              "-"}</td></tr>`
        )
        .join("");

      const trends = res.trend || {};
      const trendLabels = (trends.labels || []).slice(-6);
      const lineSeries = (trends.series || []).map((s) => ({
        name: s.name,
        data: (s.data || []).slice(-6),
      }));

      box.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">${kpis}</div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          ${R.section(
            "质差小区明细",
            res.status,
            `<table class="data-table"><thead><tr><th>小区</th><th>时延</th><th>抖动</th><th>低速用户</th><th>整治</th></tr></thead><tbody>${rows}</tbody></table>`,
            "",
            "apartment"
          )}
          <div class="card">
            <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">trending_up</span></span>整治进度趋势</div>
            <div id="trend-gigabit" style="height:240px"></div>
          </div>
        </div>`;
      if (trendLabels.length) {
        R.renderTrend("trend-gigabit", trendLabels, lineSeries);
      }
    },
  };
  R.registerView(view);
})(window.Reports);
