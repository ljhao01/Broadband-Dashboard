/* view_complaint.js — 重复投诉率看板 */
(function (R) {
  "use strict";
  const view = {
    id: "complaint",
    title: "重复投诉率",
    async init() {
      await this.load();
    },
    async load() {
      const res = await fetch("/api/data/complaint").then((r) => r.json());
      const box = document.getElementById("v-complaint");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      // KPI：保留后端结构，但"重复投诉总量/占比"由上报报表真实值回填（见 updateRealKpis）
      const kpis = (res.kpis || []).map((k) => {
        if (k.label === "重复投诉总量") {
          return `<div id="kpi-repeat-total">${R.kpiCard(k)}</div>`;
        }
        if (k.label === "重复投诉占比") {
          return `<div id="kpi-repeat-ratio">${R.kpiCard(k)}</div>`;
        }
        return R.kpiCard(k);
      }).join("");
      const problems = res.problems || [];
      const probRows = problems
        .map(
          (p) =>
            `<tr class="border-b"><td class="py-1">${p.name}</td><td class="py-1 ${R.statusColor(
              p.status
            )}">${p.cnt}</td></tr>`
        )
        .join("");
      const areas = res.areas || [];
      const areaRows = areas
        .map(
          (a) =>
            `<tr class="border-b"><td class="py-1">${a.name}</td><td class="py-1 ${R.statusColor(
              a.status
            )}">${a.cnt}</td></tr>`
        )
        .join("");

      // 先挂载上传分析块（含武汉各区重复投诉率柱状图，置顶显示）
      if (window.FEATURES && window.FEATURES.showUpload && R.ComplaintUpload) {
        R.ComplaintUpload.mount(box);
      }

      // 主看板内容（TOP 问题 / 区域分布 / 趋势）放在柱状图下方
      box.insertAdjacentHTML(
        "beforeend",
        `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">${kpis}</div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          ${R.section(
            "重复投诉 TOP 问题",
            res.status,
            `<table class="data-table"><thead><tr><th>问题</th><th>数量</th></tr></thead><tbody>${probRows}</tbody></table>`,
            "",
            "priority_high"
          )}
          ${R.section(
            "投诉区域分布",
            res.status,
            `<table class="data-table"><thead><tr><th>区域</th><th>数量</th></tr></thead><tbody>${areaRows}</tbody></table>`,
            "",
            "place"
          )}
          <div class="card">
            <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">trending_up</span></span>区域投诉趋势</div>
            <div id="trend-complaint" style="height:240px"></div>
          </div>
        </div>`
      );

      const trends = res.trend || {};
      const trendLabels = (trends.labels || []).slice(-6);
      if (trendLabels.length) {
        const lineSeries = (trends.series || []).map((s) => ({
          name: s.name,
          data: (s.data || []).slice(-6),
        }));
        R.renderTrend("trend-complaint", trendLabels, lineSeries);
      }

      // 监听月份切换，用上报报表真实值回填 KPI
      window.addEventListener("complaint:month", (e) => view.updateRealKpis(e.detail.latest));
    },

    // 用上报报表的城市汇总真实值，覆盖"重复投诉总量/占比"两个 KPI
    updateRealKpis(latest) {
      const t = document.getElementById("kpi-repeat-total");
      const r = document.getElementById("kpi-repeat-ratio");
      if (t) {
        const val = latest && latest.city_users != null ? latest.city_users : "-";
        t.innerHTML = R.kpiCard({
          label: "重复投诉总量",
          value: val,
          unit: "单",
          status: val === "-" ? "green" : "red",
          detail: latest ? `${latest.city_orders != null ? latest.city_orders : "-"} 件工单中重复` : "",
        });
      }
      if (r) {
        const val = latest && latest.city_rate != null ? latest.city_rate : "-";
        const status = val === "-" ? "green" : val >= 2 ? "red" : val >= 0.8 ? "yellow" : "green";
        r.innerHTML = R.kpiCard({
          label: "重复投诉占比",
          value: val,
          unit: "%",
          status,
          detail: latest ? `武汉整体重复投诉率` : "",
        });
      }
    },
  };
  R.registerView(view);
})(window.Reports);
