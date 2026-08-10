/* complaint_upload.js — 重复投诉率报表上传、留存与按月统计 */
(function (R) {
  "use strict";

  let lastReport = null; // 防止定时刷新清空上传结果

  function renderUploadBlock(container) {
    const block = document.createElement("div");
    block.className = "mt-4 card";
    block.innerHTML = `
      <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h4 class="card-title">
          <span class="ic"><span class="material-symbols-rounded">upload_file</span></span>
          报表上传分析
          <span class="text-xs font-normal" style="color:var(--ink-3)">《广义重投统计》Excel · 仅武汉口径 · 数据永久留存、每月清零</span>
        </h4>
        <span id="upload-period" class="text-xs" style="color:var(--ink-3)"></span>
        <select id="monthSel" class="ui-select">
          <option value="">— 选择月份 —</option>
        </select>
      </div>
      <div class="flex items-center gap-3 flex-wrap">
        <input id="reportFile" type="file" accept=".xlsx,.xls" class="block text-sm" style="color:var(--ink-2)"/>
        <button id="btnUpload" class="btn btn-primary">
          <span class="material-symbols-rounded" style="font-size:16px">cloud_upload</span>上传解析并保存
        </button>
        <button id="btnLoadDb" class="btn btn-ghost">
          <span class="material-symbols-rounded" style="font-size:16px">refresh</span>刷新本月累计
        </button>
        <select id="batchSel" class="ui-select">
          <option value="">— 选择历史批次查看 —</option>
        </select>
        <span id="uploadStatus" class="text-xs" style="color:var(--ink-3)"></span>
      </div>
      <div id="reportBar" style="height:320px" class="mt-2"></div>
      <div id="districtTable" class="mt-4"></div>
      <div id="monthSummary" class="mt-4"></div>
      <div id="uploadResult" class="mt-4"></div>
      <div id="dailyChart" style="height:240px" class="mt-2"></div>`;
    container.appendChild(block);
    bindUpload();
    loadMonthSummary(); // 进入即加载本月累计，数据不再"没了"
  }

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
        const res = await fetch("/api/upload_report", { method: "POST", body: fd }).then((r) =>
          r.json()
        );
        if (!res.ok) {
          status.textContent = "解析失败：" + (res.error || "未知错误");
          return;
        }
        lastReport = res.data;
        status.textContent = "已保存至数据库 ✓";
        renderResult(res.data, res.data.period && res.data.period.label);
        initReportBar(res.data.wuhan_districts || []);
        renderDistrictTable(res.data.wuhan_districts || []);
        loadMonthSummary(); // 上传后刷新本月累计与批次列表
      } catch (e) {
        status.textContent = "请求出错：" + e.message;
      }
    });

    const btnDb = document.getElementById("btnLoadDb");
    btnDb.addEventListener("click", async () => {
      await loadMonthSummary();
      status.textContent = "已刷新本月累计";
    });

    // 月份切换：重新加载该月柱状图/明细/KPI
    document.getElementById("monthSel").addEventListener("change", (e) => {
      loadMonthSummary(e.target.value || undefined);
    });

    // 历史批次切换：查看任意批次不变明细
    document.getElementById("batchSel").addEventListener("change", async (e) => {
      const id = e.target.value;
      if (!id) return;
      status.textContent = "加载批次中…";
      try {
        const res = await fetch("/api/complaint_batch?id=" + id).then((r) => r.json());
        if (!res.ok) {
          status.textContent = res.error || "加载失败";
          return;
        }
        const b = res.batch || {};
        const label = `${b.period_start || ""} ~ ${b.period_end || ""} (上传于 ${b.upload_date || ""})`;
        renderResult(
          {
            city: {
              repeat_users: b.city_users,
              total_orders: b.city_orders,
              repeat_rate: b.city_rate,
            },
            xinzhou: (res.districts || []).find((d) => d.district === "新洲区") || {},
          },
          label
        );
        initReportBar(res.districts || []);
        renderDistrictTable(res.districts || []);
        status.textContent = "已显示该批次（数据不变）";
      } catch (err) {
        status.textContent = "加载出错：" + err.message;
      }
    });
  }

  // 加载指定月份（默认当前月）的累计 + 每日新增 + 历史批次下拉
  async function loadMonthSummary(month) {
    try {
      const url = month ? "/api/complaint_chart?month=" + encodeURIComponent(month) : "/api/complaint_chart";
      const res = await fetch(url).then((r) => r.json());
      fillMonthSelect(res.history || [], month || res.month);
      renderMonthSummary(res);
      fillBatchSelect(res.history || []);
      if (res.has_data && res.districts && res.districts.length) {
        initReportBar(res.districts);
        renderDistrictTable(res.districts);
      } else {
        const box = document.getElementById("districtTable");
        if (box) box.innerHTML = "";
      }
      // 把该月真实城市数据广播给主看板，用于刷新 KPI（重复投诉总量/占比）
      const latest = (res.has_data && res.latest) || null;
      window.dispatchEvent(
        new CustomEvent("complaint:month", {
          detail: { month: res.month, latest },
        })
      );
    } catch (e) {
      /* 静默失败，避免阻塞主看板 */
    }
  }

  function renderMonthSummary(res) {
    const box = document.getElementById("monthSummary");
    if (!res.has_data) {
      box.innerHTML = `<div class="text-sm" style="color:var(--ink-3)">本月暂无上传记录，上传后数据将永久留存于此（每月自动清零重新累计）。</div>`;
      return;
    }
    const latest = res.latest || {};
    box.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        ${R.kpiCard({
          label: `${res.month} 累计上传批次`,
          value: res.batch_count,
          unit: "批",
          status: "green",
        })}
        ${R.kpiCard({
          label: "本月最新·武汉重复投诉率",
          value: latest.city_rate != null ? latest.city_rate : "-",
          unit: "%",
          status: latest.city_rate >= 2 ? "red" : latest.city_rate >= 0.8 ? "yellow" : "green",
        })}
        ${R.kpiCard({
          label: "本月最新·重复投诉用户",
          value: latest.city_users != null ? latest.city_users : "-",
          unit: "人",
          status: "green",
        })}
        ${R.kpiCard({
          label: "本月最新·投诉工单",
          value: latest.city_orders != null ? latest.city_orders : "-",
          unit: "件",
          status: "green",
        })}
      </div>`;
    // 每日新增趋势
    const daily = res.daily_new || [];
    const el = document.getElementById("dailyChart");
    if (daily.length) {
      const chart = echarts.init(el);
      chart.setOption({
        title: { text: `${res.month} 每日新增批次`, left: "center", textStyle: { fontSize: 13 } },
        tooltip: { trigger: "axis" },
        grid: { left: 40, right: 20, top: 40, bottom: 50 },
        xAxis: { type: "category", data: daily.map((d) => d.date.slice(5)), axisLabel: { interval: 0, rotate: 30 } },
        yAxis: { type: "value", name: "批", minInterval: 1 },
        series: [{ type: "line", smooth: true, areaStyle: {}, data: daily.map((d) => d.cnt), itemStyle: { color: "#0ea5e9" } }],
      });
      window.echartsInstances.push(chart);
    } else {
      el.innerHTML = "";
    }
  }

  function fillBatchSelect(history) {
    const sel = document.getElementById("batchSel");
    const cur = sel.value;
    sel.innerHTML =
      `<option value="">— 选择历史批次查看（${history.length}）—</option>` +
      history
        .map(
          (b) =>
            `<option value="${b.id}">#${b.id} ${b.upload_date} · ${b.period_start || ""}~${b.period_end || ""}</option>`
        )
        .join("");
    if (cur) sel.value = cur;
  }

  function fillMonthSelect(history, curMonth) {
    const sel = document.getElementById("monthSel");
    const months = Array.from(new Set((history || []).map((b) => b.stat_month).filter(Boolean))).sort().reverse();
    const cur = curMonth || sel.value || "";
    sel.innerHTML =
      `<option value="">— 选择月份（${months.length}）—</option>` +
      months.map((m) => `<option value="${m}">${m}</option>`).join("");
    if (cur) sel.value = cur;
  }

  function renderResult(res, label) {
    const box = document.getElementById("uploadResult");
    const city = res.city || {};
    const xz = res.xinzhou || {};

    document.getElementById("upload-period").textContent = label || "";

    box.innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        ${R.section(
          `武汉整体${label ? "（" + label + "）" : ""}`,
          city.status || "green",
          `<table class="data-table"><tbody>
            <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">重复投诉用户</td><td class="py-1 font-semibold">${city.repeat_users ?? "-"}</td></tr>
            <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">投诉工单总数</td><td class="py-1 font-semibold">${city.total_orders ?? "-"}</td></tr>
            <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">重复投诉率</td><td class="py-1 ${R.statusColor(
              city.status
            )} font-semibold">${city.repeat_rate != null ? city.repeat_rate + "%" : "-"}</td></tr>
          </tbody></table>`,
          "",
          "public"
        )}
        ${R.section(
          "重点：新洲区",
          xz.status || "green",
          `<table class="data-table"><tbody>
            <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">重复投诉用户</td><td class="py-1 font-semibold">${xz.repeat_users ?? "-"}</td></tr>
            <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">投诉工单总数</td><td class="py-1 font-semibold">${xz.total_orders ?? "-"}</td></tr>
            <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">重复投诉率</td><td class="py-1 ${R.statusColor(
              xz.status
            )} font-semibold">${xz.repeat_rate != null ? xz.repeat_rate + "%" : "-"}</td></tr>
          </tbody></table>`,
          `<span class="px-1.5 py-0.5 rounded text-xs bg-orange-100 text-orange-700 font-medium">重点关注</span>`,
          "flag"
        )}
      </div>`;
  }

  function initReportBar(districts) {
    if (!districts.length) return;
    const el = document.getElementById("reportBar");
    if (!el) return;
    const old = echarts.getInstanceByDom(el);
    if (old) old.dispose();
    const chart = echarts.init(el);
    const labels = districts.map((d) => d.district);
    const data = districts.map((d) => {
      const rate = parseFloat(d.repeat_rate) || 0;
      let color = "#2ea6ff";
      if (d.district === "新洲区") color = "#ff9900";
      else if (rate >= 2) color = "#ff5a65";
      else if (rate >= 0.8) color = "#ffc107";
      return { value: rate, itemStyle: { color, borderRadius: [4, 4, 0, 0] } };
    });
    chart.setOption({
      backgroundColor: "transparent",
      title: { text: "武汉各区重复投诉率(%)", left: "center", textStyle: { fontSize: 14, color: "#eaf2ff" } },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(46,166,255,.4)", textStyle: { color: "#eaf2ff" },
        formatter: (p) => {
          const i = p[0].dataIndex;
          const d = districts[i];
          return `${d.district}<br/>重复投诉率：${d.repeat_rate}%<br/>重复用户：${d.repeat_users}<br/>工单总数：${d.total_orders}`;
        },
      },
      grid: { left: 50, right: 20, top: 50, bottom: 80 },
      xAxis: { type: "category", data: labels, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { interval: 0, rotate: 45, color: "#a9c2e6" } },
      yAxis: { type: "value", name: "%", nameTextStyle: { color: "#a9c2e6" }, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
      series: [{ type: "bar", data, barMaxWidth: 36 }],
    });
    window.echartsInstances.push(chart);
  }

  function renderDistrictTable(districts) {
    const box = document.getElementById("districtTable");
    if (!box) return;
    if (!districts || !districts.length) {
      box.innerHTML = "";
      return;
    }
    const rows = districts
      .slice()
      .sort((a, b) => parseFloat(b.repeat_rate) - parseFloat(a.repeat_rate))
      .map((d) => {
        const rate = parseFloat(d.repeat_rate) || 0;
        const isXz = d.district === "新洲区";
        const rateColor = isXz
          ? "text-[#ffb454] font-bold"
          : rate >= 2
          ? "text-[#ff7a82] font-semibold"
          : rate >= 0.8
          ? "text-[#ffce3a]"
          : "text-[var(--ink-2)]";
        const rowBg = isXz ? "row-xinzhou" : "";
        const tag = isXz ? `<span class="ml-2 px-1.5 py-0.5 rounded text-xs" style="background:rgba(255,153,0,.18);color:#ffb454">重点关注</span>` : "";
        return `<tr class="border-b ${rowBg}">
          <td class="py-1.5 font-medium" style="color:var(--ink-1)">${d.district}${tag}</td>
          <td class="py-1.5 ${rateColor}">${d.repeat_rate != null ? d.repeat_rate + "%" : "-"}</td>
          <td class="py-1.5" style="color:var(--ink-2)">${d.repeat_users != null ? d.repeat_users : "-"}</td>
          <td class="py-1.5" style="color:var(--ink-2)">${d.total_orders != null ? d.total_orders : "-"}</td>
        </tr>`;
      })
      .join("");
    box.innerHTML = `
      <div class="card">
        <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">table_chart</span></span>武汉各区明细（按重复投诉率降序）</div>
        <table class="data-table">
          <thead><tr>
            <th>区域</th>
            <th>重复投诉率</th>
            <th>重复投诉用户</th>
            <th>投诉工单总数</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${renderRepeatTickets(districts)}`;
  }

  // 最下方：列出存在重复投诉的区（即重复投诉的单子），新洲高亮
  function renderRepeatTickets(districts) {
    const tickets = (districts || [])
      .filter((d) => (parseInt(d.repeat_users) || 0) > 0)
      .sort((a, b) => parseInt(b.repeat_users) - parseInt(a.repeat_users));
    if (!tickets.length) {
      return `<div class="mt-4 card" style="background:rgba(46,166,255,.06)">
        本月无重复投诉单。
      </div>`;
    }
    const rows = tickets
      .map((d) => {
        const isXz = d.district === "新洲区";
        const rowBg = isXz ? "row-xinzhou" : "";
        const tag = isXz ? `<span class="ml-2 px-1.5 py-0.5 rounded text-xs" style="background:rgba(255,153,0,.18);color:#ffb454">重点关注</span>` : "";
        return `<tr class="border-b ${rowBg}">
          <td class="py-1.5 font-medium" style="color:var(--ink-1)">${d.district}${tag}</td>
          <td class="py-1.5" style="color:var(--ink-2)">${d.repeat_users}</td>
          <td class="py-1.5" style="color:var(--ink-2)">${d.total_orders != null ? d.total_orders : "-"}</td>
          <td class="py-1.5 ${isXz ? "text-[#ffb454] font-bold" : "text-[var(--ink-2)]"}">${d.repeat_rate != null ? d.repeat_rate + "%" : "-"}</td>
        </tr>`;
      })
      .join("");
    return `<div class="mt-4 card">
      <div class="card-title mb-3"><span class="ic"><span class="material-symbols-rounded">priority_high</span></span>重复投诉的单子（共 ${tickets.length} 个区有重复投诉）</div>
      <table class="data-table">
        <thead><tr>
          <th>区域</th>
          <th>重复投诉用户(单)</th>
          <th>投诉工单总数</th>
          <th>重复投诉率</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  R.ComplaintUpload = { mount: renderUploadBlock };
})(window.Reports);
