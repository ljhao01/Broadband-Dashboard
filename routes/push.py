# -*- coding: utf-8 -*-
"""弱光推送路由（企业微信群机器人 · 网格长督办）。

接口清单：
  GET  /api/push_preview          推送预览：网格 × 网格长、未匹配池、已推状态
  POST /api/push_trigger          一键触发推送（后台线程串行发送）
  GET  /api/push_tasks            推送任务列表
  GET  /api/push_task?id=<id>     任务明细（前端轮询）
  GET  /api/push_summary          推送摘要（入口卡 / 面板顶部）
  GET  /api/push_config           读取推送配置（webhook 掩码）
  POST /api/push_config           保存推送配置（页面配置，立即生效）
  POST /api/push_test             发送测试消息验证 webhook
  POST /api/push_retry            失败条目重推
  POST /api/upload_grid_leader    上传网格长名单（CSV/XLSX）
  GET  /export/push_list          导出推送清单 CSV（无通道兜底）
  GET  /push/ack?t=<token>        网格长回执确认页（H5）
  POST /api/push_ack              提交确认
"""
import csv
import io
import os
import re
import tempfile
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, request, jsonify, make_response

from services import push_service

push_bp = Blueprint("push", __name__)


def _int_arg(name, default=0):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _host_base():
    """回执链接的默认前缀（未配置 PUSH_ACK_BASE_URL 时用当前请求 Host）。"""
    try:
        return request.host_url.rstrip("/")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 预览 / 触发
# ---------------------------------------------------------------------------
@push_bp.route("/api/push_preview")
def push_preview():
    res = push_service.build_preview(batch_id=_int_arg("batch_id", 0) or None)
    return jsonify(res)


@push_bp.route("/api/push_trigger", methods=["POST"])
def push_trigger():
    body = request.get_json(silent=True) or {}
    batch_id = body.get("batch_id")
    try:
        batch_id = int(batch_id) if batch_id else None
    except (TypeError, ValueError):
        batch_id = None
    res = push_service.trigger_push(
        batch_id=batch_id,
        grid_codes=body.get("grid_codes") or [],
        force=bool(body.get("force")),
        operator=(body.get("operator") or "")[:40],
        remark=(body.get("remark") or "")[:200],
        ack_base=_host_base(),
    )
    return jsonify(res), (200 if res.get("ok") else 400)


@push_bp.route("/api/push_tasks")
def push_tasks():
    return jsonify({"ok": True, "tasks": push_service.list_tasks(limit=_int_arg("limit", 20))})


@push_bp.route("/api/push_task")
def push_task():
    return jsonify(push_service.get_task(_int_arg("id", 0)))


@push_bp.route("/api/push_summary")
def push_summary():
    return jsonify({"ok": True, "data": push_service.summary(batch_id=_int_arg("batch_id", 0) or None)})


@push_bp.route("/api/push_retry", methods=["POST"])
def push_retry():
    body = request.get_json(silent=True) or {}
    res = push_service.retry_targets(body.get("ids") or [])
    return jsonify(res), (200 if res.get("ok") else 400)


# ---------------------------------------------------------------------------
# 推送通道配置（页面配置写入 app_setting，优先于环境变量，保存即生效）
# ---------------------------------------------------------------------------
@push_bp.route("/api/push_config")
def push_config_get():
    return jsonify({"ok": True, "config": push_service.get_config_public()})


@push_bp.route("/api/push_config", methods=["POST"])
def push_config_save():
    res = push_service.save_config(request.get_json(silent=True) or {})
    return jsonify(res), (200 if res.get("ok") else 400)


@push_bp.route("/api/push_test", methods=["POST"])
def push_test():
    """发送一条测试消息，验证 webhook 是否可用（不落库）。"""
    body = request.get_json(silent=True) or {}
    res = push_service.test_webhook(body.get("webhook") or "", body.get("msg_type") or "")
    return jsonify(res), (200 if res.get("ok") else 400)


# ---------------------------------------------------------------------------
# 网格长名单上传
# ---------------------------------------------------------------------------
@push_bp.route("/api/upload_grid_leader", methods=["POST"])
def upload_grid_leader():
    f = request.files.get("file")
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    if not f.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        return jsonify({"ok": False, "error": "仅支持 Excel(.xlsx/.xls) 或 CSV(.csv) 文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower() or ".xlsx"
    fd, tmp = tempfile.mkstemp(prefix="wl_leader_", suffix=ext)
    os.close(fd)
    f.save(tmp)
    try:
        rows = push_service.parse_grid_leader_file(tmp, f.filename)
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败：{e}"}), 500
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    if not rows:
        return jsonify({
            "ok": False,
            "error": "未解析到网格长记录，已保留原有名单（请检查是否含「网格长姓名 / 手机号」列）",
        }), 400

    saved = push_service.save_grid_leaders(rows, f.filename)
    return jsonify({
        "ok": True,
        "data": {
            "saved": saved,
            "grid_cnt": len({r["grid_code"] for r in rows}),
            "no_phone": len([r for r in rows if not r["phone"]]),
        },
    })


# ---------------------------------------------------------------------------
# 导出推送清单（无通道兜底）
# ---------------------------------------------------------------------------
@push_bp.route("/export/push_list")
def export_push_list():
    res = push_service.export_preview(batch_id=_int_arg("batch_id", 0) or None)
    if not res.get("ok"):
        return jsonify({"ok": False, "error": res.get("error", "导出失败")}), 400

    today = datetime.now().strftime("%Y%m%d")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"弱光推送清单 数据日期 {res.get('data_date') or '—'} 导出 {today}"])
    rows = res.get("rows") or []
    if rows:
        w.writerow(list(rows[0].keys()))
        for r in rows:
            w.writerow(list(r.values()))

    body = "\ufeff" + out.getvalue()
    fname = f"弱光推送清单_{today}.csv"
    resp = make_response(body)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return resp


