/* app.js — 弱光督办看板入口
 * 系统仅含弱光督办单一模块：无需 Tab 切换，打开即加载最新批次数据
 */
(function (R) {
  "use strict";

  // 全局图表实例登记表：视图/子窗口渲染时直接 push，先于任何渲染初始化
  window.echartsInstances = window.echartsInstances || [];

  const views = R.views || [];

  async function loadAll() {
    for (const v of views) {
      try {
        await v.load();
      } catch (e) {
        const box = document.getElementById("v-" + v.id);
        if (box) box.innerHTML = `<div class="text-red-500">加载出错：${e.message}</div>`;
      }
    }
  }

  async function init() {
    await loadAll();
    // 地址栏 #panel=key 恢复（刷新页面后仍停留在同一子窗口）
    if (R.Panel && R.Panel.openFromHash) R.Panel.openFromHash();
    window.addEventListener("resize", () => {
      (window.echartsInstances || []).forEach((c) => {
        try { c.resize(); } catch (e) {}
      });
    });

    // "刷新数据"：重新拉取最新批次（数据来自数据库，不产生新批次）
    const btn = document.getElementById("btnRefreshAll");
    if (btn) {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const origin = btn.innerHTML;
        btn.innerHTML = '<span class="material-symbols-rounded" style="font-size:16px">progress_activity</span>刷新中…';
        await loadAll();
        btn.disabled = false;
        btn.innerHTML = origin;
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window.Reports);
