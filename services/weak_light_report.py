# -*- coding: utf-8 -*-
"""
弱光督办报表解析服务。支持两种报表格式，均只保留归属区县 = 新洲区 的数据入库。

【旧格式】《存量及新增弱光》.xlsx —— 多 Sheet：
- 存量弱光总明细  → weak_light_detail
- 存量弱光小区分析 → weak_light_community
- 存量弱光pon口分析 → weak_light_pon
- 企宽弱光          → weak_light_enterprise
- 统计              → weak_light_stat
数据日期：从文件名识别（如「8月17日」→ 2026-08-17）。

【新格式】《智能网关用户详情报表MM.DD.csv》—— 单表 38 列、GBK 编码：
- 明细直接来自单表（按 `归属区县` == 新洲区 过滤，并按光功率/弱光次数校验弱光口径）
- 小区 / PON / 区县统计 均由单表 groupby 聚合生成
- 无「持续弱光 / 企宽弱光 / 质差小区类型 / 对应师傅 / 统计」信息 → 相应字段置空或 0
数据日期：取表内 `数据开始时间`（如 20260927 → 2026-09-27）。

两种格式共同约定：新增弱光（weak_light_new）在落库层对比上一批次网关 SN 判定，
无上一批次基线时不做新增判定。
"""
import re
from datetime import datetime

from config import WHAN_ALL_KNOWN, WHAN_SUMMARY_NAMES, XINZHOU_ACTIVE_USERS

# 需要过滤的归属区县
XINZHOU = "新洲区"
# 谷值光功率严重弱光阈值（dBm）
SEVERE_THRESHOLD = -30.0
# 谷值光功率弱光判定阈值（dBm）：低于该值即判为弱光
WEAK_THRESHOLD = -27.0
# PON 口弱光预警阈值（弱光数 ≥ 此值标红，提示分光器/主干光缆问题）
PON_WARN_THRESHOLD = 3


def _excel_date(value):
    """把 Excel 序列日期或字符串转成 YYYY-MM-DD。"""
    if value is None:
        return None
    import pandas as pd
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + pd.to_timedelta(int(value), unit="D")).strftime("%Y-%m-%d")
        except Exception:
            return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            continue
    return s


