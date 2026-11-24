# -*- coding: utf-8 -*-
"""弱光推送服务（网格长督办 · 企业微信群机器人）。

链路：
  弱光明细（小区） → 责任田（小区 → 网格/责任人） → 网格长名单（网格 → 网格长）
  → 聚合为「网格 × 网格长」推送单元 → 渲染消息 → 企微机器人发送 → 回执与状态回写

设计要点：
- 匹配键沿用现有口径：小区名 community（精确优先，归一化兜底），与 person_map 一致；
- 推送单元是「网格 × 网格长」而不是「户」，避免逐户骚扰与短信成本；
- 默认手动一键触发；已成功推送的网格在 force=False 时跳过（幂等）；
- 发送在后台线程串行执行（企微机器人限 20 条/分钟），接口立即返回 task_id 供前端轮询；
- 未配置 PUSH_WECOM_WEBHOOK 时不产生任务，前端改用「导出清单」兜底。
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import pandas as pd

import config
from db import get_conn
from db.repositories import weak_light_repository

# 网格长名单列名映射（按关键词动态识别，不硬编码列号）
GRID_COLMAP = {
    "grid_code": ("市场网格编码", "网格编码", "网格ID"),
    "grid": ("市场网格名称", "市场网格", "网格名称"),
    "leader_name": ("网格长姓名", "网格长", "姓名"),
    "phone": ("手机号码", "手机号", "联系电话", "电话"),
    "emp_no": ("工号", "员工编号"),
    "role": ("角色", "职责"),
    "update_date": ("更新日期", "数据日期"),
}

TARGET_STATUS_TEXT = {
    "pending": "待发送",
    "sent": "已发送",
    "failed": "失败",
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _s(v):
    """安全转字符串（NaN → 空）。"""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _idnum(v):
    """Excel 数字型编号 → 字符串（去掉 .0 尾巴）。"""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v.is_integer() else str(v)
    return _s(v)


def _to_int(v):
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0
        return int(float(v))
    except Exception:
        return 0


def normalize_phone(v):
    """手机号归一：保留数字，去掉空格/横线/括号。"""
    return re.sub(r"\D", "", _s(v))


def mask_phone(phone):
    """手机号脱敏：13800001234 → 138****1234。"""
    p = normalize_phone(phone)
    return p[:3] + "****" + p[-4:] if len(p) >= 8 else (p or "—")


def normalize_community(name):
    """小区名归一化：全角括号转半角、去空白、去括号内的「小区/社区」。"""
    s = _s(name).replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\((小区|社区|村|自然村)\)$", "", s)
    return s


def _pick_cols(cols, colmap):
    """按关键词定位列索引：先精确匹配，再包含匹配（长关键词优先）。"""
    picked, used = {}, set()
    for key, kws in colmap.items():
        for kw in sorted(kws, key=len, reverse=True):
            idx = None
            for i, c in enumerate(cols):
                if i not in used and str(c).strip() == kw:
                    idx = i
                    break
            if idx is None:
                for i, c in enumerate(cols):
                    if i not in used and kw in str(c):
                        idx = i
                        break
            if idx is not None:
                picked[key] = idx
                used.add(idx)
                break
    return picked


def _col(row, picked, key):
    idx = picked.get(key)
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


# ---------------------------------------------------------------------------
# 运行时配置：页面配置（app_setting 表）优先于环境变量，保存后立即生效
# ---------------------------------------------------------------------------
_CONF_KEYS = (
    "PUSH_WECOM_WEBHOOK",
    "PUSH_WECOM_MSG_TYPE",
    "PUSH_SEND_INTERVAL",
    "PUSH_DEADLINE_DAYS",
    "PUSH_ESCALATION_NAME",
    "PUSH_ESCALATION_PHONE",
)
_ENV_DEFAULT = {
    "PUSH_WECOM_WEBHOOK": lambda: config.PUSH_WECOM_WEBHOOK,
    "PUSH_WECOM_MSG_TYPE": lambda: config.PUSH_WECOM_MSG_TYPE,
    "PUSH_SEND_INTERVAL": lambda: str(config.PUSH_SEND_INTERVAL),
    "PUSH_DEADLINE_DAYS": lambda: str(config.PUSH_DEADLINE_DAYS),
    "PUSH_ESCALATION_NAME": lambda: config.PUSH_ESCALATION_NAME,
    "PUSH_ESCALATION_PHONE": lambda: config.PUSH_ESCALATION_PHONE,
}
_setting_cache = {"ts": 0.0, "data": {}}


def _db_settings():
    """读取 app_setting（3 秒进程缓存，避免逐条发送时反复查库）。"""
    now = time.time()
    if now - _setting_cache["ts"] < 3:
        return _setting_cache["data"]
    data = {}
    try:
        conn = get_conn()
        try:
            for r in conn.execute("SELECT key, value FROM app_setting"):
                data[r["key"]] = r["value"]
        finally:
            conn.close()
    except Exception:
        data = {}
    _setting_cache["ts"] = now
    _setting_cache["data"] = data
    return data


def get_setting(key, default=""):
    """取配置：页面配置（非空）→ 环境变量 → 默认值。"""
    db_val = _db_settings().get(key)
    if db_val is not None and str(db_val).strip() != "":
        return str(db_val).strip()
    fn = _ENV_DEFAULT.get(key)
    if fn:
        try:
            return str(fn() or "").strip()
        except Exception:
            return default
    return default


def _upsert_setting(conn, key, value, now):
    conn.execute(
        """
        INSERT INTO app_setting (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now),
    )


