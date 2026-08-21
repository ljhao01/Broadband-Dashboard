/* complaint_upload.js — 重复投诉率模块（重构版）
 * 核心：上传报表→自动解析入库；重点突出新洲区（投诉数/重复投诉数/占比/排名）；
 *       月度日历切换不同日期批次；15 区排名柱状图 + 排名表。
 * 数据源统一：/api/complaint_batch?id= → {ok, batch:{id, upload_date, districts:[...], daily_details}}
 */
(function (R) {
  "use strict";

  let cpBatches = []; // [{batch_id, upload_date, stat_month, city_rate}]
  let cpCal = null; // {y, m}
  let cpDateMap = {}; // upload_date(YYYY-MM-DD) → 批次对象
  let cpSelectedDate = ""; // 当前选中日期

  // ---------- 挂载 ----------
  function renderUploadBlock(container) {
    // 直接用 innerHTML 一次性插入所有容器，避免 appendChild 时序/层级导致的 DOM 缺失
    container.classList.add("mt-4");
    container.innerHTML = `
      <div class="card mb-4">
        <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h4 class="card-title">
            <span class="ic"><span class="material-symbols-rounded">upload_file</span></span>
            报表上传
            <span class="text-xs font-normal" style="color:var(--ink-3)">《广义重投统计》Excel · 自动解析 · 武汉 15 区</span>
          </h4>
          <span id="uploadStatus" class="text-xs" style="color:var(--ink-3)"></span>
        </div>
        <div class="flex items-center gap-3 flex-wrap">
          <input id="reportFile" type="file" accept=".xlsx,.xls" class="block text-sm" style="color:var(--ink-2)"/>
          <button id="btnUpload" class="btn btn-primary">
            <span class="material-symbols-rounded" style="font-size:16px">cloud_upload</span>上传解析并保存
          </button>
          <button id="btnLoadDb" class="btn btn-ghost">
            <span class="material-symbols-rounded" style="font-size:16px">refresh</span>刷新日历
          </button>
        </div>
      </div>

      <div id="cpXinzhou" class="mb-4"></div>

      <div class="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4 items-start mb-4">
        <div id="cpCalendar" class="card"></div>
        <div id="cpAiSummary"></div>
      </div>

      <div id="reportBar" style="height:320px" class="card"></div>
      <div id="districtTable" class="mt-4"></div>`;
    bindUpload();
    // 先给柱图/排名表一个"加载中"占位，避免初次进入时大片空白
    showBarPlaceholder();
    showTablePlaceholder();
    loadCalendar(); // 进入即加载日历（异步完成后会渲染真实数据）
  }

  function showBarPlaceholder() {
    const el = document.getElementById("reportBar");
    if (!el) return;
    el.innerHTML = `<div class="card-inner flex items-center justify-center" style="height:100%">
      <div class="text-sm" style="color:var(--ink-3)">
        <span class="material-symbols-rounded" style="vertical-align:middle;animation:spin 1s linear infinite">progress_activity</span>
        加载中…
      </div>
    </div>`;
  }

  function showTablePlaceholder() {
    const el = document.getElementById("districtTable");
    if (!el) return;
    el.innerHTML = `<div class="card-inner text-sm" style="color:var(--ink-3)">加载中…</div>`;
  }

  // ---------- 上传 ----------
  function bindUpload() {
    const file = document.getElementById("reportFile");
    const btn = document.getElementById("btnUpload");
    const status = document.getElementById("uploadStatus");
    btn.addEventListener("click", async () => {
      if (!file.files.length) {
        status.textContent = "请先选择 Excel 文件";
        return;
      }
      status.textContent = "解析中…";
      const fd = new FormData();
      fd.append("file", file.files[0]);
      try {
        const res = await fetch("/api/upload_report", { method: "POST", body: fd }).then((r) => r.json());
        if (!res.ok) {
          status.textContent = "解析失败：" + (res.error || "未知错误");
          return;
        }
        const dbErr = (res.data && res.data.db_error) || "";
        if (dbErr) {
          status.textContent = "已解析但入库失败：" + dbErr;
          return;
        }
        status.textContent = "已保存 ✓";
        // 刷新日历并自动选中最新批次（loadCalendar 内部会用库中数据渲染新洲+排名+柱图）
        await loadCalendar();
        await refreshScoring();
      } catch (e) {
        status.textContent = "请求出错：" + e.message;
      }
    });

    const btnDb = document.getElementById("btnLoadDb");
    btnDb.addEventListener("click", async () => {
      await loadCalendar();
      await refreshScoring();
      status.textContent = "已刷新日历";
    });
  }

  // 只刷新顶部综合评分卡（不重建整个板块，避免闪白/空白）
  async function refreshScoring() {
    if (R.Summary && R.Summary.loadScoring) {
      try { await R.Summary.loadScoring(); } catch (e) { /* 静默 */ }
    }
  }

  // ---------- 日历数据 ----------
  async function loadCalendar() {
    try {
      const res = await fetch("/api/complaint_chart").then((r) => r.json());
      cpBatches = res.upload_calendar || [];
      cpDateMap = {};
      cpBatches.forEach((b) => {
        if (b.upload_date) cpDateMap[b.upload_date] = b;
      });
      if (cpBatches.length) {
        const lb = cpBatches[0]; // 最新批次（batch_id 降序）
        const m = String(lb.upload_date || "").match(/^(\d{4})-(\d{2})/);
        if (m) cpCal = { y: parseInt(m[1], 10), m: parseInt(m[2], 10) };
        cpSelectedDate = lb.upload_date;
      } else {
        cpCal = { y: new Date().getFullYear(), m: new Date().getMonth() + 1 };
        cpSelectedDate = "";
      }
      renderCalendar();
      if (cpSelectedDate) await loadBatchByDate(cpSelectedDate);
    } catch (e) {
      /* 静默 */
    }
  }

  // ---------- 月度日历 ----------
  const CP_WEEK = ["日", "一", "二", "三", "四", "五", "六"];

  function fmtCalDate(y, m, d) {
    return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  function renderCalendar() {
    const el = document.getElementById("cpCalendar");
    if (!el) return;
    if (!cpBatches.length) {
      el.innerHTML = `<div class="card-inner wl-cal-wrap"><div class="text-xs" style="color:var(--ink-3)">暂无历史批次，上传后可在日历中按日期查看。</div></div>`;
      return;
    }
    const { y, m } = cpCal;
    const first = new Date(y, m - 1, 1);
    const firstDow = first.getDay();
    const days = new Date(y, m, 0).getDate();
    const todayStr = fmtCalDate(new Date().getFullYear(), new Date().getMonth() + 1, new Date().getDate());

    const cells = [];
    for (let i = 0; i < firstDow; i++) cells.push("");
    for (let d = 1; d <= days; d++) cells.push(fmtCalDate(y, m, d));

    const monthPrefix = `${y}-${String(m).padStart(2, "0")}-`;
    const hasDate = {};
    Object.keys(cpDateMap).forEach((ds) => {
      if (ds.startsWith(monthPrefix)) hasDate[ds] = cpDateMap[ds];
    });

    const grid = CP_WEEK.map((w, i) => `<th class="wl-cal-week ${i === 0 || i === 6 ? "wl-cal-weekend" : ""}">${w}</th>`).join("");

    el.innerHTML = `
      <div class="card-inner wl-cal-wrap">
        <div class="wl-cal-head">
          <button class="wl-cal-nav" data-nav="-1" title="上一月"><span class="material-symbols-rounded" style="font-size:16px">chevron_left</span></button>
          <div class="wl-cal-title">${y}年 ${m}月</div>
          <button class="wl-cal-nav" data-nav="1" title="下一月"><span class="material-symbols-rounded" style="font-size:16px">chevron_right</span></button>
          <div class="wl-cal-legend">
            <span class="wl-cal-dot"></span>有数据
            <span class="wl-cal-seltag">已选</span>
            <button class="wl-cal-now" id="cpCalLatest">最新</button>
          </div>
        </div>
        <table class="wl-cal-table">
          <thead><tr>${grid}</tr></thead>
          <tbody>${chunk(cells, 7).map((row) => `<tr>${row.map((ds) => dayCell(ds, hasDate, todayStr)).join("")}</tr>`).join("")}</tbody>
        </table>
      </div>`;

    el.querySelectorAll(".wl-cal-nav").forEach((btn) =>
      btn.addEventListener("click", () => {
        const dy = parseInt(btn.dataset.nav, 10);
        let nm = cpCal.m + dy;
        let ny = cpCal.y;
        if (nm > 12) { nm = 1; ny++; }
        if (nm < 1) { nm = 12; ny--; }
        cpCal = { y: ny, m: nm };
        renderCalendar();
      })
    );
    const latestBtn = el.querySelector("#cpCalLatest");
    if (latestBtn) latestBtn.addEventListener("click", async () => {
      if (!cpBatches.length) return;
      const lb = cpBatches[0];
      cpSelectedDate = lb.upload_date;
      const mm = String(lb.upload_date || "").match(/^(\d{4})-(\d{2})/);
      if (mm) cpCal = { y: parseInt(mm[1], 10), m: parseInt(mm[2], 10) };
      renderCalendar();
      await loadBatchByDate(cpSelectedDate);
    });
    el.querySelectorAll(".wl-cal-has").forEach((td) =>
      td.addEventListener("click", async () => {
        cpSelectedDate = td.dataset.date;
        renderCalendar();
        await loadBatchByDate(cpSelectedDate);
      })
    );
  }

  function dayCell(ds, hasDate, todayStr) {
    if (!ds) return `<td></td>`;
    const d = parseInt(ds.slice(8), 10);
    const rec = hasDate[ds];
    const isToday = ds === todayStr;
    const isSel = cpSelectedDate === ds;
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

  // ---------- 核心：加载并渲染指定日期批次 ----------
  async function loadBatchByDate(dateStr) {
    const status = document.getElementById("uploadStatus");
    const rec = cpDateMap[dateStr];
    if (!rec) return;
    status.textContent = "加载批次中…";
    try {
      const res = await fetch("/api/complaint_batch?id=" + rec.batch_id).then((r) => r.json());
      if (!res.ok) {
        status.textContent = res.error || "加载失败";
        return;
      }
      const b = res.batch || {};
      const districts = b.districts || [];
      // 取上一批次（按 batch_id 倒序的 cpBatches 里当前批次的下一条；当前批次是按 batch_id 降序）
      const curIdx = cpBatches.findIndex((x) => x.batch_id === b.id);
      const prev = curIdx >= 0 && curIdx + 1 < cpBatches.length ? cpBatches[curIdx + 1] : null;
      // 渲染：新洲重点卡 + 智能总结 + 柱图 + 排名表
      renderXinzhou(b, districts, dateStr);
      renderAiSummary(b, districts, prev);
      initReportBar(districts);
      renderDistrictTable(districts);
      status.textContent = "已显示 " + (b.upload_date || dateStr) + " 批次";
      // 同步顶部主看板 KPI（聚焦新洲区）
      const xz = districts.find((d) => d.district === "新洲区") || {};
      window.dispatchEvent(new CustomEvent("complaint:batch", {
        detail: {
          batch_id: b.id,
          upload_date: b.upload_date,
          latest: {
            repeat_users: xz.repeat_users,
            total_orders: xz.total_orders,
            repeat_rate: xz.repeat_rate,
          },
        },
      }));
    } catch (err) {
      status.textContent = "加载出错：" + err.message;
    }
  }

  // 新洲区重点卡：投诉数 / 重复投诉数 / 重复投诉占比 / 排名
  function renderXinzhou(b, districts, dateStr) {
    const box = document.getElementById("cpXinzhou");
    if (!box) return;
    const xz = districts.find((d) => d.district === "新洲区") || {};
    const orders = xz.total_orders != null ? xz.total_orders : "-";
    const users = xz.repeat_users != null ? xz.repeat_users : "-";
    const rate = xz.repeat_rate != null ? xz.repeat_rate : "-";
    // 排名：重复投诉率越低越优，按升序（第 1 名 = 率最低/最优）
    const sorted = districts.slice().sort((a, b) => parseFloat(a.repeat_rate) - parseFloat(b.repeat_rate));
    const rateRank = sorted.findIndex((d) => d.district === "新洲区") + 1;
    const rankTotal = districts.length;
    // 状态色
    const rateNum = parseFloat(rate);
    const rateCls = rate === "-" ? "green" : rateNum >= 2 ? "red" : rateNum >= 0.8 ? "yellow" : "green";
    const usersCls = users === "-" ? "green" : parseInt(users) > 0 ? "red" : "green";

    box.innerHTML = `
      <div class="card">
        <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h4 class="card-title">
            <span class="ic"><span class="material-symbols-rounded" style="color:#ff9900">location_on</span></span>
            新洲区 · 重复投诉重点监控
            ${rateRank > 0 && rateRank <= 3 ? `<span class="px-2 py-0.5 rounded text-xs" style="background:rgba(255,90,101,.18);color:#ff7a82">排名第 ${rateRank} 需重点关注</span>` : ""}
          </h4>
          <span class="text-xs" style="color:var(--ink-3)">${(b.period_start || "")} ~ ${(b.period_end || "")} · ${dateStr}</span>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          ${R.kpiCard({ label: "投诉工单总数", value: orders, unit: "件", status: "green" })}
          ${R.kpiCard({ label: "重复投诉数", value: users, unit: "单", status: usersCls })}
          ${R.kpiCard({ label: "重复投诉占比", value: rate, unit: "%", status: rateCls })}
          ${R.kpiCard({ label: "重复率排名", value: rateRank > 0 ? rateRank : "-", unit: "/" + (rankTotal || "-"), status: rateRank > 0 && rateRank <= 3 ? "red" : "green", detail: "按各区重复投诉率降序" })}
        </div>
      </div>`;
  }

  // 智能总结（规则模板版；可后续接入 LLM）
  function renderAiSummary(b, districts, prev) {
    const box = document.getElementById("cpAiSummary");
    if (!box) return;
    const xz = districts.find((d) => d.district === "新洲区") || {};
    const xzRate = parseFloat(xz.repeat_rate) || 0;
    const xzUsers = parseInt(xz.repeat_users) || 0;
    const xzOrders = parseInt(xz.total_orders) || 0;
    const city = districts.find((d) => d.district === "武汉整体") || null; // 兼容：若将来有武汉整体
    const cityRate = b.city_rate != null ? parseFloat(b.city_rate) : null;

    // 排名：重复投诉率升序（越低越优），1 基
    const sorted = districts.slice().sort((a, b) => parseFloat(a.repeat_rate) - parseFloat(b.repeat_rate));
    const rankTotal = sorted.length;
    const xzRank = sorted.findIndex((d) => d.district === "新洲区") + 1;

    // 趋势：与上期对比（聚焦新洲区）
    let trend = "暂无历史批次可对比。";
    if (prev && prev.city_rate != null) {
      const prevRate = parseFloat(prev.city_rate);
      if (cityRate != null) {
        const delta = (cityRate - prevRate).toFixed(2);
        if (cityRate > prevRate) {
          trend = `武汉整体重复投诉率 ${cityRate}% (本期) vs ${prevRate}% (上期 ${prev.upload_date})，较上期 **+${delta}%**（反弹）。`;
        } else if (cityRate < prevRate) {
          trend = `武汉整体重复投诉率 ${cityRate}% (本期) vs ${prevRate}% (上期 ${prev.upload_date})，较上期 **-${Math.abs(delta)}%**（压降）。`;
        } else {
          trend = `武汉整体重复投诉率 ${cityRate}% (本期) vs ${prevRate}% (上期 ${prev.upload_date})，与上期持平。`;
        }
      }
    }

    // 问题清单（仅聚焦新洲区）
    const problems = [];
    if (xzUsers > 0) {
      problems.push(`新洲区本期有 ${xzUsers} 单重复投诉（占新洲 ${xzOrders} 件工单的 ${xzRate}%），需尽快核查整改。`);
    } else {
      problems.push(`新洲区本期无重复投诉单，重复投诉率为 ${xzRate}%。`);
    }
    if (xzRank > 0 && xzRank <= 5) {
      problems.push(`新洲区重复投诉率在武汉 15 区中排名第 ${xzRank}/${rankTotal}（率越低越优），已属前列但仍有持续投诉，需保持警觉。`);
    } else if (xzRank > 5) {
      problems.push(`新洲区重复投诉率排名第 ${xzRank}/${rankTotal}（率越低越优），仍有压降空间，建议集中整治前几名用户/小区。`);
    }

    // 责任片区/责任区：新洲区内可派单责任区
    const focusPerson = xzUsers > 0
      ? `新洲区作为重点关注区（本期 ${xzUsers} 单重复投诉），请新洲分公司督办专员牵头派单到装维一线，48 小时内回填销号。`
      : `新洲区本期无重复投诉单，请保持现有整治力度。`;

    // 整改优先级
    const priority = xzUsers > 0
      ? `①核查新洲区 ${xzUsers} 单重复投诉所属小区/账号 → ②按装维/客户经理责任片区派单 → ③核查光路/光猫/账号状态 → ④48 小时内回填销号 → ⑤下一批次对比验证压降效果。`
      : `①维持现有预防机制 → ②对新装客户加强一次性解决率 SOP → ③下一批次对照核查是否有新增反弹。`;

    // title
    const title = xzUsers > 0
      ? `【${b.upload_date || ""}】新洲区重复投诉 ${xzUsers} 单、占比 ${xzRate}%，排名第 ${xzRank}/${rankTotal}`
      : `【${b.upload_date || ""}】新洲区本期无重复投诉，排名第 ${xzRank}/${rankTotal}`;

    box.innerHTML = `
      <div class="card">
        <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h4 class="card-title">
            <span class="ic"><span class="material-symbols-rounded">auto_awesome</span></span>
            智能总结 · 新洲区重点
            <span class="text-xs font-normal" style="color:var(--ink-3)">聚焦新洲区，结合历史批次自动生成</span>
          </h4>
          <span class="text-xs px-2 py-0.5 rounded" style="background:rgba(25,224,255,.12);color:var(--accent-2)">${b.upload_date || ""}</span>
        </div>
        <p class="mb-2" style="color:var(--ink-1);font-weight:600">${title}</p>
        ${xzUsers > 0 ? `
        <div class="mb-2 px-3 py-2 rounded" style="background:rgba(255,90,101,.12);border-left:3px solid #ff5a65">
          <span style="color:var(--ink-3);font-size:12px">新洲区重复投诉单（共 ${xzUsers} 单）</span>
          <div style="color:#ff7a82;font-size:20px;font-weight:700">${xzUsers} <span style="font-size:12px;font-weight:400;color:var(--ink-2)">单 · 占新洲工单 ${xzRate}%</span></div>
          ${renderRepeatTicketList(b.repeat_tickets || [])}
        </div>` : `
        <div class="mb-2 px-3 py-2 rounded" style="background:rgba(0,211,168,.12);border-left:3px solid #00d3a8">
          <span style="color:var(--ink-3);font-size:12px">新洲区重复投诉单</span>
          <div style="color:#00d3a8;font-size:20px;font-weight:700">0 <span style="font-size:12px;font-weight:400;color:var(--ink-2)">单 · 保持良好</span></div>
        </div>`}
        <p class="text-sm mb-2" style="color:var(--ink-2)">${trend.replace(/\*\*(.+?)\*\*/g, '<strong style="color:var(--ink-1)">$1</strong>')}</p>
        ${problems.length ? `
        <div class="text-sm mb-2" style="color:var(--ink-2)">
          <div class="mb-1" style="color:var(--ink-3)">问题所在：</div>
          <ul style="list-style:none;padding-left:0">${problems.map((p) => `<li class="py-0.5" style="color:var(--ink-2)">· ${p}</li>`).join("")}</ul>
        </div>` : ""}
        <p class="text-sm mb-2" style="color:var(--ink-2)">
          <span style="color:var(--ink-3)">责任片区：</span>${focusPerson}
        </p>
        <p class="text-sm" style="color:var(--ink-2)">
          <span style="color:var(--ink-3)">整改优先级：</span>${priority}
        </p>
      </div>`;
  }

  // 新洲区重复投诉单明细列表（账号/工单号）
  function renderRepeatTicketList(tickets) {
    if (!tickets || !tickets.length) return "";
    const rows = tickets.slice(0, 8).map((t) => {
      const acct = t.account || "-";
      const tno = t.ticket_no || "";
      const dt = t.stat_date || "";
      return `<div class="flex items-center gap-2 py-1 text-xs" style="color:var(--ink-2);border-bottom:1px dashed rgba(120,160,220,.15)">
        <span class="material-symbols-rounded" style="font-size:14px;color:#ff7a82">report</span>
        <span style="color:var(--ink-1);font-family:monospace">${acct}</span>
        <span class="flex-1 text-right" style="color:var(--ink-3)">${tno}${dt ? " · " + dt : ""}</span>
      </div>`;
    }).join("");
    return `<div class="mt-2">${rows}${tickets.length > 8 ? `<div class="text-xs mt-1" style="color:var(--ink-3)">… 等 ${tickets.length} 单</div>` : ""}</div>`;
  }

  // 15 区重复投诉率柱状图
  function initReportBar(districts) {
    const el = document.getElementById("reportBar");
    if (!el) return;
    const old = echarts.getInstanceByDom(el);
    if (old) old.dispose();
    if (!districts || !districts.length) {
      el.innerHTML = `<div class="card-inner"><div class="text-sm" style="color:var(--ink-3)">暂无数据，请上传报表。</div></div>`;
      return;
    }
    const chart = echarts.init(el);
    const labels = districts.map((d) => d.district);
    const data = districts.map((d) => {
      // 只让新洲不一样颜色（橙色高亮），其他区统一蓝色
      const color = d.district === "新洲区" ? "#ff9900" : "#2ea6ff";
      return { value: parseFloat(d.repeat_rate) || 0, itemStyle: { color, borderRadius: [4, 4, 0, 0] } };
    });
    chart.setOption({
      backgroundColor: "transparent",
      title: { text: "武汉各区重复投诉率(%)", left: "center", textStyle: { fontSize: 14, color: "#eaf2ff" } },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" },
        formatter: (p) => {
          const d = districts[p[0].dataIndex];
          return `${d.district}<br/>重复投诉率：${d.repeat_rate}%<br/>重复投诉数：${d.repeat_users} 单<br/>投诉工单总数：${d.total_orders} 件`;
        },
      },
      grid: { left: 50, right: 20, top: 50, bottom: 80 },
      xAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { interval: 0, rotate: 45, color: "#a9c2e6" } },
      yAxis: { type: "value", name: "%", nameTextStyle: { color: "#a9c2e6" }, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
      series: [{ type: "bar", data, barMaxWidth: 36 }],
    });
    window.echartsInstances.push(chart);
  }

  // 15 区排名表
  function renderDistrictTable(districts) {
    const box = document.getElementById("districtTable");
    if (!box) return;
    if (!districts || !districts.length) {
      box.innerHTML = "";
      return;
    }
    const sorted = districts.slice().sort((a, b) => parseFloat(a.repeat_rate) - parseFloat(b.repeat_rate));
    const rows = sorted.map((d, i) => {
      const rank = i + 1;
      const rate = parseFloat(d.repeat_rate) || 0;
      const isXz = d.district === "新洲区";
      const rateColor = isXz
        ? "text-[#ffb454] font-bold"
        : rate >= 2
        ? "text-[#ff7a82] font-semibold"
        : rate >= 0.8
        ? "text-[#ffce3a]"
        : "text-[var(--ink-2)]";
      // 行底色：新洲用更柔和的橙色调，避免遮盖数字
      const rowBg = isXz ? "style=\"background:rgba(255,153,0,.08)\"" : "";
      const tag = isXz ? `<span class="ml-2 px-1.5 py-0.5 rounded text-xs" style="background:rgba(255,153,0,.18);color:#ffb454">重点关注</span>` : "";
      // 列顺序：排名 | 区域 | 重复投诉率 | 重复投诉数 | 投诉工单总数
      // （重复投诉数紧邻重复投诉率，语义一致；投诉工单总数放最后）
      return `<tr class="border-b" ${rowBg}>
        <td class="py-1.5 font-medium" style="color:var(--ink-1)">${rank}</td>
        <td class="py-1.5 font-medium" style="color:var(--ink-1)">${d.district}${tag}</td>
        <td class="py-1.5 ${rateColor}">${d.repeat_rate != null ? d.repeat_rate + "%" : "-"}</td>
        <td class="py-1.5" style="color:${isXz ? '#ffb454' : 'var(--ink-2)'};${isXz ? 'font-weight:bold' : ''}">${d.repeat_users != null ? d.repeat_users : "-"}</td>
        <td class="py-1.5" style="color:var(--ink-2)">${d.total_orders != null ? d.total_orders : "-"}</td>
      </tr>`;
    }).join("");

    box.innerHTML = `
      <div class="card">
        <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">table_chart</span></span>武汉 15 区重复投诉排名（重复投诉率越低越优，新洲高亮）</div>
        <table class="data-table">
          <thead><tr>
            <th>排名</th>
            <th>区域</th>
            <th>重复投诉率</th>
            <th>重复投诉数</th>
            <th>投诉工单总数</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  R.ComplaintUpload = { mount: renderUploadBlock };
})(window.Reports);
