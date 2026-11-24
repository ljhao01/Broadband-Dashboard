/* view_weaklight.js — 弱光督办看板（新洲区弱光指标提升）
 * 功能：总览核心指标 + 小区分布 + OLT/PON分析 + 新增弱光督办 + 持续/严重弱光
 * 数据来自 /api/weaklight_dashboard（已落库，打开即展示最新批次）
 */
(function (R) {
  "use strict";

  let cached = null; // 缓存最近一次数据，防止重新加载时闪烁

  const view = {
    id: "weaklight",
    title: "弱光督办",
    async init() {
      await this.load();
    },
    async load() {
      const res = await fetch("/api/data/weaklight").then((r) => r.json());
      const box = document.getElementById("v-weaklight");
      if (res.error) {
        box.innerHTML = `<div class="text-red-500">加载失败：${res.error}</div>`;
        return;
      }
      cached = res;
      // 同步数据给子窗口：面板已打开时自动重渲染（「数据中心」面板除外，避免丢失上传反馈）
      if (R.Panel) R.Panel.setData(res);
      if (!res.has_data) {
        renderEmpty(box);
        return;
      }
      renderDashboard(box, res);
    },
  };

  function mountUpload() {
    if (window.FEATURES && window.FEATURES.showWeakLightUpload && R.WeakLightUpload) {
      const wrap = document.getElementById("wl-upload-wrap");
      if (wrap && !wrap.dataset.mounted) {
        wrap.dataset.mounted = "1";
        R.WeakLightUpload.mount(wrap);
      }
    }
  }

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---------- 空数据态：引导到「数据中心」子窗口 ----------
  function renderEmpty(box) {
    box.innerHTML = `
      <div class="card">
        <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">light_mode</span></span>弱光督办看板</div>
        <div class="text-sm py-2" style="color:var(--ink-3);line-height:1.95">
          暂无弱光数据。请打开「数据中心」上传《存量及新增弱光》Excel 或《智能网关用户详情报表》CSV，
          系统会自动解析新洲区数据并入库展示。
        </div>
        <div class="mt-3 flex items-center gap-3 flex-wrap">
          <button class="btn btn-primary" type="button" data-open-panel="data">
            <span class="material-symbols-rounded" style="font-size:16px">database</span>打开数据中心
          </button>
          <span class="text-xs" style="color:var(--ink-3)">支持弱光报表 / 责任田</span>
        </div>
      </div>`;
  }

  // ---------- 主视图：概览条 + KPI + 首屏可视化 + 子窗口入口 ----------
  function renderDashboard(box, res) {
    const kpis = (res.kpis || []).map(R.kpiCard).join("");
    const latest = res.latest || {};
    const cards = MODULES.map((m) => moduleCard(m, res)).join("");

    box.innerHTML = `
      <div class="wl-brief">
        <div class="wl-brief-main">
          <span class="material-symbols-rounded">dataset</span>
          <span>最新批次 <b>#${latest.id != null ? latest.id : "—"}</b></span>
          <span class="wl-brief-dot"></span>
          <span>数据日期 <b style="color:var(--accent)">${escHtml(latest.data_date || "—")}</b></span>
          <span class="wl-brief-dot"></span>
          <span class="wl-brief-file">${escHtml(latest.filename || "—")}</span>
        </div>
        <div class="wl-brief-actions">
          <button class="btn btn-ghost" type="button" data-open-panel="data">
            <span class="material-symbols-rounded" style="font-size:16px">database</span>数据中心 / 上传
          </button>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">${kpis}</div>

      <!-- 首屏可视化：近 7 日趋势 + 当日区域网格分布 -->
      <div id="wl-overview" class="wl-overview"></div>

      <div class="wl-section-head">
        <div class="card-title" style="padding-left:0">
          <span class="ic"><span class="material-symbols-rounded">widgets</span></span>督办模块
          <span class="text-xs font-normal" style="color:var(--ink-3)">点击卡片在子窗口中查看 · 子窗口内可直接切换模块（← → / 顶部标签）</span>
        </div>
      </div>
      <div class="wl-mod-grid">${cards}</div>`;

    renderOverview(res);
  }

  // ---------- 首屏概览：近 7 日弱光趋势 + 当日区域网格分布 ----------
  function renderOverview(res) {
    const wrap = document.getElementById("wl-overview");
    if (!wrap) return;

    const ov = res.overview || {};
    const trend = ov.trend || {};
    const grid = ov.grid || {};
    const labels = trend.labels || [];
    const weak = trend.weak || [];
    const severe = trend.severe || [];
    const batches = trend.batch_cnt || labels.length || 0;
    const latest = res.latest || {};

    const note = `${batches} 次导入`;
    const isGrid = (grid.mode || "grid") === "grid";
    const gridNote = isGrid
      ? `${grid.grid_cnt || 0} 个网格 · ${grid.total || 0} 户`
      : `TOP ${grid.cell_cnt || 0} 小区 · ${grid.total || 0} 户`;
    const cells = grid.cells || [];
    const cellsHtml = cells.length
      ? cells.map((c) => `
        <div class="wl-grid-cell heat-${escHtml(c.level || "low")}"
             title="${escHtml(c.name)}：弱光 ${c.weak_count} 户 · 严重 ${c.severe_cnt} 户 · ${c.community_cnt} 个小区">
          <div class="wl-grid-name">${escHtml(c.short || c.name)}</div>
          <div class="wl-grid-val">${c.weak_count}<span>户</span></div>
          <div class="wl-grid-meta">严重 ${c.severe_cnt} · ${c.community_cnt} 小区</div>
          <div class="wl-grid-bar"><i style="width:${Math.max(6, Math.round((c.ratio || 0) * 100))}%"></i></div>
        </div>`).join("")
      : `<div class="wl-grid-empty">暂无区域分布数据</div>`;

    wrap.innerHTML = `
      <div class="card wl-ov-card">
        <div class="wl-ov-head">
          <h3 class="card-title">
            <span class="ic"><span class="material-symbols-rounded">show_chart</span></span>近 7 次导入弱光变化
          </h3>
          <span class="wl-ov-note ${batches >= 2 ? "" : "is-warn"}">${note}</span>
        </div>
        <div id="wl-trend-chart" class="wl-ov-chart"></div>
        <div class="wl-ov-foot">
          <span><i style="background:#2ea6ff"></i>存量弱光</span>
          <span><i style="background:#ff5a65"></i>严重弱光</span>
          <span>最新数据 ${escHtml(latest.data_date || "—")}</span>
          ${batches <= 1 ? "<span>至少 2 次导入才能形成趋势</span>" : ""}
        </div>
      </div>

      <div class="card wl-ov-card">
        <div class="wl-ov-head">
          <h3 class="card-title">
            <span class="ic"><span class="material-symbols-rounded">grid_view</span></span>当日弱光区域分布
          </h3>
          <span class="wl-ov-note">${gridNote}</span>
        </div>
        <div class="wl-grid-map">${cellsHtml}</div>
        <div class="wl-ov-foot">
          <span>${isGrid ? "按市场网格（责任田）聚合小区弱光户数" : "未导入《责任田》，按小区弱光户数降序展示"}</span>
          ${grid.unmatched_weak ? `<span>未归属网格 ${grid.unmatched_weak} 户</span>` : ""}
        </div>
      </div>`;

    R.renderTrend("wl-trend-chart", labels, [
      { name: "存量弱光", data: weak, color: "#2ea6ff" },
      { name: "严重弱光", data: severe, color: "#ff5a65", area: false, label: false },
    ], { labelValues: batches <= 1, yName: "户" });
  }

  // ---------- 持续弱光追踪（跨批次 SN） ----------
  const SUS = { data: null };

  function mountSustained() {
    const tableEl = document.getElementById("wl-sus-table");
    if (!tableEl) return;
    tableEl.innerHTML = `<div class="text-sm text-center py-8" style="color:var(--ink-3)">加载中…</div>`;

    const high = document.getElementById("wl-sus-high");
    const sort = document.getElementById("wl-sus-sort");
    const search = document.getElementById("wl-sus-search");
    if (high) high.addEventListener("change", renderSustained);
    if (sort) sort.addEventListener("change", renderSustained);
    if (search) {
      let timer = null;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(renderSustained, 180);
      });
    }

    fetch("/api/weaklight_sustained")
      .then((r) => r.json())
      .then((d) => {
        SUS.data = d;
        renderSustained();
      })
      .catch((e) => {
        const el = document.getElementById("wl-sus-table");
        if (el) el.innerHTML = `<div class="wl-panel-error">加载失败：${escHtml(e.message)}</div>`;
      });
  }

  function renderSustained() {
    const tableEl = document.getElementById("wl-sus-table");
    if (!tableEl) return;
    const d = SUS.data || {};
    const s = d.summary || {};
    const items = d.items || [];
    const ready = (s.batch_cnt || 0) >= (s.min_batches || 3);

    const sumEl = document.getElementById("wl-sus-summary");
    if (sumEl) {
      const blocks = [
        { label: "持续弱光台数", value: ready ? (s.sustained_cnt || 0) : "—", unit: "台", tone: "red" },
        { label: "高频未整改", value: ready ? (s.high_freq_cnt || 0) : "—", unit: "台", tone: "red" },
        { label: "最长持续", value: ready ? (s.max_span_days || 0) : "—", unit: "天", tone: "yellow" },
        { label: "涉及小区", value: ready ? (s.community_cnt || 0) : "—", unit: "个", tone: "blue" },
      ];
      sumEl.innerHTML = blocks.map((b) => `
        <div class="wl-sus-metric tone-${b.tone}">
          <div class="wl-sus-metric-label">${b.label}</div>
          <div class="wl-sus-metric-value">${b.value}<span>${b.unit}</span></div>
        </div>`).join("");
    }

    const countEl = document.getElementById("wl-sus-count");
    const footEl = document.getElementById("wl-sus-foot");

    if (!ready) {
      tableEl.innerHTML = `
        <div class="wl-sus-empty">
          <span class="material-symbols-rounded">hourglass_empty</span>
          <div>当前仅 <b>${s.batch_cnt || 0}</b> 个批次，需 ≥<b>${s.min_batches || 3}</b> 个批次才能判定持续弱光</div>
          <div class="wl-sus-empty-sub">持续弱光按同一网关 SN 跨批次累计出现次数判定，不依赖报表「持续弱光」列</div>
        </div>`;
      if (countEl) countEl.textContent = "";
      if (footEl) footEl.textContent = "";
      return;
    }

    const highBox = document.getElementById("wl-sus-high");
    const sortSel = document.getElementById("wl-sus-sort");
    const searchBox = document.getElementById("wl-sus-search");
    const onlyHigh = !!(highBox && highBox.checked);
    const sortKey = (sortSel && sortSel.value) || "unfixed";
    const kw = ((searchBox && searchBox.value) || "").trim().toLowerCase();

    let rows = items.slice();
    if (onlyHigh) rows = rows.filter((r) => r.is_high_freq);
    if (kw) {
      rows = rows.filter((r) =>
        String(r.gateway_sn || "").toLowerCase().indexOf(kw) >= 0
        || String(r.community || "").toLowerCase().indexOf(kw) >= 0
        || String(r.person || "").toLowerCase().indexOf(kw) >= 0);
    }
    if (sortKey === "days") {
      rows.sort((a, b) => b.span_days - a.span_days || b.unfixed_times - a.unfixed_times);
    } else if (sortKey === "valley") {
      rows.sort((a, b) => (a.min_valley == null ? 0 : a.min_valley) - (b.min_valley == null ? 0 : b.min_valley));
    } else {
      rows.sort((a, b) => b.unfixed_times - a.unfixed_times || b.span_days - a.span_days);
    }

    if (!rows.length) {
      tableEl.innerHTML = `
        <div class="wl-sus-empty">
          <span class="material-symbols-rounded">check_circle</span>
          <div>${items.length ? "当前筛选条件下没有匹配设备" : "本批次暂无持续弱光设备，均为首次发现"}</div>
        </div>`;
    } else {
      const body = rows.map((r, i) => {
        const badge = r.is_high_freq
          ? `<span class="status-pill red">高频未整改</span>`
          : `<span class="status-pill yellow">持续中</span>`;
        const unfixedStyle = r.unfixed_times >= 2 ? `style="color:#ff8a8f;font-weight:700"` : "";
        const daysStyle = r.span_days >= 7 ? `style="color:#ff8a8f;font-weight:700"` : "";
        const valleyStyle = (r.min_valley != null && r.min_valley < -30)
          ? "color:#ff8a8f" : "color:var(--ink-2)";
        return `<tr class="${i < 3 ? "row-xinzhou" : ""}">
          <td class="py-1.5" style="color:var(--ink-3)">${i + 1}</td>
          <td class="py-1.5"><span class="wl-sus-sn" data-sn="${escHtml(r.gateway_sn)}" title="点击复制">${escHtml(r.gateway_sn || "—")}</span></td>
          <td class="py-1.5" style="color:var(--ink-2)">${escHtml(r.community || "—")}</td>
          <td class="py-1.5" style="color:var(--ink-2)">${escHtml(r.person || "—")}${r.phone ? `<span class="wl-sus-phone">${escHtml(r.phone)}</span>` : ""}</td>
          <td class="py-1.5" style="color:var(--ink-2)">${r.appear_batches}</td>
          <td class="py-1.5" ${unfixedStyle}>${r.unfixed_times}</td>
          <td class="py-1.5" ${daysStyle}>${r.span_days}</td>
          <td class="py-1.5" style="${valleyStyle}">${r.min_valley != null ? r.min_valley : "—"}</td>
          <td class="py-1.5">${badge}</td>
        </tr>`;
      }).join("");
      tableEl.innerHTML = `
        <table class="data-table wl-sus-table">
          <thead><tr>
            <th>#</th><th>网关SN</th><th>小区</th><th>对应人员</th>
            <th>出现批次</th><th>未整改次数</th><th>持续天数</th><th>最低谷值(dBm)</th><th>状态</th>
          </tr></thead>
          <tbody>${body}</tbody>
        </table>`;
      tableEl.querySelectorAll(".wl-sus-sn").forEach((el) => {
        el.addEventListener("click", () => copySn(el, el.dataset.sn || ""));
      });
    }

    if (countEl) countEl.textContent = `显示 ${rows.length} / ${items.length} 台`;
    if (footEl) {
      const b = d.batches_used || [];
      const from = b.length ? b[0].data_date : "—";
      const to = b.length ? b[b.length - 1].data_date : "—";
      footEl.textContent = `数据窗口：近 ${b.length} 个批次（${from} ~ ${to}）`
        + ` · 已闭环 ${s.closed_cnt || 0} 台（曾复现、最新批次已消失）`
        + ` · 判定口径：累计出现 ≥${s.min_batches || 3} 个批次`;
    }
  }

  function copySn(el, sn) {
    const restore = () => { el.textContent = sn || "—"; };
    const flash = () => {
      el.textContent = "已复制";
      setTimeout(restore, 900);
    };
    if (!sn) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(sn).then(flash).catch(flash);
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = sn;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* 忽略 */ }
    document.body.removeChild(ta);
    flash();
  }

  function renderFocusSustained(res) {
    const el = document.getElementById("wl-focus-sustained");
    if (!el) return;
    const s = res.sustained_summary || {};
    const ready = (s.batch_cnt || 0) >= (s.min_batches || 3);
    el.innerHTML = `
      <div class="wl-sus-inline-box">
        <div class="wl-sus-inline-num">${ready ? (s.sustained_cnt || 0) : "—"}<span>台</span></div>
        <div class="wl-sus-inline-meta">
          高频未整改 ${ready ? (s.high_freq_cnt || 0) : "—"} 台 · 最长持续 ${ready ? (s.max_span_days || 0) : "—"} 天<br/>
          ${ready ? `已闭环 ${s.closed_cnt || 0} 台（最新批次已不再弱光）`
                  : `需 ≥${s.min_batches || 3} 个批次（当前 ${s.batch_cnt || 0} 个）`}
        </div>
        <button class="btn btn-ghost wl-sus-inline-btn" type="button" data-open-panel="sustained">
          <span class="material-symbols-rounded" style="font-size:15px">open_in_new</span>查看追踪明细
        </button>
      </div>`;
  }

  // ---------- 智能总结：结构化问题清单（类别/集中度/闭环/复发/优先级） ----------
  const INS = { data: null };

  function mountInsights() {
    const tableEl = document.getElementById("wl-ins-table");
    if (!tableEl) return;
    tableEl.innerHTML = `<div class="text-sm text-center py-8" style="color:var(--ink-3)">加载中…</div>`;

    const cat = document.getElementById("wl-ins-cat");
    const pri = document.getElementById("wl-ins-pri");
    const rev = document.getElementById("wl-ins-revived");
    const search = document.getElementById("wl-ins-search");
    const exportBtn = document.getElementById("wl-ins-export");
    if (cat) cat.addEventListener("change", renderInsights);
    if (pri) pri.addEventListener("change", renderInsights);
    if (rev) rev.addEventListener("change", renderInsights);
    if (exportBtn) exportBtn.addEventListener("click", exportInsights);
    if (search) {
      let timer = null;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(renderInsights, 160);
      });
    }

    fetch("/api/weaklight_insights")
      .then((r) => r.json())
      .then((d) => {
        INS.data = d;
        fillInsightCats(d.items || []);
        renderInsights();
      })
      .catch((e) => {
        const el = document.getElementById("wl-ins-table");
        if (el) el.innerHTML = `<div class="wl-panel-error">加载失败：${escHtml(e.message)}</div>`;
      });
  }

  function fillInsightCats(items) {
    const sel = document.getElementById("wl-ins-cat");
    if (!sel) return;
    const cats = [];
    items.forEach((it) => {
      if (it.category && cats.indexOf(it.category) < 0) cats.push(it.category);
    });
    sel.innerHTML = `<option value="">全部类别</option>`
      + cats.map((c) => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join("");
  }

  function renderInsights() {
    const d = INS.data || {};
    const s = d.summary || {};
    const all = d.items || [];
    const tableEl = document.getElementById("wl-ins-table");
    if (!tableEl) return;

    const sumEl = document.getElementById("wl-ins-summary");
    if (sumEl) {
      const blocks = [
        { label: "P0 立即处置", value: s.p0 || 0, tone: "p0" },
        { label: "P1 优先处置", value: s.p1 || 0, tone: "p1" },
        { label: "P2 计划处置", value: s.p2 || 0, tone: "p2" },
        { label: "P3 持续观察", value: s.p3 || 0, tone: "p3" },
      ];
      sumEl.innerHTML = blocks.map((b) => `
        <div class="wl-ins-metric tone-${b.tone}">
          <div class="wl-ins-metric-label">${b.label}</div>
          <div class="wl-ins-metric-value">${b.value}<span>项</span></div>
        </div>`).join("");
    }

    const catEl = document.getElementById("wl-ins-cat");
    const priEl = document.getElementById("wl-ins-pri");
    const revEl = document.getElementById("wl-ins-revived");
    const searchEl = document.getElementById("wl-ins-search");
    const cat = catEl ? catEl.value : "";
    const pri = priEl ? priEl.value : "";
    const onlyRev = !!(revEl && revEl.checked);
    const kw = ((searchEl && searchEl.value) || "").trim().toLowerCase();

    let rows = all.slice();
    if (cat) rows = rows.filter((r) => r.category === cat);
    if (pri) rows = rows.filter((r) => r.priority === pri);
    if (onlyRev) rows = rows.filter((r) => (r.history || {}).revived);
    if (kw) {
      rows = rows.filter((r) =>
        String(r.title || "").toLowerCase().indexOf(kw) >= 0
        || String(r.category || "").toLowerCase().indexOf(kw) >= 0
        || String(r.suggestion || "").toLowerCase().indexOf(kw) >= 0);
    }

    if (!rows.length) {
      tableEl.innerHTML = `<div class="wl-ins-empty">
        <span class="material-symbols-rounded">fact_check</span>
        <div>${all.length ? "当前筛选条件下没有问题项" : "暂无问题项（需先上传弱光报表）"}</div>
      </div>`;
    } else {
      tableEl.innerHTML = `
        <table class="data-table wl-ins-table">
          <thead><tr>
            <th>优先级</th><th>问题类别</th><th>摘要</th><th>集中度</th>
            <th>闭环状态</th><th>历史出现</th><th>建议处置</th>
          </tr></thead>
          <tbody>${rows.map(insightRow).join("")}</tbody>
        </table>`;
      tableEl.querySelectorAll(".wl-ins-row").forEach((tr) => {
        tr.addEventListener("click", () => {
          const next = tr.nextElementSibling;
          if (next && next.classList.contains("wl-ins-ev-row")) {
            next.classList.toggle("is-open");
          }
        });
      });
    }

    const countEl = document.getElementById("wl-ins-count");
    if (countEl) countEl.textContent = `显示 ${rows.length} / ${all.length} 项`;

    const footEl = document.getElementById("wl-ins-foot");
    if (footEl) {
      const parts = [
        `批次 ${s.data_date || "—"}`,
        `对比上一批 ${s.compare_date || "—"}`,
        `超期 ${s.overdue_cnt || 0} 台（≥${s.overdue_days || 14} 天）`,
        `复发 ${s.revived_cnt || 0} 项`,
        "闭环状态由「最新批次是否仍弱光」推断",
      ];
      if (s.quality_missing) parts.push("本批未提供质差类型，已跳过质差归因");
      footEl.textContent = parts.join(" · ");
    }
  }

  function insightRow(it) {
    const h = it.history || {};
    const st = it.status || {};
    const c = it.concentration || {};
    const share = Math.round((c.share || 0) * 100);
    const pri = it.priority || "P3";
    const statusHtml = st.state === "overdue"
      ? `<span class="status-pill red">超期 ${st.overdue_days || 0} 天</span>`
      : `<span class="status-pill yellow">未闭环</span>`;
    const hist = h.first_seen
      ? `${escHtml(h.first_seen)} 起 · ${h.appear_batches || 1} 批${h.gaps ? " · 中断 " + h.gaps + " 批" : ""}`
      : "—";
    return `<tr class="wl-ins-row">
      <td><span class="wl-ins-pri pri-${pri.toLowerCase()}">${pri}</span></td>
      <td style="color:var(--ink-2);white-space:nowrap">${escHtml(it.category || "")}</td>
      <td class="wl-ins-title">${escHtml(it.title || "")}</td>
      <td>
        <div class="wl-ins-conc"><span>${c.value || 0}</span><i style="width:${Math.max(6, share)}%"></i></div>
        <div class="wl-ins-conc-sub">占全区 ${share}%</div>
      </td>
      <td style="white-space:nowrap">${statusHtml}</td>
      <td>
        <div class="wl-ins-hist">${hist}</div>
        ${h.revived ? `<span class="wl-ins-rev">复发</span>` : ""}
      </td>
      <td class="wl-ins-sug">${escHtml(it.suggestion || "")}</td>
    </tr>
    <tr class="wl-ins-ev-row"><td colspan="7">${evidenceHtml(it)}</td></tr>`;
  }

  function evidenceHtml(it) {
    const ev = it.evidence || {};
    const comms = ev.communities || [];
    const pons = ev.pons || [];
    const sns = ev.sn || [];
    const f = it.factors || {};
    const factorTxt = `评分 ${it.score}：集中 ${Math.round((f.conc || 0) * 100)}% · 严重 ${Math.round((f.sev || 0) * 100)}%`
      + ` · 持续 ${Math.round((f.dur || 0) * 100)}% · 超期 ${Math.round((f.over || 0) * 100)}%`
      + ` · 覆盖 ${Math.round((f.cov || 0) * 100)}%`;
    const chips = (list, render) => (list.length
      ? `<div class="wl-ins-ev-chips">${list.map(render).join("")}</div>`
      : `<span class="wl-ins-ev-none">—</span>`);
    const snTable = sns.length ? `
      <table class="data-table wl-ins-ev-table">
        <thead><tr><th>网关SN</th><th>小区</th><th>对应人员</th><th>出现批次</th><th>持续天数</th><th>谷值(dBm)</th></tr></thead>
        <tbody>${sns.map((x) => `<tr>
          <td class="wl-ins-sn">${escHtml(x.sn || "")}</td>
          <td>${escHtml(x.community || "—")}</td>
          <td>${escHtml(x.person || "—")}</td>
          <td>${x.appear_batches || 0}</td>
          <td>${x.span_days || 0}</td>
          <td>${x.valley_power != null ? x.valley_power : "—"}</td>
        </tr>`).join("")}</tbody>
      </table>` : "";
    return `<div class="wl-ins-ev">
      <div class="wl-ins-ev-factor">${escHtml(factorTxt)}</div>
      <div class="wl-ins-ev-block"><b>涉及小区</b>${chips(comms, (x) => `<span class="wl-ins-chip">${escHtml(x.name)} · ${x.count} 户</span>`)}</div>
      <div class="wl-ins-ev-block"><b>涉及 PON</b>${chips(pons, (x) => `<span class="wl-ins-chip">${escHtml(x.short || x.pon || "")} · ${x.count} 户</span>`)}</div>
      ${snTable}
    </div>`;
  }

  function exportInsights() {
    const d = INS.data || {};
    const rows = d.items || [];
    if (!rows.length) return;
    const header = ["优先级", "问题类别", "摘要", "集中度(户)", "占全区比例", "闭环状态",
      "超期天数", "首次出现", "出现批次", "复发", "评分", "建议处置"];
    const lines = [header.join(",")];
    rows.forEach((it) => {
      const st = it.status || {};
      const h = it.history || {};
      const c = it.concentration || {};
      lines.push([
        it.priority, it.category, it.title, c.value,
        Math.round((c.share || 0) * 100) + "%",
        st.state === "overdue" ? "超期未闭环" : "未闭环",
        st.overdue_days || 0, h.first_seen || "", h.appear_batches || 0,
        h.revived ? "是" : "否", it.score, it.suggestion,
      ].map(csvCell).join(","));
    });
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `智能总结_${((d.summary || {}).data_date) || "latest"}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  function csvCell(v) {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  // ---------- 推送督办：网格长（企业微信群机器人） ----------
  const PUSH_SOURCE_TEXT = { roster: "名单", derived: "责任田派生", fallback: "区级兜底" };
  const PUSH_TASK_TEXT = {
    pending: "排队中", running: "发送中", done: "已完成", partial: "部分失败", failed: "失败",
  };
  const pushState = { preview: null, selected: new Set(), force: false, taskId: null, timer: null };

  function pushBodyHtml() {
    return `
      <div id="wl-push-root">
        <div id="wl-push-badges" class="wl-push-bar"></div>
        <div class="wl-push-upload">
          <span class="text-xs" style="color:var(--ink-3)">网格长名单</span>
          <input id="wl-push-leader-file" type="file" accept=".csv,.xlsx,.xls"
                 class="text-xs" style="color:var(--ink-2)" />
          <button id="wl-push-leader-upload" class="btn btn-ghost" type="button"
                  style="padding:5px 10px;font-size:12px">
            <span class="material-symbols-rounded" style="font-size:15px">upload</span>上传名单
          </button>
          <span id="wl-push-leader-status" class="text-xs" style="color:var(--ink-3)"></span>
          <span class="text-xs" style="color:var(--ink-3);margin-left:auto">
            列：市场网格编码 / 市场网格名称 / 网格长姓名 / 手机号（可选工号、角色）
          </span>
        </div>
        <div id="wl-push-summary" class="wl-ins-summary"></div>
        <div class="wl-panel-toolbar">
          <div class="flex items-center gap-2 flex-wrap">
            <label class="flex items-center gap-1.5 text-xs" style="color:var(--ink-3)">
              <input type="checkbox" id="wl-push-all" class="accent-[#2ea6ff]">全选
            </label>
            <label class="flex items-center gap-1.5 text-xs" style="color:var(--ink-3)">
              <input type="checkbox" id="wl-push-force" class="accent-[#2ea6ff]">强制重推已推网格
            </label>
            <input id="wl-push-search" type="search" placeholder="搜索网格 / 网格长"
                   class="wl-ins-select" style="min-width:160px" />
          </div>
          <div class="flex items-center gap-2">
            <span id="wl-push-count" class="text-xs" style="color:var(--ink-3)"></span>
            <button id="wl-push-export" class="btn btn-ghost" type="button"
                    style="padding:6px 12px;font-size:12px">
              <span class="material-symbols-rounded" style="font-size:15px">download</span>导出清单
            </button>
            <button id="wl-push-refresh" class="btn btn-ghost" type="button"
                    style="padding:6px 12px;font-size:12px">
              <span class="material-symbols-rounded" style="font-size:15px">refresh</span>刷新预览
            </button>
            <button id="wl-push-send" class="btn btn-primary" type="button"
                    style="padding:6px 14px;font-size:12px">
              <span class="material-symbols-rounded" style="font-size:15px">send</span>一键推送
            </button>
          </div>
        </div>
        <div id="wl-push-table" class="wl-scroll wl-ins-table-wrap"></div>
        <div id="wl-push-extra" class="mt-2"></div>
        <div class="wl-panel-toolbar mt-3">
          <div class="text-xs" style="color:var(--ink-3)">推送任务记录</div>
          <div class="flex items-center gap-2">
            <select id="wl-push-task-sel" class="wl-ins-select"></select>
          </div>
        </div>
        <div id="wl-push-task"></div>
        <div id="wl-push-foot" class="wl-panel-footnote"></div>

        <!-- 企微群机器人配置窗口 -->
        <div id="wl-push-cfg-mask" class="wl-push-modal" hidden>
          <div class="wl-push-modal-box">
            <div class="wl-push-modal-head">
              <span class="ic"><span class="material-symbols-rounded">smart_toy</span></span>
              <div style="flex:1;min-width:0">
                <div class="wl-push-modal-title">企业微信群机器人</div>
                <div class="wl-push-modal-sub">保存后立即生效，无需重启服务</div>
              </div>
              <button id="wl-push-cfg-close" class="wl-panel-icon-btn" type="button" title="关闭">
                <span class="material-symbols-rounded">close</span>
              </button>
            </div>
            <div class="wl-push-modal-body">
              <label class="wl-push-field">
                <span>Webhook 地址 <b style="color:#ff8a8f">*</b></span>
                <input id="wl-push-cfg-webhook" type="text" spellcheck="false"
                       placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
                <span class="wl-push-field-hint" id="wl-push-cfg-hint"></span>
              </label>
              <div class="wl-push-grid2">
                <label class="wl-push-field">
                  <span>消息类型</span>
                  <select id="wl-push-cfg-msgtype">
                    <option value="markdown">markdown（排版清晰）</option>
                    <option value="text">text（可 @ 手机号强提醒）</option>
                  </select>
                </label>
                <label class="wl-push-field">
                  <span>发送间隔（秒）</span>
                  <input id="wl-push-cfg-interval" type="number" min="0" max="60" step="0.5" />
                </label>
                <label class="wl-push-field">
                  <span>整改时限（工作日）</span>
                  <input id="wl-push-cfg-deadline" type="number" min="1" max="30" />
                </label>
                <label class="wl-push-field">
                  <span>兜底督办人</span>
                  <input id="wl-push-cfg-escname" type="text" placeholder="网格长缺失时使用" />
                  <input id="wl-push-cfg-escphone" type="text" placeholder="兜底手机号（可选）" />
                </label>
              </div>
              <div class="wl-push-modal-tip">
                获取方式：企业微信群 → 右上角「…」→ 群机器人 → 添加机器人 → 复制 Webhook 地址。
                Webhook 含密钥，页面只显示掩码；留空保存表示不修改。
              </div>
            </div>
            <div class="wl-push-modal-foot">
              <span id="wl-push-cfg-status" class="text-xs" style="color:var(--ink-3)"></span>
              <button id="wl-push-cfg-test" class="btn btn-ghost" type="button">
                <span class="material-symbols-rounded" style="font-size:15px">science</span>测试发送
              </button>
              <button id="wl-push-cfg-save" class="btn btn-primary" type="button">
                <span class="material-symbols-rounded" style="font-size:15px">save</span>保存配置
              </button>
            </div>
          </div>
        </div>
      </div>`;
  }

  function mountPush(body) {
    body.innerHTML = pushBodyHtml();
    const root = body.querySelector("#wl-push-root");
    if (!root) return;
    if (pushState.timer) { clearInterval(pushState.timer); pushState.timer = null; }

    root.addEventListener("click", async (e) => {
      if (e.target.id === "wl-push-cfg-mask") { closePushConfig(); return; }
      const btn = e.target.closest("button");
      if (!btn) return;
      if (btn.dataset.pushConfig !== undefined) { await openPushConfig(); }
      else if (btn.id === "wl-push-cfg-close") { closePushConfig(); }
      else if (btn.id === "wl-push-cfg-save") { await savePushConfig(); }
      else if (btn.id === "wl-push-cfg-test") { await testPushConfig(); }
      else if (btn.id === "wl-push-refresh") { await loadPushPreview(); }
      else if (btn.id === "wl-push-export") { exportPushList(); }
      else if (btn.id === "wl-push-leader-upload") { await uploadPushLeaders(); }
      else if (btn.id === "wl-push-send") { await submitPush(); }
      else if (btn.dataset.retry) { await retryPushTarget(btn.dataset.retry); }
    });

    root.addEventListener("change", (e) => {
      const el = e.target;
      if (el.id === "wl-push-all") {
        const p = pushState.preview;
        if (!p) return;
        pushState.selected = el.checked
          ? new Set(p.targets.filter((t) => pushState.force || !t.pushed).map((t) => t.grid_code))
          : new Set();
        renderPushTable();
      } else if (el.id === "wl-push-force") {
        pushState.force = el.checked;
        renderPushTable();
      } else if (el.classList && el.classList.contains("wl-push-check")) {
        const code = el.dataset.grid;
        if (el.checked) pushState.selected.add(code);
        else pushState.selected.delete(code);
        renderPushTable();
      } else if (el.id === "wl-push-task-sel" && el.value) {
        loadPushTask(el.value);
      }
    });

    root.addEventListener("input", (e) => {
      if (e.target.id === "wl-push-search") renderPushTable();
    });

    loadPushPreview();
    loadPushTaskOptions();
  }

  async function loadPushPreview() {
    const box = pushEl("wl-push-table");
    if (!box) return;
    box.innerHTML = `<div class="wl-ins-empty">加载预览中…</div>`;
    try {
      const res = await fetch("/api/push_preview").then((r) => r.json());
      if (!res.ok) {
        box.innerHTML = `<div class="wl-ins-empty">${escHtml(res.error || "加载失败")}</div>`;
        return;
      }
      pushState.preview = res;
      pushState.selected = new Set(res.targets.filter((t) => !t.pushed).map((t) => t.grid_code));
      const all = pushEl("wl-push-all");
      if (all) all.checked = pushState.selected.size > 0;
      renderPushBadges(res);
      renderPushSummary(res);
      renderPushTable();
      renderPushExtra(res);
      const foot = pushEl("wl-push-foot");
      if (foot) {
        foot.textContent = `数据日期 ${res.data_date || "—"} · 匹配口径：小区名 → 责任田（网格）→ 网格长名单；`
          + `未匹配小区不推送。推送对象 ${res.summary.target_cnt} 条，已推网格 ${res.summary.pushed_grid_cnt} 个。`;
      }
    } catch (e) {
      box.innerHTML = `<div class="wl-ins-empty">加载失败：${escHtml(e.message)}</div>`;
    }
  }

  function renderPushBadges(p) {
    const el = pushEl("wl-push-badges");
    if (!el) return;
    const s = p.leader_stat || {};
    const badges = [
      `<button class="wl-push-badge${p.webhook_ready ? " is-ok" : " is-warn"}" type="button"
               data-push-config title="点击配置企业微信群机器人">
         <span class="material-symbols-rounded" style="font-size:14px">${p.webhook_ready ? "check_circle" : "settings"}</span>
         企微群机器人：${p.webhook_ready ? "已配置" : "未配置"} · 点击配置
       </button>`,
      `<span class="wl-push-badge${p.targets.length ? " is-ok" : " is-warn"}">
         <span class="material-symbols-rounded" style="font-size:14px">groups</span>
         网格长名单：${(s.grid_cnt || 0) ? s.grid_cnt + " 个网格 / " + (s.leader_cnt || 0) + " 人" : "未上传"}
       </span>`,
      `<span class="wl-push-badge${(p.summary.pushed_grid_cnt || 0) ? " is-ok" : ""}">
         已推 ${p.summary.pushed_grid_cnt || 0} 网格
       </span>`,
      `<span class="wl-push-badge">批次 #${(p.batch && p.batch.id) || "—"} · ${escHtml(p.data_date || "—")}</span>`,
    ];
    el.innerHTML = badges.join("");
  }

  function renderPushSummary(p) {
    const el = pushEl("wl-push-summary");
    if (!el) return;
    const s = p.summary || {};
    const items = [
      { label: "可推网格", value: s.grid_cnt || 0, unit: "个" },
      { label: "推送对象", value: s.target_cnt || 0, unit: "人" },
      { label: "覆盖弱光", value: s.weak_cnt || 0, unit: "户" },
      { label: "未匹配", value: s.unmatched_cnt || 0, unit: "小区", tone: (s.unmatched_cnt || 0) ? "p1" : "" },
    ];
    el.innerHTML = items.map((it) => `
      <div class="wl-ins-metric${it.tone ? " tone-" + it.tone : ""}">
        <div class="wl-ins-metric-label">${it.label}</div>
        <div class="wl-ins-metric-value">${it.value}<span>${it.unit}</span></div>
      </div>`).join("");
  }

  function renderPushTable() {
    const box = pushEl("wl-push-table");
    const p = pushState.preview;
    if (!box || !p) return;
    const kw = ((pushEl("wl-push-search") || {}).value || "").trim();
    const rows = (p.targets || []).filter((t) => {
      if (!kw) return true;
      return (t.grid || "").indexOf(kw) >= 0
        || (t.grid_code || "").indexOf(kw) >= 0
        || (t.leader_name || "").indexOf(kw) >= 0;
    });

    if (!rows.length) {
      box.innerHTML = `<div class="wl-ins-empty">没有可推送的网格：请先上传《弱光报表》与《责任田》，或检查搜索条件。</div>`;
      renderPushCount();
      return;
    }

    const body = rows.map((t) => {
      const on = pushState.selected.has(t.grid_code);
      const disabled = t.pushed && !pushState.force;
      return `<tr class="wl-push-row">
        <td><input type="checkbox" class="wl-push-check accent-[#2ea6ff]" data-grid="${escHtml(t.grid_code)}"
                   ${on ? "checked" : ""} ${disabled ? "disabled" : ""}></td>
        <td>${escHtml(t.grid || "—")}<div class="wl-push-sub">${escHtml(t.grid_code || "—")}</div></td>
        <td>${escHtml(t.leader_name || "—")}<div class="wl-push-sub">${escHtml(t.phone_masked || "未留手机号")}</div></td>
        <td><span class="wl-push-badge${t.source === "roster" ? "" : " is-warn"}">${PUSH_SOURCE_TEXT[t.source] || t.source}</span></td>
        <td class="wl-push-num">${t.community_cnt || 0}</td>
        <td class="wl-push-num" style="color:#ff8a8f">${t.weak_cnt || 0}</td>
        <td>${t.severe_cnt || 0} / ${t.new_cnt || 0} / ${t.sustained_cnt || 0}</td>
        <td>${t.pushed
          ? '<span class="wl-push-st st-sent">已推送</span>'
          : '<span class="wl-push-st st-pending">未推送</span>'}</td>
        <td><button class="wl-ins-select" type="button" data-grid-detail="${escHtml(t.grid_code)}"
                    style="padding:2px 8px;font-size:11px">明细</button></td>
      </tr>
      <tr class="wl-push-detail" data-detail="${escHtml(t.grid_code)}" style="display:none">
        <td colspan="9" style="white-space:normal">
          <div class="wl-push-sub">小区：${(t.communities || []).slice(0, 8).map((c) =>
            `${escHtml(c.community)}（弱光 ${c.weak_cnt} / 严重 ${c.severe_cnt}）`).join("、") || "—"}</div>
          <div class="wl-push-sub">集中 PON：${(t.pons || []).map((x) =>
            `${escHtml(x.pon)}（${x.weak_cnt} 户）`).join("；") || "—"}</div>
          <div class="wl-push-sub">重点户：${(t.samples || []).map((x) =>
            `SN尾号 ${escHtml(x.sn_tail)} / ${x.valley_power}dBm`).join("；") || "—"}</div>
        </td>
      </tr>`;
    }).join("");

    box.innerHTML = `
      <table class="data-table wl-push-table">
        <thead><tr>
          <th>选</th><th>网格</th><th>网格长</th><th>来源</th><th>小区</th>
          <th>弱光</th><th>严重/新增/持续</th><th>状态</th><th>操作</th>
        </tr></thead>
        <tbody>${body}</tbody>
      </table>`;

    box.querySelectorAll("[data-grid-detail]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tr = btn.closest("tr").nextElementSibling;
        if (tr && tr.classList.contains("wl-push-detail")) {
          tr.style.display = tr.style.display === "none" ? "table-row" : "none";
        }
      });
    });
    renderPushCount();
  }

  function renderPushCount() {
    const el = pushEl("wl-push-count");
    if (!el) return;
    const p = pushState.preview;
    if (!p) { el.textContent = ""; return; }
    const sel = Array.from(pushState.selected);
    const cnt = p.targets.filter((t) => pushState.selected.has(t.grid_code)).length;
    el.textContent = `已选 ${sel.length} 网格 / ${cnt} 个推送对象`;
  }

  function renderPushExtra(p) {
    const el = pushEl("wl-push-extra");
    if (!el) return;
    const parts = [];
    if ((p.unmatched || []).length) {
      const list = p.unmatched.slice(0, 8).map((u) =>
        `${escHtml(u.community)}（${u.weak_cnt} 户）`).join("、");
      parts.push(`<div class="wl-push-badge is-warn">未匹配小区 ${p.unmatched.length} 个：${list}
        ${p.unmatched.length > 8 ? " 等" : ""} · 请在《责任田》中补充这些小区</div>`);
    }
    if ((p.no_leader || []).length) {
      parts.push(`<div class="wl-push-badge is-warn" style="margin-top:6px">
        缺少网格长（已用责任田派生/区级兜底）：${p.no_leader.map((g) => escHtml(g.grid)).join("、")}
      </div>`);
    }
    if ((p.conflicts || []).length) {
      parts.push(`<div class="wl-push-badge is-warn" style="margin-top:6px">
        责任田存在同一小区多条记录（已按用户数取一条）：${p.conflicts.length} 个小区
      </div>`);
    }
    el.innerHTML = parts.join("");
  }

  async function uploadPushLeaders() {
    const input = pushEl("wl-push-leader-file");
    const status = pushEl("wl-push-leader-status");
    if (!input || !input.files.length) {
      if (status) status.textContent = "请先选择名单文件（CSV/Excel）";
      return;
    }
    if (status) status.textContent = "解析中…";
    const fd = new FormData();
    fd.append("file", input.files[0]);
    try {
      const res = await fetch("/api/upload_grid_leader", { method: "POST", body: fd }).then((r) => r.json());
      if (!res.ok) {
        if (status) status.textContent = "上传失败：" + (res.error || "未知错误");
        return;
      }
      const d = res.data || {};
      if (status) status.textContent = `已保存 ${d.saved || 0} 条 · ${d.grid_cnt || 0} 个网格${d.no_phone ? ` · ${d.no_phone} 条无手机号` : ""} ✓`;
      input.value = "";
      await loadPushPreview();
    } catch (e) {
      if (status) status.textContent = "请求出错：" + e.message;
    }
  }

  async function submitPush() {
    const p = pushState.preview;
    if (!p) return;
    const codes = Array.from(pushState.selected);
    if (!codes.length) { alert("请先勾选需要推送的网格"); return; }
    const targets = p.targets.filter((t) => codes.indexOf(t.grid_code) >= 0 && (pushState.force || !t.pushed));
    if (!targets.length) { alert("选中网格均已推送，如需重发请勾选「强制重推已推网格」"); return; }
    if (!confirm(`将向 ${targets.length} 个推送对象（${codes.length} 个网格）发送弱光督办消息\n数据日期：${p.data_date}\n\n确认发送？`)) return;

    const btn = pushEl("wl-push-send");
    const origin = btn ? btn.innerHTML : "";
    if (btn) { btn.disabled = true; btn.textContent = "推送中…"; }
    try {
      const res = await fetch("/api/push_trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grid_codes: codes, force: pushState.force }),
      }).then((r) => r.json());
      if (!res.ok) { alert(res.error || "推送失败"); return; }
      pushState.taskId = res.task_id;
      if (res.skipped) console.info("跳过已推网格对象数：", res.skipped);
      pollPushTask(res.task_id);
      loadPushTaskOptions(res.task_id);
    } catch (e) {
      alert("推送请求出错：" + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = origin; }
    }
  }

  function pollPushTask(taskId) {
    if (pushState.timer) clearInterval(pushState.timer);
    const tick = async () => {
      if (!pushEl("wl-push-task")) { clearInterval(pushState.timer); return; }
      try {
        const res = await fetch("/api/push_task?id=" + taskId).then((r) => r.json());
        if (!res.ok) return;
        renderPushTask(res);
        if (res.task.status !== "pending" && res.task.status !== "running") {
          clearInterval(pushState.timer);
          pushState.timer = null;
          await loadPushPreview();
          loadPushTaskOptions(taskId);
        }
      } catch (e) { /* 静默重试 */ }
    };
    tick();
    pushState.timer = setInterval(tick, 2000);
  }

  function renderPushTask(res) {
    const el = pushEl("wl-push-task");
    if (!el) return;
    const task = res.task || {};
    const rows = (res.targets || []).map((t) => `
      <tr>
        <td>${escHtml(t.grid || "—")}</td>
        <td>${escHtml(t.leader_name || "—")}<div class="wl-push-sub">${escHtml(t.phone_masked || "—")}</div></td>
        <td>${t.weak_cnt || 0}</td>
        <td><span class="wl-push-st st-${escHtml(t.status)}">${escHtml(t.status_text || t.status)}</span>
          ${t.error_msg ? `<div class="wl-push-sub" style="color:#ff7a82">${escHtml(t.error_msg)}</div>` : ""}</td>
        <td>${t.ack_at
          ? `<span class="wl-push-st st-ack">已确认 ${escHtml(t.ack_at)}</span><div class="wl-push-sub">${escHtml(t.ack_by || "")}</div>`
          : `<span class="wl-push-sub">未确认</span>`}</td>
        <td>${t.status === "failed"
          ? `<button class="wl-ins-select" type="button" data-retry="${t.id}" style="padding:2px 8px;font-size:11px">重推</button>`
          : ""}</td>
      </tr>`).join("");

    const sent = (res.targets || []).filter((t) => t.status === "sent").length;
    el.innerHTML = `
      <div class="text-xs mb-2" style="color:var(--ink-2)">
        任务 #${task.id} · <b style="color:${task.status === "done" ? "#2fe3bd" : (task.status === "failed" ? "#ff7a82" : "#ffce3a")}">
        ${PUSH_TASK_TEXT[task.status] || task.status}</b>
        · 已发送 ${sent}/${(res.targets || []).length}
        · 创建 ${escHtml(task.created_at || "")}
        ${task.finished_at ? " · 完成 " + escHtml(task.finished_at) : ""}
      </div>
      <table class="data-table wl-push-table">
        <thead><tr><th>网格</th><th>网格长</th><th>弱光</th><th>发送状态</th><th>回执</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  async function loadPushTaskOptions(selectId) {
    const sel = pushEl("wl-push-task-sel");
    if (!sel) return;
    try {
      const res = await fetch("/api/push_tasks?limit=10").then((r) => r.json());
      const tasks = res.tasks || [];
      sel.innerHTML = tasks.length
        ? tasks.map((t) => `<option value="${t.id}">#${t.id} ${escHtml(t.data_date || "")} · ${PUSH_TASK_TEXT[t.status] || t.status} (${t.sent_cnt || 0}/${t.total_targets || 0})</option>`).join("")
        : `<option value="">暂无推送任务</option>`;
      const want = selectId || (tasks.length ? tasks[0].id : null);
      if (want) { sel.value = String(want); await loadPushTask(want); }
    } catch (e) { /* 静默 */ }
  }

  async function loadPushTask(taskId) {
    if (!taskId) return;
    try {
      const res = await fetch("/api/push_task?id=" + taskId).then((r) => r.json());
      if (res.ok) renderPushTask(res);
    } catch (e) { /* 静默 */ }
  }

  async function retryPushTarget(id) {
    if (!confirm("确认重推该条消息？")) return;
    try {
      const res = await fetch("/api/push_retry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [Number(id)] }),
      }).then((r) => r.json());
      if (!res.ok) { alert(res.error || "重推失败"); return; }
      if (pushState.taskId) pollPushTask(pushState.taskId);
      else if (pushEl("wl-push-task-sel")) loadPushTask(pushEl("wl-push-task-sel").value);
    } catch (e) {
      alert("重推请求出错：" + e.message);
    }
  }

  function exportPushList() {
    const p = pushState.preview;
    const bid = p && p.batch ? p.batch.id : "";
    const a = document.createElement("a");
    a.href = "/export/push_list" + (bid ? "?batch_id=" + bid : "");
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  // ---------- 企微群机器人配置窗口 ----------
  let pushCfgKeyHandler = null;

  async function openPushConfig() {
    const mask = pushEl("wl-push-cfg-mask");
    if (!mask) return;
    mask.hidden = false;
    const status = pushEl("wl-push-cfg-status");
    if (status) { status.style.color = "var(--ink-3)"; status.textContent = "读取配置中…"; }
    try {
      const res = await fetch("/api/push_config").then((r) => r.json());
      fillPushConfig((res && res.config) || {});
      if (status) status.textContent = "";
    } catch (e) {
      if (status) { status.style.color = "#ff7a82"; status.textContent = "读取失败：" + e.message; }
    }
    if (pushCfgKeyHandler) document.removeEventListener("keydown", pushCfgKeyHandler, true);
    pushCfgKeyHandler = (ev) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        closePushConfig();
      }
    };
    document.addEventListener("keydown", pushCfgKeyHandler, true);
    const input = pushEl("wl-push-cfg-webhook");
    if (input) setTimeout(() => input.focus(), 60);
  }

  function closePushConfig() {
    const mask = pushEl("wl-push-cfg-mask");
    if (mask) mask.hidden = true;
    if (pushCfgKeyHandler) {
      document.removeEventListener("keydown", pushCfgKeyHandler, true);
      pushCfgKeyHandler = null;
    }
  }

  function fillPushConfig(c) {
    const webhook = pushEl("wl-push-cfg-webhook");
    if (webhook) {
      webhook.value = "";
      webhook.placeholder = c.webhook_set
        ? `已配置（${c.webhook_hint || "已隐藏"}），留空保存表示不修改`
        : "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...";
    }
    const hint = pushEl("wl-push-cfg-hint");
    if (hint) {
      if (c.webhook_set) {
        const src = c.source === "db" ? "页面配置" : "环境变量";
        hint.textContent = `当前生效：${c.webhook_hint || "已配置"}（来源：${src}）`;
      } else {
        hint.textContent = "尚未配置，保存后即可一键推送";
      }
    }
    const set = (id, v) => {
      const el = pushEl(id);
      if (el && v !== undefined && v !== null) el.value = v;
    };
    set("wl-push-cfg-msgtype", c.msg_type || "markdown");
    set("wl-push-cfg-interval", c.send_interval != null ? c.send_interval : 3);
    set("wl-push-cfg-deadline", c.deadline_days || 3);
    set("wl-push-cfg-escname", c.escalation_name || "");
    set("wl-push-cfg-escphone", c.escalation_phone || "");
  }

  async function savePushConfig() {
    const status = pushEl("wl-push-cfg-status");
    const payload = {
      webhook: (pushEl("wl-push-cfg-webhook") || {}).value || "",
      msg_type: (pushEl("wl-push-cfg-msgtype") || {}).value || "",
      send_interval: (pushEl("wl-push-cfg-interval") || {}).value || "",
      deadline_days: (pushEl("wl-push-cfg-deadline") || {}).value || "",
      escalation_name: (pushEl("wl-push-cfg-escname") || {}).value || "",
      escalation_phone: (pushEl("wl-push-cfg-escphone") || {}).value || "",
    };
    try {
      const res = await fetch("/api/push_config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then((r) => r.json());
      if (!res.ok) {
        if (status) { status.style.color = "#ff7a82"; status.textContent = res.error || "保存失败"; }
        return false;
      }
      if (status) { status.style.color = "#2fe3bd"; status.textContent = "已保存 ✓"; }
      fillPushConfig(res.config || {});
      await loadPushPreview();
      setTimeout(() => closePushConfig(), 500);
      return true;
    } catch (e) {
      if (status) { status.style.color = "#ff7a82"; status.textContent = "保存失败：" + e.message; }
      return false;
    }
  }

  async function testPushConfig() {
    const btn = pushEl("wl-push-cfg-test");
    const status = pushEl("wl-push-cfg-status");
    const origin = btn ? btn.innerHTML : "";
    if (btn) { btn.disabled = true; btn.textContent = "发送中…"; }
    if (status) { status.style.color = "var(--ink-3)"; status.textContent = "正在发送测试消息…"; }
    try {
      const res = await fetch("/api/push_test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          webhook: (pushEl("wl-push-cfg-webhook") || {}).value || "",
          msg_type: (pushEl("wl-push-cfg-msgtype") || {}).value || "",
        }),
      }).then((r) => r.json());
      if (status) {
        status.style.color = res.ok ? "#2fe3bd" : "#ff7a82";
        status.textContent = res.ok ? "测试消息已发送，请到群里查看 ✓" : (res.error || "发送失败");
      }
    } catch (e) {
      if (status) { status.style.color = "#ff7a82"; status.textContent = "发送失败：" + e.message; }
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = origin; }
    }
  }

  function pushEl(id) {
    return document.getElementById(id);
  }

  // ---------- 子窗口模块定义（顺序即 Tab 顺序） ----------
  const MODULES = [
    {
      key: "data",
      title: "数据中心",
      icon: "database",
      sub: "上传弱光报表 / 责任田 · 历史批次回溯 · AI 摘要",
      metric: (res) => (res.latest && res.latest.data_date) ? `数据日期 ${res.latest.data_date}` : "暂无批次",
      hint: () => "上传解析、批次日历、智能总结集中在此",
      mount: (body, res) => {
        body.innerHTML = `<div id="wl-upload-wrap"></div>`;
        mountUpload();
        renderAiSummary(res);
      },
    },
    {
      key: "person",
      title: "人员整治排行",
      icon: "groups",
      sub: "各人员名下需整治弱光户数（小区 → 责任人回填）",
      metric: (res) => `${(res.person_ranking || []).length} 位责任人`,
      hint: (res) => {
        const t = (res.person_ranking || [])[0];
        return t ? `TOP1 ${t.person} · ${t.count} 户` : "暂无人员数据，请先上传《责任田》";
      },
      mount: (body, res) => {
        body.innerHTML = `
          <div class="wl-panel-cols">
            <div id="wl-person-chart" class="wl-panel-chart" style="height:360px"></div>
            <div id="wl-person-table" class="wl-scroll"></div>
          </div>`;
        renderPersonRanking(res);
      },
    },
    {
      key: "community",
      title: "小区弱光排行",
      icon: "apartment",
      sub: "按小区聚合弱光户数、对应责任人与质差情况",
      metric: (res) => `${(res.communities || []).length} 个小区`,
      hint: (res) => {
        const t = (res.communities || [])[0];
        return t ? `TOP1 ${t.community} · ${t.weak_count} 户` : "暂无小区数据";
      },
      mount: (body, res) => {
        body.innerHTML = `
          <div id="wl-community-chart" class="wl-panel-chart" style="height:320px"></div>
          <div id="wl-community-table" class="wl-scroll"></div>`;
        renderCommunity(res);
      },
    },
    {
      key: "pon",
      title: "PON 口集中度",
      icon: "lan",
      sub: "同一 PON 口下弱光户数 ≥ 3 标红，提示分光器/主干光缆质差",
      metric: (res) => `${(res.pons || []).length} 个 PON 口`,
      hint: (res) => {
        const hot = (res.pons || []).filter((p) => p.weak_count >= 3);
        return hot.length ? `热点 ${hot.length} 个 · 最集中 ${hot[0].weak_count} 户` : "无达到预警线的 PON 口";
      },
      mount: (body, res) => {
        body.innerHTML = `
          <div id="wl-pon-chart" class="wl-panel-chart" style="height:300px"></div>
          <div class="wl-panel-footnote">弱光数 ≥ 3 户的 PON 口优先核查分光器与主干光缆</div>
          <div id="wl-pon-table" class="wl-scroll"></div>`;
        renderPon(res);
      },
    },
    {
      key: "new",
      title: "新增弱光督办",
      icon: "add_circle",
      sub: "与上一批次按网关 SN 对比判定的新增弱光，支持只看未整改",
      metric: (res) => `${(res.new_weaks_summary || {}).total || 0} 台`,
      hint: (res) => {
        const sm = res.new_weaks_summary || {};
        return `未整改 ${sm.unfixed || 0} · 涉及人员 ${sm.person_cnt || 0}`;
      },
      mount: (body, res) => {
        body.innerHTML = `
          <div class="wl-panel-toolbar">
            <div id="wl-new-summary" class="text-xs" style="color:var(--ink-3)"></div>
            <label class="flex items-center gap-2 text-xs" style="color:var(--ink-3)">
              <input type="checkbox" id="wl-unfixed-only" class="accent-[#2ea6ff]">仅看未整改
            </label>
          </div>
          <div id="wl-new-table" class="wl-scroll"></div>
          <div id="wl-new-chart" class="wl-panel-chart mt-3" style="height:240px"></div>`;
        const cb = body.querySelector("#wl-unfixed-only");
        if (cb) cb.addEventListener("change", () => renderNewWeak(res));
        renderNewWeak(res);
      },
    },
    {
      key: "sustained",
      title: "持续弱光追踪",
      icon: "autorenew",
      sub: "同一网关 SN 跨批次反复弱光：出现批次 / 未整改次数 / 持续天数",
      metric: (res) => {
        const s = res.sustained_summary || {};
        const ready = (s.batch_cnt || 0) >= (s.min_batches || 3);
        return ready ? `${s.sustained_cnt || 0} 台持续` : "批次不足";
      },
      hint: (res) => {
        const s = res.sustained_summary || {};
        const ready = (s.batch_cnt || 0) >= (s.min_batches || 3);
        if (!ready) return `需 ≥${s.min_batches || 3} 个批次（当前 ${s.batch_cnt || 0} 个）`;
        return `高频未整改 ${s.high_freq_cnt || 0} 台 · 最长 ${s.max_span_days || 0} 天`;
      },
      alert: (res) => {
        const s = res.sustained_summary || {};
        return (s.high_freq_cnt || 0) > 0;
      },
      mount: (body) => {
        body.innerHTML = `
          <div id="wl-sus-summary" class="wl-sus-summary"></div>
          <div class="wl-panel-toolbar">
            <div class="flex items-center gap-3 flex-wrap">
              <label class="flex items-center gap-2 text-xs" style="color:var(--ink-3)">
                <input type="checkbox" id="wl-sus-high" class="accent-[#2ea6ff]">仅看高频未整改
              </label>
              <select id="wl-sus-sort" class="ui-select" style="padding:6px 10px;font-size:12px">
                <option value="unfixed">按未整改次数</option>
                <option value="days">按持续天数</option>
                <option value="valley">按最低谷值</option>
              </select>
              <input id="wl-sus-search" type="search" placeholder="搜索 SN / 小区 / 人员"
                     class="ui-select" style="padding:6px 10px;font-size:12px;min-width:190px" />
            </div>
            <span id="wl-sus-count" class="text-xs" style="color:var(--ink-3)"></span>
          </div>
          <div id="wl-sus-table" class="wl-scroll wl-sus-table-wrap"></div>
          <div id="wl-sus-foot" class="wl-panel-footnote"></div>`;
        mountSustained();
      },
    },
    {
      key: "focus",
      title: "重点督办清单",
      icon: "priority_high",
      sub: "持续弱光（跨批次追踪）与严重弱光（谷值 < -30dBm）逐户清单",
      metric: (res) => {
        const s = res.sustained_summary || {};
        const l = res.latest || {};
        const ready = (s.batch_cnt || 0) >= (s.min_batches || 3);
        return `${(ready ? (s.sustained_cnt || 0) : 0) + (l.severe_cnt || 0)} 户待攻坚`;
      },
      hint: (res) => {
        const s = res.sustained_summary || {};
        const l = res.latest || {};
        return `持续 ${s.sustained_cnt || 0} · 严重 ${l.severe_cnt || 0}`;
      },
      mount: (body, res) => {
        body.innerHTML = `
          <div class="wl-panel-cols">
            <div>
              <div class="wl-mini-title">持续弱光（同一网关 SN 累计出现 ≥3 个批次）</div>
              <div id="wl-focus-sustained"></div>
            </div>
            <div>
              <div class="wl-mini-title">严重弱光（谷值 &lt; -30dBm）</div>
              <div id="wl-severe-table" class="wl-scroll"></div>
            </div>
          </div>
          <div id="wl-power-chart" class="wl-panel-chart mt-3" style="height:260px"></div>`;
        renderFocusSustained(res);
        renderPriority(res);
      },
    },
    {
      key: "push",
      title: "推送督办",
      icon: "send",
      sub: "一键推送弱光情况与整改要求至网格长（企业微信群机器人）· 回执确认",
      metric: (res) => {
        const p = res.push_summary || {};
        if (!p.enabled) return "推送已关闭";
        if (!p.webhook_ready) return "未配置通道";
        return (p.pushed_grid_cnt || 0) ? `${p.pushed_grid_cnt} 网格已推` : "未推送";
      },
      hint: (res) => {
        const p = res.push_summary || {};
        if (!p.grid_leader_cnt) return "请先上传网格长名单";
        return `名单 ${p.grid_leader_cnt} 网格 · 确认 ${p.ack_cnt || 0} · 失败 ${p.failed_cnt || 0}`;
      },
      alert: (res) => ((res.push_summary || {}).failed_cnt || 0) > 0,
      mount: (body) => mountPush(body),
    },
    {
      key: "ai",
      title: "智能总结",
      icon: "psychology",
      sub: "结构化问题清单：类别集中度 · 闭环状态 · 复发追踪 · 优先级建议",
      metric: (res) => {
        const s = res.insights_summary || {};
        if (!s.total) return "暂无问题项";
        return `${s.total} 项 · P0 ${s.p0 || 0}`;
      },
      hint: (res) => {
        const s = res.insights_summary || {};
        return `超期 ${s.overdue_cnt || 0} 台 · 复发 ${s.revived_cnt || 0} 项`;
      },
      alert: (res) => ((res.insights_summary || {}).p0 || 0) > 0,
      mount: (body, res) => {
        body.innerHTML = `
          <div id="wl-ai-summary"></div>
          <div id="wl-insight-wrap" class="wl-insight-wrap">
            <div id="wl-ins-summary" class="wl-ins-summary"></div>
            <div class="wl-panel-toolbar">
              <div class="flex items-center gap-2 flex-wrap">
                <select id="wl-ins-cat" class="wl-ins-select">
                  <option value="">全部类别</option>
                </select>
                <select id="wl-ins-pri" class="wl-ins-select">
                  <option value="">全部优先级</option>
                  <option value="P0">P0</option>
                  <option value="P1">P1</option>
                  <option value="P2">P2</option>
                  <option value="P3">P3</option>
                </select>
                <label class="flex items-center gap-2 text-xs" style="color:var(--ink-3)">
                  <input type="checkbox" id="wl-ins-revived" class="accent-[#2ea6ff]">仅看复发
                </label>
                <input id="wl-ins-search" type="search" placeholder="搜索类别 / 摘要 / 建议"
                       class="wl-ins-select" style="min-width:190px" />
              </div>
              <div class="flex items-center gap-2">
                <span id="wl-ins-count" class="text-xs" style="color:var(--ink-3)"></span>
                <button id="wl-ins-export" class="btn btn-ghost" type="button"
                        style="padding:6px 12px;font-size:12px">
                  <span class="material-symbols-rounded" style="font-size:15px">download</span>导出清单
                </button>
              </div>
            </div>
            <div id="wl-ins-table" class="wl-scroll wl-ins-table-wrap"></div>
            <div id="wl-ins-foot" class="wl-panel-footnote"></div>
          </div>`;
        renderAiSummary(res);
        mountInsights();
      },
    },
  ];

  // ---------- 入口卡 ----------
  function moduleCard(m, res) {
    let metric = "";
    let hint = "";
    let alert = false;
    try { metric = typeof m.metric === "function" ? m.metric(res) : (m.metric || ""); } catch (e) { /* 忽略 */ }
    try { hint = typeof m.hint === "function" ? m.hint(res) : (m.hint || ""); } catch (e) { /* 忽略 */ }
    try { alert = typeof m.alert === "function" ? !!m.alert(res) : false; } catch (e) { /* 忽略 */ }
    return `<button class="wl-mod-card${alert ? " is-alert" : ""}" type="button" data-open-panel="${m.key}">
      <div class="wl-mod-head">
        <span class="ic"><span class="material-symbols-rounded">${m.icon}</span></span>
        <span class="wl-mod-title">${escHtml(m.title)}</span>
        <span class="material-symbols-rounded wl-mod-arrow">arrow_forward</span>
      </div>
      <div class="wl-mod-metric">${escHtml(metric)}</div>
      <div class="wl-mod-hint">${escHtml(hint)}</div>
    </button>`;
  }

  // ---------- 智能总结（自动生成，位于日历右侧） ----------
  function renderAiSummary(res) {
    const el = document.getElementById("wl-ai-summary");
    if (!el) return;
    const s = res.ai_summary;
    if (!s || !s.title) {
      el.innerHTML = `<div class="wl-cal-wrap"><div class="text-sm" style="color:var(--ink-3)">暂无总结数据。</div></div>`;
      return;
    }
    const latest = res.latest || {};
    const dataDate = latest.data_date || "—";
    // 状态色：有新增/严重/持续问题则橙/红，否则绿
    const hasRisk = (s.problems || []).length > 0;
    const accent = hasRisk ? "#ffb454" : "#2fe3bd";
    const icon = hasRisk ? "campaign" : "verified";

    // 区块标题
    const blockTitle = (txt, ic, color) => `
      <div class="flex items-center gap-1.5 mb-1.5 text-xs font-semibold" style="color:${color};letter-spacing:.5px">
        <span class="material-symbols-rounded" style="font-size:15px">${ic}</span>${txt}
      </div>`;

    // 问题所在
    const probs = (s.problems || []).map((p) => `
      <li class="flex items-start gap-2">
        <span class="material-symbols-rounded" style="font-size:15px;color:#ff7a82">error</span>
        <span class="text-sm" style="color:var(--ink-2)">${p}</span>
      </li>`).join("");
    const probsHtml = probs ? `
      <div class="mb-2.5">
        ${blockTitle("问题所在", "report", "#ff7a82")}
        <ul class="space-y-1" style="list-style:none">${probs}</ul>
      </div>` : "";

    // 谁的片区多 / 重点责任人员
    const focusHtml = s.focus_person
      ? `<div class="mb-2.5">
           ${blockTitle("片区弱光集中（对应人员）", "group", "#ffb454")}
           <div class="text-sm" style="color:var(--ink-1)">${s.focus_person}</div>
         </div>` : "";

    // 集中整治优先级
    const priorityHtml = s.priority
      ? `<div>
           ${blockTitle("集中整治建议", "flag", "#2fe3bd")}
           <div class="text-sm font-medium" style="color:var(--ink-1)">${s.priority}</div>
         </div>` : "";

    el.innerHTML = `
      <div class="wl-cal-wrap h-full" style="max-width:none">
        <div class="wl-cal-head">
          <span class="material-symbols-rounded" style="font-size:18px;color:${accent}">${icon}</span>
          <div class="wl-cal-title" style="text-align:left">智能总结</div>
          <div class="wl-cal-legend">
            <span class="text-xs" style="color:var(--ink-3)">数据日期</span>
            <span class="wl-cal-seltag">${dataDate}</span>
          </div>
        </div>
        <div class="text-sm font-semibold mb-2.5 pb-2.5" style="color:var(--ink-1);border-bottom:1px dashed rgba(120,160,220,.16)">${s.title}</div>
        ${focusHtml}
        ${probsHtml}
        ${priorityHtml}
      </div>`;
  }

  // ---------- 人员整治排行（按对应人员） ----------
  function renderPersonRanking(res) {
    const chartEl = document.getElementById("wl-person-chart");
    const tableEl = document.getElementById("wl-person-table");
    const ranking = res.person_ranking || [];
    if (!ranking.length) {
      if (tableEl) tableEl.innerHTML = `<div class="text-sm text-center py-8" style="color:var(--ink-3)">暂无人员排行数据，请先上传《人员录》建立小区对应人员</div>`;
      if (chartEl) chartEl.innerHTML = "";
      return;
    }
    const top = ranking.slice(0, 12);
    // 柱状图：每人需整治弱光户数
    if (chartEl && window.echarts) {
      const old = window.echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = window.echarts.init(chartEl);
      const labels = top.map((p) => p.person);
      const values = top.map((p) => p.count);
      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" },
          formatter: (ps) => {
            const p = top[ps[0].dataIndex];
            return `${p.person}${p.phone ? "（" + p.phone + "）" : ""}<br/>需整治：${p.count} 户<br/>其中持续 ${p.sustained} · 严重 ${p.severe} · 新增 ${p.new}<br/>涉及小区 ${p.community_cnt} 个`;
          },
        },
        grid: { left: 50, right: 20, top: 30, bottom: 40 },
        xAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { interval: 0, rotate: 35, color: "#a9c2e6", fontSize: 11 } },
        yAxis: { type: "value", name: "户", nameTextStyle: { color: "#a9c2e6" }, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } }, minInterval: 1 },
        series: [{
          type: "bar", barMaxWidth: 26,
          data: values.map((v, i) => ({
            value: v,
            itemStyle: {
              color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "#19e0ff" },
                { offset: 1, color: "rgba(25,224,255,.2)" },
              ]),
              borderRadius: [4, 4, 0, 0],
            },
          })),
        }],
      });
      window.echartsInstances.push(chart);
    }
    // 表格：全部人员按需整治数降序
    const rows = ranking.map((p, i) => {
      const hot = p.count >= 10;
      return `<tr class="border-b ${hot ? "row-xinzhou" : ""}">
        <td class="py-1.5 font-medium" style="color:var(--ink-1)">${i + 1}. ${p.person}</td>
        <td class="py-1.5 font-semibold" style="color:${hot ? "#ff5a65" : "var(--ink-1)"}">${p.count}</td>
        <td class="py-1.5" style="color:var(--ink-3)">${p.sustained}</td>
        <td class="py-1.5" style="color:${p.severe > 0 ? "#ff5a65" : "var(--ink-3)"}">${p.severe}</td>
        <td class="py-1.5" style="color:var(--ink-2)">${p.new}</td>
        <td class="py-1.5 text-xs" style="color:var(--ink-3)">${p.community_cnt} 个</td>
        <td class="py-1.5 text-xs" style="color:var(--ink-2)">${(p.communities || []).slice(0, 2).join("、")}${(p.communities || []).length > 2 ? "…" : ""}</td>
      </tr>`;
    }).join("");
    if (tableEl) tableEl.innerHTML = `
      <table class="data-table">
        <thead><tr><th>人员</th><th>需整治</th><th>持续</th><th>严重</th><th>新增</th><th>小区数</th><th>代表小区</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ---------- 小区分布 ----------
  function renderCommunity(res) {
    const communities = res.communities || [];
    const chartEl = document.getElementById("wl-community-chart");
    const tableEl = document.getElementById("wl-community-table");
    if (!communities.length) {
      if (chartEl) chartEl.innerHTML = `<div class="text-sm text-center py-8" style="color:var(--ink-3)">暂无数据</div>`;
      return;
    }
    // 柱状图：TOP10
    if (chartEl && window.echarts) {
      const old = window.echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = window.echarts.init(chartEl);
      const top = communities.slice(0, 10);
      const labels = top.map((c) => c.community);
      const values = top.map((c) => c.weak_count);
      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" },
          formatter: (p) => {
            const c = top[p[0].dataIndex];
            return `${c.community}<br/>弱光数：${c.weak_count} 户<br/>前日：${c.prev_count} · 变化：${c.change_val}<br/>对应人员：${c.technician || "—"}<br/>质差：${c.quality_type || "无"}`;
          },
        },
        grid: { left: 50, right: 20, top: 20, bottom: 60 },
        xAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { interval: 0, rotate: 35, color: "#a9c2e6", fontSize: 11 } },
        yAxis: { type: "value", name: "户", nameTextStyle: { color: "#a9c2e6" }, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
        series: [{
          type: "bar", barMaxWidth: 30,
          data: values.map((v, i) => ({
            value: v,
            itemStyle: {
              color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: top[i].quality_type ? "#ffb454" : "#2ea6ff" },
                { offset: 1, color: "rgba(46,166,255,.25)" },
              ]),
              borderRadius: [4, 4, 0, 0],
            },
          })),
        }],
      });
      window.echartsInstances.push(chart);
    }
    // 表格：全部小区按弱光数降序
    const rows = communities.map((c, i) => {
      const chgCls = c.change_val > 0 ? "text-[#ff7a82]" : c.change_val < 0 ? "text-[#2fe3bd]" : "text-[var(--ink-3)]";
      const qt = c.quality_type;
      const qtTag = qt ? `<span class="status-pill red" style="font-size:11px;padding:1px 8px">${qt}</span>` : "";
      const rowCls = c.weak_count >= 5 ? "row-xinzhou" : "";
      const tech = c.technician || '<span style="color:var(--ink-3)">—</span>';
      return `<tr class="border-b ${rowCls}">
        <td class="py-1.5 font-medium" style="color:var(--ink-1)">${i + 1}. ${c.community}</td>
        <td class="py-1.5 font-semibold" style="color:${c.weak_count >= 5 ? "#ffb454" : "var(--ink-1)"}">${c.weak_count}</td>
        <td class="py-1.5" style="color:var(--ink-3)">${c.prev_count}</td>
        <td class="py-1.5 ${chgCls}">${c.change_val > 0 ? "+" + c.change_val : c.change_val}</td>
        <td class="py-1.5" style="color:var(--accent)">${tech}</td>
        <td class="py-1.5">${qtTag || `<span style="color:var(--ink-3)">—</span>`}</td>
      </tr>`;
    }).join("");
    if (tableEl) tableEl.innerHTML = `
      <table class="data-table">
        <thead><tr><th>小区</th><th>弱光数</th><th>前日</th><th>变化</th><th>对应人员</th><th>质差类型</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ---------- PON 口分析 ----------
  function renderPon(res) {
    const pons = res.pons || [];
    const chartEl = document.getElementById("wl-pon-chart");
    const tableEl = document.getElementById("wl-pon-table");
    if (!pons.length) {
      if (chartEl) chartEl.innerHTML = `<div class="text-sm text-center py-8" style="color:var(--ink-3)">暂无数据</div>`;
      return;
    }
    // 条形图：TOP 弱光PON
    if (chartEl && window.echarts) {
      const old = window.echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = window.echarts.init(chartEl);
      const top = pons.filter((p) => p.weak_count >= 2).slice(0, 10);
      if (!top.length) top.push(...pons.slice(0, 5));
      const labels = top.map((p) => shortPon(p.pon));
      const values = top.map((p) => p.weak_count);
      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" },
          formatter: (ps) => {
            const p = top[ps[0].dataIndex];
            return `${p.pon}<br/>弱光数：${p.weak_count} 户<br/>前日：${p.prev_count} · 变化：${p.change_val}<br/>小区：${p.community || "—"}<br/>质差：${p.quality_type || (p.weak_mark ? "是" : "无")}`;
          },
        },
        grid: { left: 60, right: 30, top: 20, bottom: 40 },
        xAxis: { type: "value", name: "户", nameTextStyle: { color: "#a9c2e6" }, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
        yAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6", fontSize: 10 } },
        series: [{
          type: "bar", barMaxWidth: 16,
          data: values.map((v, i) => ({
            value: v,
            itemStyle: {
              color: new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: v >= 3 ? "#ff5a65" : top[i].weak_mark ? "#ffb454" : "#19e0ff" },
                { offset: 1, color: "rgba(46,166,255,.3)" },
              ]),
              borderRadius: [0, 4, 4, 0],
            },
          })),
        }],
      });
      window.echartsInstances.push(chart);
    }
    // 表格
    const rows = pons.map((p) => {
      const isHot = p.weak_count >= 3;
      const chgCls = p.change_val > 0 ? "text-[#ff7a82]" : p.change_val < 0 ? "text-[#2fe3bd]" : "text-[var(--ink-3)]";
      const mark = p.weak_mark ? `<span class="status-pill red" style="font-size:11px;padding:1px 8px">质差</span>` : "";
      const rowCls = isHot ? "row-xinzhou" : "";
      return `<tr class="border-b ${rowCls}">
        <td class="py-1.5 font-medium" style="color:var(--ink-1)">${shortPon(p.pon)}</td>
        <td class="py-1.5 font-semibold" style="color:${isHot ? "#ff5a65" : "var(--ink-1)"}">${p.weak_count}${isHot ? " 🔺" : ""}</td>
        <td class="py-1.5" style="color:var(--ink-3)">${p.prev_count}</td>
        <td class="py-1.5 ${chgCls}">${p.change_val > 0 ? "+" + p.change_val : p.change_val}</td>
        <td class="py-1.5" style="color:var(--ink-2)">${p.community || "—"}</td>
        <td class="py-1.5">${mark}</td>
      </tr>`;
    }).join("");
    if (tableEl) tableEl.innerHTML = `
      <table class="data-table">
        <thead><tr><th>PON口</th><th>弱光数</th><th>前日</th><th>变化</th><th>小区</th><th>质差</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ---------- 新增弱光 ----------
  function renderNewWeak(res) {
    let newWeaks = res.new_weaks || [];
    const tableEl = document.getElementById("wl-new-table");
    const chartEl = document.getElementById("wl-new-chart");
    const cb = document.getElementById("wl-unfixed-only");
    const unfixedOnly = cb ? cb.checked : false;
    if (unfixedOnly) newWeaks = newWeaks.filter((n) => !n.is_rectified);

    // 顶部摘要（对比上次上传）
    const sm = res.new_weaks_summary || {};
    const sumEl = document.getElementById("wl-new-summary");
    if (sumEl) {
      const prev = res.prev_batch;
      sumEl.innerHTML = `（${sm.total || 0} 台 · 未整改 <b style="color:#ff5a65">${sm.unfixed || 0}</b>${prev ? " · 对比上一批次 " + prev.data_date : " · 首次导入无可比批次"}）`;
    }

    if (!newWeaks.length) {
      if (tableEl) tableEl.innerHTML = `<div class="text-sm text-center py-6" style="color:var(--ink-3)">暂无新增弱光${unfixedOnly ? "（未整改）" : ""}数据</div>`;
      if (chartEl) chartEl.innerHTML = "";
      return;
    }
    // 表格
    const rows = newWeaks.map((n, i) => {
      const days = n.weak_days != null ? n.weak_days : "-";
      const daysCls = (n.weak_days || 0) > 7 ? "text-[#ff5a65] font-semibold" : "text-[var(--ink-1)]";
      const fixTag = n.is_rectified
        ? `<span class="status-pill green" style="font-size:11px;padding:1px 8px">已整改</span>`
        : `<span class="status-pill red" style="font-size:11px;padding:1px 8px">未整改</span>`;
      const cmpTag = n.is_new_vs_prev
        ? `<span class="status-pill green" style="font-size:10px;padding:1px 6px">较上次新增</span>`
        : (n.prev_existed
            ? `<span class="status-pill yellow" style="font-size:10px;padding:1px 6px">上次已有</span>`
            : "");
      const rowCls = !n.is_rectified && (n.weak_days || 0) > 7 ? "row-xinzhou" : "";
      return `<tr class="border-b ${rowCls}">
        <td class="py-1.5 ${daysCls}">${days}</td>
        <td class="py-1.5" style="color:var(--ink-2)">${n.install_date || "—"}</td>
        <td class="py-1.5 font-mono text-xs" style="color:var(--ink-1)">${n.gateway_sn || "—"}</td>
        <td class="py-1.5" style="color:var(--ink-2)">${n.community || "—"}</td>
        <td class="py-1.5" style="color:var(--accent)">${n.technician || "—"}</td>
        <td class="py-1.5" style="color:var(--ink-2)">${n.valley_power != null ? n.valley_power : "—"}</td>
        <td class="py-1.5">${cmpTag}</td>
        <td class="py-1.5">${fixTag}</td>
      </tr>`;
    }).join("");
    if (tableEl) tableEl.innerHTML = `
      <table class="data-table">
        <thead><tr><th>弱光天数</th><th>装机日期</th><th>网关SN</th><th>小区</th><th>对应人员</th><th>谷值功率</th><th>对比上次</th><th>整改</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;

    // 天数分布柱状图
    if (chartEl && window.echarts) {
      const old = window.echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = window.echarts.init(chartEl);
      const buckets = { "1-7天": 0, "8-30天": 0, "30天以上": 0 };
      newWeaks.forEach((n) => {
        const d = n.weak_days || 0;
        if (d > 30) buckets["30天以上"]++;
        else if (d > 7) buckets["8-30天"]++;
        else buckets["1-7天"]++;
      });
      chart.setOption({
        backgroundColor: "transparent",
        title: { text: "新增弱光天数分布", left: "center", textStyle: { fontSize: 13, color: "#eaf2ff" } },
        tooltip: { trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" } },
        grid: { left: 40, right: 20, top: 40, bottom: 30 },
        xAxis: { type: "category", data: Object.keys(buckets), axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" } },
        yAxis: { type: "value", minInterval: 1, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
        series: [{
          type: "bar", barMaxWidth: 40,
          data: Object.values(buckets).map((v) => ({
            value: v,
            itemStyle: { color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "#00d3a8" }, { offset: 1, color: "rgba(0,211,168,.2)" }]), borderRadius: [4, 4, 0, 0] },
          })),
        }],
      });
      window.echartsInstances.push(chart);
    }
  }

  // ---------- 持续/严重弱光 + 光功率分布 ----------
  function renderPriority(res) {
    const sustainedEl = document.getElementById("wl-sustained-table");
    const severeEl = document.getElementById("wl-severe-table");
    const chartEl = document.getElementById("wl-power-chart");

    // 持续弱光清单
    const sustained = res.sustained_users || [];
    if (sustainedEl) {
      if (!sustained.length) {
        sustainedEl.innerHTML = `<div class="text-sm text-center py-6" style="color:var(--ink-3)">暂无持续弱光用户</div>`;
      } else {
        sustainedEl.innerHTML = `<table class="data-table">
          <thead><tr><th>网关SN</th><th>小区</th><th>谷值功率</th></tr></thead>
          <tbody>${sustained.slice(0, 15).map((s) => `<tr class="border-b">
            <td class="py-1.5 font-mono text-xs" style="color:var(--ink-1)">${s.gateway_sn || "—"}</td>
            <td class="py-1.5" style="color:var(--ink-2)">${s.community || "—"}</td>
            <td class="py-1.5" style="color:${s.valley_power < -30 ? "#ff5a65" : "var(--ink-2)"}">${s.valley_power != null ? s.valley_power : "—"}</td>
          </tr>`).join("")}</tbody>
        </table>`;
      }
    }

    // 严重弱光清单（谷值<-30dBm）
    const severe = res.severe_users || [];
    if (severeEl) {
      if (!severe.length) {
        severeEl.innerHTML = `<div class="text-sm text-center py-6" style="color:var(--ink-3)">暂无严重弱光用户</div>`;
      } else {
        severeEl.innerHTML = `<table class="data-table">
          <thead><tr><th>网关SN</th><th>小区</th><th>谷值功率</th></tr></thead>
          <tbody>${severe.slice(0, 15).map((s) => `<tr class="border-b">
            <td class="py-1.5 font-mono text-xs" style="color:var(--ink-1)">${s.gateway_sn || "—"}</td>
            <td class="py-1.5" style="color:var(--ink-2)">${s.community || "—"}</td>
            <td class="py-1.5 font-semibold" style="color:#ff5a65">${s.valley_power != null ? s.valley_power : "—"}</td>
          </tr>`).join("")}</tbody>
        </table>`;
      }
    }

    // 光功率分布直方图
    if (chartEl && window.echarts) {
      const old = window.echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = window.echarts.init(chartEl);
      const details = res.sustained_users.concat(res.severe_users);
      const buckets = {};
      (res.sustained_users || []).concat(res.severe_users || []).forEach((u) => {
        const v = u.valley_power;
        if (v == null) return;
        const key = Math.floor(v) + "~" + (Math.floor(v) + 1);
        buckets[key] = (buckets[key] || 0) + 1;
      });
      const labels = Object.keys(buckets).sort();
      const values = labels.map((k) => buckets[k]);
      chart.setOption({
        backgroundColor: "transparent",
        title: { text: "弱光用户谷值光功率分布", left: "center", textStyle: { fontSize: 13, color: "#eaf2ff" } },
        tooltip: { trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(255,90,101,.4)", textStyle: { color: "#eaf2ff" } },
        grid: { left: 40, right: 20, top: 40, bottom: 50 },
        xAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6", interval: 0, rotate: 45, fontSize: 10 } },
        yAxis: { type: "value", minInterval: 1, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
        series: [{
          type: "bar", barMaxWidth: 24,
          data: values.map((v, i) => ({
            value: v,
            itemStyle: {
              color: parseFloat(labels[i]) < -30 ? "#ff5a65" : new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "#ffb454" }, { offset: 1, color: "rgba(255,180,84,.2)" }]),
              borderRadius: [4, 4, 0, 0],
            },
          })),
        }],
      });
      window.echartsInstances.push(chart);
    }
  }

  function shortPon(pon) {
    if (!pon) return "—";
    // 取 PON 的 框/槽/端口 + OLT 名简写
    const parts = pon.split("_");
    const oltPart = pon.match(/武汉\/新洲区\/(.+?)-(OLT\d+)/);
    const oltName = oltPart ? oltPart[1] + "-" + oltPart[2] : (parts[0] || pon).slice(-30);
    const pos = parts.length > 1 ? parts[1] : "";
    return `${oltName} ${pos}`;
  }

  // ---------- 子窗口注册与入口（事件委托，视图重渲染后仍有效） ----------
  if (R.Panel) {
    MODULES.forEach((m) => R.Panel.register(m.key, {
      title: m.title,
      icon: m.icon,
      subtitle: m.sub,
      mount: m.mount,
    }));
  }

  document.addEventListener("click", (e) => {
    const btn = e.target && e.target.closest ? e.target.closest("[data-open-panel]") : null;
    if (btn && R.Panel) R.Panel.open(btn.dataset.openPanel);
  });

  R.registerView(view);
})(window.Reports);
