/* weaklight_upload.js — 弱光报表上传、留存与批次切换
 * 支持《存量及新增弱光》Excel 一键上传解析，自动落库并刷新看板。
 */
(function (R) {
  "use strict";

  let lastResult = null;
  let wlBatches = []; // 全部历史批次（含 data_date）
  let wlCal = null; // 日历当前年月 {y, m}（m 1-12）
  let wlDateMap = {}; // data_date(YYYY-MM-DD) → 该日期最新批次对象

  function renderUploadBlock(container) {
    const block = document.createElement("div");
    block.className = "card mb-4";
    block.innerHTML = `
      <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h4 class="card-title">
          <span class="ic"><span class="material-symbols-rounded">upload_file</span></span>
          上传弱光报表
          <span class="text-xs font-normal" style="color:var(--ink-3)">《存量及新增弱光》Excel · 自动识别新洲区 · 每日留存</span>
        </h4>
        <span id="wl-period" class="text-xs" style="color:var(--ink-3)"></span>
      </div>
      <div class="flex items-center gap-3 flex-wrap">
        <input id="wlFile" type="file" accept=".xlsx,.xls" class="block text-sm" style="color:var(--ink-2)"/>
        <button id="btnWlUpload" class="btn btn-primary">
          <span class="material-symbols-rounded" style="font-size:16px">cloud_upload</span>上传解析并保存
        </button>
        <span id="wlUploadStatus" class="text-xs" style="color:var(--ink-3)"></span>
      </div>
      <div id="wlCalendarRow" class="mt-3 grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4 items-start">
        <div id="wlCalendar"></div>
        <div id="wl-ai-summary"></div>
      </div>
      <div id="wlUploadResult" class="mt-4"></div>
      <div class="mt-3 pt-3 border-t" style="border-color:var(--panel-border)">
        <div class="flex items-center gap-3 flex-wrap">
          <input id="wlPersonFile" type="file" accept=".xlsx,.xls" class="block text-sm" style="color:var(--ink-2)"/>
          <button id="btnWlPersonUpload" class="btn btn-ghost" style="border-color:rgba(46,166,255,.4);color:var(--accent)">
            <span class="material-symbols-rounded" style="font-size:16px">person_add</span>上传人员录（小区→对应人员）
          </button>
          <span id="wlPersonStatus" class="text-xs" style="color:var(--ink-3)"></span>
        </div>
        <p class="text-xs mt-1" style="color:var(--ink-3)">用于看板「小区对应人员」「人员整治排行」：需含「姓名/网格」与「小区名称/装机人员清单」两表。</p>
      </div>`;
    container.appendChild(block);
    bindUpload();
    loadBatches(); // 进入即加载历史批次
  }

  function bindUpload() {
    const file = document.getElementById("wlFile");
    const btn = document.getElementById("btnWlUpload");
    const status = document.getElementById("wlUploadStatus");
    btn.addEventListener("click", async () => {
      if (!file.files.length) {
        status.textContent = "请先选择 Excel 文件";
        return;
      }
      status.textContent = "解析中…";
      const fd = new FormData();
      fd.append("file", file.files[0]);
      try {
        const res = await fetch("/api/upload_weaklight", { method: "POST", body: fd }).then((r) => r.json());
        if (!res.ok) {
          status.textContent = "解析失败：" + (res.error || "未知错误");
          return;
        }
        lastResult = res.data;
        const sm = res.data.summary || {};
        status.textContent = "已保存至数据库 ✓";
        renderResult(res.data);
        loadBatches();
        // 刷新看板主体
        const v = R.views.find((x) => x.id === "weaklight");
        if (v) await v.load();
      } catch (e) {
        status.textContent = "请求出错：" + e.message;
      }
    });

    // 人员录上传
    const personFile = document.getElementById("wlPersonFile");
    const btnPerson = document.getElementById("btnWlPersonUpload");
    const personStatus = document.getElementById("wlPersonStatus");
    btnPerson.addEventListener("click", async () => {
      if (!personFile.files.length) {
        personStatus.textContent = "请先选择《人员录》Excel 文件";
        return;
      }
      personStatus.textContent = "解析中…";
      const fd = new FormData();
      fd.append("file", personFile.files[0]);
      try {
        const res = await fetch("/api/upload_weaklight_person", { method: "POST", body: fd }).then((r) => r.json());
        if (!res.ok) {
          personStatus.textContent = "解析失败：" + (res.error || "未知错误");
          return;
        }
        const d = res.data || {};
        personStatus.textContent = `已保存：小区映射 ${d.count || 0} 条 · 人员 ${(d.personnel || []).length} 人 ✓`;
        // 刷新看板主体（回填对应人员 + 人员排行）
        const v = R.views.find((x) => x.id === "weaklight");
        if (v) await v.load();
      } catch (e) {
        personStatus.textContent = "请求出错：" + e.message;
      }
    });
  }

  async function loadBatches() {
    try {
      const res = await fetch("/api/weaklight_batches").then((r) => r.json());
      const batches = res.batches || [];
      wlBatches = batches;
      // 建立 日期 → 该日期最新批次 映射（按创建时间倒序，取第一个）
      wlDateMap = {};
      batches.forEach((b) => {
        if (b.data_date && wlDateMap[b.data_date] === undefined) {
          wlDateMap[b.data_date] = b;
        }
      });
      // 默认定位到有数据的最新月份
      if (batches.length) {
        const lb = batches[0];
        const m = String(lb.data_date || "").match(/^(\d{4})-(\d{2})/);
        if (m) wlCal = { y: parseInt(m[1], 10), m: parseInt(m[2], 10) };
        const periodEl = document.getElementById("wl-period");
        if (periodEl) periodEl.textContent = `已留存 ${batches.length} 个批次 · 最新 #${lb.id} ${lb.data_date} · 弱光 ${lb.weak_total} 户 · 上传于 ${lb.upload_date}`;
      } else {
        wlCal = { y: new Date().getFullYear(), m: new Date().getMonth() + 1 };
      }
      renderCalendar();
    } catch (e) {
      /* 静默 */
    }
  }

  // ---------- 月度小日历：点击日期切换历史批次 ----------
  const WL_WEEK = ["日", "一", "二", "三", "四", "五", "六"];

  function fmtCalDate(y, m, d) {
    return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  function renderCalendar() {
    const el = document.getElementById("wlCalendar");
    if (!el) return;
    if (!wlBatches.length) {
      el.innerHTML = `<div class="text-xs" style="color:var(--ink-3)">暂无历史批次，上传后可在日历中按日期查看。</div>`;
      return;
    }
    const { y, m } = wlCal;
    // 当月第一天与天数
    const first = new Date(y, m - 1, 1);
    const daysInMonth = new Date(y, m, 0).getDate();
    const lead = first.getDay(); // 0=周日
    const todayStr = (() => {
      const t = new Date();
      return fmtCalDate(t.getFullYear(), t.getMonth() + 1, t.getDate());
    })();

    const cells = [];
    for (let i = 0; i < lead; i++) cells.push("");
    for (let d = 1; d <= daysInMonth; d++) cells.push(fmtCalDate(y, m, d));

    // 该月内有数据的日期集合
    const monthPrefix = fmtCalDate(y, m, 1).slice(0, 7);
    const hasDate = {};
    Object.keys(wlDateMap).forEach((ds) => {
      if (ds.startsWith(monthPrefix)) hasDate[ds] = wlDateMap[ds];
    });

    const grid = WL_WEEK.map((w, i) => `<th class="wl-cal-week ${i === 0 || i === 6 ? "wl-cal-weekend" : ""}">${w}</th>`).join("");

    el.innerHTML = `
      <div class="card-inner wl-cal-wrap">
        <div class="wl-cal-head">
          <button class="wl-cal-nav" data-nav="-1" title="上一月"><span class="material-symbols-rounded" style="font-size:16px">chevron_left</span></button>
          <div class="wl-cal-title">${y}年 ${m}月</div>
          <button class="wl-cal-nav" data-nav="1" title="下一月"><span class="material-symbols-rounded" style="font-size:16px">chevron_right</span></button>
          <div class="wl-cal-legend">
            <span class="wl-cal-dot"></span>有数据
            <span class="wl-cal-seltag">已选</span>
            <button class="wl-cal-now" id="wlCalLatest">最新</button>
          </div>
        </div>
        <table class="wl-cal-table">
          <thead><tr>${grid}</tr></thead>
          <tbody>${chunk(cells, 7).map((row) => `<tr>${row.map((ds) => dayCell(ds, hasDate, todayStr)).join("")}</tr>`).join("")}</tbody>
        </table>
      </div>`;

    // 绑定事件
    el.querySelectorAll(".wl-cal-nav").forEach((btn) =>
      btn.addEventListener("click", () => {
        const dy = parseInt(btn.dataset.nav, 10);
        let nm = wlCal.m + dy;
        let ny = wlCal.y;
        if (nm > 12) { nm = 1; ny++; }
        if (nm < 1) { nm = 12; ny--; }
        wlCal = { y: ny, m: nm };
        renderCalendar();
      })
    );
    const latestBtn = el.querySelector("#wlCalLatest");
    if (latestBtn) latestBtn.addEventListener("click", () => loadLatestBatch());
    el.querySelectorAll(".wl-cal-has").forEach((td) =>
      td.addEventListener("click", () => loadBatchByDate(td.dataset.date))
    );
  }

  function dayCell(ds, hasDate, todayStr) {
    if (!ds) return `<td></td>`;
    const d = parseInt(ds.slice(8), 10);
    const rec = hasDate[ds];
    const isToday = ds === todayStr;
    const isSel = lastResult && lastResult.batch && lastResult.batch.data_date === ds;
    let cls = "wl-cal-day";
    let inner = String(d);
    if (rec) {
      cls += " wl-cal-has";
      if (isSel) cls += " wl-cal-sel";
      inner = `<span class="wl-cal-dot"></span>${d}`;
    }
    if (isToday && !rec) cls += " wl-cal-today";
    return `<td class="${cls}" data-date="${ds}" ${rec ? 'style="cursor:pointer"' : ""}>${inner}</td>`;
  }

  function chunk(arr, size) {
    const out = [];
    for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
    return out;
  }

  async function loadBatchByDate(dateStr) {
    const rec = wlDateMap[dateStr];
    if (!rec) return;
    const status = document.getElementById("wlUploadStatus");
    if (status) status.textContent = "加载批次中…";
    try {
      const res = await fetch("/api/weaklight_batch?id=" + rec.id).then((r) => r.json());
      if (!res.ok) {
        if (status) status.textContent = res.error || "加载失败";
        return;
      }
      lastResult = res;
      renderResultFromBatch(res);
      if (status) status.textContent = "已显示该日期批次（历史数据不变）";
      renderCalendar(); // 更新选中高亮
    } catch (err) {
      if (status) status.textContent = "加载出错：" + err.message;
    }
  }

  async function loadLatestBatch() {
    const b = wlBatches[0];
    if (!b) return;
    await loadBatchByDate(b.data_date);
  }

  // 上传解析结果摘要
  function renderResult(data) {
    const box = document.getElementById("wlUploadResult");
    if (!box) return;
    const sm = data.summary || {};
    const avgRate = sm.avg_rate != null ? sm.avg_rate : sm.weak_rate;
    const rate = avgRate != null ? (avgRate * 100).toFixed(3) + "%" : "-";
    const kpis = [
      { label: "存量弱光", value: sm.weak_total, unit: "户", status: (sm.weak_total || 0) > 0 ? "red" : "green" },
      { label: "平均弱光率", value: avgRate != null ? (avgRate * 100).toFixed(3) : "-", unit: "%", status: "red" },
      { label: "持续弱光", value: sm.sustained_cnt, unit: "户", status: (sm.sustained_cnt || 0) > 0 ? "red" : "green" },
      { label: "质差小区户数", value: sm.poor_cell_cnt, unit: "户", status: (sm.poor_cell_cnt || 0) > 0 ? "yellow" : "green" },
      { label: "严重弱光", value: sm.severe_cnt, unit: "户", status: (sm.severe_cnt || 0) > 0 ? "red" : "green" },
      { label: "弱光PON口", value: sm.pon_cnt, unit: "个", status: "yellow" },
      { label: "新增弱光", value: sm.new_weak_cnt, unit: "台", status: (sm.new_weak_cnt || 0) > 0 ? "yellow" : "green" },
    ];
    const rateColor = avgRate != null ? (avgRate >= 0.0028 ? "text-[#ff7a82]" : "text-[#2fe3bd]") : "text-[var(--ink-2)]";
    box.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-3">
        ${kpis.map(R.kpiCard).join("")}
      </div>
      <div class="text-xs" style="color:var(--ink-3)">
        解析明细：存量弱光 <b style="color:var(--ink-1)">${(data.details || []).length}</b> 条 ·
        小区 <b style="color:var(--ink-1)">${(data.communities || []).length}</b> 个 ·
        PON口 <b style="color:var(--ink-1)">${(data.pons || []).length}</b> 个 ·
        新增 <b style="color:var(--ink-1)">${(data.new_weaks || []).length}</b> 台 ·
        企宽 <b style="color:var(--ink-1)">${(data.enterprises || []).length}</b> 户 ·
        数据日期 <b style="color:var(--accent)">${data.data_date || "-"}</b>
        ${data.db_error ? `<span style="color:#ff5a65">（${data.db_error}）</span>` : ""}
      </div>`;
  }

  // 历史批次详情摘要
  function renderResultFromBatch(res) {
    const box = document.getElementById("wlUploadResult");
    if (!box) return;
    const b = res.batch || {};
    const avgRate = b.avg_rate != null ? b.avg_rate : b.weak_rate;
    const rate = avgRate != null ? (avgRate * 100).toFixed(3) : "-";
    const ranking = res.person_ranking || [];
    const sm = res.new_weaks_summary || {};
    const rankRows = ranking.slice(0, 8).map((p, i) => `<tr class="border-b">
      <td class="py-1.5" style="color:var(--ink-1)">${i + 1}. ${p.person}</td>
      <td class="py-1.5 font-semibold" style="color:var(--ink-1)">${p.count}</td>
      <td class="py-1.5" style="color:var(--ink-3)">${p.sustained}</td>
      <td class="py-1.5" style="color:var(--ink-3)">${p.severe}</td>
    </tr>`).join("");
    box.innerHTML = `
      <div class="text-sm mb-2" style="color:var(--ink-1)">
        批次 #${b.id} · 数据日期 <b style="color:var(--accent)">${b.data_date || "-"}</b> · ${b.filename}
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${R.kpiCard({ label: "存量弱光", value: b.weak_total, unit: "户", status: "red" })}
        ${R.kpiCard({ label: "平均弱光率", value: rate, unit: "%", status: "red" })}
        ${R.kpiCard({ label: "持续弱光", value: b.sustained_cnt, unit: "户", status: "red" })}
        ${R.kpiCard({ label: "新增弱光", value: b.new_weak_cnt, unit: "台", status: "yellow" })}
      </div>
      ${ranking.length ? `
      <div class="mt-3">
        <div class="text-xs mb-1" style="color:var(--ink-3)">人员整治排行 TOP8（需整治户数）</div>
        <table class="data-table">
          <thead><tr><th>人员</th><th>需整治</th><th>持续</th><th>严重</th></tr></thead>
          <tbody>${rankRows}</tbody>
        </table>
      </div>` : ""}
      ${sm.total != null ? `<div class="text-xs mt-2" style="color:var(--ink-3)">新增弱光 ${sm.total} 台 · 未整改 ${sm.unfixed} · 较上次新增 ${sm.new_vs_prev}</div>` : ""}`;
  }

  R.WeakLightUpload = { mount: renderUploadBlock };
})(window.Reports);
