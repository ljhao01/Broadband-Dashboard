# -*- coding: utf-8 -*-
"""数据接口：看板数据、报表上传、图表、导出、阈值配置（JSON / 文件）"""
import csv
import io
import os
from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, redirect, url_for

from db import get_conn
from db.models import COLLECTORS, save_complaint_report, latest_complaint_report, complaint_month_summary, complaint_batch_detail
from services import complaint_report as report_svc

api_bp = Blueprint("api", __name__)

# 进程级内存缓存（最近一次上传解析结果，供前端刷新保持）
REPORT_CACHE = {"complaint": None}


@api_bp.route("/api/data/<view>")
def api_data(view):
    if view not in COLLECTORS:
        return jsonify({"error": "未知看板"}), 404
    conn = get_conn()
    try:
        data = COLLECTORS[view](conn)
    finally:
        conn.close()
    return jsonify(data)


@api_bp.route("/api/upload_report", methods=["POST"])
def upload_report():
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    if not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": "仅支持 Excel 文件(.xlsx/.xls)"}), 400
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_upload_tmp.xlsx")
    f.save(tmp)
    try:
        res = report_svc.parse_complaint_report(tmp)
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败：{e}"}), 500
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    # 落库
    try:
        save_complaint_report(res, f.filename)
    except Exception as e:
        res["db_error"] = f"保存数据库失败：{e}"
    REPORT_CACHE["complaint"] = res
    return jsonify({"ok": True, "data": res})


@api_bp.route("/api/report_cache")
def report_cache():
    return jsonify(REPORT_CACHE["complaint"] or {"ok": False, "error": "暂无上传报表"})


@api_bp.route("/api/complaint_chart")
def complaint_chart():
    """按月累计汇总：本月批次数、每日新增、最新整体与各区明细、历史批次列表"""
    month = request.args.get("month")
    return jsonify(complaint_month_summary(month))


@api_bp.route("/api/complaint_batch")
def complaint_batch():
    """读取指定批次的完整明细（数据不变，可切换查看任意历史批次）"""
    try:
        batch_id = int(request.args.get("id", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "批次ID无效"}), 400
    return jsonify(complaint_batch_detail(batch_id))


@api_bp.route("/export/<view>")
def export_report(view):
    if view not in COLLECTORS:
        return jsonify({"error": "未知看板"}), 404
    conn = get_conn()
    try:
        data = COLLECTORS[view](conn)
    finally:
        conn.close()

    collector_name = {
        "workorder": "装维工单", "fttr": "FTTR无线连接率", "gigabit": "千兆质差小区",
        "complaint": "重复投诉率", "satisfaction": "用户满意度", "terminal": "三类问题终端",
    }.get(view, view)
    today = datetime.now().strftime("%Y%m%d")
    fname = f"{collector_name}_报表_{today}.csv"

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"{collector_name} 报表导出", today])
    for kp in data.get("kpis", []):
        w.writerow([kp.get("label", ""), f"{kp.get('value','')}{kp.get('unit','')}"])
    # 看板特有明细
    if view == "complaint":
        w.writerow([])
        w.writerow(["TOP问题", "数量"])
        for p in data.get("problems", []):
            w.writerow([p["name"], p["cnt"]])
        w.writerow(["区域", "数量"])
        for a in data.get("areas", []):
            w.writerow([a["name"], a["cnt"]])
    elif view == "satisfaction":
        w.writerow([])
        w.writerow(["不满意分类", "数量"])
        for c in data.get("cats", []):
            w.writerow([c["category"], c["cnt"]])
        w.writerow(["班组", "满意度得分"])
        for t in data.get("teams", []):
            w.writerow([t["team"], t["score"]])
    elif view == "terminal":
        w.writerow([])
        w.writerow(["故障区域", "数量"])
        for d in data.get("dist", []):
            w.writerow([d["name"], d["cnt"]])
    elif view == "gigabit":
        w.writerow([])
        w.writerow(["小区", "时延ms", "抖动ms", "不达标用户", "状态", "进度%"])
        for c in data.get("cells", []):
            w.writerow([c["cell"], c["latency"], c["jitter"], c["low_speed_users"], c["repair_status"], c["progress"]])
    elif view == "workorder":
        w.writerow([])
        w.writerow(["网格", "效能%"])
        for g in data.get("grids", []):
            w.writerow([g["grid"], g["eff"]])
    elif view == "fttr":
        w.writerow([])
        w.writerow(["区域", "质量分", "问题"])
        for a in data.get("areas", []):
            w.writerow([a["area"], a["score"], a["issue"]])

    resp = make_response("\ufeff" + out.getvalue())
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    return resp


@api_bp.route("/admin/thresholds/update", methods=["POST"])
def update_threshold():
    indicator = request.form.get("indicator")
    min_ok = request.form.get("min_ok") or None
    max_ok = request.form.get("max_ok") or None
    warn_min = request.form.get("warn_min") or None
    warn_max = request.form.get("warn_max") or None
    good_is_high = request.form.get("good_is_high", "1")

    def to_float(x):
        try:
            return float(x) if x not in (None, "") else None
        except ValueError:
            return None

    conn = get_conn()
    conn.execute(
        """UPDATE thresholds SET min_ok=?, max_ok=?, warn_min=?, warn_max=?, good_is_high=?
           WHERE indicator=?""",
        (to_float(min_ok), to_float(max_ok), to_float(warn_min), to_float(warn_max),
         int(good_is_high), indicator))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard.admin_thresholds", saved=indicator))