def parse_weak_light_report(path, filename=""):
    """解析弱光报表，自动适配两种表格格式。

    - 旧格式：`《存量及新增弱光》.xlsx`（多 Sheet）→ 原逐 Sheet 解析
    - 新格式：`智能网关用户详情报表MM.DD.csv`（单表 38 列、GBK 编码）→ _parse_gateway_csv
    """
    import pandas as pd

    # 新格式分发：CSV 单表（智能网关用户详情报表）
    if str(filename or path).lower().endswith(".csv"):
        return _parse_gateway_csv(path, filename)

    result = {
        "ok": True, "error": "", "sheets_found": [],
        "data_date": _parse_data_date(filename),
        "summary": {},
        "details": [], "communities": [], "pons": [],
        "new_weaks": [], "enterprises": [], "stats": [],
        "quality_cells": [],
    }

    def _safe_read(sheet):
        try:
            return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
        except Exception:
            return None

    # ---- 1. 存量弱光总明细（主表，过滤新洲区） ----
    df = _safe_read("存量弱光总明细")
    if df is not None:
        result["sheets_found"].append("存量弱光总明细")
        for _, row in df.iterrows():
            if str(row.get("归属区县", "")).strip() != XINZHOU:
                continue
            result["details"].append(_detail_row(row))

    # ---- 2. 小区分析（新洲区） ----
    dfc = _safe_read("存量弱光小区分析")
    if dfc is not None:
        result["sheets_found"].append("存量弱光小区分析")
        for _, row in dfc.iterrows():
            if str(row.get("区县", "")).strip() != XINZHOU:
                continue
            result["communities"].append({
                "community": _s(row.get("归属小区")),
                "weak_count": _i(row.get("弱光数")),
                "prev_count": _i(row.get("前日弱光数")),
                "change_val": _i(row.get("变化")),
                "quality_type": _s(row.get("质差小区类型")),
            })

    # ---- 3. PON 口分析（新洲区） ----
    dfp = _safe_read("存量弱光pon口分析")
    if dfp is not None:
        result["sheets_found"].append("存量弱光pon口分析")
        for _, row in dfp.iterrows():
            if str(row.get("区县", "")).strip() != XINZHOU:
                continue
            result["pons"].append({
                "pon": _s(row.get("归属pon")),
                "weak_count": _i(row.get("弱光数")),
                "prev_count": _i(row.get("前日弱光数")),
                "change_val": _i(row.get("变化")),
                "community": _s(row.get("小区")),
                "weak_mark": 1 if str(row.get("弱光质差", "")).strip() == "是" else 0,
                "quality_type": _s(row.get("质差小区类型")),
            })

    # ---- 4. 新增弱光 ----
    # 注意：不再读取 excel 的「新增弱光」sheet。
    # 新增弱光改为：对比「存量弱光总明细」与上一次上传批次的网关SN 判定（在落库层处理），
    # 此处 new_weaks 保持为空，summary.new_weak_cnt 由落库层按对比结果覆盖。

    # ---- 5. 企宽弱光（新洲区，取明细部分归属区县列） ----
    dfe = _safe_read("企宽弱光")
    if dfe is not None:
        result["sheets_found"].append("企宽弱光")
        for _, row in dfe.iterrows():
            if str(row.get("归属区县", "")).strip() != XINZHOU:
                continue
            result["enterprises"].append({
                "gateway_sn": _s(row.get("网关sn")),
                "account": _s(row.get("上网账号")),
                "mac": _s(row.get("mac地址")),
                "active_count": _i(row.get("用户活跃次数")),
                "valley_power": _f(row.get("谷值接收光功率(dbm)")),
                "peak_power": _f(row.get("峰值接收光功率(dbm)")),
                "weak_count": _i(row.get("接收光功率弱光次数")),
                "community": _s(row.get("归属小区")),
                "olt": _s(row.get("归属olt")),
                "pon": _s(row.get("归属pon")),
                "onu": _s(row.get("归属onu")),
            })

    # ---- 6. 统计（各区县，含新洲区 + 全市平均） ----
    dfs = _safe_read("统计")
    if dfs is not None:
        result["sheets_found"].append("统计")
        result["stats"] = _parse_stat_sheet(dfs)

    # ---- 汇总：新洲区核心指标 ----
    details = result["details"]
    new_weaks = result["new_weaks"]
    stats = result["stats"]
    xz_stat = next((s for s in stats if s["district"] == XINZHOU), None)

    sustained_cnt = sum(1 for d in details if d.get("sustained"))
    poor_cells = set()
    for d in details:
        qt = d.get("quality_type")
        if qt:
            poor_cells.add(d["community"])
    severe_cnt = sum(1 for d in details if (d.get("valley_power") or 0) < SEVERE_THRESHOLD)
    pon_cnt = len({p["pon"] for p in result["pons"]})

    result["summary"] = {
        "weak_total": len(details),
        "weak_rate": xz_stat["weak_rate"] if xz_stat and xz_stat.get("weak_rate") is not None else None,
        "active_users": xz_stat.get("active_users") if xz_stat else None,
        "sustained_cnt": sustained_cnt,
        "poor_cell_cnt": len(poor_cells),
        "severe_cnt": severe_cnt,
        "pon_cnt": pon_cnt,
        # 新增弱光在落库层按「存量明细对比上一批次网关SN」计算并覆盖，此处先置 0
        "new_weak_cnt": 0,
    }

    # 质差小区类型清单（用于督办）
    quality_cells = {}
    for d in details:
        qt = d.get("quality_type")
        if not qt:
            continue
        key = d["community"]
        if key not in quality_cells:
            quality_cells[key] = {"community": key, "weak_count": 0, "quality_type": set(), "olt": d.get("olt", "")}
        quality_cells[key]["weak_count"] += 1
        quality_cells[key]["quality_type"].add(qt)
    result["quality_cells"] = [
        {**v, "quality_type": "、".join(sorted(v["quality_type"]))} for v in quality_cells.values()
    ]
    result["quality_cells"].sort(key=lambda x: x["weak_count"], reverse=True)

    return result


