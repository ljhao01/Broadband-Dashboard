/* view_fttr.js — FTTR 无线连接质量看板 */
(function (R) {
  "use strict";
  const view = {
    id: "fttr",
    title: "FTTR无线连接质量",
    async init() {
      await this.load();
    },
    async load() {
      const res = await fetch("/api/data/fttr").then((r) => r.json());
      const box = document.getElementById("v-fttr");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      const kpis = (res.kpis || []).map(R.kpiCard).join("");
      const areas = res.areas || [];
      const rows = areas
        .map(
          (a) =>
          `<tr class="border-b"><td class="py-1">${a.area}</td><td class="py-1 ${R.statusColor(
            a.status
          )} font-semibold">${a.score}</td><td class="py-1" style="color:var(--ink-3)">${a.issue || "-"}</td></tr>`
        )
        .join("");

      // 趋势数据
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
            "区域连接质量",
            res.status,
            `<table class="data-table"><thead><tr><th>区域</th><th>质量分</th><th>问题</th></tr></thead><tbody>${rows}</tbody></table>`,
            "",
            "location_on"
          )}
          <div class="card">
            <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">trending_up</span></span>质量趋势</div>
            <div id="trend-fttr" style="height:240px"></div>
          </div>
        </div>`;
      if (trendLabels.length) {
        R.renderTrend("trend-fttr", trendLabels, lineSeries);
      }
    },
  };
  R.registerView(view);
})(window.Reports);
