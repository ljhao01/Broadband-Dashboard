/* panel.js — 通用子窗口（弹窗面板）管理器
 *
 * 设计目标：主页面只保留概览，各业务模块在子窗口中独立呈现。
 * 能力：
 *   - 模块注册：R.Panel.register(key, {title, icon, subtitle, mount(body, data)})
 *   - 打开/关闭/切换：open / close / toggle，面板内 Tab 与 ← → 直接切换，无需关掉重开
 *   - 关闭方式统一：右上关闭按钮、点击遮罩、Esc
 *   - 交互一致性：body 滚动锁定、打开时焦点移入面板、关闭时归还焦点、Tab 焦点环内循环
 *   - 图表安全：切换/关闭前销毁面板内 ECharts 实例，避免尺寸为 0 与内存泄漏
 *   - 深链接：地址栏 #panel=key 可刷新恢复，关闭时清除
 */
(function (R) {
  "use strict";

  const mods = new Map();
  const order = [];
  const S = {
    root: null, mask: null, panel: null, body: null, tabs: null,
    titleEl: null, subEl: null, iconEl: null,
    key: null, data: null, lastFocus: null,
  };
  const ANIM_MS = 180;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -------------------------------------------------------------------------
  // 注册
  // -------------------------------------------------------------------------
  function register(key, def) {
    if (!key || !def || typeof def.mount !== "function") return;
    mods.set(key, Object.assign({ key: key }, def));
    if (order.indexOf(key) === -1) order.push(key);
  }

  function has(key) {
    return mods.has(key);
  }

  // -------------------------------------------------------------------------
  // DOM 骨架（首次打开时惰性创建）
  // -------------------------------------------------------------------------
  function ensure() {
    if (S.root && document.body.contains(S.root)) return S.root;

    const root = document.createElement("div");
    root.id = "wl-panel-root";
    root.innerHTML = `
      <div class="wl-panel-mask" data-mask hidden>
        <div class="wl-panel" role="dialog" aria-modal="true" aria-labelledby="wl-panel-title" tabindex="-1">
          <div class="wl-panel-head">
            <div class="wl-panel-heading">
              <span class="ic" id="wl-panel-icon"><span class="material-symbols-rounded">dashboard</span></span>
              <div class="wl-panel-heading-text">
                <div class="wl-panel-title" id="wl-panel-title"></div>
                <div class="wl-panel-sub" id="wl-panel-sub"></div>
              </div>
            </div>
            <div class="wl-panel-actions">
              <button class="wl-panel-icon-btn" data-panel-prev type="button" title="上一个模块（←）">
                <span class="material-symbols-rounded">chevron_left</span>
              </button>
              <button class="wl-panel-icon-btn" data-panel-next type="button" title="下一个模块（→）">
                <span class="material-symbols-rounded">chevron_right</span>
              </button>
              <button class="wl-panel-icon-btn wl-panel-close" data-panel-close type="button" title="关闭（Esc）">
                <span class="material-symbols-rounded">close</span>
              </button>
            </div>
          </div>
          <div class="wl-panel-tabs" id="wl-panel-tabs" role="tablist"></div>
          <div class="wl-panel-body" id="wl-panel-body"></div>
        </div>
      </div>`;

    document.body.appendChild(root);
    S.root = root;
    S.mask = root.querySelector("[data-mask]");
    S.panel = root.querySelector(".wl-panel");
    S.body = root.querySelector("#wl-panel-body");
    S.tabs = root.querySelector("#wl-panel-tabs");
    S.titleEl = root.querySelector("#wl-panel-title");
    S.subEl = root.querySelector("#wl-panel-sub");
    S.iconEl = root.querySelector("#wl-panel-icon .material-symbols-rounded");

    S.mask.addEventListener("click", (e) => {
      if (e.target === S.mask) close();
    });
    root.querySelector("[data-panel-close]").addEventListener("click", close);
    root.querySelector("[data-panel-prev]").addEventListener("click", () => step(-1));
    root.querySelector("[data-panel-next]").addEventListener("click", () => step(1));
    S.tabs.addEventListener("click", (e) => {
      const tab = e.target.closest && e.target.closest("[data-tab]");
      if (tab && tab.dataset.tab !== S.key) open(tab.dataset.tab);
    });

    document.addEventListener("keydown", onKeydown);
    return root;
  }

  // -------------------------------------------------------------------------
  // 键盘：Esc 关闭 / ← → 切换 / Tab 焦点环
  // -------------------------------------------------------------------------
  function onKeydown(e) {
    if (!S.key) return;
    const tag = (e.target && e.target.tagName) || "";
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(tag) || (e.target && e.target.isContentEditable);

    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (typing) return;
    if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); return; }
    if (e.key === "ArrowRight") { e.preventDefault(); step(1); return; }
    if (e.key === "Tab") trapTab(e);
  }

  function trapTab(e) {
    const nodes = S.panel.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!nodes.length) {
      e.preventDefault();
      S.panel.focus();
      return;
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === S.panel)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  // -------------------------------------------------------------------------
  // 渲染
  // -------------------------------------------------------------------------
  function renderHead() {
    const def = mods.get(S.key);
    if (!def) return;
    if (S.titleEl) S.titleEl.textContent = def.title || "";
    if (S.subEl) S.subEl.textContent = def.subtitle || "";
    if (S.iconEl) S.iconEl.textContent = def.icon || "dashboard";

    const multi = order.length > 1;
    S.root.querySelectorAll("[data-panel-prev],[data-panel-next]").forEach((b) => {
      b.disabled = !multi;
    });

    if (S.tabs) {
      S.tabs.innerHTML = order.map((k) => {
        const m = mods.get(k);
        return `<button class="wl-panel-tab${k === S.key ? " is-on" : ""}" type="button"
                  role="tab" data-tab="${k}" aria-selected="${k === S.key}">
                  <span class="material-symbols-rounded" style="font-size:14px">${m.icon || "circle"}</span>${esc(m.title)}
                </button>`;
      }).join("");
    }
  }

  function mountBody() {
    const def = mods.get(S.key);
    if (!def || !S.body) return;
    destroyCharts(S.body);
    S.body.innerHTML = "";
    S.body.scrollTop = 0;
    S.body.dataset.panel = S.key;
    try {
      def.mount(S.body, S.data || {});
    } catch (err) {
      S.body.innerHTML = `<div class="wl-panel-error">模块渲染失败：${esc(err.message)}</div>`;
      console.error("[panel]", err);
    }
    // 面板刚插入 DOM，等一帧让容器宽度确定后再对齐图表尺寸
    requestAnimationFrame(() => {
      (window.echartsInstances || []).forEach((c) => {
        try { if (c && !c.isDisposed()) c.resize(); } catch (e) { /* 忽略 */ }
      });
    });
  }

  function destroyCharts(root) {
    if (!root || !window.echarts) return;
    root.querySelectorAll("div").forEach((el) => {
      const inst = window.echarts.getInstanceByDom(el);
      if (inst) {
        try { inst.dispose(); } catch (e) { /* 忽略 */ }
      }
    });
    window.echartsInstances = (window.echartsInstances || []).filter((c) => c && !c.isDisposed());
  }

  // -------------------------------------------------------------------------
  // 打开 / 关闭 / 切换
  // -------------------------------------------------------------------------
  function open(key) {
    if (!mods.has(key)) return;
    ensure();

    // 用 S.key 判断是否已打开，而不是 mask.hidden（关闭动画期间 hidden 仍为 false）
    const alreadyOpen = !!S.key;
    if (alreadyOpen && S.key === key) {
      S.panel.focus();
      return;
    }
    if (!alreadyOpen) {
      S.lastFocus = document.activeElement;
      S.mask.hidden = false;
      document.body.classList.add("wl-panel-open");
      // 先插入再补动画类，保证过渡生效
      requestAnimationFrame(() => {
        if (S.key) S.mask.classList.add("is-open");
      });
    }

    S.key = key;
    renderHead();
    mountBody();
    S.panel.focus({ preventScroll: true });
    syncHash(key);
  }

  function close() {
    if (!S.mask || S.mask.hidden || !S.key) return null;
    const closedKey = S.key;
    S.key = null;

    destroyCharts(S.body);
    S.mask.classList.remove("is-open");
    document.body.classList.remove("wl-panel-open");
    clearHash();

    window.setTimeout(() => {
      if (!S.key && S.mask) {
        S.mask.hidden = true;
        if (S.body) S.body.innerHTML = "";
      }
    }, ANIM_MS);

    if (S.lastFocus && typeof S.lastFocus.focus === "function") {
      try { S.lastFocus.focus({ preventScroll: true }); } catch (e) { /* 忽略 */ }
    }
    S.lastFocus = null;
    return closedKey;
  }

  function toggle(key) {
    if (S.key === key) close();
    else open(key);
  }

  function step(dir) {
    if (!order.length) return;
    const idx = order.indexOf(S.key || order[0]);
    const next = order[(idx + dir + order.length) % order.length];
    if (next && next !== S.key) open(next);
  }

  // -------------------------------------------------------------------------
  // 数据注入：主视图刷新后同步给已打开的面板
  // -------------------------------------------------------------------------
  function setData(data) {
    S.data = data;
    // 「数据中心」面板内是上传表单与反馈，重渲染会丢失输入/状态，故跳过
    if (S.key && S.key !== "data") mountBody();
  }

  function refresh() {
    if (S.key) mountBody();
  }

  function current() {
    return S.key;
  }

  function isOpen() {
    return !!S.key;
  }

  // -------------------------------------------------------------------------
  // 地址栏同步（可刷新恢复）
  // -------------------------------------------------------------------------
  function syncHash(key) {
    try {
      window.history.replaceState(null, "", "#panel=" + key);
    } catch (e) { /* file:// 等环境忽略 */ }
  }

  function clearHash() {
    try {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    } catch (e) { /* 忽略 */ }
  }

  function openFromHash() {
    const m = /^#panel=([\w-]+)$/.exec(window.location.hash || "");
    if (m && mods.has(m[1])) open(m[1]);
  }

  R.Panel = {
    register,
    has,
    open,
    close,
    toggle,
    step,
    setData,
    refresh,
    current,
    isOpen,
    openFromHash,
  };
})(window.Reports);