def _read_gateway_csv(path):
    """读取智能网关 CSV（GBK 为主，依次尝试多种编码），返回 DataFrame 或 None。"""
    import pandas as pd
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
        except Exception:
            continue
    return None


def _parse_gateway_csv(path, filename=""):
    """解析新格式《智能网关用户详情报表 MM.DD.csv》。

    与旧 xlsx（5 个 Sheet）的最大差异：
    - 单表 38 列，无 Sheet；小区/PON 聚合需自行 groupby 生成；
    - 无「持续弱光」「企宽弱光」「质差小区类型」「对应师傅」列 → 对应字段置空/0，
      对应人员完全依赖《责任田》按小区回填；
    - 无「统计」Sheet → 拿不到活跃用户数与官方弱光率，weak_rate/avg_rate 置 None；
    - 区县标识：单一 `归属区县` 列（值 == 新洲区）；
    - 数据日期：取表内 `数据开始时间`（如 20260927 → 2026-09-27），比文件名更可靠。
    """
    df = _read_gateway_csv(path)
    result = {
        "ok": True, "error": "", "sheets_found": ["智能网关用户详情报表(CSV)"],
        "format": "gateway_csv",
        "data_date": None,
        "summary": {},
        "details": [], "communities": [], "pons": [],
        "new_weaks": [], "enterprises": [], "stats": [], "quality_cells": [],
        "_rows_total": 0, "_rows_xinzhou": 0,
    }
    if df is None or len(df) == 0:
        result["ok"] = False
        result["error"] = "CSV 读取失败或为空"
        return result

    result["_rows_total"] = len(df)
    # 数据日期：优先表内「数据开始时间」
    raw_date = _s(df.iloc[0].get("数据开始时间")) if "数据开始时间" in df.columns else ""
    result["data_date"] = _yyyymmdd(raw_date) or _parse_data_date(filename)

    # 区县过滤：新格式以「归属区县」列标识，仅保留新洲区
    if "归属区县" not in df.columns:
        result["ok"] = False
        result["error"] = "缺少「归属区县」列，无法识别区县"
        return result

    xz = df[df["归属区县"].astype(str).str.strip() == XINZHOU]
    result["_rows_xinzhou"] = len(xz)

    for _, row in xz.iterrows():
        valley = _f(row.get("谷值接收光功率(dbm)"))
        weak_times = _i(row.get("接收光功率弱光次数"))
        # 弱光判定：该报表本身为弱光用户清单，此处再做一次口径校验（谷值<-27 或 弱光次数>0）
        if not ((valley is not None and valley < WEAK_THRESHOLD) or weak_times > 0):
            continue
        result["details"].append({
            "gateway_sn": _s(row.get("网关SN")),
            "account": _idstr(row.get("上网账号")),
            "mac": _s(row.get("MAC地址")),
            "active_count": _i(row.get("用户活跃次数")),
            "valley_power": valley,
            "peak_power": _f(row.get("峰值接收光功率(dbm)")),
            "weak_count": weak_times,
            "community": _s(row.get("归属小区")),
            "technician": "",          # 新格式无「对应师傅」，由《责任田》按小区回填
            "olt": _s(row.get("归属OLT")),
            "pon": _s(row.get("归属PON")),
            "onu": _s(row.get("归属ONU")),
            "sustained": False,        # 新格式无「是否持续弱光」
            "enterprise": False,       # 新格式无企宽标识
            "is_new": False,           # 由落库层对比上一批次判定
            "quality_type": "",        # 新格式无「质差小区类型」
        })

    details = result["details"]

    # ---- 小区聚合（groupby 生成，替代旧格式的「存量弱光小区分析」Sheet） ----
    comm = {}
    for d in details:
        c = d["community"] or "未知小区"
        rec = comm.setdefault(c, {"community": c, "weak_count": 0, "prev_count": 0,
                                  "change_val": 0, "quality_type": ""})
        rec["weak_count"] += 1
    result["communities"] = sorted(comm.values(), key=lambda x: x["weak_count"], reverse=True)

    # ---- PON 聚合（groupby 生成，替代旧格式的「存量弱光pon口分析」Sheet） ----
    pon_map = {}
    for d in details:
        p = d["pon"]
        if not p:
            continue
        rec = pon_map.setdefault(p, {"pon": p, "weak_count": 0, "prev_count": 0,
                                     "change_val": 0, "community": "",
                                     "weak_mark": 0, "quality_type": ""})
        rec["weak_count"] += 1
        if not rec["community"]:
            rec["community"] = d["community"]
    for rec in pon_map.values():
        rec["weak_mark"] = 1 if rec["weak_count"] >= PON_WARN_THRESHOLD else 0
    result["pons"] = sorted(pon_map.values(), key=lambda x: x["weak_count"], reverse=True)

    # ---- 企宽弱光：新格式无该标识，保持为空（无法判定） ----
    result["enterprises"] = []

    # ---- 区县统计：新格式无「统计」Sheet；弱光率 = 弱光户数 / 新洲区活跃用户数 ----
    weak_total = len(details)
    active_users = XINZHOU_ACTIVE_USERS
    weak_rate = round(weak_total / active_users, 6) if active_users else None

    result["stats"] = [{
        "district": XINZHOU,
        "weak_count": weak_total,
        "weak_rate": weak_rate,
        "prev_count": 0,
        "active_users": active_users,
        "change_count": 0,
        "change_rate": None,
        "avg_rate": weak_rate,   # 新洲区平均弱光率（无官方口径，取该计算值）
    }]

    # ---- 汇总 ----
    severe_cnt = sum(1 for d in details if (d.get("valley_power") or 0) < SEVERE_THRESHOLD)
    result["summary"] = {
        "weak_total": weak_total,
        "weak_rate": weak_rate,
        "active_users": active_users,
        "sustained_cnt": 0,     # 新格式无持续弱光标记
        "poor_cell_cnt": 0,     # 新格式无质差小区类型
        "severe_cnt": severe_cnt,
        "pon_cnt": len(result["pons"]),
        "new_weak_cnt": 0,      # 由落库层按上一批次对比覆盖
    }
    return result


