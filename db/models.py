# -*- coding: utf-8 -*-
"""
看板数据模型层（DAO 聚合）。

本文件只保留六看板通用的 collector 入口，以及各看板所需的轻量查询。
投诉/重复投诉模块因业务复杂、数据表多，已按 Repository 模式拆分到
`db.repositories.complaint_repository`，此处直接调用，避免 models.py 过度膨胀。
"""
import random

from db import get_thresholds_map
from db.repositories import complaint_repository, weak_light_repository


def _status(v, min_ok=None, max_ok=None, warn_min=None, warn_max=None):
    """根据阈值区间判断状态。"""
    if v is None:
        return "green"
    if (min_ok is not None and v < min_ok) or (max_ok is not None and v > max_ok):
        return "red"
    if (warn_min is not None and v < warn_min) or (warn_max is not None and v > warn_max):
        return "yellow"
    return "green"


def _warn(v, min_ok=None, max_ok=None, warn_min=None, warn_max=None):
    """返回是否触发预警。"""
    if v is None:
        return False
    if (min_ok is not None and v < min_ok) or (max_ok is not None and v > max_ok):
        return True
    if (warn_min is not None and v < warn_min) or (warn_max is not None and v > warn_max):
        return True
    return False


def _format_float(v, digits=2):
    """安全格式化浮点数，None 返回 '-'。"""
    if v is None:
        return "-"
    return f"{round(float(v), digits):.{digits}f}"


# ---------------------------------------------------------------------------
# 1. 重复投诉率
# ---------------------------------------------------------------------------
def collect_complaint(conn):
    """重复投诉率看板：仅保留核心 KPI，明细与趋势由上传模块自行渲染。"""
    thresholds = get_thresholds_map(conn)
    latest = complaint_repository.latest_complaint_report()

    # 默认兜底：未上传报表时给出占位值，避免页面报错
    city_users = latest["city_users"] if latest else None
    city_rate = latest["city_rate"] if latest else None

    kpis = []
    cfg = thresholds.get("repeat_total", {})
    kpis.append({
        "label": "重复投诉总量",
        "value": city_users if city_users is not None else "-",
        "unit": "单",
        "status": _status(
            city_users,
            cfg.get("min_ok"), cfg.get("max_ok"),
            cfg.get("warn_min"), cfg.get("warn_max"),
            
        ),
        "warn": _warn(
            city_users,
            cfg.get("min_ok"), cfg.get("max_ok"),
            cfg.get("warn_min"), cfg.get("warn_max"),
        ),
    })

    cfg = thresholds.get("repeat_ratio", {})
    kpis.append({
        "label": "重复投诉占比",
        "value": _format_float(city_rate),
        "unit": "%",
        "status": _status(
            city_rate,
            cfg.get("min_ok"), cfg.get("max_ok"),
            cfg.get("warn_min"), cfg.get("warn_max"),
            
        ),
        "warn": _warn(
            city_rate,
            cfg.get("min_ok"), cfg.get("max_ok"),
            cfg.get("warn_min"), cfg.get("warn_max"),
        ),
        "detail": "武汉整体重复投诉率",
    })

    return {
        "status": "green",
        "kpis": kpis,
        "latest": latest,
    }


# ---------------------------------------------------------------------------
# 7. 弱光督办（新洲区弱光指标提升）
# ---------------------------------------------------------------------------
def collect_weaklight(conn):
    """弱光督办看板：数据已落库，直接读最新批次。"""
    return weak_light_repository.weak_light_dashboard()