def _mask_webhook(url):
    """掩码展示 webhook：保留域名 + key 尾 6 位。"""
    u = _s(url)
    if not u:
        return ""
    key = ""
    m = re.search(r"[?&]key=([^&]+)", u)
    if m:
        key = m.group(1)
    tail = key[-6:] if len(key) > 6 else key
    if tail:
        return f"…key=••••{tail}"
    return u[:22] + "…" if len(u) > 22 else u


def get_config_public():
    """配置窗口展示用：webhook 只返回掩码，不泄露完整 key。"""
    db = _db_settings()
    webhook = get_setting("PUSH_WECOM_WEBHOOK")
    return {
        "webhook_set": bool(webhook),
        "webhook_hint": _mask_webhook(webhook),
        "source": "db" if _s(db.get("PUSH_WECOM_WEBHOOK")) else ("env" if config.PUSH_WECOM_WEBHOOK else "none"),
        "msg_type": get_setting("PUSH_WECOM_MSG_TYPE") or "markdown",
        "send_interval": _to_float(get_setting("PUSH_SEND_INTERVAL"), 3.0),
        "deadline_days": _to_int(get_setting("PUSH_DEADLINE_DAYS")) or 3,
        "escalation_name": get_setting("PUSH_ESCALATION_NAME") or "区级弱光督办",
        "escalation_phone": get_setting("PUSH_ESCALATION_PHONE"),
        "enabled": bool(config.PUSH_ENABLED),
        "channel": config.PUSH_CHANNEL,
    }


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def save_config(payload):
    """保存推送配置（页面配置写入 app_setting，优先于环境变量）。

    - webhook 留空 = 不修改；clear_webhook=True = 删除页面配置并回落到环境变量；
    - 数值/文本项留空 = 不修改。
    """
    payload = payload or {}
    now = _now()
    webhook = _s(payload.get("webhook"))
    if webhook:
        if not re.match(r"^https?://", webhook):
            return {"ok": False, "error": "Webhook 需以 http:// 或 https:// 开头"}
        if "key=" not in webhook:
            return {"ok": False, "error": "企微机器人地址缺少 key 参数，请检查是否复制完整"}

    msg_type = _s(payload.get("msg_type")).lower()
    if msg_type and msg_type not in ("markdown", "text"):
        return {"ok": False, "error": "消息类型仅支持 markdown 或 text"}

    interval = _s(payload.get("send_interval"))
    iv = 0.0
    if interval:
        try:
            iv = float(interval)
        except ValueError:
            return {"ok": False, "error": "发送间隔需为数字（秒）"}
        if iv < 0 or iv > 60:
            return {"ok": False, "error": "发送间隔建议 0~60 秒（企微限 20 条/分钟）"}

    deadline = _s(payload.get("deadline_days"))
    if deadline:
        if not deadline.isdigit() or not (1 <= int(deadline) <= 30):
            return {"ok": False, "error": "整改时限需为 1~30 的整数（工作日）"}

    conn = get_conn()
    try:
        if webhook:
            _upsert_setting(conn, "PUSH_WECOM_WEBHOOK", webhook, now)
        if payload.get("clear_webhook"):
            conn.execute("DELETE FROM app_setting WHERE key = 'PUSH_WECOM_WEBHOOK'")
        if msg_type:
            _upsert_setting(conn, "PUSH_WECOM_MSG_TYPE", msg_type, now)
        if interval:
            _upsert_setting(conn, "PUSH_SEND_INTERVAL", str(iv), now)
        if deadline:
            _upsert_setting(conn, "PUSH_DEADLINE_DAYS", str(int(deadline)), now)
        name = _s(payload.get("escalation_name"))
        if name:
            _upsert_setting(conn, "PUSH_ESCALATION_NAME", name, now)
        phone = normalize_phone(payload.get("escalation_phone"))
        if phone:
            _upsert_setting(conn, "PUSH_ESCALATION_PHONE", phone, now)
        conn.commit()
    finally:
        conn.close()
    _setting_cache["ts"] = 0.0
    return {"ok": True, "config": get_config_public()}


def render_test_message():
    mt = (get_setting("PUSH_WECOM_MSG_TYPE") or "markdown").lower()
    ts = _now()
    if mt == "text":
        return (f"【弱光督办】推送通道测试\n配置时间：{ts}\n"
                f"收到本条消息说明企业微信群机器人配置正确，弱光督办将按网格推送到本群。")
    return "\n".join([
        "### 弱光督办 · 推送通道测试",
        f"> 配置时间：{ts}",
        "",
        "收到本条消息说明**企业微信群机器人配置正确**，弱光督办消息将按网格推送到本群。",
    ])


