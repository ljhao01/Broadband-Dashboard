/* components.js — 公共 UI 组件（看板共享）
 * 所有函数挂载到 window.Reports 命名空间，避免污染全局作用域。
 */
window.Reports = window.Reports || {};
// 所有 ECharts 实例集中管理，便于窗口 resize 时统一 resize
window.echartsInstances = window.echartsInstances || [];
// 各看板模块在加载时即调用 R.registerView，须早于 app.js 入口
window.Reports.views = window.Reports.views || [];
window.Reports.registerView = function (v) {
  window.Reports.views.push(v);
};

(function (R) {
  "use strict";

  function statusColor(s) {
    if (s === "red") return "text-[#ff7a82]";
    if (s === "yellow") return "text-[#ffce3a]";
    return "text-[#2fe3bd]";
  }

  // 大屏深色图表主题
  const CHART_PALETTE = ["#2ea6ff", "#19e0ff", "#00d3a8", "#7c5cff", "#ffb454", "#ff7a82"];
  const CHART_AXIS = {
    axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } },
    axisLabel: { color: "#a9c2e6" },
    splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } },
  };
  // 各状态对应的 Material Symbols 图标（用于 KPI / 状态标签）
  function statusIcon(s) {
    if (s === "red") return "error";
    if (s === "yellow") return "warning";
    return "check_circle";
  }
  function statusTag(s) {
    const c =
      s === "red" ? "red" : s === "yellow" ? "yellow" : "green";
    const t = s === "red" ? "预警" : s === "yellow" ? "关注" : "正常";
    return `<span class="status-pill ${c}">
      <span class="material-symbols-rounded" style="font-size:14px">${statusIcon(s)}</span>${t}
    </span>`;
  }

  // ECharts 是否可用（CDN 不可达/离线时降级，避免整页 ReferenceError）
  function hasEcharts() {
    return typeof window.echarts !== "undefined";
  }

  // 图表不可用时的占位提示
  function chartFallback(el, msg) {
    if (!el) return;
    el.innerHTML = `<div class="flex items-center justify-center h-full text-sm" style="color:var(--ink-3)">
      <span class="material-symbols-rounded" style="font-size:18px;margin-right:6px">bar_chart</span>
      ${msg || "图表库未加载，暂不显示图表"}
    </div>`;
  }

  function _safeInit(box) {
    const el = document.getElementById(box);
    if (!el) return null;
    if (!hasEcharts()) {
      chartFallback(el);
      return null;
    }
    const ec = window.echarts;
    const old = ec.getInstanceByDom(el);
    if (old) old.dispose(); // 重绘前销毁旧实例，避免叠加/闪烁
    return ec.init(el);
  }

  function renderBar(box, labels, values, opts) {
    opts = opts || {};
    const chart = _safeInit(box);
    if (!chart) return null;
    const data = labels.map((l, i) => ({
      value: values[i],
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: opts.color || "#2ea6ff" },
          { offset: 1, color: "rgba(46,166,255,.25)" },
        ]),
      },
    }));
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" } },
      grid: { left: 50, right: 20, top: 20, bottom: 50 },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: CHART_AXIS.axisLine,
        axisLabel: { interval: 0, rotate: opts.rotate || 30, color: "#a9c2e6" },
      },
      yAxis: { type: "value", axisLine: CHART_AXIS.axisLine, axisLabel: { color: "#a9c2e6" }, splitLine: CHART_AXIS.splitLine },
      series: [{ type: "bar", data, barMaxWidth: 36 }],
    });
    echartsInstances.push(chart);
    return chart;
  }

  function renderTrend(box, labels, series, opts) {
    opts = opts || {};
    const chart = _safeInit(box);
    if (!chart) return null;
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" } },
      legend: {
        data: series.map((s) => s.name),
        textStyle: { color: "#a9c2e6", fontSize: 11 },
        itemWidth: 14, itemHeight: 8, top: 0, right: 0,
      },
      grid: opts.grid || { left: 46, right: 18, top: 34, bottom: 28 },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: opts.boundaryGap === true,
        axisLine: CHART_AXIS.axisLine,
        axisTick: { show: false },
        axisLabel: { color: "#a9c2e6", fontSize: 11, margin: 8 },
      },
      yAxis: {
        type: "value",
        name: opts.yName || "户",
        nameTextStyle: { color: "#6c87b3", fontSize: 11, padding: [0, 0, 4, -26] },
        minInterval: 1,
        axisLine: CHART_AXIS.axisLine,
        axisLabel: { color: "#a9c2e6", fontSize: 11 },
        splitLine: CHART_AXIS.splitLine,
      },
      series: series.map((s, i) => {
        const color = s.color || CHART_PALETTE[i % CHART_PALETTE.length];
        return {
          name: s.name,
          type: "line",
          smooth: true,
          connectNulls: opts.connectNulls === true,
          symbol: "circle",
          symbolSize: 7,
          showSymbol: true,
          lineStyle: { width: 2.5, color: color },
          itemStyle: { color: color },
          areaStyle: s.area === false ? undefined : {
            color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: color + "55" },
              { offset: 1, color: "transparent" },
            ]),
          },
          label: s.label === false ? undefined : {
            show: opts.labelValues === true,
            position: "top",
            color: color,
            fontSize: 11,
            fontWeight: 600,
          },
          emphasis: { focus: "series" },
          data: s.data,
        };
      }),
    });
    echartsInstances.push(chart);
    return chart;
  }

  function kpiCard(k) {
    const ic = k.icon || statusIcon(k.status);
    return `
      <div class="kpi s-${k.status || "green"}">
        <span class="material-symbols-rounded kpi-ic">${ic}</span>
        <div class="kpi-label">${k.label}</div>
        <div class="kpi-value">${k.value}${k.unit ? `<span class="u">${k.unit}</span>` : ""}</div>
        ${k.detail ? `<div class="kpi-detail">${k.detail}</div>` : ""}
      </div>`;
  }

  function section(title, status, bodyHtml, extraHead, icon) {
    return `
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <h3 class="card-title">
            <span class="ic"><span class="material-symbols-rounded">${icon || "insights"}</span></span>
            ${title} ${statusTag(status)}
          </h3>
          ${extraHead || ""}
        </div>
        ${bodyHtml}
      </div>`;
  }

  function refreshButton(view) {
    return `<button data-refresh="${view}" class="btn btn-ghost"><span class="material-symbols-rounded" style="font-size:16px">refresh</span>刷新</button>`;
  }
  function exportButton(view) {
    return `<a href="/export/${view}" class="btn btn-link"><span class="material-symbols-rounded" style="font-size:16px">download</span>导出</a>`;
  }

  R.statusColor = statusColor;
  R.statusTag = statusTag;
  R.renderBar = renderBar;
  R.renderTrend = renderTrend;
  R.kpiCard = kpiCard;
  R.section = section;
  R.refreshButton = refreshButton;
  R.exportButton = exportButton;
  R.hasEcharts = hasEcharts;
  R.chartFallback = chartFallback;
})(window.Reports);
