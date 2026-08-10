/* view_terminal.js — 三类问题终端看板 */
(function (R) {
  "use strict";
  const view = {
    id: "terminal",
    title: "三类问题终端",
    async init() {
      await this.load();
    },
    async load() {
      const res = await fetch("/api/data/terminal").then((r) => r.json());
      const box = document.getElementById("v-terminal");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      const kpis = (res.kpis || []).map(R.kpiCard).join("");
      const dist = res.dist || [];
      const rows = dist
        .map(
          (d) =>
            `<tr class="border-b"><td class="py-1">${d.name}</td><td class="py-1 ${R.statusColor(
              d.status
            )}">${d.cnt}</td></tr>`
        )
        .join("");

      box.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">${kpis}</div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          ${R.section(
            "故障区域分布",
            res.status,
            `<table class="data-table"><thead><tr><th>区域</th><th>数量</th></tr></thead><tbody>${rows}</tbody></table>`,
            "",
            "map"
          )}
          <div class="card">
            <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">bar_chart</span></span>数量分布</div>
            <div id="bar-terminal" style="height:260px"></div>
          </div>
        </div>`;
      R.renderBar(
        "bar-terminal",
        dist.map((d) => d.name),
        dist.map((d) => d.cnt),
        { color: "#7c3aed" }
      );
    },
  };
  R.registerView(view);
})(window.Reports);