def test_webhook(webhook="", msg_type=""):
    """发送一条测试消息（可用表单值而不落库），用于验证配置。"""
    url = _s(webhook) or get_setting("PUSH_WECOM_WEBHOOK")
    if not url:
        return {"ok": False, "error": "请先填写 Webhook 地址"}
    if not re.match(r"^https?://", url):
        return {"ok": False, "error": "Webhook 需以 http:// 或 https:// 开头"}
    mt = (_s(msg_type) or get_setting("PUSH_WECOM_MSG_TYPE") or "markdown").lower()
    try:
        _post_wecom(render_test_message(), [], url=url, msg_type=mt)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {"ok": True}


# ---------------------------------------------------------------------------
# 网格长名单：解析 / 覆盖式入库 / 读取
# ---------------------------------------------------------------------------
def parse_grid_leader_file(path, filename=""):
    """解析网格长名单（CSV/XLSX），返回 [{grid_code, grid, leader_name, phone, emp_no, role, update_date}]。

    兼容列名：市场网格编码/网格编码、市场网格名称/市场网格、网格长姓名/网格长/姓名、
    手机号/手机号码/联系电话、工号、更新日期。无手机号的行保留（可推送但无法 @）。
    """
    ext = os.path.splitext(filename or path)[1].lower()
    if ext == ".csv":
        df, last_err = None, None
        for enc in ("utf-8-sig", "gbk", "utf-8"):
            try:
                df = pd.read_csv(path, dtype=str, encoding=enc)
                break
            except UnicodeDecodeError as exc:
                last_err = exc
        if df is None:
            raise RuntimeError(f"CSV 编码无法识别：{last_err}")
    else:
        df = pd.read_excel(path, dtype=str)

    if df is None or df.empty:
        return []

    cols = list(df.columns)
    picked = _pick_cols(cols, GRID_COLMAP)
    if "leader_name" not in picked or "phone" not in picked:
        raise ValueError("名单缺少「网格长姓名」或「手机号」列")

    out, seen = [], set()
    for row in df.itertuples(index=False):
        vals = list(row)
        name = _s(_col(vals, picked, "leader_name"))
        if not name:
            continue
        grid_code = _idnum(_col(vals, picked, "grid_code"))
        grid = _s(_col(vals, picked, "grid"))
        phone = normalize_phone(_col(vals, picked, "phone"))
        role_txt = _s(_col(vals, picked, "role"))
        role = "deputy" if ("副" in role_txt or "副" in name) else "leader"
        key = (grid_code, name, phone)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "grid_code": grid_code,
            "grid": grid,
            "leader_name": name,
            "phone": phone,
            "emp_no": _idnum(_col(vals, picked, "emp_no")),
            "role": role,
            "update_date": _s(_col(vals, picked, "update_date")),
        })
    return out


def save_grid_leaders(rows, filename=""):
    """覆盖式写入网格长名单（解析为空时拒绝覆盖，避免误清空）。"""
    if not rows:
        return 0
    now = _now()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM grid_leader")
        conn.executemany(
            """
            INSERT INTO grid_leader
                (filename, grid_code, grid, leader_name, phone, emp_no, role, source,
                 update_date, upload_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'roster', ?, ?, ?)
            """,
            [
                (filename, r["grid_code"], r["grid"], r["leader_name"], r["phone"],
                 r["emp_no"], r["role"], r["update_date"], now, now)
                for r in rows
            ],
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def _leaders_by_grid(conn):
    """{grid_code: [leader, ...]}，网格长（leader）排在副网格长之前。"""
    rows = conn.execute(
        "SELECT grid_code, grid, leader_name, phone, emp_no, role FROM grid_leader"
    ).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["grid_code"] or "", []).append({
            "grid": r["grid"] or "",
            "leader_name": r["leader_name"] or "",
            "phone": r["phone"] or "",
            "emp_no": r["emp_no"] or "",
            "role": r["role"] or "leader",
        })
    for code in out:
        out[code].sort(key=lambda x: (x["role"] != "leader", x["leader_name"]))
    return out


