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
      if (!res.has_data) {
        box.innerHTML = `
          <div id="wl-upload-wrap"></div>
          <div class="card">
            <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">light_mode</span></span>弱光督办看板</div>
            <div class="text-sm py-6" style="color:var(--ink-3)">
              暂无弱光数据。请在上方「上传弱光报表」区域上传《存量及新增弱光》Excel，
              系统将自动解析新洲区数据并入库展示。
            </div>
          </div>`;
        mountUpload();
        cached = res;
        return;
      }
      cached = res;
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

  function renderDashboard(box, res) {
    const latest = res.latest || {};
    const period = latest.data_date ? `数据日期：${latest.data_date}` : "";
    const kpis = (res.kpis || []).map(R.kpiCard).join("");

    box.innerHTML = `
      <div id="wl-upload-wrap"></div>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">${kpis}</div>

      <!-- 人员整治排行（新增） -->
      <div class="card mb-4">
        <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div class="card-title"><span class="ic"><span class="material-symbols-rounded">groups</span></span>人员整治排行（按对应人员）</div>
          <span class="text-xs" style="color:var(--ink-3)">各人员名下需整治弱光户数 · 小区对应人员来自《人员录》</span>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div id="wl-person-chart" style="height:320px"></div>
          <div id="wl-person-table" class="max-h-96 overflow-auto"></div>
        </div>
      </div>

      <!-- 小区分布 + PON 口分析 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div class="card">
          <div class="flex items-center justify-between mb-3">
            <div class="card-title"><span class="ic"><span class="material-symbols-rounded">apartment</span></span>小区弱光排行</div>
            <span class="text-xs" style="color:var(--ink-3)">TOP ${(res.communities || []).length} 小区</span>
          </div>
          <div id="wl-community-chart" style="height:280px"></div>
          <div id="wl-community-table" class="mt-3 max-h-72 overflow-auto"></div>
        </div>
        <div class="card">
          <div class="flex items-center justify-between mb-3">
            <div class="card-title"><span class="ic"><span class="material-symbols-rounded">lan</span></span>PON 口集中度</div>
            <span class="text-xs" style="color:var(--ink-3)">弱光数≥3 标红预警</span>
          </div>
          <div id="wl-pon-chart" style="height:280px"></div>
          <div id="wl-pon-table" class="mt-3 max-h-72 overflow-auto"></div>
        </div>
      </div>

      <!-- 新增弱光 + 督办清单 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div class="card">
          <div class="flex items-center justify-between mb-3">
            <div class="card-title"><span class="ic"><span class="material-symbols-rounded">add_circle</span></span>新增弱光督办
              <span id="wl-new-summary" class="text-xs font-normal" style="color:var(--ink-3)"></span>
            </div>
            <label class="flex items-center gap-2 text-xs" style="color:var(--ink-3)">
              <input type="checkbox" id="wl-unfixed-only" class="accent-[#2ea6ff]">仅看未整改
            </label>
          </div>
          <div id="wl-new-table" class="max-h-80 overflow-auto"></div>
          <div id="wl-new-chart" style="height:220px" class="mt-3"></div>
        </div>
        <div class="card">
          <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">priority_high</span></span>重点督办清单</div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div class="text-xs mb-2" style="color:var(--ink-3)">持续弱光（长期未解决）</div>
              <div id="wl-sustained-table" class="max-h-64 overflow-auto"></div>
            </div>
            <div>
              <div class="text-xs mb-2" style="color:var(--ink-3)">严重弱光（谷值&lt;-30dBm）</div>
              <div id="wl-severe-table" class="max-h-64 overflow-auto"></div>
            </div>
          </div>
          <div id="wl-power-chart" style="height:240px" class="mt-3"></div>
        </div>
      </div>

      <!-- 区县统计表 -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <div class="card-title"><span class="ic"><span class="material-symbols-rounded">table_chart</span></span>区县弱光率排行</div>
          <span class="text-xs" style="color:var(--ink-3)">截止 ${latest.data_date || "—"} 存量弱光</span>
        </div>
        <div id="wl-stat-table"></div>
      </div>`;

    mountUpload();
    renderPersonRanking(res);
    renderCommunity(res);
    renderPon(res);
    renderNewWeak(res);
    renderPriority(res);
    renderStat(res);

    // 绑定未整改筛选
    const cb = document.getElementById("wl-unfixed-only");
    if (cb) cb.addEventListener("change", () => renderNewWeak(res));
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
    if (chartEl && echarts) {
      const old = echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = echarts.init(chartEl);
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
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
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
    if (chartEl && echarts) {
      const old = echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = echarts.init(chartEl);
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
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
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
    if (chartEl && echarts) {
      const old = echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = echarts.init(chartEl);
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
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
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
      sumEl.innerHTML = `（${sm.total || 0} 台 · 未整改 <b style="color:#ff5a65">${sm.unfixed || 0}</b> · 较上次新增 <b style="color:#2fe3bd">${sm.new_vs_prev || 0}</b>${prev ? "（对比 " + prev.data_date + "）" : ""}）`;
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
    if (chartEl && echarts) {
      const old = echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = echarts.init(chartEl);
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
            itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "#00d3a8" }, { offset: 1, color: "rgba(0,211,168,.2)" }]), borderRadius: [4, 4, 0, 0] },
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
    if (chartEl && echarts) {
      const old = echarts.getInstanceByDom(chartEl);
      if (old) old.dispose();
      const chart = echarts.init(chartEl);
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
              color: parseFloat(labels[i]) < -30 ? "#ff5a65" : new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "#ffb454" }, { offset: 1, color: "rgba(255,180,84,.2)" }]),
              borderRadius: [4, 4, 0, 0],
            },
          })),
        }],
      });
      window.echartsInstances.push(chart);
    }
  }

  // ---------- 区县统计（弱光率升序，越小越好；武汉整体行放最后，弱光率显示平均） ----------
  function renderStat(res) {
    const el = document.getElementById("wl-stat-table");
    let stats = res.stats || [];
    if (!stats.length) {
      if (el) el.innerHTML = `<div class="text-sm text-center py-6" style="color:var(--ink-3)">暂无统计表数据</div>`;
      return;
    }
    // 武汉汇总行单独取出（报表中可能叫 武汉/武汉市/全市），放最后一行
    const summaryNames = ["武汉", "武汉市", "全市"];
    const wuhan = stats.filter((s) => summaryNames.includes(s.district))[0] || null;
    const districts = stats.filter((s) => !summaryNames.includes(s.district));
    // 区县按弱光率升序（弱光率越小越好），无弱光率的排最后
    districts.sort((a, b) => {
      const ra = a.weak_rate != null ? a.weak_rate : Infinity;
      const rb = b.weak_rate != null ? b.weak_rate : Infinity;
      return ra - rb;
    });
    const ordered = wuhan ? districts.concat([wuhan]) : districts;

    // 数据日期提取月份：如 2026-08-17 → 8月
    let month = "";
    const dd = (res.latest && res.latest.data_date) || "";
    const m = String(dd || "").match(/^\d{4}-(\d{2})/);
    month = m ? parseInt(m[1], 10) + "月" : "本月";

    let seq = 0;
    const rows = ordered.map((s) => {
      const isXz = s.district === "新洲区";
      const isWuhan = summaryNames.includes(s.district);
      // 武汉行显示「平均弱光率」avg_rate；区县行显示自身 weak_rate
      const rateVal = isWuhan && s.avg_rate != null ? s.avg_rate : s.weak_rate;
      const rate = rateVal != null ? (rateVal * 100).toFixed(3) : "-";
      const chgCls = (s.change_count || 0) > 0 ? "text-[#ff7a82]" : (s.change_count || 0) < 0 ? "text-[#2fe3bd]" : "text-[var(--ink-3)]";
      const rowCls = isXz ? "row-xinzhou" : isWuhan ? "row-wuhan" : "";
      const tag = isXz
        ? `<span class="ml-1 px-1.5 py-0.5 rounded text-xs" style="background:rgba(255,153,0,.18);color:#ffb454">重点关注</span>`
        : isWuhan
          ? `<span class="ml-1 px-1.5 py-0.5 rounded text-xs" style="background:rgba(46,166,255,.18);color:#2ea6ff">${month}平均</span>`
          : "";
      const nameCell = isWuhan
        ? `<td class="py-1.5 font-bold" style="color:var(--accent)">武汉${tag}</td>`
        : `<td class="py-1.5 font-medium" style="color:var(--ink-1)">${++seq}. ${s.district}${tag}</td>`;
      const rateCell = isWuhan
        ? `<td class="py-1.5 font-bold" style="color:var(--accent)">${rate}<span class="text-xs font-normal" style="color:var(--ink-3)">（${month}平均弱光率）</span></td>`
        : `<td class="py-1.5" style="color:var(--ink-2)">${rate}</td>`;
      return `<tr class="border-b ${rowCls}">
        ${nameCell}
        <td class="py-1.5 font-semibold" style="color:${isXz ? "#ffb454" : "var(--ink-1)"}">${s.weak_count}</td>
        ${rateCell}
        <td class="py-1.5" style="color:var(--ink-2)">${s.active_users || "-"}</td>
        <td class="py-1.5 ${chgCls}">${s.change_count != null ? (s.change_count > 0 ? "+" + s.change_count : s.change_count) : "-"}</td>
      </tr>`;
    }).join("");
    if (el) el.innerHTML = `<table class="data-table">
      <thead><tr><th>区县（弱光率升序）</th><th>弱光数</th><th>弱光率%</th><th>活跃用户</th><th>压降数</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
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

  R.registerView(view);
})(window.Reports);