# ---------------------------------------------------------------------------
# 2. 装维工单
# ---------------------------------------------------------------------------
def collect_workorder(conn):
    thresholds = get_thresholds_map(conn)
    grids = ["网格A", "网格B", "网格C", "网格D", "网格E"]
    data = []
    for g in grids:
        eff = round(random.uniform(82, 99), 1)
        cfg = thresholds.get("workorder_eff", {})
        data.append({
            "grid": g,
            "eff": eff,
            "status": _status(eff, cfg.get("min_ok"), cfg.get("max_ok"),
                              cfg.get("warn_min"), cfg.get("warn_max"),
                              ),
        })
    cfg = thresholds.get("workorder_eff", {})
    avg_eff = round(sum(d["eff"] for d in data) / len(data), 1) if data else None
    return {
        "status": "green",
        "kpis": [
            {"label": "平均装机效能", "value": avg_eff, "unit": "%", "status": _status(
                avg_eff, cfg.get("min_ok"), cfg.get("max_ok"),
                cfg.get("warn_min"), cfg.get("warn_max"), )},
            {"label": "超时工单", "value": random.randint(0, 15), "unit": "单", "status": "green"},
        ],
        "grids": data,
        "trend": {
            "labels": ["周一", "周二", "周三", "周四", "周五", "周六"],
            "series": [{"name": "装机效能", "data": [round(random.uniform(85, 98), 1) for _ in range(6)]}],
        },
    }


# ---------------------------------------------------------------------------
# 3. FTTR 无线连接率
# ---------------------------------------------------------------------------
def collect_fttr(conn):
    thresholds = get_thresholds_map(conn)
    areas = ["客厅", "主卧", "次卧", "书房", "厨房"]
    data = []
    for a in areas:
        score = round(random.uniform(78, 98), 1)
        cfg = thresholds.get("fttr_score", {})
        data.append({
            "area": a,
            "score": score,
            "issue": "弱覆盖" if score < 85 else "正常",
            "status": _status(score, cfg.get("min_ok"), cfg.get("max_ok"),
                              cfg.get("warn_min"), cfg.get("warn_max"),
                              ),
        })
    cfg = thresholds.get("fttr_score", {})
    avg_score = round(sum(d["score"] for d in data) / len(data), 1) if data else None
    return {
        "status": "green",
        "kpis": [
            {"label": "平均连接率", "value": avg_score, "unit": "%", "status": _status(
                avg_score, cfg.get("min_ok"), cfg.get("max_ok"),
                cfg.get("warn_min"), cfg.get("warn_max"), )},
            {"label": "弱覆盖房间", "value": sum(1 for d in data if d["issue"] == "弱覆盖"), "unit": "个", "status": "yellow"},
        ],
        "areas": data,
        "trend": {
            "labels": ["周一", "周二", "周三", "周四", "周五", "周六"],
            "series": [{"name": "连接率", "data": [round(random.uniform(80, 97), 1) for _ in range(6)]}],
        },
    }


# ---------------------------------------------------------------------------
# 4. 千兆质差小区
# ---------------------------------------------------------------------------
def collect_gigabit(conn):
    thresholds = get_thresholds_map(conn)
    cells = ["小区{}".format(i) for i in range(1, 7)]
    data = []
    for c in cells:
        latency = round(random.uniform(20, 80), 1)
        jitter = round(random.uniform(5, 30), 1)
        low = random.randint(0, 20)
        progress = random.randint(40, 95)
        cfg = thresholds.get("gigabit_latency", {})
        data.append({
            "cell": c,
            "latency": latency,
            "jitter": jitter,
            "low_speed_users": low,
            "repair_status": "整改中" if progress < 100 else "已销号",
            "progress": progress,
            "status": _status(latency, cfg.get("min_ok"), cfg.get("max_ok"),
                              cfg.get("warn_min"), cfg.get("warn_max"),
                              ),
        })
    cfg = thresholds.get("gigabit_latency", {})
    avg_latency = round(sum(d["latency"] for d in data) / len(data), 1) if data else None
    return {
        "status": "green",
        "kpis": [
            {"label": "平均时延", "value": avg_latency, "unit": "ms", "status": _status(
                avg_latency, cfg.get("min_ok"), cfg.get("max_ok"),
                cfg.get("warn_min"), cfg.get("warn_max"), )},
            {"label": "质差小区数", "value": sum(1 for d in data if d["status"] != "green"), "unit": "个", "status": "red"},
        ],
        "cells": data,
        "trend": {
            "labels": ["周一", "周二", "周三", "周四", "周五", "周六"],
            "series": [{"name": "平均时延", "data": [round(random.uniform(25, 70), 1) for _ in range(6)]}],
        },
    }


