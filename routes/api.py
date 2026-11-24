# -*- coding: utf-8 -*-
"""
弱光督办模块数据接口。

接口清单（全部属于弱光模块）：
  GET  /api/data/weaklight              弱光看板数据（最新批次，前端主接口）
  GET  /api/weaklight_dashboard         同 /api/data/weaklight（语义化别名）
  GET  /api/weaklight_batches           全部历史批次列表
  GET  /api/weaklight_batch?id=<id>     指定批次完整数据
  POST /api/upload_weaklight            上传《存量及新增弱光》Excel → 解析落库
  POST /api/upload_weaklight_person     上传《人员录》→ 建立小区 → 装维人员映射
  GET  /api/weaklight_sustained         持续弱光追踪（同一网关SN跨批次反复弱光）
  GET  /api/weaklight_insights          智能总结（结构化问题清单 + 优先级）
  GET  /export/weaklight                导出弱光报表 CSV

推送督办接口见 routes/push.py（/api/push_*、/export/push_list、/push/ack）。
"""
import csv
import io
import os
import tempfile
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, request, jsonify, make_response

from db.repositories import weak_light_repository
from services import person_map as person_svc
from services import push_service
from services import weak_light_report as weak_svc

api_bp = Blueprint("api", __name__)

# 进程级内存缓存（最近一次弱光上传解析结果，供前端即时展示）
REPORT_CACHE = {"weaklight": None}


def _dashboard_payload():
    """看板数据 + 推送摘要（推送摘要失败不影响主看板）。"""
    data = weak_light_repository.weak_light_dashboard()
    try:
        data["push_summary"] = push_service.summary()
    except Exception:
        data["push_summary"] = {}
    return data


# ---------------------------------------------------------------------------
# 看板数据
# ---------------------------------------------------------------------------
@api_bp.route("/api/data/weaklight")
def api_data_weaklight():
    """弱光看板数据（基于最新批次，数据已落库，打开即展示）。"""
    return jsonify(_dashboard_payload())


@api_bp.route("/api/weaklight_dashboard")
def weaklight_dashboard():
    """弱光看板数据（语义化别名，与 /api/data/weaklight 等价）。"""
    return jsonify(_dashboard_payload())


@api_bp.route("/api/weaklight_batches")
def weaklight_batches():
    """全部历史批次列表。"""
    return jsonify({"batches": weak_light_repository.weak_light_batches()})


@api_bp.route("/api/weaklight_field")
def weaklight_field():
    """责任田清单：按责任人聚合 + 每人负责的责任田明细。

    可选参数：
      ?person=张三   仅返回该责任人的责任田
      ?summary=1     仅返回汇总（不含逐条明细，减小响应体）
    """
    person = request.args.get("person")
    data = weak_light_repository.field_listing(person)
    if request.args.get("summary") == "1":
        data["persons"] = [
            {k: v for k, v in p.items() if k != "fields"} for p in data["persons"]
        ]
    return jsonify(data)


@api_bp.route("/api/weaklight_sustained")
def weaklight_sustained():
    """持续弱光追踪：同一网关 SN 在最近批次窗口内累计出现 ≥N 个批次。

    可选参数：min_batches（默认 3）、lookback（默认 10）、limit（默认 200）。
    """
    def _int_arg(name, default):
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    return jsonify(weak_light_repository.sustained_tracking(
        min_batches=_int_arg("min_batches", weak_light_repository.SUSTAINED_MIN_BATCHES),
        lookback=_int_arg("lookback", weak_light_repository.SUSTAINED_LOOKBACK),
        limit=_int_arg("limit", 200),
    ))


@api_bp.route("/api/weaklight_insights")
def weaklight_insights():
    """智能总结：结构化问题清单 + 优先级排序（规则计算，不依赖 LLM）。

    可选参数：batch_id（缺省最新批次）、overdue_days（默认 14）。
    """
    def _int_arg(name, default=0):
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    return jsonify(weak_light_repository.build_insights(
        batch_id=_int_arg("batch_id", 0) or None,
        overdue_days=_int_arg("overdue_days", weak_light_repository.INSIGHT_OVERDUE_DAYS),
    ))


@api_bp.route("/api/weaklight_batch")
def weaklight_batch():
    """读取指定批次的完整数据。"""
    try:
        batch_id = int(request.args.get("id", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "批次ID无效"}), 400
    return jsonify(weak_light_repository.weak_light_batch_detail(batch_id))


