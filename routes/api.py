# -*- coding: utf-8 -*-
"""数据接口：看板数据、报表上传、图表、导出、阈值配置（JSON / 文件）"""
import csv
import io
import json
import os
from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, redirect, url_for

from db import get_conn, load_snapshot, save_snapshot
from db.models import COLLECTORS, save_complaint_report
from db.repositories import complaint_repository, weak_light_repository
from services import complaint_report as report_svc
from services import weak_light_report as weak_svc
from services import person_map as person_svc

api_bp = Blueprint("api", __name__)

# 进程级内存缓存（最近一次上传解析结果，供前端刷新保持）
REPORT_CACHE = {"complaint": None, "weaklight": None}

# 需要走"快照缓存"的看板（打开页面即展示上次采集的数据，不每次重新随机）
# 注意：complaint / weaklight 数据本身已落库，不走此快照，直接读 DB 最新批次
SNAPSHOT_VIEWS = {"workorder", "fttr", "gigabit", "satisfaction", "terminal"}


@api_bp.route("/api/data/<view>")
def api_data(view):
    if view not in COLLECTORS:
        return jsonify({"error": "未知看板"}), 404

    # 投诉 / 弱光看板：数据已落库，直接读取最新，不走随机快照
    if view in ("complaint", "weaklight"):
        conn = get_conn()
        try:
            return jsonify(COLLECTORS[view](conn))
        finally:
            conn.close()

    # 其他看板：默认返回上次数据快照（打开即"上一次的"）；带 ?refresh=1 强制重新采集并存档
    force_refresh = request.args.get("refresh") == "1"
    conn = get_conn()
    try:
        snap = load_snapshot(conn, view)
        if snap and not force_refresh:
            return jsonify(json.loads(snap))
        data = COLLECTORS[view](conn)
        save_snapshot(conn, view, json.dumps(data, ensure_ascii=False))
        return jsonify(data)
    finally:
        conn.close()


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
    return jsonify(complaint_repository.complaint_month_summary(month))


@api_bp.route("/api/complaint_batch")
def complaint_batch():
    """读取指定批次的完整明细（数据不变，可切换查看任意历史批次）"""
    try:
        batch_id = int(request.args.get("id", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "批次ID无效"}), 400
    return jsonify(complaint_repository.complaint_batch_detail(batch_id))


# ---------------------------------------------------------------------------
# 弱光督办（新洲区弱光指标提升）
# ---------------------------------------------------------------------------
@api_bp.route("/api/upload_weaklight", methods=["POST"])
def upload_weaklight():
    """上传《存量及新增弱光》Excel，解析新洲区数据并落库。"""
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    if not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": "仅支持 Excel 文件(.xlsx/.xls)"}), 400
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_upload_weak_tmp.xlsx")
    f.save(tmp)
    try:
        res = weak_svc.parse_weak_light_report(tmp, f.filename)
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败：{e}"}), 500
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    if not res.get("ok"):
        return jsonify({"ok": False, "error": res.get("error", "解析失败")}), 500
    # 落库
    try:
        batch_id = weak_light_repository.save_weak_light_report(res, f.filename)
        res["batch_id"] = batch_id
    except Exception as e:
        res["db_error"] = f"保存数据库失败：{e}"
    REPORT_CACHE["weaklight"] = res
    return jsonify({"ok": True, "data": res})


@api_bp.route("/api/upload_weaklight_person", methods=["POST"])
def upload_weaklight_person():
    """上传《人员录》xls，建立小区/网格 → 对应人员映射（覆盖更新）。"""
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    if not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": "仅支持 Excel 文件(.xlsx/.xls)"}), 400
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_upload_person_tmp.xls")
    f.save(tmp)
    try:
        res = person_svc.parse_person_report(tmp, f.filename)
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败：{e}"}), 500
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    if not res.get("ok"):
        return jsonify({"ok": False, "error": res.get("error", "解析失败")}), 500
    try:
        saved = weak_light_repository.save_person_map(res, f.filename)
        res["saved"] = saved
    except Exception as e:
        res["db_error"] = f"保存数据库失败：{e}"
    return jsonify({"ok": True, "data": res})


@api_bp.route("/api/weaklight_dashboard")
def weaklight_dashboard():
    """弱光看板数据（基于最新批次）。"""
    return jsonify(weak_light_repository.weak_light_dashboard())


@api_bp.route("/api/weaklight_batches")
def weaklight_batches():
    """全部历史批次列表。"""
    return jsonify({"batches": weak_light_repository.weak_light_batches()})


