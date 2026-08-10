/* app.js — 入口：注册看板、Tab 切换、定时刷新、注入全局配置 */
(function (R) {
  "use strict";

  // 全局配置由后端注入（见 templates/dashboard.html 中的 <script> 设置）
  // 注意：看板不做自动定时刷新（避免页面闪烁），仅手动切换 Tab 时加载对应数据
  const FEATURES = window.FEATURES || {};
  const views = R.views || [];

  // 各看板 Tab 对应 Material Symbols 图标
  const TAB_ICONS = {
    workorder: "build",
    fttr: "wifi",
    gigabit: "speed",
    complaint: "repeat",
    satisfaction: "sentiment_satisfied",
    terminal: "router",
  };

  function buildTabs() {
    const nav = document.getElementById("tabs");
    nav.innerHTML = views
      .map(
        (v, i) =>
          `<button data-tab="${v.id}" class="tab-btn ${i === 0 ? "active" : ""}">
             <span class="material-symbols-rounded">${TAB_ICONS[v.id] || "dashboard"}</span>
             ${v.title}
           </button>`
      )
      .join("");
    nav.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-tab]");
      if (!btn) return;
      switchTab(btn.dataset.tab);
    });
  }

  function switchTab(id) {
    document.querySelectorAll("#tabs [data-tab]").forEach((b) => {
      b.className = `tab-btn ${b.dataset.tab === id ? "active" : ""}`;
    });
    views.forEach((v) => {
      document.getElementById("v-" + v.id).style.display = v.id === id ? "block" : "none";
    });
    // 显示目标 Tab 后，图表容器尺寸才生效，需 resize 恢复（在隐藏态 init 的图表现为空白）
    setTimeout(() => {
      (window.echartsInstances || []).forEach((c) => {
        try { c.resize(); } catch (e) {}
      });
    }, 0);
  }

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
    buildTabs();
    await loadAll();
    // 默认显示第一个（打开即展示数据库已有数据，无需刷新）
    switchTab(views[0].id);
    window.addEventListener("resize", () => {
      (window.echartsInstances || []).forEach((c) => c.resize());
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window.Reports);