# ---------------------------------------------------------------------------
# 5. 用户满意度
# ---------------------------------------------------------------------------
def collect_satisfaction(conn):
    thresholds = get_thresholds_map(conn)
    cats = ["服务态度", "装机及时率", "网络质量", "收费争议", "故障处理"]
    data = []
    for c in cats:
        cnt = random.randint(0, 20)
        data.append({"category": c, "cnt": cnt, "status": "red" if cnt > 10 else "yellow" if cnt > 5 else "green"})
    teams = ["班组A", "班组B", "班组C", "班组D", "班组E"]
    tdata = []
    for t in teams:
        score = round(random.uniform(85, 99), 1)
        cfg = thresholds.get("satisfaction_score", {})
        tdata.append({
            "team": t,
            "score": score,
            "status": _status(score, cfg.get("min_ok"), cfg.get("max_ok"),
                              cfg.get("warn_min"), cfg.get("warn_max"),
                              ),
        })
    cfg = thresholds.get("satisfaction_score", {})
    avg_score = round(sum(d["score"] for d in tdata) / len(tdata), 1) if tdata else None
    return {
        "status": "green",
        "kpis": [
            {"label": "综合满意度", "value": avg_score, "unit": "分", "status": _status(
                avg_score, cfg.get("min_ok"), cfg.get("max_ok"),
                cfg.get("warn_min"), cfg.get("warn_max"), )},
            {"label": "不满意工单", "value": sum(d["cnt"] for d in data), "unit": "单", "status": "yellow"},
        ],
        "cats": data,
        "teams": tdata,
        "trend": {
            "labels": ["周一", "周二", "周三", "周四", "周五", "周六"],
            "series": [{"name": "满意度", "data": [round(random.uniform(86, 98), 1) for _ in range(6)]}],
        },
    }


# ---------------------------------------------------------------------------
# 6. 三类问题终端
# ---------------------------------------------------------------------------
def collect_terminal(conn):
    thresholds = get_thresholds_map(conn)
    dists = ["江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "新洲区"]
    data = []
    for d in dists:
        cnt = random.randint(0, 30)
        cfg = thresholds.get("terminal_fault", {})
        data.append({
            "name": d,
            "cnt": cnt,
            "status": _status(cnt, cfg.get("min_ok"), cfg.get("max_ok"),
                              cfg.get("warn_min"), cfg.get("warn_max"),
                              ),
        })
    cfg = thresholds.get("terminal_fault", {})
    total = sum(d["cnt"] for d in data)
    return {
        "status": "green",
        "kpis": [
            {"label": "问题终端总数", "value": total, "unit": "台", "status": _status(
                total, cfg.get("min_ok"), cfg.get("max_ok"),
                cfg.get("warn_min"), cfg.get("warn_max"), )},
            {"label": "故障率", "value": round(total / 600 * 100, 2), "unit": "%", "status": "green"},
        ],
        "dist": data,
        "trend": {
            "labels": ["周一", "周二", "周三", "周四", "周五", "周六"],
            "series": [{"name": "问题终端", "data": [random.randint(10, 35) for _ in range(6)]}],
        },
    }


# ---------------------------------------------------------------------------
# 路由便捷入口
# ---------------------------------------------------------------------------
COLLECTORS = {
    "workorder": collect_workorder,
    "fttr": collect_fttr,
    "gigabit": collect_gigabit,
    "complaint": collect_complaint,
    "satisfaction": collect_satisfaction,
    "terminal": collect_terminal,
    "weaklight": collect_weaklight,
}

# 兼容旧入口： complaints 相关 Repository 函数仍从 db 包暴露
save_complaint_report = complaint_repository.save_complaint_report
latest_complaint_report = complaint_repository.latest_complaint_report
complaint_month_summary = complaint_repository.complaint_month_summary
complaint_batch_detail = complaint_repository.complaint_batch_detail

# 弱光督办 Repository 入口
save_weak_light_report = weak_light_repository.save_weak_light_report
weak_light_dashboard = weak_light_repository.weak_light_dashboard
latest_weak_light = weak_light_repository.latest_weak_light
