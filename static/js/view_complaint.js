/* view_complaint.js — 重复投诉率看板
 * 武汉整体 KPI（重复投诉 / 重复投诉占比）置顶，上传分析模块随其后
 */
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

      // 武汉整体核心 KPI：重复投诉总量 / 重复投诉占比 置顶
      const kpis = (res.kpis || []).map((k) => {
        if (k.label === "重复投诉总量") {
          return `<div id="kpi-repeat-total">${R.kpiCard(k)}</div>`;
        }
        if (k.label === "重复投诉占比") {
          return `<div id="kpi-repeat-ratio">${R.kpiCard(k)}</div>`;
        }
        return R.kpiCard(k);
      }).join("");

      // 主看板 KPI 放最前
      box.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">${kpis}</div>
        <div id="upload-wrap"></div>`;

      // 上传分析模块（区县动态选择 + 每日趋势）随后
      if (window.FEATURES && window.FEATURES.showUpload && R.ComplaintUpload) {
        R.ComplaintUpload.mount(document.getElementById("upload-wrap"));
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
