/* complaint_upload.js — 重复投诉率报表上传、留存与按月统计
 * 支持 15 区县动态选择（默认武汉整体在前，重复投诉/占比置顶）
 */
(function (R) {
  "use strict";

  let lastReport = null; // 防止定时刷新清空上传结果
  let currentDistrict = ""; // 当前选中的区县（空=武汉整体）

  function renderUploadBlock(container) {
    const block = document.createElement("div");
    block.className = "mt-4 card";
    block.innerHTML = `
      <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h4 class="card-title">
          <span class="ic"><span class="material-symbols-rounded">upload_file</span></span>
          报表上传分析
          <span class="text-xs font-normal" style="color:var(--ink-3)">《广义重投统计》Excel · 武汉口径 · 按月存储</span>
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
      <div id="uploadResult" class="mt-4"></div>`;
    container.appendChild(block);
    bindUpload();
    loadMonthSummary(); // 进入即加载本月累计（DB 上次数据）
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
        const period = res.data.period || {};
        const label = period.start ? `${period.start} ~ ${period.end || ""}` : "";
        status.textContent = "已保存至数据库 ✓";
        renderResult(res.data, label);
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

    // 月份切换：重新加载该月全部数据
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
            latest: {
              city_users: b.city_users,
              city_orders: b.city_orders,
              city_rate: b.city_rate,
            },
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

  // 加载指定月份（默认当前月）的累计 + 各区每日趋势 + 历史批次下拉
  async function loadMonthSummary(month) {
    try {
      const url = month ? "/api/complaint_chart?month=" + encodeURIComponent(month) : "/api/complaint_chart";
      const res = await fetch(url).then((r) => r.json());
      fillMonthSelect(res.history || [], month || res.month);
      renderMonthSummary(res);
      fillBatchSelect(res.all_batches || []);
      const districts = (res.latest && res.latest.districts) || [];
      if (res.has_data && districts.length) {
        initReportBar(districts);
        renderDistrictTable(districts);
        renderResult(res, res.latest ? `${res.latest.period_start || ""} ~ ${res.latest.period_end || ""} (上传于 ${res.latest.upload_date || ""})` : "");
      } else {
        const box = document.getElementById("districtTable");
        if (box) box.innerHTML = "";
      }
      // 广播城市数据给主看板 KPI
      const latest = (res.has_data && res.latest) || null;
      window.dispatchEvent(
        new CustomEvent("complaint:month", {
          detail: { month: res.month, latest },
        })
      );
    } catch (e) {
      /* 静默失败 */
    }
  }

  // 按区县计算本月累计：
  //   - 优先从 district_daily（每日明细）汇总
  //   - 无每日明细时回退到 latest.districts（该区批次汇总）
  //   - 空 district = 武汉整体，用 latest
  function calcDistrictTotals(res, district) {
    const latest = res.latest || {};
    if (!district) {
      return {
        label: "武汉整体",
        complaints: latest.city_orders != null ? latest.city_orders : "-",
        repeats: latest.city_users != null ? latest.city_users : "-",
        rate: latest.city_rate != null ? latest.city_rate : "-",
      };
    }
    const daily = (res.district_daily && res.district_daily[district]) || [];
    if (daily.length) {
      const complaints = daily.reduce((s, d) => s + (d.complaint_count || 0), 0);
      const repeats = daily.reduce((s, d) => s + (d.repeat_count || 0), 0);
      const rate = complaints > 0 ? (repeats / complaints * 100).toFixed(2) : "0.00";
      return { label: district, complaints, repeats, rate };
    }
    // 回退：从该区批次汇总读取
    const d = (latest.districts || []).find((x) => x.district === district) || {};
    return {
      label: district,
      complaints: d.total_orders != null ? d.total_orders : "-",
      repeats: d.repeat_users != null ? d.repeat_users : "-",
      rate: d.repeat_rate != null ? d.repeat_rate : "-",
    };
  }

  function renderMonthSummary(res) {
    const box = document.getElementById("monthSummary");
    if (!res.has_data) {
      box.innerHTML = `<div class="text-sm" style="color:var(--ink-3)">本月暂无上传记录，上传 Excel 报表后自动解析并按月份存储，可在月份下拉中切换查看。</div>`;
      return;
    }
    const latest = res.latest || {};
    const dailyDistricts = (res.daily_districts || []).filter(Boolean);
    // 默认选中武汉整体；若用户已选某区则保留
    if (!currentDistrict) currentDistrict = "";

    // 武汉整体核心 KPI（重复投诉/占比置顶）
    const wuhan = calcDistrictTotals(res, "");

    // 当前选中区县 KPI
    const sel = calcDistrictTotals(res, currentDistrict);

    // 区县选择下拉（15 区从 latest.districts 取，含无每日明细的区）
    const allDistricts = (latest.districts || []).map((d) => d.district).filter(Boolean);
    const options = ["", ...allDistricts].map(
      (d) => `<option value="${d}">${d === "" ? "武汉整体" : d}</option>`
    ).join("");

    // 每日趋势容器：仅选中具体区县时展示
    const dailyTrendHtml = currentDistrict
      ? `<div id="districtDailyChart" style="height:300px" class="mt-4"></div>`
      : "";

    box.innerHTML = `
      <div class="flex items-center gap-3 mb-3 flex-wrap">
        <span class="text-sm" style="color:var(--ink-2)">数据范围：</span>
        <select id="districtSel" class="ui-select">
          ${options}
        </select>
      </div>

      <!-- 武汉整体核心指标（重复投诉 / 重复投诉占比置顶） -->
      <div class="mb-2" style="color:var(--accent-2);font-weight:600;">
        <span class="material-symbols-rounded" style="vertical-align:middle">public</span>
        武汉整体
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        ${R.kpiCard({
          label: "重复投诉总量",
          value: wuhan.repeats,
          unit: "单",
          status: wuhan.repeats === "-" ? "green" : "red",
          detail: latest.city_orders != null ? `共 ${latest.city_orders} 件工单` : "",
        })}
        ${R.kpiCard({
          label: "重复投诉占比",
          value: wuhan.rate,
          unit: "%",
          status: wuhan.rate === "-" ? "green" : parseFloat(wuhan.rate) >= 2 ? "red" : parseFloat(wuhan.rate) >= 0.8 ? "yellow" : "green",
          detail: "武汉整体重复投诉率",
        })}
        ${R.kpiCard({
          label: "投诉工单总数",
          value: wuhan.complaints,
          unit: "件",
          status: "green",
        })}
        ${R.kpiCard({
          label: "覆盖区县",
          value: allDistricts.length || "-",
          unit: "个",
          status: "green",
        })}
      </div>

      <!-- 选中区县详情 -->
      ${currentDistrict ? `
      <div class="mb-2" style="color:var(--accent);font-weight:600;">
        <span class="material-symbols-rounded" style="vertical-align:middle">location_on</span>
        ${currentDistrict} · 本月汇总
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        ${R.kpiCard({ label: `${currentDistrict} · 本月投诉总量`, value: sel.complaints, unit: "件", status: sel.complaints > 0 ? "yellow" : "green" })}
        ${R.kpiCard({ label: `${currentDistrict} · 本月重复投诉量`, value: sel.repeats, unit: "件", status: sel.repeats > 0 ? "red" : "green" })}
        ${R.kpiCard({ label: `${currentDistrict} · 重复投诉率`, value: sel.rate, unit: "%", status: parseFloat(sel.rate) >= 2 ? "red" : parseFloat(sel.rate) >= 0.8 ? "yellow" : "green" })}
      </div>
      ${dailyTrendHtml}` : ""}`;

    // 绑定区县切换
    const dSel = document.getElementById("districtSel");
    if (dSel) {
      dSel.value = currentDistrict;
      dSel.addEventListener("change", (e) => {
        currentDistrict = e.target.value;
        renderMonthSummary(res); // 重绘，保留已加载的数据
        renderDistrictDailyChart(res, currentDistrict);
      });
    }
    // 首次进入默认武汉整体；若仅想快速看某区每日趋势，可选具体区
    if (currentDistrict) renderDistrictDailyChart(res, currentDistrict);
  }

  // 指定区县每日投诉量 + 重复投诉量趋势（双线图）
  function renderDistrictDailyChart(res, district) {
    const el = document.getElementById("districtDailyChart");
    if (!el || !district) return;
    const old = echarts.getInstanceByDom(el);
    if (old) old.dispose();

    const daily = (res.district_daily && res.district_daily[district]) || [];
    if (!daily.length) {
      el.innerHTML = `<div class="text-sm text-center py-8" style="color:var(--ink-3)">暂无 ${district} 每日明细数据</div>`;
      return;
    }
    const chart = echarts.init(el);
    const dates = daily.map((d) => d.date.slice(5));
    const complaints = daily.map((d) => d.complaint_count || 0);
    const repeats = daily.map((d) => d.repeat_count || 0);
    chart.setOption({
      backgroundColor: "transparent",
      title: { text: `${district} · 每日投诉量与重复投诉量趋势`, left: "center", textStyle: { fontSize: 14, color: "#ffb454" } },
      tooltip: { trigger: "axis", backgroundColor: "rgba(10,21,48,.9)", borderColor: "rgba(255,153,0,.4)", textStyle: { color: "#eaf2ff" } },
      legend: { data: ["投诉量", "重复投诉量"], bottom: 0, textStyle: { color: "#a9c2e6" } },
      grid: { left: 50, right: 20, top: 50, bottom: 50 },
      xAxis: { type: "category", data: dates, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { interval: 0, rotate: 30, color: "#a9c2e6" } },
      yAxis: { type: "value", name: "件", minInterval: 1, nameTextStyle: { color: "#a9c2e6" }, axisLine: { lineStyle: { color: "rgba(120,160,220,.3)" } }, axisLabel: { color: "#a9c2e6" }, splitLine: { lineStyle: { color: "rgba(120,160,220,.1)" } } },
      series: [
        { name: "投诉量", type: "line", smooth: true, data: complaints, itemStyle: { color: "#2ea6ff" }, areaStyle: { color: "rgba(46,166,255,.08)" } },
        { name: "重复投诉量", type: "line", smooth: true, data: repeats, itemStyle: { color: "#ff5a65" }, areaStyle: { color: "rgba(255,90,101,.08)" }, lineStyle: { type: "dashed" } },
      ],
    });
    window.echartsInstances.push(chart);
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

  // 渲染武汉整体汇总表；兼容两种数据源：
  //   1) 上传解析结果 res.data：{ city:{repeat_users,total_orders,repeat_rate}, wuhan_districts:[...] }
  //   2) 月度汇总 res：{ latest:{city_users,city_orders,city_rate}, districts:[...] }
  function renderResult(res, label) {
    const box = document.getElementById("uploadResult");
    if (!box) return;
    let city;
    if (res.latest) {
      city = {
        repeat_users: res.latest.city_users,
        total_orders: res.latest.city_orders,
        repeat_rate: res.latest.city_rate,
      };
    } else {
      city = res.city || {};
    }
    document.getElementById("upload-period").textContent = label || "";
    const rateColor = (city.repeat_rate ?? null) == null ? "text-[var(--ink-2)]" : city.repeat_rate >= 2 ? "text-[#ff7a82]" : city.repeat_rate >= 0.8 ? "text-[#ffce3a]" : "text-[#2ea6ff]";
    box.innerHTML = R.section(
      `武汉整体${label ? "（" + label + "）" : ""}`,
      "green",
      `<table class="data-table"><tbody>
        <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">重复投诉用户</td><td class="py-1 font-semibold" style="color:var(--ink-1)">${city.repeat_users ?? "-"}</td></tr>
        <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">投诉工单总数</td><td class="py-1 font-semibold" style="color:var(--ink-1)">${city.total_orders ?? "-"}</td></tr>
        <tr class="border-b"><td class="py-1" style="color:var(--ink-3)">重复投诉率</td><td class="py-1 font-semibold ${rateColor}">${city.repeat_rate != null ? city.repeat_rate + "%" : "-"}</td></tr>
      </tbody></table>`,
      "",
      "public"
    );
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

  // 最下方：列出存在重复投诉的区，新洲高亮
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
