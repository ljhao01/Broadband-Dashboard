# -*- coding: utf-8 -*-
"""
数据访问层（DAO）：各看板的数据查询，与路由/解析解耦
每个看板一个 collect_* 函数，相互独立，便于单独维护与替换数据源
"""
from collections import Counter

from db import get_conn, classify
from services import ai_service


def _threshold_map(conn):
    from db import get_thresholds_map
    return get_thresholds_map(conn)


# ================= 1. 装维工单 =================
def collect_workorder(conn):
    thr = _threshold_map(conn)
    rows = conn.execute("SELECT * FROM work_order_daily ORDER BY stat_date").fetchall()
    accepted = [r["accepted"] for r in rows]
    closed = [r["closed"] for r in rows]
    labels = [r["stat_date"][5:] for r in rows]
    today = rows[-1] if rows else None
    accepted_total = sum(accepted)
    closed_total = sum(closed)
    complete_rate = round(closed_total / accepted_total * 100, 1) if accepted_total else 0
    timely = today["timely_rate"] if today else 0
    refund = today["refund_rate"] if today else 0
    rework = today["rework_rate"] if today else 0
    overtime = conn.execute("SELECT COUNT(*) c FROM work_orders WHERE status='overtime'").fetchone()["c"]
    backlog = conn.execute("SELECT COUNT(*) c FROM work_orders WHERE status IN ('processing','overtime')").fetchone()["c"]
    grids = conn.execute("SELECT * FROM grid_eff ORDER BY eff DESC").fetchall()
    orders = conn.execute("SELECT * FROM work_orders ORDER BY overtime_hours DESC LIMIT 8").fetchall()

    def lv(k, v): return classify(v, thr[k])
    return {
        "kpis": [
            {"icon": "assignment_add", "label": "工单受理量", "value": f"{accepted_total:,}", "sub": "近14日", "delta": None},
            {"icon": "task_alt", "label": "工单办结率", "value": f"{complete_rate:.1f}", "unit": "%", "delta": "+1.8%", "good": True, "level": lv("wo_complete_rate", complete_rate)},
            {"icon": "timer", "label": "及时率", "value": f"{timely:.1f}", "unit": "%", "delta": "-2.1%", "good": False, "level": lv("wo_timely_rate", timely)},
            {"icon": "error", "label": "超时工单", "value": f"{overtime}", "unit": "单", "delta": "+12", "good": False, "level": "danger" if overtime > 80 else "warn"},
            {"icon": "inventory_2", "label": "积压工单", "value": f"{backlog}", "unit": "单", "delta": "+8", "good": False, "level": "danger" if backlog > 300 else "warn"},
            {"icon": "undo", "label": "退单率", "value": f"{refund:.1f}", "unit": "%", "delta": "-0.6%", "good": True, "level": lv("wo_refund_rate", refund)},
            {"icon": "build", "label": "返工率", "value": f"{rework:.1f}", "unit": "%", "delta": "+0.4%", "good": False, "level": lv("wo_rework_rate", rework)},
            {"icon": "leaderboard", "label": "效能最优网格", "value": grids[0]["grid"] if grids else "-", "sub": f"{grids[0]['eff']:.1f}%" if grids else ""},
        ],
        "trend": {"labels": labels, "accepted": accepted, "closed": closed},
        "grids": [dict(g) for g in grids],
        "orders": [dict(o) for o in orders],
        "suggestions": ai_service.gen_workorder_suggestions([dict(g) for g in grids], lv("wo_timely_rate", timely), refund, rework),
    }