@api_bp.route("/api/weaklight_batch")
def weaklight_batch():
    """读取指定批次的完整数据。"""
    try:
        batch_id = int(request.args.get("id", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "批次ID无效"}), 400
    return jsonify(weak_light_repository.weak_light_batch_detail(batch_id))


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
        "weaklight": "弱光督办",
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
        w.writerow(["重复投诉总量", f"{data.get('kpis', [{}])[0].get('value', '-')}单"])
        w.writerow(["重复投诉占比", f"{data.get('kpis', [{}, {}])[1].get('value', '-')}%"])
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
    elif view == "weaklight":
        w.writerow([])
        w.writerow(["小区弱光排行", "弱光数", "前日", "变化", "质差类型"])
        for c in data.get("communities", []):
            w.writerow([c["community"], c["weak_count"], c["prev_count"], c["change_val"], c.get("quality_type", "")])
        w.writerow([])
        w.writerow(["PON口集中度", "弱光数", "前日", "变化", "小区", "质差标记"])
        for p in data.get("pons", []):
            w.writerow([p["pon"], p["weak_count"], p["prev_count"], p["change_val"], p.get("community", ""), "是" if p.get("weak_mark") else ""])
        w.writerow([])
        w.writerow(["新增弱光清单", "弱光天数", "装机日期", "网关SN", "小区", "回单人员", "是否整改"])
        for n in data.get("new_weaks", []):
            w.writerow([n.get("community", ""), n.get("weak_days"), n.get("install_date", ""), n.get("gateway_sn", ""), n.get("community", ""), n.get("technician", ""), "是" if n.get("is_rectified") else "否"])
        w.writerow([])
        w.writerow(["持续弱光清单", "网关SN", "小区", "谷值光功率", "质差类型"])
        for s in data.get("sustained_users", []):
            w.writerow([s.get("gateway_sn", ""), s.get("community", ""), s.get("valley_power"), s.get("quality_type", "")])
        w.writerow([])
        w.writerow(["严重弱光清单", "网关SN", "小区", "谷值光功率", "质差类型"])
        for s in data.get("severe_users", []):
            w.writerow([s.get("gateway_sn", ""), s.get("community", ""), s.get("valley_power"), s.get("quality_type", "")])

    resp = make_response("\ufeff" + out.getvalue())
    # 文件名含中文，需用 RFC 5987 编码（filename*=UTF-8''...），否则 latin-1 报错
    from urllib.parse import quote
    resp.headers["Content-Disposition"] = f"attachment; filename={quote(fname)}; filename*=UTF-8''{quote(fname)}"
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    return resp


@api_bp.route("/api/scoring")
def api_scoring():
    """综合评分：按 5 个模块的考核规则 + 当前指标值计算加权得分。

    当前值来源：
        - satisfaction：satisfaction 看板综合满意度（kpis 中 "综合满意度"）
        - workorder  ：workorder 看板平均装机效能（kpis 中 "平均装机效能"）反向归一化为"质差率"
        - complaint  ：complaint 看板 city_rate（已落库的真实最新数据）
        - fttr       ：fttr 看板平均连接率（kpis 中 "平均连接率"）
        - terminal   ：terminal 看板故障率（kpis 中 "故障率"）
    """
    from db import get_score_rules, compute_module_score

    conn = get_conn()
    try:
        rules = get_score_rules(conn)

        # 各模块当前值采集器：从对应看板的 kpis 中提取，并按规则标准化（%/小数）
        def _current_for(indicator):
            view = {
                "satisfaction": "satisfaction",
                "workorder": "workorder",
                "complaint": "complaint",
                "fttr": "fttr",
                "terminal": "terminal",
            }[indicator]
            data = COLLECTORS[view](conn)
            kpis = data.get("kpis", [])
            if indicator == "satisfaction":
                for k in kpis:
                    if k.get("label") == "综合满意度":
                        return k.get("value")
                return None
            if indicator == "workorder":
                # 用"平均装机效能"反推"质差率"=100-效能
                for k in kpis:
                    if k.get("label") == "平均装机效能":
                        eff = k.get("value")
                        if isinstance(eff, (int, float)):
                            return round(100.0 - float(eff), 2)
                        return None
                return None
            if indicator == "fttr":
                # 平均连接率为百分数（如 96），基准值为小数（如 0.96），统一除以 100
                for k in kpis:
                    if k.get("label") == "平均连接率":
                        v = k.get("value")
                        if isinstance(v, (int, float)):
                            return round(float(v) / 100.0, 4)
                        return None
                return None
            if indicator == "terminal":
                # 故障率 %（如 5.5） → 保持原值与基准对齐
                for k in kpis:
                    if k.get("label") == "故障率":
                        return k.get("value")
                return None
            return None

        # 投诉：单独从 complaint_repository 读取真实最新数据（不读快照）
        # 聚焦新洲区：取最新批次中「新洲区」的重复投诉率（15 区口径内）
        latest_complaint = complaint_repository.latest_complaint_report()
        complaint_value = None
        if latest_complaint:
            xz = next(
                (d for d in (latest_complaint.get("districts") or [])
                 if d.get("district") == "新洲区"),
                None,
            )
            complaint_value = (xz or {}).get("repeat_rate")

        results = []
        total_weight = 0.0
        total_score = 0.0
        for r in rules:
            if r["indicator"] == "complaint":
                cur = complaint_value
            else:
                cur = _current_for(r["indicator"])
            calc = compute_module_score(r, cur)
            item = {**r, **calc}
            # 不返回过大的 criteria/scoring 文本，减少数据量
            results.append(item)
            total_weight += r["weight"]
            total_score += calc["score"]

        return jsonify({
            "modules": results,
            "total_weight": total_weight,
            "total_score": round(total_score, 2),
            "total_ratio": round(total_score / total_weight * 100 if total_weight else 0, 1),
        })
    finally:
        conn.close()


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
