# -*- coding: utf-8 -*-
"""
重复投诉率报表解析服务（广义重投统计 xlsx）
- 解析时间周期、武汉整体、各区县明细
- 动态识别武汉下辖区县（不再硬编码白名单，避免漏掉功能区/口径变化）
- 重点聚焦新洲区，生成 AI 分析结论
"""
import re

from config import WHAN_SUMMARY_NAMES, WHAN_ALL_KNOWN, merge_wuhan_district


def parse_complaint_report(path):
    """解析运营商广义重复投诉统计报表。

    识别原则：
    - 武汉市列(地市) == "武汉" 且 区县列 != 汇总行(武汉市/武汉/全市) 的，全部视为武汉的区县/功能区
    - 动态识别，兼容 13 行政区 + 东湖高新区/武汉经开区等任意口径，避免漏区
    - 新增：解析「明细」/「重投用户」sheet，提取每日+区县粒度的投诉量/重复投诉量
    """
    import pandas as pd
    from datetime import datetime

    # 武汉行政区口径（用户明确：武汉只有 15 个区 = 13 行政区中去掉汉南区 + 东湖高新区 + 武汉经开区 + 长江新区）。
    # 报表里「汉南区」已并入经开区口径，不应作为独立区县统计，予以排除。
    WHAN_15 = set(WHAN_ALL_KNOWN) - {"汉南区"}

    def _safe_read(sheet):
        try:
            return pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
        except Exception:
            return None

    def _safe_read_header(sheet, header_row=0):
        """尝试按指定行作为表头读取（容错）"""
        try:
            return pd.read_excel(path, sheet_name=sheet, header=header_row, engine="openpyxl")
        except Exception:
            return None

    result = {"ok": True, "error": "", "sheets_found": [], "period": {},
              "city": {}, "district_summary": {}, "xinzhou": {},
              "wuhan_districts": [], "daily_details": [], "xinzhou_daily": [],
              "xinzhou_repeat_tickets": [], "ai_analysis": []}

    # ---- 时间周期解析 ----
    period = {}
    for sn in ("地市统计", "区县统计"):
        df = _safe_read(sn)
        if df is None:
            continue
        result["sheets_found"].append(sn)
        for _, row in df.iterrows():
            vals = [str(v) for v in row.tolist() if v is not None and str(v) != "nan"]
            for v in vals:
                if "报表类型" in v:
                    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})", v)
                    if m:
                        period["report_type"] = "日报" if "日报" in v else ("月报" if "月报" in v else "")
                        period["report_date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            date_nums = sorted(v for v in vals if re.match(r"^\d{8}$", v))
            if len(date_nums) >= 2:
                period["start"] = f"{date_nums[0][:4]}-{date_nums[0][4:6]}-{date_nums[0][6:8]}"
                period["end"] = f"{date_nums[-1][:4]}-{date_nums[-1][4:6]}-{date_nums[-1][6:8]}"

    # ---- 地市统计：提取武汉整体 ----
    ds = _safe_read("地市统计")
    city = {}
    if ds is not None:
        for _, r in ds.iterrows():
            if str(r[3]) == "武汉":
                city = {
                    "repeat_users": int(r[4]) if pd.notna(r[4]) else 0,
                    "total_orders": int(r[5]) if pd.notna(r[5]) else 0,
                    "repeat_rate": float(r[6]) if pd.notna(r[6]) else 0.0,
                }
    result["city"] = city

    # ---- 区县统计：按「武汉已知口径清单」动态识别武汉全部区县/功能区 ----
    qx = _safe_read("区县统计")
    wh_districts = []
    xinzhou = {}
    merged = {}
    if qx is not None:
        for _, r in qx.iterrows():
            city_col = str(r[3]).strip()
            district_col = str(r[4]).strip()
            if city_col != "武汉":
                continue
            if district_col in WHAN_SUMMARY_NAMES:
                result["district_summary"] = {
                    "repeat_users": int(r[5]) if pd.notna(r[5]) else 0,
                    "total_orders": int(r[6]) if pd.notna(r[6]) else 0,
                    "repeat_rate": float(r[7]) if pd.notna(r[7]) else 0.0,
                }
                continue
            std_name = merge_wuhan_district(district_col)
            if std_name not in WHAN_15:
                continue
            try:
                rec = {
                    "repeat_users": int(r[5]) if pd.notna(r[5]) else 0,
                    "total_orders": int(r[6]) if pd.notna(r[6]) else 0,
                    "repeat_rate": float(r[7]) if pd.notna(r[7]) else 0.0,
                }
            except (ValueError, TypeError):
                continue
            if std_name in merged:
                m = merged[std_name]
                tot = m["total_orders"] + rec["total_orders"]
                m["repeat_users"] += rec["repeat_users"]
                m["total_orders"] = tot
                m["repeat_rate"] = round((m["repeat_rate"] * (tot - rec["total_orders"]) + rec["repeat_rate"] * rec["total_orders"]) / tot, 2) if tot else 0.0
            else:
                merged[std_name] = {**rec}
            if std_name == "新洲区":
                xinzhou = {**merged[std_name], "district": "新洲区"}
        wh_districts = [{"district": k, **v} for k, v in merged.items()]
    wh_districts.sort(key=lambda x: x["repeat_rate"], reverse=True)
    result["wuhan_districts"] = wh_districts
    result["xinzhou"] = xinzhou

    # ---- 每日明细解析（从「明细」/「重投用户」sheet）----
    daily_details = []      # 全部每日+区县粒度的投诉/重复投诉
    xinzhou_daily = []      # 新洲区每日数据（重点）
    detail_sheet_names = ["明细", "重投用户", "投诉明细", "用户明细"]
    for sn in detail_sheet_names:
        df = _safe_read(sn)
        if df is None:
            continue
        result["sheets_found"].append(sn)
        daily = _parse_detail_sheet(df, sn)
        if daily:
            daily_details = daily
            break

    # 按日期+区县聚合
    agg = {}  # key: (date, district)
    for rec in daily_details:
        k = (rec["stat_date"], rec["district"])
        if k not in agg:
            agg[k] = {"stat_date": rec["stat_date"], "district": rec["district"],
                       "complaint_count": 0, "repeat_count": 0}
        agg[k]["complaint_count"] += rec["complaint_count"]
        agg[k]["repeat_count"] += rec["repeat_count"]

    result["daily_details"] = sorted(agg.values(), key=lambda x: (x["stat_date"], x["district"]))

    # ---- 新洲区重复投诉单（具体账号，用于前端单独展示）----
    xz_tickets = []
    for sn in ("重投用户", "明细", "投诉明细", "用户明细"):
        df = _safe_read(sn)
        if df is None:
            continue
        xz_tickets = _parse_xinzhou_repeat_tickets(df, sn)
        if xz_tickets:
            break
    # 去重：按工单编号/账号去重
    seen = set()
    uniq_tickets = []
    for t in xz_tickets:
        key = t.get("ticket_no") or t.get("account")
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        uniq_tickets.append(t)
    result["xinzhou_repeat_tickets"] = uniq_tickets

    # 提取新洲区每日数据
    xz_daily_agg = {}
    for rec in daily_details:
        if rec["district"] != "新洲区":
            continue
        d = rec["stat_date"]
        if d not in xz_daily_agg:
            xz_daily_agg[d] = {"date": d, "complaint_count": 0, "repeat_count": 0}
        xz_daily_agg[d]["complaint_count"] += rec["complaint_count"]
        xz_daily_agg[d]["repeat_count"] += rec["repeat_count"]
    result["xinzhou_daily"] = sorted(xz_daily_agg.values(), key=lambda x: x["date"])

    # ---- AI 分析结论（重点新洲区）----
    result["ai_analysis"] = _gen_upload_analysis(city, xinzhou, wh_districts, period)
    result["period"] = period
    # 批次归属月份（用于 complaint_upload.stat_month 隔离）
    result["stat_month"] = (period.get("start") or "")[:7] or datetime.now().strftime("%Y-%m")
    return result


def _parse_detail_sheet(df, sheet_name):
    """解析明细/重投用户 sheet，提取每条记录中的日期、区县、是否重复投诉。

    自动识别列名（兼容「投诉日期」「工单日期」「归属区县」等常见表头），
    并判断「是否重复投诉」列（如含「重复」关键字）。
    若存在「工单地市/地市」列，则仅保留武汉地市的行（明细 sheet 常为全省数据）。
    返回 list[dict]: [{stat_date, district, complaint_count(1), repeat_count(0或1)}]
    """
    import re
    import pandas as pd
    from datetime import datetime
    # 武汉 15 区口径（汉南区并入经开区，不作为独立区县；保留长江新区）
    WHAN_15 = set(WHAN_ALL_KNOWN) - {"汉南区"}
    rows = []
    # 扫描前 5 行找表头行
    header_row = None
    for scan in range(min(5, len(df))):
        rv = [str(v).strip() for v in df.iloc[scan].tolist() if v is not None and str(v) != "nan"]
        date_like = sum(1 for v in rv if "日期" in v or "时间" in v)
        dist_like = sum(1 for v in rv if ("区县" in v) or ("区" in v and "归属" in v) or "所属区县" in v or "归属区县" in v)
        if date_like >= 1 and dist_like >= 1:
            header_row = scan
            break

    if header_row is None:
        return rows

    # 构建列索引映射
    headers = [str(v).strip() for v in df.iloc[header_row].tolist()]
    date_col = None
    dist_col = None
    repeat_col = None
    city_col = None  # 工单地市/地市列（用于过滤全省数据仅留武汉）
    for i, h in enumerate(headers):
        hl = h.lower()
        if date_col is None and ("日期" in hl or "时间" in hl):
            date_col = i
        # 归属区县优先于普通"区/县"（避免误匹配"地市/小区"等）
        if dist_col is None and ("区县" in hl or "所属区" in hl or "归属区" in hl):
            dist_col = i
        if repeat_col is None and ("重复" in hl or "是否重" in hl):
            repeat_col = i
        if city_col is None and ("地市" in hl or "所属地市" in hl):
            city_col = i
    # 兜底：若没匹配到归属区县，再放宽到"区/县/归属"
    if dist_col is None:
        for i, h in enumerate(headers):
            hl = h.lower()
            if "区" in hl or "县" in hl or "区域" in hl or "归属" in hl:
                if hl not in ("工单地市", "地市", "所属地市"):
                    dist_col = i
                    break

    if date_col is None or dist_col is None:
        return rows

    # 从表头下一行开始读取数据
    start = (header_row or 0) + 1
    for idx in range(start, len(df)):
        try:
            row = df.iloc[idx]
            date_str = str(row[date_col]).strip() if pd.notna(row[date_col]) else ""
            dist_str = str(row[dist_col]).strip() if pd.notna(row[dist_col]) else ""
            if not date_str or not dist_str or date_str == "nan" or dist_str == "nan":
                continue

            # 若存在地市列，仅保留武汉地市（明细 sheet 常为全省数据）
            if city_col is not None:
                city_val = str(row[city_col]).strip() if pd.notna(row[city_col]) else ""
                if city_val and city_val != "武汉":
                    continue

            # 判断是否重复投诉
            is_repeat = 0
            if repeat_col is not None:
                rv = str(row[repeat_col]).strip()
                if rv in ("是", "1", "True", "true", "重复", "重投"):
                    is_repeat = 1

            # 日期格式化：用正则提取年月日，兼容 20260819 / 2026-08-19 / 2026/8/9 等
            m = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})", date_str)
            if not m:
                continue
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                continue
            dt = datetime(y, mo, d)

            # 区县名标准化（武汉 15 区口径）
            std_dist = merge_wuhan_district(dist_str)
            if std_dist not in WHAN_15:
                continue

            rows.append({
                "stat_date": dt.strftime("%Y-%m-%d"),
                "district": std_dist,
                "complaint_count": 1,
                "repeat_count": is_repeat,
            })
        except Exception:
            continue
    return rows