# ================= 2. FTTR =================
def collect_fttr(conn):
    thr = _threshold_map(conn)
    rows = conn.execute("SELECT * FROM fttr_daily ORDER BY stat_date").fetchall()
    labels = [r["stat_date"][5:] for r in rows]
    success = [r["success_rate"] for r in rows]
    fail = [r["fail_freq"] for r in rows]
    today = rows[-1] if rows else None
    success_rate = today["success_rate"] if today else 0
    fail_freq = today["fail_freq"] if today else 0
    dropout = today["dropout_rate"] if today else 0
    areas = conn.execute("SELECT * FROM fttr_area ORDER BY score DESC").fetchall()
    abnormals = conn.execute("SELECT * FROM fttr_abnormal ORDER BY cnt DESC").fetchall()

    def lv(k, v): return classify(v, thr[k])
    return {
        "kpis": [
            {"icon": "wifi", "label": "连接成功率", "value": f"{success_rate:.1f}", "unit": "%", "delta": "+0.6%", "good": True, "level": lv("fttr_success_rate", success_rate)},
            {"icon": "cancel", "label": "失败频次", "value": f"{fail_freq:,}", "unit": "次/日", "delta": "+34", "good": False, "level": "warn" if fail_freq > 300 else "ok"},
            {"icon": "power_off", "label": "掉线率", "value": f"{dropout:.1f}", "unit": "%", "delta": "-0.3%", "good": True, "level": lv("fttr_dropout_rate", dropout)},
            {"icon": "location_on", "label": "监测区域", "value": f"{len(areas)}", "unit": "个", "sub": "在线监测"},
            {"icon": "warning", "label": "异常点位", "value": str(len([a for a in abnormals if a['level'] != 'ok'])), "unit": "户", "delta": "+3", "good": False, "level": "warn" if len([a for a in abnormals if a['level'] != 'ok']) > 0 else "ok"},
            {"icon": "auto_awesome", "label": "AI 自优化", "value": "运行中", "sub": "智能调度"},
        ],
        "trend": {"labels": labels, "success": success, "fail": fail},
        "areas": [dict(a) for a in areas],
        "abnormals": [dict(a) for a in abnormals],
        "suggestions": ai_service.gen_fttr_suggestions([dict(a) for a in areas], lv("fttr_success_rate", success_rate)),
    }


# ================= 3. 千兆质差小区 =================
def collect_gigabit(conn):
    thr = _threshold_map(conn)
    cells = conn.execute("SELECT * FROM gigabit_cells").fetchall()
    daily = conn.execute("SELECT * FROM gigabit_daily ORDER BY stat_date").fetchall()
    today = daily[-1] if daily else None
    total = today["total_cells"] if today else 0
    poor = today["poor_cells"] if today else 0
    ratio = round(poor / total * 100, 1) if total else 0
    qualify = today["qualify_rate"] if today else 0
    low_users = sum(c["low_speed_users"] for c in cells)
    fixed = len([c for c in cells if c["repair_status"] == "已修复"])
    unfixed = len(cells) - fixed

    def lv(k, v): return classify(v, thr[k])
    return {
        "kpis": [
            {"icon": "domain", "label": "千兆小区总数", "value": f"{total}", "unit": "个", "sub": "在线监测"},
            {"icon": "warning", "label": "质差小区占比", "value": f"{ratio:.1f}", "unit": "%", "delta": "+1.2%", "good": False, "level": lv("giga_poor_ratio", ratio)},
            {"icon": "person", "label": "速率不达标用户", "value": f"{low_users:,}", "unit": "户", "delta": "+156", "good": False, "level": "warn" if low_users > 800 else "ok"},
            {"icon": "verified", "label": "测速合格率", "value": f"{qualify:.1f}", "unit": "%", "delta": "+0.8%", "good": True, "level": lv("giga_qualify_rate", qualify)},
            {"icon": "check_circle", "label": "已修复小区", "value": f"{fixed}", "unit": "个", "sub": "闭环台账"},
            {"icon": "pending", "label": "未修复小区", "value": f"{unfixed}", "unit": "个", "delta": "-2", "good": True, "level": "warn" if unfixed > 2 else "ok"},
            {"icon": "speed", "label": "平均下行速率", "value": "920", "unit": "Mbps", "delta": "+12", "good": True, "sub": "千兆目标"},
            {"icon": "auto_awesome", "label": "AI 质差识别", "value": "实时", "sub": "智能研判"},
        ],
        "cells": [dict(c) for c in cells],
        "trend": {"labels": [d["stat_date"][5:] for d in daily], "ratio": [round(d["poor_cells"] / d["total_cells"] * 100, 1) for d in daily]},
        "suggestions": ai_service.gen_gigabit_suggestions([dict(c) for c in cells]),
    }