def _yyyymmdd(v):
    """把 20260927 这类 8 位数字日期转成 2026-09-27。"""
    s = _s(v)
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _idstr(v):
    """编号/账号类字段转字符串（去 .0 尾巴，空值返回空串）。"""
    s = _s(v)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _parse_stat_sheet(df):
    """解析「统计」sheet 中的「截止xx日存量弱光情况」主表，仅保留该表各区县数据。

    统计 sheet 内含多张堆叠的表格（存量弱光情况 / 存量弱光分布情况 / 企宽弱光情况等），
    历史解析会把后续表格也读进来污染「区县弱光率排行」。此处只解析第一张主表：
    - 以列2(区分)作为区县名；
    - 主表开始后，遇到非区县/汇总/未归属 的标题行（如「18日存量弱光分布情况」「区县」）
      即视为下一张表开始，停止解析；
    - 列10 的「武汉平均弱光率」一并提取。

    统计 sheet 主表结构（第0行表头，第1行子表头）：
    - 列2(区分)：区县名
    - 列3(弱光数)当日、列4(弱光占比)当日
    - 列5(弱光数)次日、列6(参考活跃用户数)、列7(弱光占比)次日
    - 列8(压降数)、列9(压降占比)
    - 列10：武汉8月平均弱光率
    """
    # 主表数据行名：武汉已知区县 + 汇总行 + 未归属 + 报表别名（东新区/经开区）
    valid_names = set(WHAN_ALL_KNOWN) | set(WHAN_SUMMARY_NAMES) | {"未归属", "东新区", "经开区"}

    stats = []
    wuhan_avg = None
    started = False
    # 用 positional 取值（统计 sheet 表头非规范，用 iloc 按位置读取）
    for idx in range(len(df)):
        row = df.iloc[idx].tolist()
        name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if name in ("区分", "nan", "", "None"):
            continue
        # 主表开始后，遇到非区县/汇总/未归属 的行 → 下一个表格标题，停止解析
        if name not in valid_names:
            if started:
                break
            continue  # 前导标题行（如「截止xx日存量弱光情况」），直接跳过
        started = True
        # 武汉8月平均弱光率列（列10）
        if len(row) > 9 and row[9] is not None:
            try:
                avg = float(row[9])
                if avg and avg > 0:
                    wuhan_avg = avg
            except (ValueError, TypeError):
                pass
        rec = {
            "district": name,
            "weak_count": _i(row[4]) if len(row) > 4 else 0,
            "weak_rate": _f(row[6]) if len(row) > 6 else None,
            "prev_count": _i(row[2]) if len(row) > 2 else 0,
            "active_users": _i(row[5]) if len(row) > 5 else 0,
            "change_count": _i(row[7]) if len(row) > 7 else 0,
            "change_rate": _f(row[8]) if len(row) > 8 else None,
            "avg_rate": wuhan_avg,
        }
        stats.append(rec)
    return stats