def leader_stats():
    """名单统计（人数 / 网格数），供面板展示。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt, COUNT(DISTINCT grid_code) AS grids FROM grid_leader"
        ).fetchone()
        return {"leader_cnt": row["cnt"] or 0, "grid_cnt": row["grids"] or 0}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 匹配：小区 → 责任田（网格 + 责任人）
# ---------------------------------------------------------------------------
def _field_index(conn):
    """建立 小区 → 责任田 索引，返回 (exact, normalized)。

    同一小区多行时按「小区用户数大 → 更新日期新」裁决，冲突记录在返回的 index_conflicts。
    """
    rows = conn.execute(
        """
        SELECT community, grid_code, grid, person, phone, user_count, update_date
        FROM weak_light_person
        """
    ).fetchall()
    exact, norm, conflicts = {}, {}, {}
    for r in rows:
        rec = {
            "community": r["community"] or "",
            "grid_code": r["grid_code"] or "",
            "grid": r["grid"] or "",
            "person": r["person"] or "",
            "phone": r["phone"] or "",
            "user_count": _to_int(r["user_count"]),
            "update_date": r["update_date"] or "",
        }
        key = _s(rec["community"])
        if not key:
            continue
        exact.setdefault(key, []).append(rec)
        nk = normalize_community(key)
        if nk:
            norm.setdefault(nk, []).append(rec)

    def _best(cands):
        return max(cands, key=lambda x: (x["user_count"], x["update_date"] or ""))

    for bucket in (exact, norm):
        for k, cands in list(bucket.items()):
            if len(cands) > 1:
                conflicts[k] = len(cands)
            bucket[k] = [_best(cands)]

    return exact, norm, conflicts


def _match_field(community, exact, norm):
    key = _s(community)
    if key and key in exact:
        return exact[key][0], "exact"
    nk = normalize_community(key)
    if nk and nk in norm:
        return norm[nk][0], "normalized"
    return None, ""


def _derived_leaders(conn):
    """责任田派生兜底：{grid_code: [{leader_name, phone, role}]}（去重，最多 3 人）。"""
    rows = conn.execute(
        """
        SELECT grid_code, person, phone FROM weak_light_person
        WHERE grid_code != '' AND person != ''
        """
    ).fetchall()
    out, seen = {}, set()
    for r in rows:
        code = r["grid_code"] or ""
        name = r["person"] or ""
        phone = normalize_phone(r["phone"])
        if (code, name, phone) in seen:
            continue
        seen.add((code, name, phone))
        out.setdefault(code, []).append({
            "grid": "",
            "leader_name": name,
            "phone": phone,
            "emp_no": "",
            "role": "leader",
        })
    for code in out:
        out[code] = out[code][:3]
    return out


# ---------------------------------------------------------------------------
# 预览：聚合为推送单元
# ---------------------------------------------------------------------------
def _resolve_batch(conn, batch_id=None):
    if batch_id:
        row = conn.execute(
            "SELECT id, filename, data_date, weak_total, severe_cnt FROM weak_light_upload WHERE id = ?",
            (int(batch_id),),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, filename, data_date, weak_total, severe_cnt
            FROM weak_light_upload ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def _sustained_sn(batch_id):
    """跨批次持续弱光 SN → 持续天数（失败时降级为空，仅用明细 sustained 标记）。"""
    try:
        res = weak_light_repository.sustained_tracking(upto_batch_id=batch_id, limit=5000)
        return {it.get("gateway_sn"): _to_int(it.get("span_days")) for it in (res.get("items") or [])}
    except Exception:
        return {}


def build_preview(batch_id=None, scope="all"):
    """生成推送预览：网格 × 网格长 单元 + 未匹配池 + 冲突/告警。

    返回结构（全部 JSON 可序列化）：
      {ok, batch, data_date, channel, webhook_ready, targets[], unmatched[],
       conflicts[], already_pushed[], summary{}}
    """
    conn = get_conn()
    try:
        batch = _resolve_batch(conn, batch_id)
        if not batch:
            return {"ok": False, "error": "暂无弱光批次，请先上传弱光报表"}
        bid = batch["id"]
        exact, norm, conflicts = _field_index(conn)
        leaders = _leaders_by_grid(conn)
        derived = _derived_leaders(conn)
        already = {
            r["grid_code"] for r in conn.execute(
                "SELECT DISTINCT grid_code FROM push_target WHERE batch_id = ? AND status = 'sent'",
                (bid,),
            ).fetchall()
        }
        details = conn.execute(
            """
            SELECT gateway_sn, account, community, pon, valley_power, sustained, is_new
            FROM weak_light_detail WHERE batch_id = ?
            """,
            (bid,),
        ).fetchall()
    finally:
        conn.close()

    sustained_map = _sustained_sn(bid)

    units = {}          # key(grid_code) → 聚合单元
    unmatched = {}      # community → {reason, weak_cnt}
    total_matched = 0

    for d in details:
        community = _s(d["community"]) or "（未知小区）"
        field, how = _match_field(community, exact, norm)
        if not field:
            u = unmatched.setdefault(community, {"community": community, "weak_cnt": 0, "reason": "责任田未覆盖该小区"})
            u["weak_cnt"] += 1
            continue

        code = _s(field["grid_code"])
        grid_name = _s(field["grid"]) or "未归属网格"
        if not code:
            # 无网格编码：按责任人聚合，仍可推送
            code = "PERSON:" + (_s(field["person"]) or "未指派")
            grid_name = grid_name if grid_name != "未归属网格" else f"未归属网格（{field['person'] or '未指派'}）"

        u = units.setdefault(code, {
            "grid_code": _s(field["grid_code"]),
            "grid": grid_name,
            "communities": {},
            "pons": {},
            "samples": [],
            "weak_cnt": 0,
            "severe_cnt": 0,
            "new_cnt": 0,
            "sustained_cnt": 0,
        })
        total_matched += 1
        u["weak_cnt"] += 1
        severe = float(d["valley_power"] or 0) < -30
        if severe:
            u["severe_cnt"] += 1
        if _to_int(d["is_new"]) == 1:
            u["new_cnt"] += 1
        sn = _s(d["gateway_sn"])
        span = sustained_map.get(sn)
        if span is None and _to_int(d["sustained"]) == 1:
            span = 0
        if span is not None:
            u["sustained_cnt"] += 1

        c = u["communities"].setdefault(community, {"community": community, "weak_cnt": 0, "severe_cnt": 0, "new_cnt": 0})
        c["weak_cnt"] += 1
        if severe:
            c["severe_cnt"] += 1
        if _to_int(d["is_new"]) == 1:
            c["new_cnt"] += 1

        pon = _s(d["pon"])
        if pon:
            u["pons"][pon] = u["pons"].get(pon, 0) + 1

        u["samples"].append({
            "sn_tail": sn[-4:] if len(sn) >= 4 else sn,
            "account": _mask_account(d["account"]),
            "community": community,
            "valley_power": round(float(d["valley_power"] or 0), 2),
            "sustained_days": span or 0,
        })

    # 每个聚合单元 → 网格长（名单 → 责任田派生 → 区级兜底）
    targets, no_leader = [], []
    for code, u in units.items():
        roster = leaders.get(u["grid_code"]) if u["grid_code"] else None
        if roster:
            cands, source = roster, "roster"
        elif derived.get(u["grid_code"]):
            cands, source = derived[u["grid_code"]], "derived"
        else:
            cands, source = [{
                "grid": u["grid"],
                "leader_name": get_setting("PUSH_ESCALATION_NAME") or "区级督办",
                "phone": normalize_phone(get_setting("PUSH_ESCALATION_PHONE")),
                "emp_no": "",
                "role": "leader",
            }], "fallback"
            no_leader.append({"grid_code": u["grid_code"], "grid": u["grid"], "weak_cnt": u["weak_cnt"]})

        comms = sorted(u["communities"].values(), key=lambda x: (-x["weak_cnt"], x["community"]))
        pons = sorted(u["pons"].items(), key=lambda x: -x[1])
        samples = sorted(u["samples"], key=lambda x: x["valley_power"])[: config.PUSH_DETAIL_LIMIT]
        for ld in cands:
            targets.append({
                "grid_code": u["grid_code"],
                "grid": u["grid"],
                "leader_name": ld["leader_name"],
                "phone": ld["phone"],
                "phone_masked": mask_phone(ld["phone"]) if ld["phone"] else "",
                "role": ld["role"],
                "source": source,
                "community_cnt": len(comms),
                "communities": comms,
                "pons": [{"pon": p, "weak_cnt": n} for p, n in pons[:3]],
                "samples": samples,
                "weak_cnt": u["weak_cnt"],
                "severe_cnt": u["severe_cnt"],
                "new_cnt": u["new_cnt"],
                "sustained_cnt": u["sustained_cnt"],
                "pushed": u["grid_code"] in already,
            })

    targets.sort(key=lambda t: (-t["weak_cnt"], t["grid_code"]))
    return {
        "ok": True,
        "batch": batch,
        "data_date": batch.get("data_date") or "",
        "channel": config.PUSH_CHANNEL,
        "webhook_ready": bool(get_setting("PUSH_WECOM_WEBHOOK")),
        "leader_stat": leader_stats(),
        "targets": targets,
        "unmatched": sorted(unmatched.values(), key=lambda x: -x["weak_cnt"]),
        "conflicts": [{"community": k, "rows": v} for k, v in sorted(conflicts.items())],
        "no_leader": no_leader,
        "already_pushed": sorted(already),
        "summary": {
            "grid_cnt": len(units),
            "target_cnt": len(targets),
            "weak_cnt": total_matched,
            "matched_community_cnt": len({c["community"] for u in units.values() for c in u["communities"].values()}),
            "unmatched_cnt": len(unmatched),
            "unmatched_weak": sum(x["weak_cnt"] for x in unmatched.values()),
            "pushed_grid_cnt": len(already),
        },
    }


def _mask_account(account):
    s = _s(account)
    if len(s) >= 7:
        return s[:3] + "****" + s[-3:]
    return s


# ---------------------------------------------------------------------------
# 消息渲染（企微 markdown / text）
# ---------------------------------------------------------------------------
def _deadline_text(data_date):
    """整改时限文案：T+N 个工作日。"""
    days = _to_int(get_setting("PUSH_DEADLINE_DAYS")) or 3
    return f"{days} 个工作日内"


def render_markdown(t, data_date="", ack_url=""):
    """企微 markdown 消息（排版清晰，但 @ 不到个人）。"""
    lines = [
        f"### 弱光督办 · {t['grid']}（{data_date or '—'}）",
        f"> 网格编码：{t['grid_code'] or '—'} · 网格长：**{t['leader_name']}**（{t['phone_masked']}）",
        "",
        f"**弱光情况**：弱光 **{t['weak_cnt']}** 户 · 严重 **{t['severe_cnt']}** 户 · "
        f"新增 **{t['new_cnt']}** 户 · 持续 **{t['sustained_cnt']}** 户",
    ]
    comms = t.get("communities") or []
    if comms:
        txt = "、".join(f"{c['community']} {c['weak_cnt']} 户" for c in comms[:5])
        if len(comms) > 5:
            txt += f" 等 {len(comms)} 个小区"
        lines.append(f"**小区分布**：{txt}")
    pons = t.get("pons") or []
    if pons:
        lines.append(f"**集中 PON**：{pons[0]['pon']}（{pons[0]['weak_cnt']} 户）")
    samples = t.get("samples") or []
    if samples:
        s0 = samples[0]
        lines.append(
            f"**重点户**：SN 尾号 {s0['sn_tail']} · 谷值 {s0['valley_power']} dBm"
            + (f" · 持续 {s0['sustained_days']} 天" if s0["sustained_days"] else "")
        )
    lines += [
        "",
        f'<font color="warning">整改要求：{_deadline_text(data_date)}完成上门核查与整治，'
        f"目标谷值 ≥ -27dBm 且弱光次数 = 0；重点核查尾纤/分光器/入户皮线，必要时更换尾纤或 ONU。</font>",
    ]
    if ack_url:
        lines.append(f"[点击确认接收]({ack_url})")
    return "\n".join(lines)


def render_text(t, data_date="", ack_url=""):
    """企微 text 消息（配合 mentioned_mobile_list 可 @ 到人，强提醒）。"""
    comms = t.get("communities") or []
    comm_txt = "、".join(f"{c['community']}{c['weak_cnt']}户" for c in comms[:3])
    if len(comms) > 3:
        comm_txt += f"等{len(comms)}个小区"
    lines = [
        f"【弱光督办】{data_date or ''} {t['grid']}",
        f"弱光{t['weak_cnt']}户(严重{t['severe_cnt']}/新增{t['new_cnt']}/持续{t['sustained_cnt']})",
    ]
    if comm_txt:
        lines.append(f"小区：{comm_txt}")
    lines.append(f"要求：{_deadline_text(data_date)}上门整改，目标谷值≥-27dBm")
    if ack_url:
        lines.append(f"确认接收：{ack_url}")
    return "\n".join(lines)


def render_target(t, data_date="", ack_url=""):
    if (get_setting("PUSH_WECOM_MSG_TYPE") or "markdown").lower() == "text":
        return render_text(t, data_date, ack_url)
    return render_markdown(t, data_date, ack_url)


# ---------------------------------------------------------------------------
# 企微群机器人发送
# ---------------------------------------------------------------------------
def _post_wecom(content, phones=None, url=None, msg_type=None):
    """调用企微群机器人 webhook；失败抛异常（消息内容不落日志）。"""
    url = url or get_setting("PUSH_WECOM_WEBHOOK")
    if not url:
        raise RuntimeError("未配置企业微信群机器人 Webhook（可在推送督办面板点「配置」填写）")

    mt = (msg_type or get_setting("PUSH_WECOM_MSG_TYPE") or "markdown").lower()
    if mt == "text":
        payload = {"msgtype": "text", "text": {"content": content[:2000]}}
        mobiles = [p for p in (phones or []) if p]
        if mobiles:
            payload["text"]["mentioned_mobile_list"] = mobiles
    else:
        payload = {"msgtype": "markdown", "markdown": {"content": content[:4000]}}

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"企微 HTTP {exc.code}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"企微网络不可达：{exc.reason}")
    try:
        ret = json.loads(body)
    except Exception:
        raise RuntimeError(f"企微返回非 JSON：{body[:80]}")
    if ret.get("errcode") != 0:
        raise RuntimeError(f"企微错误 {ret.get('errcode')}：{ret.get('errmsg') or ''}")
    return True


def _ack_base(fallback=""):
    base = config.PUSH_ACK_BASE_URL or fallback or ""
    return base.rstrip("/")


def ack_url_for(token, base=""):
    return f"{_ack_base(base)}/push/ack?t={token}" if token else ""


# ---------------------------------------------------------------------------
# 任务：创建 / 后台发送 / 查询 / 重推
# ---------------------------------------------------------------------------
def _insert_task(conn, batch, scope, total_grids, total_targets, total_users, operator="", remark=""):
    cur = conn.execute(
        """
        INSERT INTO push_task
            (batch_id, data_date, channel, scope, total_grids, total_targets, total_users,
             status, operator, remark, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (batch["id"], batch.get("data_date") or "", config.PUSH_CHANNEL, scope,
         total_grids, total_targets, total_users, operator, remark, _now()),
    )
    return cur.lastrowid