# ================= 4. 重复投诉 =================
def collect_complaint(conn):
    thr = _threshold_map(conn)
    daily = conn.execute("SELECT * FROM complaint_daily ORDER BY stat_date").fetchall()
    today = daily[-1] if daily else None
    total = today["total"] if today else 0
    repeat = today["repeat_cnt"] if today else 0
    ratio = round(repeat / total * 100, 1) if total else 0
    closed_rate = today["closed_rate"] if today else 0
    complaints = conn.execute("SELECT * FROM complaints ORDER BY days_overdue DESC").fetchall()
    overdue = [c for c in complaints if c["status"] in ("超时", "临期")]
    prob_counter = Counter(c["problem"] for c in complaints)
    top_problem = prob_counter.most_common(1)[0][0] if prob_counter else ""
    area_counter = Counter(c["area"].split("·")[0] for c in complaints)
    areas = [{"name": k, "cnt": v} for k, v in area_counter.items()]

    def lv(k, v): return classify(v, thr[k])
    return {
        "kpis": [
            {"icon": "forum", "label": "重复投诉总量", "value": f"{repeat}", "unit": "件", "delta": "+9", "good": False, "level": "warn" if ratio > 15 else "ok"},
            {"icon": "percent", "label": "重复投诉占比", "value": f"{ratio:.1f}", "unit": "%", "delta": "+0.7%", "good": False, "level": lv("cp_repeat_ratio", ratio)},
            {"icon": "timer_off", "label": "超时未闭环", "value": str(len(overdue)), "unit": "件", "delta": "+1", "good": False, "level": "danger" if len(overdue) > 3 else "warn"},
            {"icon": "check_circle", "label": "整改销号率", "value": f"{closed_rate:.1f}", "unit": "%", "delta": "+3%", "good": True, "level": lv("cp_closed_rate", closed_rate)},
            {"icon": "auto_awesome", "label": "AI 根因分析", "value": "运行中", "sub": "智能研判"},
            {"icon": "trending_down", "label": "环比压降", "value": "-4.2%", "unit": "", "good": True, "sub": "目标↓"},
        ],
        "problems": [{"name": k, "cnt": v} for k, v in prob_counter.most_common()],
        "areas": areas,
        "overdue": [dict(c) for c in overdue],
        "suggestions": ai_service.gen_complaint_suggestions(len(overdue), top_problem),
    }


# ================= 5. 用户满意度 =================
def collect_satisfaction(conn):
    thr = _threshold_map(conn)
    daily = conn.execute("SELECT * FROM satisfaction_daily ORDER BY stat_date").fetchall()
    today = daily[-1] if daily else None
    score = today["score"] if today else 0
    good = today["good_rate"] if today else 0
    bad = today["bad_rate"] if today else 0
    cats = conn.execute("SELECT * FROM satisfaction_cat ORDER BY cnt DESC").fetchall()
    teams = conn.execute("SELECT * FROM satisfaction_team ORDER BY score DESC").fetchall()

    def lv(k, v): return classify(v, thr[k])
    return {
        "kpis": [
            {"icon": "sentiment_satisfied", "label": "全网满意度得分", "value": f"{score:.1f}", "unit": "分", "delta": "+0.8", "good": True, "level": lv("sat_score", score)},
            {"icon": "thumb_up", "label": "好评率", "value": f"{good:.1f}", "unit": "%", "delta": "+1.2%", "good": True, "level": "ok"},
            {"icon": "thumb_down", "label": "差评率", "value": f"{bad:.1f}", "unit": "%", "delta": "-0.4%", "good": True, "level": lv("sat_bad_rate", bad)},
            {"icon": "trending_up", "label": "整改提升成效", "value": "+3.1", "unit": "分", "sub": "本期"},
            {"icon": "category", "label": "不满意分类", "value": str(len(cats)), "unit": "类", "sub": "实时"},
            {"icon": "leaderboard", "label": "口碑排名班组", "value": str(len(teams)), "unit": "个", "sub": "实时"},
            {"icon": "star", "label": "NPS 净推荐", "value": "46", "unit": "", "delta": "+3", "good": True},
            {"icon": "auto_awesome", "label": "AI 评价挖掘", "value": "运行中", "sub": "智能研判"},
        ],
        "trend": {"labels": [d["stat_date"][5:] for d in daily], "score": [d["score"] for d in daily], "good": [d["good_rate"] for d in daily]},
        "cats": [dict(c) for c in cats],
        "teams": [dict(t) for t in teams],
        "suggestions": ai_service.gen_satisfaction_suggestions([dict(c) for c in cats], [dict(t) for t in teams]),
    }