# ---------------------------------------------------------------------------
# 回执确认（H5 页面 + 提交）
# ---------------------------------------------------------------------------
_ACK_PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>弱光督办回执</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;padding:18px;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
       background:#0a1530;color:#eaf2ff;min-height:100vh}
  .card{max-width:520px;margin:0 auto;background:linear-gradient(180deg,#12244d,#0e1c3d);
        border:1px solid rgba(46,166,255,.28);border-radius:14px;padding:18px}
  h1{font-size:17px;margin:0 0 6px}
  .sub{font-size:12px;color:#6c87b3;margin-bottom:14px}
  .row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(120,160,220,.14);font-size:13px}
  .row:last-child{border-bottom:none}
  .k{color:#a9c2e6}
  .v{font-weight:700}
  .warn{color:#ff7a82}
  .ok{color:#2fe3bd}
  input,textarea{width:100%;margin-top:8px;padding:10px 12px;border-radius:10px;font-size:14px;
        background:#0b1a3a;border:1px solid rgba(46,166,255,.3);color:#eaf2ff;outline:none}
  button{width:100%;margin-top:14px;padding:12px;border-radius:10px;border:none;font-size:15px;font-weight:700;
        background:linear-gradient(90deg,#2ea6ff,#19e0ff);color:#031329;cursor:pointer}
  button:disabled{opacity:.55}
  .tip{font-size:12px;color:#6c87b3;margin-top:12px;line-height:1.7}
  .done{text-align:center;padding:26px 0}
</style></head><body>
<div class="card" id="app">__BODY__</div>
<script>
async function submitAck(){
  const btn=document.getElementById('ackBtn');
  const name=(document.getElementById('ackName').value||'').trim();
  if(!name){ alert('请填写您的姓名'); return; }
  btn.disabled=true; btn.textContent='提交中…';
  try{
    const r=await fetch('/api/push_ack',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:'__TOKEN__',name:name,note:document.getElementById('ackNote').value||''})}).then(x=>x.json());
    if(r.ok){ document.getElementById('app').innerHTML='<div class="done"><div style="font-size:44px">✅</div><h1>已确认接收</h1><div class="sub">区级督办已收到您的回执</div></div>'; }
    else { btn.disabled=false; btn.textContent='确认接收'; alert(r.error||'提交失败'); }
  }catch(e){ btn.disabled=false; btn.textContent='确认接收'; alert('网络异常，请稍后重试'); }
}
</script></body></html>"""


@push_bp.route("/push/ack")
def push_ack_page():
    token = re.sub(r"[^A-Za-z0-9_\-]", "", request.args.get("t", ""))[:64]
    t = push_service.get_ack_target(token)
    if not t:
        html = _ACK_PAGE.replace("__BODY__", '<div class="done"><h1>链接无效或已失效</h1>'
                                 '<div class="sub">请联系区级弱光督办重新推送</div></div>')
        return make_response(html, 404)

    if t.get("ack_at"):
        body = (
            '<div class="done"><div style="font-size:44px">✅</div><h1>已确认接收</h1>'
            f'<div class="sub">确认人 {t.get("ack_by") or "—"} · {t.get("ack_at")}</div></div>'
        )
    else:
        body = (
            f'<h1>弱光督办 · {t.get("grid") or "—"}</h1>'
            f'<div class="sub">网格长 {t.get("leader_name") or "—"} · {t.get("phone_masked") or "—"}</div>'
            f'<div class="row"><span class="k">弱光户数</span><span class="v warn">{t.get("weak_cnt") or 0} 户</span></div>'
            f'<div class="row"><span class="k">严重 / 新增 / 持续</span>'
            f'<span class="v">{t.get("severe_cnt") or 0} / {t.get("new_cnt") or 0} / {t.get("sustained_cnt") or 0}</span></div>'
            f'<div class="row"><span class="k">整改时限</span><span class="v">'
            f'{push_service.get_setting("PUSH_DEADLINE_DAYS") or 3} 个工作日内</span></div>'
            '<input id="ackName" placeholder="请填写您的姓名（必填）" maxlength="40"/>'
            '<textarea id="ackNote" rows="2" placeholder="备注（选填，如已安排上门时间）" maxlength="200"></textarea>'
            '<button id="ackBtn" onclick="submitAck()">确认接收</button>'
            '<div class="tip">确认后区级督办可看到您的回执；整改完成后，下一批次数据导入时系统会自动比对闭环情况。</div>'
        )
    html = _ACK_PAGE.replace("__BODY__", body).replace("__TOKEN__", token)
    return make_response(html)


@push_bp.route("/api/push_ack", methods=["POST"])
def push_ack_submit():
    body = request.get_json(silent=True) or {}
    res = push_service.ack_target(
        body.get("token") or "", body.get("name") or "", body.get("note") or "",
    )
    return jsonify(res), (200 if res.get("ok") else 400)
