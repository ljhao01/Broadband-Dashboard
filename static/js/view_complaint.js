/* view_complaint.js — 重复投诉率看板
 * 顶部不再单独展示 KPI（重复投诉总量/占比已并入下方上传模块的「新洲区重点监控」卡片），
 * 本视图仅负责挂载上传分析模块（日历 + 智能总结 + 柱图 + 排名表）。
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

      // 仅渲染上传分析模块（含新洲重点监控、日历、智能总结、柱图、排名表）
      box.innerHTML = `<div id="upload-wrap"></div>`;

      if (window.FEATURES && window.FEATURES.showUpload && R.ComplaintUpload) {
        R.ComplaintUpload.mount(document.getElementById("upload-wrap"));
      }
    },
  };
  R.registerView(view);
})(window.Reports);