# ================= 6. 三类问题终端 =================
def collect_terminal(conn):
    thr = _threshold_map(conn)
    daily = conn.execute("SELECT * FROM terminal_daily ORDER BY stat_date").fetchall()
    today = daily[-1] if daily else None
    stock = today["stock"] if today else 0
    abnormal = today["abnormal"] if today else 0
    fixed_rate = today["fixed_rate"] if today else 0
    terminals = conn.execute("SELECT * FROM terminals ORDER BY days_overdue DESC").fetchall()
    overdue_list = [t for t in terminals if t["status"] in ("逾期", "临期")]
    area_counter = Counter(t["area"].split("·")[0] for t in terminals)
    dist = [{"name": k, "cnt": v} for k, v in area_counter.items()]

    def lv(k, v): return classify(v, thr[k])
    return {
        "kpis": [
            {"icon": "router", "label": "三类问题终端存量", "value": f"{stock:,}", "unit": "台", "delta": "+42", "good": False, "level": "warn"},
            {"icon": "error", "label": "在线异常终端", "value": f"{abnormal:,}", "unit": "台", "delta": "+18", "good": False, "level": "warn" if abnormal > 200 else "ok"},
            {"icon": "check_circle", "label": "整改完成率", "value": f"{fixed_rate:.1f}", "unit": "%", "delta": "+2.4%", "good": True, "level": lv("term_fixed_rate", fixed_rate)},
            {"icon": "timer_off", "label": "逾期未处置", "value": str(len(overdue_list)), "unit": "台", "delta": "+5", "good": False, "level": "danger" if len(overdue_list) > 3 else "warn"},
            {"icon": "swap_horiz", "label": "迭代替换进度", "value": "75", "unit": "%", "delta": "+6%", "good": True, "sub": "本期"},
            {"icon": "location_on", "label": "故障分布区域", "value": str(len(dist)), "unit": "个", "sub": "实时"},
            {"icon": "auto_awesome", "label": "AI 终端研判", "value": "运行中", "sub": "智能识别"},
            {"icon": "monitor_heart", "label": "在线健康度", "value": "94", "unit": "%", "delta": "+0.5%", "good": True, "sub": "实时"},
        ],
        "dist": dist,
        "terminals": [dict(t) for t in overdue_list],
        "suggestions": ai_service.gen_terminal_suggestions([dict(t) for t in overdue_list], lv("term_fixed_rate", fixed_rate)),
    }


# 看板查询入口映射（路由层按 view 名调用，互不耦合）
COLLECTORS = {
    "workorder": collect_workorder,
    "fttr": collect_fttr,
    "gigabit": collect_gigabit,
    "complaint": collect_complaint,
    "satisfaction": collect_satisfaction,
    "terminal": collect_terminal,
}


# ================= 报表上传：落库与读取（DAO） =================
def save_complaint_report(res, filename):
    """将解析结果写入数据库（每次上传一条批次 + 武汉各区明细），永久留存、不变"""
    from datetime import datetime
    now = datetime.now()
    period = res.get("period", {})
    city = res.get("city", {})
    districts = res.get("wuhan_districts", [])
    upload_date = now.strftime("%Y-%m-%d")
    # 账期月份：优先取报表数据开始日期的年月，无法识别则用上传月份
    stat_month = (period.get("start") or upload_date)[:7]
    conn = get_conn()
    try:
        sql_main = ("INSERT INTO complaint_upload "
                    "(filename, report_date, period_start, period_end, city_rate, city_users, "
                    " city_orders, upload_date, stat_month, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)")
        params_main = (filename, period.get("report_date"), period.get("start"), period.get("end"),
                       city.get("repeat_rate"), city.get("repeat_users"), city.get("total_orders"),
                       upload_date, stat_month, now.strftime("%Y-%m-%d %H:%M:%S"))
        cur = conn.execute(sql_main, params_main)
        batch_id = cur.lastrowid
        for d in districts:
            conn.execute(
                """INSERT INTO complaint_upload_district
                   (batch_id, district, repeat_users, total_orders, repeat_rate)
                   VALUES (?,?,?,?,?)""",
                (batch_id, d["district"], d["repeat_users"], d["total_orders"], d["repeat_rate"]))
        conn.commit()
        return batch_id
    finally:
        conn.close()


