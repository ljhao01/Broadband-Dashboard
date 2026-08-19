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
              "wuhan_districts": [], "daily_details": [], "xinzhou_daily": [], "ai_analysis": []}

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
            if std_name not in WHAN_ALL_KNOWN:
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
    return result


def _parse_detail_sheet(df, sheet_name):
    """解析明细/重投用户 sheet，提取每条记录中的日期、区县、是否重复投诉。

    自动识别列名（兼容「投诉日期」「工单日期」「区县」「所属区县」等常见表头），
    并判断「是否重复投诉」列（如含「重复」关键字）。
    返回 list[dict]: [{stat_date, district, complaint_count(1), repeat_count(0或1)}]
    """
    import pandas as pd
    rows = []
    # 先尝试第一行做表头，不行就用前几行扫描找表头
    header_row = None
    # 扫描前 5 行找表头行
    for scan in range(min(5, len(df))):
        rv = [str(v).strip() for v in df.iloc[scan].tolist() if v is not None and str(v) != "nan"]
        date_like = sum(1 for v in rv if "日期" in v or "时间" in v)
        dist_like = sum(1 for v in rv if "区" in v or "县" in v or "区域" in v or "归属" in v)
        if date_like >= 1 and dist_like >= 1:
            header_row = scan
            break

    if header_row is None:
        # 回退：尝试用第一行做表头
        try:
            df_h = pd.read_excel(df, header=0) if hasattr(df, 'to_excel') else df
        except Exception:
            return rows

    # 构建列索引映射
    headers = [str(v).strip() for v in df.iloc[header_row or 0].tolist()]
    date_col = None
    dist_col = None
    repeat_col = None
    for i, h in enumerate(headers):
        hl = h.lower()
        if date_col is None and ("日期" in hl or "时间" in hl):
            date_col = i
        if dist_col is None and ("区" in hl or "县" in hl or "区域" in hl or "归属" in hl):
            dist_col = i
        if repeat_col is None and ("重复" in hl or "是否重" in hl):
            repeat_col = i

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

            # 判断是否重复投诉
            is_repeat = 0
            if repeat_col is not None:
                rv = str(row[repeat_col]).strip()
                if rv in ("是", "1", "True", "true", "重复", "重投"):
                    is_repeat = 1

            # 日期格式化
            from datetime import datetime
            dt = None
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
                try:
                    dt = datetime.strptime(date_str[:len(fmt)], fmt)
                    break
                except (ValueError, IndexError):
                    continue
            if dt is None:
                continue

            # 区县名标准化
            std_dist = merge_wuhan_district(dist_str)
            if std_dist not in WHAN_ALL_KNOWN:
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