def _parse_xinzhou_repeat_tickets(df, sheet_name):
    """从「重投用户」/明细 sheet 提取新洲区重复投诉的具体账号单子。

    返回 list[dict]: [{stat_date, ticket_no, account, channel, repeat_times}]
    用于前端"智能总结"中单独列出新洲区重复投诉单。
    """
    import re
    import pandas as pd
    rows = []
    # 找表头行
    header_row = None
    for scan in range(min(5, len(df))):
        rv = [str(v).strip() for v in df.iloc[scan].tolist() if v is not None and str(v) != "nan"]
        date_like = sum(1 for v in rv if "日期" in v or "时间" in v)
        dist_like = sum(1 for v in rv if "区县" in v or "归属区" in v or "所属区" in v)
        if date_like >= 1 and dist_like >= 1:
            header_row = scan
            break
    if header_row is None:
        return rows

    headers = [str(v).strip() for v in df.iloc[header_row].tolist()]
    date_col = dist_col = ticket_col = account_col = city_col = None
    for i, h in enumerate(headers):
        hl = h.lower()
        if date_col is None and ("日期" in hl or "时间" in hl):
            date_col = i
        if dist_col is None and ("区县" in hl or "归属区" in hl or "所属区" in hl):
            dist_col = i
        if ticket_col is None and ("工单编号" in hl or "工单id" in hl or "工单号" in hl):
            ticket_col = i
        if account_col is None and ("宽带账号" in hl or "账号" in hl or "宽带号" in hl):
            account_col = i
        if city_col is None and ("地市" in hl or "所属地市" in hl):
            city_col = i

    if dist_col is None or date_col is None:
        return rows

    start = (header_row or 0) + 1
    for idx in range(start, len(df)):
        try:
            row = df.iloc[idx]
            date_str = str(row[date_col]).strip() if pd.notna(row[date_col]) else ""
            dist_str = str(row[dist_col]).strip() if pd.notna(row[dist_col]) else ""
            if not date_str or not dist_str or date_str == "nan" or dist_str == "nan":
                continue
            if city_col is not None:
                cv = str(row[city_col]).strip() if pd.notna(row[city_col]) else ""
                if cv and cv != "武汉":
                    continue
            if merge_wuhan_district(dist_str) != "新洲区":
                continue
            m = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})", date_str)
            if not m:
                continue
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                continue
            rows.append({
                "stat_date": f"{y:04d}-{mo:02d}-{d:02d}",
                "ticket_no": str(row[ticket_col]).strip() if ticket_col is not None and pd.notna(row[ticket_col]) else "",
                "account": str(row[account_col]).strip() if account_col is not None and pd.notna(row[account_col]) else "",
                "channel": "",
                "repeat_times": "",
            })
        except Exception:
            continue
    return rows


