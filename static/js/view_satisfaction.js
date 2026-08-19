/* view_satisfaction.js — 用户满意度看板 */
(function (R) {
  "use strict";
  const view = {
    id: "satisfaction",
    title: "用户满意度",
    async init() {
      await this.load();
    },
    async load(refresh) {
      const url = "/api/data/satisfaction" + (refresh ? "?refresh=1" : "");
      const res = await fetch(url).then((r) => r.json());
      const box = document.getElementById("v-satisfaction");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      const kpis = (res.kpis || []).map(R.kpiCard).join("");
      const cats = res.cats || [];
      const catRows = cats
        .map(
          (c) =>
            `<tr class="border-b"><td class="py-1">${c.category}</td><td class="py-1 ${R.statusColor(
              c.status
            )}">${c.cnt}</td></tr>`
        )
        .join("");
      const teams = res.teams || [];
      const teamRows = teams
        .map(
          (t) =>
            `<tr class="border-b"><td class="py-1">${t.team}</td><td class="py-1 ${R.statusColor(
              t.status
            )}">${t.score}</td></tr>`
        )
        .join("");

      box.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">${kpis}</div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          ${R.section(
            "不满意分类",
            res.status,
            `<table class="data-table"><thead><tr><th>分类</th><th>数量</th></tr></thead><tbody>${catRows}</tbody></table>`,
            "",
            "category"
          )}
          ${R.section(
            "班组满意度",
            res.status,
            `<table class="data-table"><thead><tr><th>班组</th><th>得分</th></tr></thead><tbody>${teamRows}</tbody></table>`,
            "",
            "groups"
          )}
        </div>`;
    },
  };
  R.registerView(view);
})(window.Reports);
