/* view_workorder.js — 装维工单看板 */
(function (R) {
  "use strict";
  const view = {
    id: "workorder",
    title: "装维工单",
    async init() {
      await this.load();
    },
    async load(refresh) {
      const url = "/api/data/workorder" + (refresh ? "?refresh=1" : "");
      const res = await fetch(url).then((r) => r.json());
      const box = document.getElementById("v-workorder");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      const kpis = (res.kpis || []).map(R.kpiCard).join("");
      const grids = res.grids || [];
      const gridRows = grids
        .map(
          (g) =>
            `<tr class="border-b"><td class="py-1">${g.grid}</td><td class="py-1 ${R.statusColor(
              g.status
            )}">${g.eff}%</td></tr>`
        )
        .join("");
      box.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">${kpis}</div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          ${R.section(
            "网格装维效能",
            res.status,
            `<table class="data-table"><thead><tr><th>网格</th><th>效能</th></tr></thead><tbody>${gridRows}</tbody></table>`,
            "",
            "grid_view"
          )}
          <div class="card">
            <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">bar_chart</span></span>效能对比</div>
            <div id="bar-workorder" style="height:260px"></div>
          </div>
        </div>`;
      R.renderBar(
        "bar-workorder",
        grids.map((g) => g.grid),
        grids.map((g) => g.eff),
        { color: "#2563eb" }
      );
    },
  };
  R.registerView(view);
})(window.Reports);
