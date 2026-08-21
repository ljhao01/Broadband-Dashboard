/* summary.js — 顶部综合评分模块
 *  综合评分卡：5 大模块按权重 + 基准值/挑战值 线性打分
 */
(function (R) {
  "use strict";

  // ---------- 综合评分 ----------
  async function loadScoring() {
    const box = document.getElementById("score-modules");
    const totalEl = document.getElementById("score-total");
    if (!box) return;
    try {
      const res = await fetch("/api/scoring").then((r) => r.json());
      box.innerHTML = (res.modules || []).map(renderScoreCard).join("");
      if (totalEl) {
        totalEl.innerHTML = `总权重 <b style="color:var(--ink-1)">${res.total_weight}</b> ·
          加权得分 <b style="color:${scoreColor(res.total_ratio)}">${res.total_score}</b> ·
          得分率 <b style="color:${scoreColor(res.total_ratio)}">${res.total_ratio}%</b>`;
      }
    } catch (e) {
      box.innerHTML = `<div class="text-sm" style="color:var(--ink-3)">评分加载失败：${e.message}</div>`;
    }
  }

  function renderScoreCard(m) {
    const cur = m.current == null ? "-" : m.current;
    const base = m.base_value;
    const challenge = m.challenge_value;
    const isHigh = m.good_is_high === 1;
    const direction = isHigh ? "↑越高越好" : "↓越低越好";
    const pct = Math.max(0, Math.min(100, m.ratio || 0));
    const barColor = m.status === "excellent" ? "var(--accent-3)"
                    : m.status === "below_base" ? "#ff5a65"
                    : "var(--accent)";

    return `
      <div class="card" style="padding:14px 16px">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span class="material-symbols-rounded" style="color:var(--accent)">${iconFor(m.indicator)}</span>
            <div class="text-sm font-semibold" style="color:var(--ink-1)">${m.label}</div>
          </div>
          <span class="text-xs px-2 py-0.5 rounded" style="background:rgba(46,166,255,.12);color:var(--accent)">权重 ${m.weight}</span>
        </div>
        <div class="text-xs mb-2" style="color:var(--ink-3)">${m.period} · ${direction}</div>
        <div class="grid grid-cols-3 gap-2 text-center mb-2">
          <div>
            <div class="text-xs" style="color:var(--ink-3)">当前值</div>
            <div class="text-lg font-bold" style="color:${scoreColor(pct)}">${cur}${m.unit || ""}</div>
          </div>
          <div>
            <div class="text-xs" style="color:var(--ink-3)">基准值</div>
            <div class="text-sm" style="color:var(--ink-2)">${base}</div>
          </div>
          <div>
            <div class="text-xs" style="color:var(--ink-3)">挑战值</div>
            <div class="text-sm" style="color:var(--ink-2)">${challenge}</div>
          </div>
        </div>
        <div style="height:6px;background:rgba(120,160,220,.15);border-radius:3px;overflow:hidden;margin-bottom:8px">
          <div style="height:100%;width:${pct}%;background:${barColor};transition:width .4s"></div>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-xs" style="color:var(--ink-3)">${statusText(m.status)}</span>
          <span class="text-sm font-semibold" style="color:${scoreColor(pct)}">得分 ${m.score} / ${m.weight}</span>
        </div>
      </div>`;
  }

  function iconFor(indicator) {
    return ({
      satisfaction: "sentiment_satisfied",
      workorder: "build",
      complaint: "repeat",
      fttr: "wifi",
      terminal: "router",
    })[indicator] || "insights";
  }

  function statusText(status) {
    if (status === "excellent") return "已达挑战值";
    if (status === "below_base") return "未达基准值";
    if (status === "linear") return "线性计分中";
    return "暂无数据";
  }

  function scoreColor(pct) {
    if (pct >= 90) return "var(--accent-3)";
    if (pct >= 60) return "var(--accent)";
    if (pct >= 30) return "#ffce3a";
    return "#ff7a82";
  }

  R.Summary = { loadScoring };
})(window.Reports);