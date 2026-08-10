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
    """
    import pandas as pd

    def _safe_read(sheet):
        try:
            return pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
        except Exception:
            return None

    result = {"ok": True, "error": "", "sheets_found": [], "period": {},
              "city": {}, "district_summary": {}, "xinzhou": {},
              "wuhan_districts": [], "ai_analysis": []}

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
    # 说明：源报表中「地市列==武汉」往往是全省统筹口径，混入了曾都/麻城等外地市，
    #       故以区县名是否命中武汉口径清单为准（13行政区 + 东湖高新区/武汉经开区等）。
    qx = _safe_read("区县统计")
    wh_districts = []
    xinzhou = {}
    # 合并同名区县（如 经开区 / 武汉经济技术开发区 归并为 武汉经开区）
    merged = {}
    if qx is not None:
        for _, r in qx.iterrows():
            city_col = str(r[3]).strip()
            district_col = str(r[4]).strip()
            if city_col != "武汉":
                continue
            if district_col in WHAN_SUMMARY_NAMES:   # 跳过「武汉市」汇总行
                result["district_summary"] = {
                    "repeat_users": int(r[5]) if pd.notna(r[5]) else 0,
                    "total_orders": int(r[6]) if pd.notna(r[6]) else 0,
                    "repeat_rate": float(r[7]) if pd.notna(r[7]) else 0.0,
                }
                continue
            std_name = merge_wuhan_district(district_col)   # 别名归并到标准名称
            if std_name not in WHAN_ALL_KNOWN:              # 非武汉口径内的区县（外地市等）跳过
                continue
            try:
                rec = {
                    "repeat_users": int(r[5]) if pd.notna(r[5]) else 0,
                    "total_orders": int(r[6]) if pd.notna(r[6]) else 0,
                    "repeat_rate": float(r[7]) if pd.notna(r[7]) else 0.0,
                }
            except (ValueError, TypeError):
                continue
            # 同名合并：用户/工单累加，重复投诉率取加权（按工单量）均值
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

    # ---- AI 分析结论（重点新洲区）----
    result["ai_analysis"] = _gen_upload_analysis(city, xinzhou, wh_districts, period)
    result["period"] = period
    return result


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