def _gen_upload_analysis(city, xinzhou, districts, period):
    tips = []
    rd = period.get("report_date", "本期")
    if city:
        tips.append(f"【{rd} 武汉整体】重复投诉率 {city.get('repeat_rate', 0):.2f}%，"
                    f"重复投诉用户 {city.get('repeat_users', 0)} 人，投诉工单 {city.get('total_orders', 0)} 件。"
                    f"在各地市中需结合全省横向对标定位差距。")
    if xinzhou:
        rate = xinzhou.get("repeat_rate", 0)
        users = xinzhou.get("repeat_users", 0)
        orders = xinzhou.get("total_orders", 0)
        if rate == 0 or users == 0:
            tips.append(f"【新洲区·重点关注】当前重复投诉率 {rate:.2f}%、重复投诉用户 {users} 人、"
                        f"投诉工单 {orders} 件，本期无重复投诉，态势良好。"
                        f"建议保持盯控，结合工单量({orders}件)做前置预警，防止苗头性问题演变为重复投诉。")
        else:
            tips.append(f"【新洲区·重点关注】重复投诉率 {rate:.2f}%、重复投诉用户 {users} 人、"
                        f"投诉工单 {orders} 件，已出现重复投诉，需立即溯源整改、限期销号。")
        rank = next((i + 1 for i, d in enumerate(districts) if d["district"] == "新洲区"), None)
        if rank:
            tips.append(f"新洲区在武汉 {len(districts)} 个区县中重复投诉率排名第 {rank} 位，"
                        f"建议纳入新洲区网格长重点督办清单。")
    else:
        tips.append("【新洲区】报表中未检索到「新洲区」明细行，请确认报表是否包含该区县数据。")
    if districts:
        top = districts[0]
        tips.append(f"武汉重复投诉率最高的区县为 {top['district']}（{top['repeat_rate']:.2f}%），"
                    f"建议作为全市重点整治标杆对象。")
    return tips