def _detail_row(row):
    """把「存量弱光总明细」一行转换为落库结构（含持续/企宽/新增/质差标记）。"""
    return {
        "gateway_sn": _s(row.get("网关sn")),
        "account": _s(row.get("上网账号")),
        "mac": _s(row.get("mac地址")),
        "active_count": _i(row.get("用户活跃次数")),
        "valley_power": _f(row.get("谷值接收光功率(dbm)")),
        "peak_power": _f(row.get("峰值接收光功率(dbm)")),
        "weak_count": _i(row.get("接收光功率弱光次数")),
        "community": _s(row.get("归属小区")),
        "technician": _s(row.get("对应师傅")),
        "olt": _s(row.get("归属olt")),
        "pon": _s(row.get("归属pon")),
        "onu": _s(row.get("归属onu")),
        "sustained": str(row.get("持续弱光", "")).strip() == "持续弱光",
        "enterprise": str(row.get("企宽弱光", "")).strip() == "企宽弱光",
        "is_new": bool(row.get("新增弱光")) if str(row.get("新增弱光", "")).strip() else False,
        "quality_type": _s(row.get("质差小区类型")),
    }


def _parse_data_date(filename):
    """从文件名识别数据日期（如「8月17日」「2026-08-17」→ 2026-08-17）。"""
    if not filename:
        return None
    year = str(datetime.now().year)
    # 优先匹配 4 位年份：2026-08-17 / 2026年8月17日
    m = re.search(r"(\d{4})[-_.年/]?(\d{1,2})月?[-_.日]?(\d{1,2})", filename)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 无年份：8月17日 → 当年-08-17
    m = re.search(r"(\d{1,2})月(\d{1,2})", filename)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # 无年份简写：9.27 / 9-27 → 当年-09-27（智能网关用户详情报表9.27.csv）
    m = re.search(r"(\d{1,2})[.\-](\d{1,2})(?!\d)", filename)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _s(v):
    """安全转字符串。"""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s == "nan" else s


def _i(v):
    """安全转整数。"""
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0
        return int(v)
    except (ValueError, TypeError):
        return 0


def _f(v):
    """安全转浮点数。"""
    try:
        if v is None or (isinstance(v, float) and v != v):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None