def trigger_push(batch_id=None, grid_codes=None, force=False, operator="", remark="", ack_base=""):
    """一键触发：校验 → 建任务与明细 → 后台线程发送。

    返回 {ok, task_id, targets, skipped} 或 {ok: False, error}。
    """
    if not config.PUSH_ENABLED:
        return {"ok": False, "error": "推送功能已关闭（PUSH_ENABLED=0）"}
    if not get_setting("PUSH_WECOM_WEBHOOK"):
        return {"ok": False, "error": "未配置企业微信群机器人：请在推送督办面板点「企微群机器人」配置，或先导出推送清单人工转发"}

    preview = build_preview(batch_id=batch_id)
    if not preview.get("ok"):
        return preview

    selected = set(grid_codes or [])
    targets = [t for t in preview["targets"] if not selected or t["grid_code"] in selected]
    if not force:
        skipped = [t for t in targets if t["pushed"]]
        targets = [t for t in targets if not t["pushed"]]
    else:
        skipped = []

    if not targets:
        return {"ok": False, "error": "没有需要推送的网格（可能已全部推送，可勾选「强制重推」）",
                "skipped": len(skipped)}
    if len(targets) > config.PUSH_MAX_GRIDS:
        return {"ok": False, "error": f"单次最多推送 {config.PUSH_MAX_GRIDS} 个网格，当前 {len(targets)} 个，请缩小范围"}

    data_date = preview["data_date"]
    now = _now()
    conn = get_conn()
    try:
        task_id = _insert_task(
            conn, preview["batch"], "selected" if selected else "all",
            len({t["grid_code"] for t in targets}), len(targets),
            sum(t["weak_cnt"] for t in targets), operator, remark,
        )
        for t in targets:
            token = secrets.token_urlsafe(12)
            content = render_target(t, data_date, ack_url_for(token, ack_base))
            conn.execute(
                """
                INSERT INTO push_target
                    (task_id, batch_id, grid_code, grid, leader_name, phone, source,
                     community_cnt, weak_cnt, severe_cnt, new_cnt, sustained_cnt,
                     payload_json, content, status, token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (task_id, preview["batch"]["id"], t["grid_code"], t["grid"], t["leader_name"],
                 t["phone"], t["source"], t["community_cnt"], t["weak_cnt"], t["severe_cnt"],
                 t["new_cnt"], t["sustained_cnt"], json.dumps(t, ensure_ascii=False),
                 content, token),
            )
        conn.execute("UPDATE push_task SET status = 'running' WHERE id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()

    threading.Thread(target=_run_task, args=(task_id,), daemon=True).start()
    return {"ok": True, "task_id": task_id, "target_cnt": len(targets), "skipped": len(skipped)}


def _run_task(task_id):
    """后台串行发送：企微机器人限 20 条/分钟，按 PUSH_SEND_INTERVAL 节流。"""
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, content, phone, status FROM push_target WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()]
    finally:
        conn.close()

    ok_cnt, fail_cnt = 0, 0
    for row in rows:
        if row["status"] != "pending":
            continue
        ok, err = _send_one(row["id"], row["content"], row["phone"])
        if ok:
            ok_cnt += 1
        else:
            fail_cnt += 1
        time.sleep(max(0.0, _to_float(get_setting("PUSH_SEND_INTERVAL"), 3.0)))

    status = "done" if fail_cnt == 0 else ("partial" if ok_cnt else "failed")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE push_task SET status = ?, finished_at = ? WHERE id = ?",
            (status, _now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def _send_one(target_id, content, phone):
    """发送单条并回写状态；返回 (ok, error)。"""
    ok, err = True, ""
    try:
        _post_wecom(content, [phone] if phone else [])
    except Exception as exc:
        ok, err = False, str(exc)[:300]

    conn = get_conn()
    try:
        if ok:
            conn.execute(
                "UPDATE push_target SET status = 'sent', sent_at = ?, error_msg = '' WHERE id = ?",
                (_now(), target_id),
            )
        else:
            conn.execute(
                "UPDATE push_target SET status = 'failed', error_msg = ?, retry_cnt = retry_cnt + 1 WHERE id = ?",
                (err, target_id),
            )
        conn.commit()
    finally:
        conn.close()
    return ok, err


def retry_targets(target_ids):
    """重推指定明细（同步执行，数量少）。返回 {ok, retried, failed}。"""
    if not get_setting("PUSH_WECOM_WEBHOOK"):
        return {"ok": False, "error": "未配置企业微信群机器人地址"}
    ids = [int(x) for x in (target_ids or []) if str(x).isdigit()]
    if not ids:
        return {"ok": False, "error": "未选择需要重推的条目"}

    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, content, phone FROM push_target WHERE id IN (%s)" % ",".join("?" * len(ids)),
            ids,
        ).fetchall()]
        conn.execute(
            "UPDATE push_target SET status = 'pending' WHERE id IN (%s)" % ",".join("?" * len(ids)),
            ids,
        )
        conn.commit()
    finally:
        conn.close()

    failed = 0
    for row in rows:
        ok, _ = _send_one(row["id"], row["content"], row["phone"])
        if not ok:
            failed += 1
        time.sleep(max(0.0, _to_float(get_setting("PUSH_SEND_INTERVAL"), 3.0)))
    return {"ok": True, "retried": len(rows) - failed, "failed": failed}


def list_tasks(limit=20):
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.*,
                   (SELECT COUNT(*) FROM push_target WHERE task_id = t.id AND status = 'sent') AS sent_cnt,
                   (SELECT COUNT(*) FROM push_target WHERE task_id = t.id AND status = 'failed') AS failed_cnt,
                   (SELECT COUNT(*) FROM push_target WHERE task_id = t.id AND ack_at IS NOT NULL) AS ack_cnt
            FROM push_task t ORDER BY t.id DESC LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id):
    conn = get_conn()
    try:
        task = conn.execute("SELECT * FROM push_task WHERE id = ?", (int(task_id),)).fetchone()
        if not task:
            return {"ok": False, "error": "任务不存在"}
        targets = [dict(r) for r in conn.execute(
            "SELECT * FROM push_target WHERE task_id = ? ORDER BY status = 'failed' DESC, weak_cnt DESC, id",
            (int(task_id),),
        ).fetchall()]
        for t in targets:
            t.pop("payload_json", None)
            t["phone_masked"] = mask_phone(t.get("phone")) if t.get("phone") else ""
            t["status_text"] = TARGET_STATUS_TEXT.get(t.get("status"), t.get("status"))
        return {"ok": True, "task": dict(task), "targets": targets}
    finally:
        conn.close()


def summary(batch_id=None):
    """入口卡与面板摘要：推送覆盖与确认情况。"""
    conn = get_conn()
    try:
        bid = batch_id
        if not bid:
            row = conn.execute(
                "SELECT id FROM weak_light_upload ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            bid = row["id"] if row else None
        stats = {"leader_cnt": 0, "grid_cnt": 0}
        if bid:
            agg = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) AS sent,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                       SUM(CASE WHEN ack_at IS NOT NULL THEN 1 ELSE 0 END) AS ack,
                       COUNT(DISTINCT CASE WHEN status = 'sent' THEN grid_code END) AS grids
                FROM push_target WHERE batch_id = ?
                """,
                (bid,),
            ).fetchone()
            stats = {
                "target_total": agg["total"] or 0,
                "sent_cnt": agg["sent"] or 0,
                "failed_cnt": agg["failed"] or 0,
                "ack_cnt": agg["ack"] or 0,
                "pushed_grid_cnt": agg["grids"] or 0,
            }
        task_cnt = conn.execute("SELECT COUNT(*) AS c FROM push_task").fetchone()["c"] or 0
        leader = conn.execute(
            "SELECT COUNT(*) AS c, COUNT(DISTINCT grid_code) AS g FROM grid_leader"
        ).fetchone()
        stats["leader_cnt"] = leader["c"] or 0
        stats["grid_leader_cnt"] = leader["g"] or 0
        stats["task_cnt"] = task_cnt
        stats["batch_id"] = bid
        stats["enabled"] = bool(config.PUSH_ENABLED)
        stats["webhook_ready"] = bool(get_setting("PUSH_WECOM_WEBHOOK"))
        stats["webhook_hint"] = _mask_webhook(get_setting("PUSH_WECOM_WEBHOOK"))
        stats["channel"] = config.PUSH_CHANNEL
        stats["msg_type"] = get_setting("PUSH_WECOM_MSG_TYPE") or "markdown"
        return stats
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 回执确认
# ---------------------------------------------------------------------------
def get_ack_target(token):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM push_target WHERE token = ?", (token or "",)).fetchone()
        if not row:
            return None
        t = dict(row)
        t.pop("payload_json", None)
        t["phone_masked"] = mask_phone(t.get("phone"))
        return t
    finally:
        conn.close()