# ---------------------------------------------------------------------------
# 上传解析
# ---------------------------------------------------------------------------
@api_bp.route("/api/upload_weaklight", methods=["POST"])
def upload_weaklight():
    """上传《存量及新增弱光》Excel，解析新洲区数据并落库。"""
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    if not f.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        return jsonify({"ok": False, "error": "仅支持 Excel(.xlsx/.xls) 或 CSV(.csv) 文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower() or ".xlsx"
    fd, tmp = tempfile.mkstemp(prefix="wl_weak_", suffix=ext)  # 系统临时目录，不污染项目
    os.close(fd)
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
    # 临时文件沿用原始扩展名，并放在系统临时目录（避免残留污染项目根目录）
    ext = os.path.splitext(f.filename)[1].lower() or ".xlsx"
    fd, tmp = tempfile.mkstemp(prefix="wl_person_", suffix=ext)
    os.close(fd)
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
    # 解析结果为空时拒绝落库，避免覆盖清空已有责任田数据
    if not (res.get("fields") or res.get("community_map")):
        return jsonify({
            "ok": False,
            "error": "未解析到任何人员/责任田记录，已保留原有数据（请检查文件格式）",
        }), 400
    try:
        saved = weak_light_repository.save_person_map(res, f.filename)
        res["saved"] = saved
    except Exception as e:
        res["db_error"] = f"保存数据库失败：{e}"
    # 逐条责任田记录可能上千条，响应中不回传，仅返回统计
    res.pop("fields", None)
    return jsonify({"ok": True, "data": res})


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
@api_bp.route("/export/weaklight")
def export_weaklight():
    """导出弱光报表 CSV（小区排行 / PON 口 / 新增 / 持续 / 严重）。"""
    data = weak_light_repository.weak_light_dashboard()
    today = datetime.now().strftime("%Y%m%d")
    fname = f"弱光督办_报表_{today}.csv"

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["弱光督办 报表导出", today])
    for kp in data.get("kpis", []):
        w.writerow([kp.get("label", ""), f"{kp.get('value', '')}{kp.get('unit', '')}"])

    w.writerow([])
    w.writerow(["小区弱光排行", "弱光数", "前日", "变化", "质差类型"])
    for c in data.get("communities", []):
        w.writerow([c["community"], c["weak_count"], c["prev_count"],
                    c["change_val"], c.get("quality_type", "")])

    w.writerow([])
    w.writerow(["PON口集中度", "弱光数", "前日", "变化", "小区", "质差标记"])
    for p in data.get("pons", []):
        w.writerow([p["pon"], p["weak_count"], p["prev_count"],
                    p["change_val"], p.get("community", ""), "是" if p.get("weak_mark") else ""])

    w.writerow([])
    w.writerow(["新增弱光清单", "弱光天数", "装机日期", "网关SN", "小区", "回单人员", "是否整改"])
    for n in data.get("new_weaks", []):
        w.writerow([n.get("community", ""), n.get("weak_days"), n.get("install_date", ""),
                    n.get("gateway_sn", ""), n.get("community", ""), n.get("technician", ""),
                    "是" if n.get("is_rectified") else "否"])

    w.writerow([])
    w.writerow(["持续弱光清单", "网关SN", "小区", "谷值光功率", "质差类型"])
    for s in data.get("sustained_users", []):
        w.writerow([s.get("gateway_sn", ""), s.get("community", ""),
                    s.get("valley_power"), s.get("quality_type", "")])

    w.writerow([])
    w.writerow(["严重弱光清单", "网关SN", "小区", "谷值光功率", "质差类型"])
    for s in data.get("severe_users", []):
        w.writerow([s.get("gateway_sn", ""), s.get("community", ""),
                    s.get("valley_power"), s.get("quality_type", "")])

    w.writerow([])
    w.writerow([f"持续弱光追踪（同一网关SN累计出现≥{weak_light_repository.SUSTAINED_MIN_BATCHES}个批次）"])
    w.writerow(["网关SN", "小区", "对应人员", "出现批次", "未整改次数",
                "持续天数", "首次日期", "最近日期", "最低谷值", "是否高频"])
    sus = weak_light_repository.sustained_tracking(limit=500)
    for it in sus.get("items", []):
        w.writerow([it["gateway_sn"], it["community"], it.get("person", ""),
                    it["appear_batches"], it["unfixed_times"], it["span_days"],
                    it["first_date"], it["last_date"],
                    "" if it["min_valley"] is None else it["min_valley"],
                    "是" if it["is_high_freq"] else "否"])

    resp = make_response("\ufeff" + out.getvalue())
    # 文件名含中文，需用 RFC 5987 编码（filename*=UTF-8''...），否则 latin-1 报错
    resp.headers["Content-Disposition"] = (
        f"attachment; filename={quote(fname)}; filename*=UTF-8''{quote(fname)}"
    )
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    return resp