def _batch_to_dict(r):
    return {
        "id": r["id"], "filename": r["filename"],
        "period_start": r["period_start"], "period_end": r["period_end"],
        "city_rate": r["city_rate"], "upload_date": r["upload_date"],
        "stat_month": r["stat_month"], "created_at": r["created_at"],
    }


def latest_complaint_report():
    """读取数据库最新批次的报表数据（含各区明细 + 历史批次列表）"""
    conn = get_conn()
    try:
        latest = conn.execute(
            "SELECT id, filename, period_start, period_end, city_rate, city_users, "
            "city_orders, upload_date, stat_month, created_at "
            "FROM complaint_upload ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return {"ok": True, "has_data": False}
        batch_id = latest["id"]
        rows = conn.execute(
            "SELECT district, repeat_rate, repeat_users, total_orders FROM complaint_upload_district "
            "WHERE batch_id=? ORDER BY repeat_rate DESC", (batch_id,)
        ).fetchall()
        history = conn.execute(
            "SELECT id, filename, period_start, period_end, city_rate, city_users, "
            "city_orders, upload_date, stat_month, created_at "
            "FROM complaint_upload ORDER BY id DESC LIMIT 20"
        ).fetchall()
        return {
            "ok": True,
            "has_data": True,
            "batch": dict(latest),
            "districts": [dict(r) for r in rows],
            "history": [_batch_to_dict(r) for r in history],
        }
    finally:
        conn.close()


def complaint_month_summary(month=None):
    """按月累计汇总（每月清零语义）：返回该月批次数、最新武汉整体、最新各区明细、每日新增"""
    from datetime import datetime
    conn = get_conn()
    try:
        if not month:
            month = datetime.now().strftime("%Y-%m")
        # 该月全部批次
        batches = conn.execute(
            "SELECT id, filename, period_start, period_end, city_rate, city_users, "
            "city_orders, upload_date, stat_month, created_at "
            "FROM complaint_upload WHERE stat_month=? ORDER BY id", (month,)
        ).fetchall()
        if not batches:
            return {"ok": True, "has_data": False, "month": month,
                    "batch_count": 0, "daily_new": [], "latest": None, "districts": []}
        # 每日新增批次数（按上传日期聚合）
        daily = conn.execute(
            "SELECT upload_date, COUNT(*) AS cnt FROM complaint_upload "
            "WHERE stat_month=? GROUP BY upload_date ORDER BY upload_date", (month,)
        ).fetchall()
        # 取该月最新一条作为整体值
        latest = batches[-1]
        rows = conn.execute(
            "SELECT district, repeat_rate, repeat_users, total_orders FROM complaint_upload_district "
            "WHERE batch_id=? ORDER BY repeat_rate DESC", (latest["id"],)
        ).fetchall()
        return {
            "ok": True,
            "has_data": True,
            "month": month,
            "batch_count": len(batches),
            "daily_new": [{"date": r["upload_date"], "cnt": r["cnt"]} for r in daily],
            "latest": _batch_to_dict(latest),
            "districts": [dict(r) for r in rows],
            "history": [_batch_to_dict(r) for r in batches],
        }
    finally:
        conn.close()


def complaint_batch_detail(batch_id):
    """读取指定批次的完整明细（数据不变）"""
    conn = get_conn()
    try:
        batch = conn.execute(
            "SELECT id, filename, period_start, period_end, city_rate, city_users, "
            "city_orders, upload_date, stat_month, created_at "
            "FROM complaint_upload WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch:
            return {"ok": False, "error": "批次不存在"}
        rows = conn.execute(
            "SELECT district, repeat_rate, repeat_users, total_orders FROM complaint_upload_district "
            "WHERE batch_id=? ORDER BY repeat_rate DESC", (batch_id,)
        ).fetchall()
        return {
            "ok": True,
            "batch": _batch_to_dict(batch),
            "districts": [dict(r) for r in rows],
        }
    finally:
        conn.close()