def ack_target(token, name="", note=""):
    """网格长确认接收：写 ack_at / ack_by / ack_note（重复确认只更新备注）。"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT id, ack_at FROM push_target WHERE token = ?", (token or "",)).fetchone()
        if not row:
            return {"ok": False, "error": "回执链接无效或已失效"}
        if row["ack_at"]:
            conn.execute(
                "UPDATE push_target SET ack_note = ? WHERE id = ?",
                ((note or "")[:200], row["id"]),
            )
        else:
            conn.execute(
                "UPDATE push_target SET ack_at = ?, ack_by = ?, ack_note = ? WHERE id = ?",
                (_now(), (name or "")[:40], (note or "")[:200], row["id"]),
            )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 导出（无通道兜底）
# ---------------------------------------------------------------------------
def export_preview(batch_id=None, scope="all"):
    """返回预览 + 展开后的扁平行，供 CSV 导出。"""
    preview = build_preview(batch_id=batch_id, scope=scope)
    if not preview.get("ok"):
        return preview
    rows = []
    for t in preview["targets"]:
        comms = "、".join(f"{c['community']}({c['weak_cnt']})" for c in t["communities"])
        rows.append({
            "网格编码": t["grid_code"],
            "市场网格": t["grid"],
            "网格长": t["leader_name"],
            "手机号": t["phone_masked"],
            "来源": {"roster": "名单", "derived": "责任田派生", "fallback": "区级兜底"}.get(t["source"], t["source"]),
            "小区数": t["community_cnt"],
            "弱光户数": t["weak_cnt"],
            "严重弱光": t["severe_cnt"],
            "新增弱光": t["new_cnt"],
            "持续弱光": t["sustained_cnt"],
            "小区分布": comms,
            "数据日期": preview["data_date"],
        })
    return {"ok": True, "rows": rows, "batch": preview["batch"], "data_date": preview["data_date"]}
