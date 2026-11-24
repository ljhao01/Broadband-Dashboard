# -*- coding: utf-8 -*-
"""
弱光督办模块数据访问对象（Repository）。

职责：
- 封装 weak_light_upload / weak_light_detail / weak_light_community /
  weak_light_pon / weak_light_new / weak_light_enterprise / weak_light_stat
  七张表，以及 weak_light_person（人员/责任田）的读写逻辑；
- 为路由层与业务服务层提供高阶查询接口；
- 不直接处理 HTTP 请求或 Excel 解析。
"""
import json
import re
import sqlite3
from datetime import datetime

from config import XINZHOU_ACTIVE_USERS
from db import get_conn
from services import llm_service

# 需要关注归属区县
XINZHOU = "新洲区"


def _normalize_person(name):
    """人员名归一化（去掉装维人员/括号等后缀），用于回填后的展示一致性。"""
    if not name:
        return ""
    s = str(name).strip()
    s = re.sub(r"[（(]\s*(装维|装维人员|装维师傅)\s*[)）]", "", s)
    s = re.sub(r"[\s（）()]", "", s)
    return s


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def save_weak_light_report(res, filename):
    """把解析后的弱光报表结果写入数据库（批次 + 明细 + 小区 + PON + 新增 + 企宽 + 统计）。"""
    conn = get_conn()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        upload_date = datetime.now().strftime("%Y-%m-%d")
        data_date = res.get("data_date") or now
        summary = res.get("summary", {})

        # ---- 上一批次及其「存量弱光总明细」网关SN集合（用于判定新增弱光）----
        # 新增弱光口径：不读取 excel 的「新增弱光」sheet，改为对比「存量弱光总明细」，
        # 当前批次网关SN 不在上一批次 → 视为新增。
        # 上一批次 = 数据日期更早的最近一批（同一天重复上传时不把上一份当成基线，
        # 否则会因 SN 完全相同而误判「新增 0」）
        prev_row = conn.execute(
            "SELECT id FROM weak_light_upload WHERE data_date < ? "
            "ORDER BY data_date DESC, id DESC LIMIT 1",
            (data_date,),
        ).fetchone()
        if not prev_row:
            prev_row = conn.execute(
                "SELECT id FROM weak_light_upload ORDER BY id DESC LIMIT 1"
            ).fetchone()
        prev_batch_id = prev_row["id"] if prev_row else None
        prev_sns = set()
        if prev_batch_id:
            prev_sns = {
                r["gateway_sn"] for r in conn.execute(
                    "SELECT gateway_sn FROM weak_light_detail "
                    "WHERE batch_id = ? AND gateway_sn != ''",
                    (prev_batch_id,),
                ).fetchall()
            }

        # 存量弱光总明细（新洲区）
        details = res.get("details", [])

        # 判定每条存量明细是否为「新增弱光」（网关SN 不在上一批次），
        # 并为新增弱光生成可落 weak_light_new 表的数据结构。
        new_weaks = []
        for d in details:
            sn = d.get("gateway_sn")
            # 无上一批次基线时不做「新增」判定（否则会把全部存量误标为新增）
            is_new = bool(prev_batch_id) and bool(sn) and sn not in prev_sns
            d["is_new"] = is_new
            if is_new:
                new_weaks.append({
                    "gateway_sn": sn,
                    "account": d.get("account", ""),
                    "mac": d.get("mac", ""),
                    "active_count": d.get("active_count", 0),
                    "valley_power": d.get("valley_power"),
                    "peak_power": d.get("peak_power"),
                    "weak_count": d.get("weak_count", 0),
                    "community": d.get("community", ""),
                    "olt": d.get("olt", ""),
                    "pon": d.get("pon", ""),
                    "onu": d.get("onu", ""),
                    "technician": d.get("technician", ""),
                    # 存量明细无弱光天数/整改等字段，新增判定仅凭网关SN，以下用空值
                    "weak_days": 0,
                    "rectification": "",
                    "weak_date": None,
                    "install_date": None,
                    "technician_no": "",
                    "is_rectified": 0,
                })
        new_weak_cnt = len(new_weaks)
        # 回写解析结果摘要，使上传接口返回的新增弱光数量与实际落库一致
        summary["new_weak_cnt"] = new_weak_cnt
        res["new_weaks"] = new_weaks

        # 平均弱光率：取「统计」中新洲区行的 avg_rate（武汉8月平均弱光率）
        avg_rate = None
        for s in res.get("stats", []):
            if s.get("district") == XINZHOU and s.get("avg_rate") is not None:
                avg_rate = s.get("avg_rate")
                break
        summary["avg_rate"] = avg_rate

        cur = conn.execute(
            """
            INSERT INTO weak_light_upload
              (filename, data_date, weak_total, weak_rate, avg_rate,
               sustained_cnt, poor_cell_cnt, severe_cnt, pon_cnt, new_weak_cnt,
               upload_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                data_date,
                summary.get("weak_total", 0),
                summary.get("weak_rate"),
                avg_rate,
                summary.get("sustained_cnt", 0),
                summary.get("poor_cell_cnt", 0),
                summary.get("severe_cnt", 0),
                summary.get("pon_cnt", 0),
                new_weak_cnt,
                upload_date,
                now,
            ),
        )
        batch_id = cur.lastrowid

        # 存量弱光总明细
        for d in details:
            conn.execute(
                """
                INSERT INTO weak_light_detail
                  (batch_id, gateway_sn, account, mac, active_count,
                   valley_power, peak_power, weak_count, community, technician,
                   olt, pon, onu, sustained, enterprise, is_new, quality_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, d.get("gateway_sn"), d.get("account"), d.get("mac"),
                    d.get("active_count"), d.get("valley_power"), d.get("peak_power"),
                    d.get("weak_count"), d.get("community"), d.get("technician"),
                    d.get("olt"), d.get("pon"), d.get("onu"),
                    1 if d.get("sustained") else 0,
                    1 if d.get("enterprise") else 0,
                    1 if d.get("is_new") else 0,
                    d.get("quality_type"),
                ),
            )

        # 小区分析
        for c in res.get("communities", []):
            conn.execute(
                """
                INSERT INTO weak_light_community
                  (batch_id, community, weak_count, prev_count, change_val, quality_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, c.get("community"), c.get("weak_count"),
                    c.get("prev_count"), c.get("change_val"), c.get("quality_type"),
                ),
            )

        # PON 口分析
        for p in res.get("pons", []):
            conn.execute(
                """
                INSERT INTO weak_light_pon
                  (batch_id, pon, weak_count, prev_count, change_val,
                   community, weak_mark, quality_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, p.get("pon"), p.get("weak_count"),
                    p.get("prev_count"), p.get("change_val"), p.get("community"),
                    1 if p.get("weak_mark") else 0, p.get("quality_type"),
                ),
            )

        # 新增弱光（由「存量弱光总明细」对比上一批次网关SN 判定得出）
        for n in new_weaks:
            conn.execute(
                """
                INSERT INTO weak_light_new
                  (batch_id, weak_days, rectification, weak_date, install_date,
                   gateway_sn, account, mac, active_count, valley_power, peak_power,
                   weak_count, community, olt, pon, onu,
                   technician, technician_no, is_rectified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, n.get("weak_days"), n.get("rectification"),
                    n.get("weak_date"), n.get("install_date"),
                    n.get("gateway_sn"), n.get("account"), n.get("mac"),
                    n.get("active_count"), n.get("valley_power"), n.get("peak_power"),
                    n.get("weak_count"), n.get("community"), n.get("olt"),
                    n.get("pon"), n.get("onu"),
                    n.get("technician"), n.get("technician_no"),
                    1 if n.get("is_rectified") else 0,
                ),
            )

        # 企宽弱光
        for e in res.get("enterprises", []):
            conn.execute(
                """
                INSERT INTO weak_light_enterprise
                  (batch_id, gateway_sn, account, mac, active_count,
                   valley_power, peak_power, weak_count, community, olt, pon, onu)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, e.get("gateway_sn"), e.get("account"), e.get("mac"),
                    e.get("active_count"), e.get("valley_power"), e.get("peak_power"),
                    e.get("weak_count"), e.get("community"), e.get("olt"),
                    e.get("pon"), e.get("onu"),
                ),
            )

        # 区县统计
        for s in res.get("stats", []):
            conn.execute(
                """
                INSERT INTO weak_light_stat
                  (batch_id, district, weak_count, weak_rate, prev_count,
                   active_users, change_count, change_rate, avg_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, s.get("district"), s.get("weak_count"), s.get("weak_rate"),
                    s.get("prev_count"), s.get("active_users"), s.get("change_count"),
                    s.get("change_rate"), s.get("avg_rate"),
                ),
            )

        conn.commit()
        return batch_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 数据清理（按月份/区县删除历史批次）
# ---------------------------------------------------------------------------
# 弱光批次的所有子表（删除批次时需一并清理）
_BATCH_CHILD_TABLES = [
    "weak_light_detail",
    "weak_light_community",
    "weak_light_pon",
    "weak_light_new",
    "weak_light_enterprise",
    "weak_light_stat",
]


def purge_batches(month=None):
    """删除弱光批次及其全部明细数据。

    month: "YYYY-MM" → 仅删除 data_date 属于该月的批次；None → 删除全部批次。
    返回 {"batches": 删除批次数, "rows": {表名: 删除行数}}。
    """
    conn = get_conn()
    try:
        if month:
            rows = conn.execute(
                "SELECT id FROM weak_light_upload WHERE substr(data_date, 1, 7) = ?",
                (month,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT id FROM weak_light_upload").fetchall()
        batch_ids = [r["id"] for r in rows]

        deleted = {}
        if batch_ids:
            marks = ",".join("?" * len(batch_ids))
            for table in _BATCH_CHILD_TABLES:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE batch_id IN ({marks})", batch_ids
                )
                deleted[table] = cur.rowcount
            cur = conn.execute(
                f"DELETE FROM weak_light_upload WHERE id IN ({marks})", batch_ids
            )
            deleted["weak_light_upload"] = cur.rowcount
        conn.commit()
        return {"month": month, "batches": len(batch_ids), "rows": deleted}
    finally:
        conn.close()


def recalc_weak_rate(active_users=None):
    """按「弱光户数 / 新洲区活跃用户数」重算并回写平均弱光率。

    用于弱光率口径调整后修正已入库的批次（无需重新上传）：
    - `weak_light_upload.weak_rate` / `avg_rate`
    - `weak_light_stat`（新洲区行）`weak_rate` / `avg_rate` / `active_users`

    返回 {"active_users": 活跃用户数, "batches": 更新批次数}。
    """
    users = active_users or XINZHOU_ACTIVE_USERS
    conn = get_conn()
    try:
        if not users or users <= 0:
            return {"active_users": users, "batches": 0, "error": "活跃用户数无效"}
        rows = conn.execute("SELECT id, weak_total FROM weak_light_upload").fetchall()
        for r in rows:
            rate = round((r["weak_total"] or 0) / users, 6)
            conn.execute(
                "UPDATE weak_light_upload SET weak_rate = ?, avg_rate = ? WHERE id = ?",
                (rate, rate, r["id"]),
            )
            conn.execute(
                """
                UPDATE weak_light_stat
                   SET weak_rate = ?, avg_rate = ?, active_users = ?
                 WHERE batch_id = ? AND district = ?
                """,
                (rate, rate, users, r["id"], XINZHOU),
            )
        conn.commit()
        return {"active_users": users, "batches": len(rows)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 人员映射（小区/网格 → 对应装维人员）
# ---------------------------------------------------------------------------
def save_person_map(res, filename=""):
    """把《责任田》/《人员录》解析结果落库（全量覆盖式更新人员与责任田映射）。

    - 《责任田》格式（res["format"] == "field"）：逐条写入责任田全字段，
      **替换全部旧记录**；业务更新日期取文件「更新日期」，系统上传日期另存 upload_date。
    - 《人员录》格式：按 小区 → 人员 映射写入（兼容旧格式）。
    """
    conn = get_conn()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        upload_date = datetime.now().strftime("%Y-%m-%d")
        fname = filename or res.get("filename", "")
        fields = res.get("fields") or []

        # 安全护栏：解析结果为空时拒绝覆盖，避免误清空已有责任田数据
        if not fields and not res.get("community_map"):
            return {"ok": False, "error": "解析结果为空，已保留原责任田数据",
                    "count": 0, "personnel": 0}

        conn.execute("DELETE FROM weak_light_person")  # 每次全量覆盖，替换旧记录

        if fields:
            conn.executemany(
                """
                INSERT INTO weak_light_person
                  (filename, community, person, grid, phone, emp_no,
                   city, district, grid_code, community_code, user_count,
                   install_persons, complain_persons, is_standard, scene,
                   scene_category, asset_owner, update_date, upload_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        fname, r.get("community", ""), r.get("person", ""),
                        r.get("grid", ""), r.get("phone", ""), r.get("emp_no", ""),
                        r.get("city", ""), r.get("district", ""), r.get("grid_code", ""),
                        r.get("community_code", ""), r.get("user_count", 0),
                        r.get("install_persons", ""), r.get("complain_persons", ""),
                        r.get("is_standard", ""), r.get("scene", ""),
                        r.get("scene_category", ""), r.get("asset_owner", ""),
                        r.get("update_date", ""), upload_date, now,
                    )
                    for r in fields
                ],
            )
            conn.commit()
            persons = {r.get("person") for r in fields if r.get("person")}
            return {
                "ok": True, "format": "field",
                "count": len(fields), "personnel": len(persons),
                "community": len({r.get("community") for r in fields if r.get("community")}),
                "update_date": res.get("update_date", ""),
            }

        # 兼容《人员录》格式
        personnel = res.get("personnel", [])
        phone_map = {p["name"]: p.get("phone", "") for p in personnel if p.get("name")}
        grid_map = {p["name"]: p.get("grid", "") for p in personnel if p.get("name")}
        emp_map = {p["name"]: p.get("emp_no", "") for p in personnel if p.get("name")}
        community_map = res.get("community_map", {})
        for community, person in community_map.items():
            conn.execute(
                """
                INSERT INTO weak_light_person
                  (filename, community, person, grid, phone, emp_no, upload_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fname, community, person,
                    grid_map.get(person, ""), phone_map.get(person, ""),
                    emp_map.get(person, ""), upload_date, now,
                ),
            )
        conn.commit()
        return {"ok": True, "format": "roster",
                "count": len(community_map), "personnel": len(personnel)}
    finally:
        conn.close()


def field_listing(person=None):
    """责任田清单：按责任人聚合 + 每人负责的责任田明细。

    返回：
    {
        "ok": True,
        "update_date": 最新业务更新日期,
        "upload_date": 最新上传日期,
        "person_count": 责任人数,
        "field_count": 责任田（小区）总数,
        "user_total": 用户数合计,
        "persons": [{
            "person", "field_count", "user_total", "phone", "emp_no",
            "grids": [网格名...], "grid_codes": [网格编码...],
            "scenes": {场景: 数量},
            "fields": [{community, community_code, user_count, grid, grid_code,
                        scene, scene_category, is_standard}]
        }]
    }
    """
    conn = get_conn()
    try:
        sql = """
            SELECT community, community_code, person, grid, grid_code, phone, emp_no,
                   user_count, scene, scene_category, is_standard, update_date, upload_date
            FROM weak_light_person
        """
        params = ()
        if person:
            sql += " WHERE person = ?"
            params = (person,)
        sql += " ORDER BY person, user_count DESC, community"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    if not rows:
        return {
            "ok": True, "update_date": "", "upload_date": "",
            "person_count": 0, "field_count": 0, "user_total": 0, "persons": [],
        }

    grouped = {}
    for r in rows:
        p = r["person"] or "未指派"
        g = grouped.setdefault(p, {
            "person": p, "field_count": 0, "user_total": 0,
            "phone": r.get("phone") or "", "emp_no": r.get("emp_no") or "",
            "grids": [], "grid_codes": [], "scenes": {}, "fields": [],
        })
        g["field_count"] += 1
        g["user_total"] += int(r.get("user_count") or 0)
        if r.get("grid") and r["grid"] not in g["grids"]:
            g["grids"].append(r["grid"])
        if r.get("grid_code") and r["grid_code"] not in g["grid_codes"]:
            g["grid_codes"].append(r["grid_code"])
        sc = r.get("scene") or "未知"
        g["scenes"][sc] = g["scenes"].get(sc, 0) + 1
        g["fields"].append({
            "community": r["community"],
            "community_code": r.get("community_code") or "",
            "user_count": int(r.get("user_count") or 0),
            "grid": r.get("grid") or "",
            "grid_code": r.get("grid_code") or "",
            "scene": r.get("scene") or "",
            "scene_category": r.get("scene_category") or "",
            "is_standard": r.get("is_standard") or "",
        })

    persons = sorted(grouped.values(), key=lambda x: (-x["field_count"], x["person"]))
    update_dates = {r.get("update_date") for r in rows if r.get("update_date")}
    upload_dates = {r.get("upload_date") for r in rows if r.get("upload_date")}
    return {
        "ok": True,
        "update_date": max(update_dates) if update_dates else "",
        "upload_date": max(upload_dates) if upload_dates else "",
        "person_count": len(persons),
        "field_count": len(rows),
        "user_total": sum(int(r.get("user_count") or 0) for r in rows),
        "persons": persons,
    }


def get_person_map():
    """返回小区→人员 映射字典 {community: {person, grid, phone, emp_no, user_count}}。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT community, person, grid, phone, emp_no, user_count FROM weak_light_person"
        ).fetchall()
        return {r["community"]: dict(r) for r in rows}
    finally:
        conn.close()


def get_person_list():
    """返回人员基础档案列表（去重）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT person, grid, phone, emp_no
            FROM weak_light_person
            GROUP BY person
            ORDER BY person
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 读取：最新批次 + 看板数据
# ---------------------------------------------------------------------------
def latest_weak_light():
    """返回最近一次上传的弱光批次汇总。"""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id, filename, data_date, weak_total, weak_rate, avg_rate, sustained_cnt,
                   poor_cell_cnt, severe_cnt, pon_cnt, new_weak_cnt, upload_date, created_at
            FROM weak_light_upload
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        r["avg_rate"] = _resolve_avg_rate(conn, r["id"], r.get("avg_rate"))
        return r
    finally:
        conn.close()


def _resolve_avg_rate(conn, batch_id, current=None):
    """取批次平均弱光率 avg_rate；为空/0 时回退到该批次「统计」表新洲区行的 avg_rate。"""
    if current:
        return current
    row = conn.execute(
        """
        SELECT avg_rate FROM weak_light_stat
        WHERE batch_id = ? AND district = ? AND avg_rate IS NOT NULL AND avg_rate > 0
        ORDER BY id DESC LIMIT 1
        """,
        (batch_id, XINZHOU),
    ).fetchone()
    return row["avg_rate"] if row else None


def _prev_batch_and_sns(conn, batch_id):
    """取上一批次及其存量弱光网关SN集合（用于按网关SN判定「新增」）。

    判定口径：
    - 以「网关SN」为唯一依据；
    - 取 id 小于当前批次且最新的一批（上一批次）；
    - 收集上一批次「存量弱光明细 weak_light_detail」的网关SN 集合；
    - 若当前设备网关SN 不在该集合中 → 判定为「新增弱光」（较上次新增）。
    """
    cur = conn.execute(
        "SELECT id, data_date FROM weak_light_upload WHERE id = ?", (batch_id,)
    ).fetchone()
    cur_date = (cur["data_date"] if cur else "") or ""

    # 「上一批次」以数据日期为准：同一天重复上传时不会被当成基线
    prev = conn.execute(
        """
        SELECT id, data_date FROM weak_light_upload
        WHERE data_date < ? ORDER BY data_date DESC, id DESC LIMIT 1
        """,
        (cur_date,),
    ).fetchone()
    if not prev:
        # 日期缺失的历史数据回退到按 id 取上一批
        prev = conn.execute(
            "SELECT id, data_date FROM weak_light_upload WHERE id < ? "
            "ORDER BY id DESC LIMIT 1",
            (batch_id,),
        ).fetchone()
    prev_batch = dict(prev) if prev else None
    prev_sns = set()
    if prev_batch:
        prev_sns = {
            r["gateway_sn"] for r in conn.execute(
                "SELECT gateway_sn FROM weak_light_detail WHERE batch_id = ? AND gateway_sn != ''",
                (prev_batch["id"],),
            ).fetchall()
        }
    return prev_batch, prev_sns


def _collect_new_weaks(conn, batch_id, prev_sns, resolver=None):
    """生成「新增弱光」清单：当前批次网关SN 减去上一数据批次的 SN 集合。

    weak_light_new 仅作为字段补充来源（weak_days / 整改 / 装机日期等），
    清单本身以实时差集为准 —— 同一天重复上传不会因 SN 完全相同而得到 0，
    也不会沿用历史批次里因基线取错而失真的行。

    resolver(community, fallback) 用于回填对应人员，缺省仅做名称归一化。
    """
    def _default_resolver(community, fallback=""):
        return _normalize_person(fallback) if fallback else ""

    resolve = resolver or _default_resolver
    stored = {
        r["gateway_sn"]: dict(r) for r in conn.execute(
            """
            SELECT weak_days, rectification, weak_date, install_date, gateway_sn,
                   account, mac, active_count, valley_power, peak_power, weak_count,
                   community, olt, pon, onu, technician, technician_no, is_rectified
            FROM weak_light_new WHERE batch_id = ? AND gateway_sn != ''
            """,
            (batch_id,),
        ).fetchall()
    }

    items, seen = [], set()
    for r in conn.execute(
        """
        SELECT gateway_sn, account, mac, active_count, valley_power, peak_power,
               weak_count, community, olt, pon, onu, quality_type
        FROM weak_light_detail WHERE batch_id = ? AND gateway_sn != ''
        ORDER BY valley_power ASC
        """,
        (batch_id,),
    ).fetchall():
        sn = (r["gateway_sn"] or "").strip()
        if not sn or sn in prev_sns or sn in seen:
            continue
        seen.add(sn)
        row = stored.get(sn) or {}
        community = r["community"] or row.get("community") or ""
        items.append({
            "gateway_sn": sn,
            "account": row.get("account") or r["account"] or "",
            "mac": row.get("mac") or r["mac"] or "",
            "active_count": row.get("active_count") or r["active_count"] or 0,
            "valley_power": r["valley_power"] if r["valley_power"] is not None else row.get("valley_power"),
            "peak_power": r["peak_power"] if r["peak_power"] is not None else row.get("peak_power"),
            "weak_count": row.get("weak_count") or r["weak_count"] or 0,
            "community": community,
            "olt": r["olt"] or row.get("olt") or "",
            "pon": r["pon"] or row.get("pon") or "",
            "onu": r["onu"] or row.get("onu") or "",
            "quality_type": r["quality_type"] or "",
            "weak_days": row.get("weak_days"),
            "rectification": row.get("rectification") or "",
            "weak_date": row.get("weak_date"),
            "install_date": row.get("install_date"),
            "technician": resolve(community, row.get("technician")),
            "technician_no": row.get("technician_no") or "",
            "is_rectified": row.get("is_rectified") or 0,
            "is_new_vs_prev": True,
            "prev_existed": False,
        })

    items.sort(key=lambda n: (int(n.get("is_rectified") or 0),
                              -(int(n.get("weak_days") or 0))))
    return items


def _recent_history(conn, batch_id, limit=4):
    """取当前批次之前的最近几批（不含本期），作为「以前的经验」供大模型参考。"""
    rows = conn.execute(
        """
        SELECT data_date, weak_total, weak_rate, avg_rate, sustained_cnt
        FROM weak_light_upload
        WHERE id < ?
        ORDER BY data_date DESC
        LIMIT ?
        """,
        (batch_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 首屏概览：近 7 日弱光趋势 + 当日网格分布
# ---------------------------------------------------------------------------
OVERVIEW_BATCHES = 7       # 趋势窗口：最近 N 次导入（批次）
GRID_NAME_PREFIX = "新洲"  # 市场网格名前缀，展示时剥离


def _overview_trend(conn, latest, batches=OVERVIEW_BATCHES):
    """最近 N 次导入的弱光趋势（按批次，而非按自然日补零）。

    取最近 N 个批次（同一 data_date 只取 id 最大者），每条点对应一次真实导入；
    批次不足 N 个时有几批画几批，不补空日期、不插值。
    """
    window = _batch_window(conn, batches)
    if not window:
        return {
            "dates": [], "labels": [], "weak": [], "severe": [],
            "batch_cnt": 0, "days_with_data": 0,
        }

    ids = [b["id"] for b in window]
    rows = conn.execute(
        "SELECT id, weak_total, severe_cnt FROM weak_light_upload WHERE id IN (%s)"
        % ",".join("?" * len(ids)),
        ids,
    ).fetchall()
    by_id = {r["id"]: r for r in rows}

    weak, severe = [], []
    for b in window:
        r = by_id.get(b["id"])
        weak.append(int(r["weak_total"] or 0) if r else None)
        severe.append(int(r["severe_cnt"] or 0) if r else None)

    return {
        "dates": [b["data_date"] for b in window],
        "labels": [b["data_date"][5:].replace("-", "/") for b in window],
        "weak": weak,
        "severe": severe,
        "batch_cnt": len(window),
        "days_with_data": sum(1 for v in weak if v is not None),
    }


def _overview_grids(conn, batch_id, person_map):
    """当日弱光区域分布（小区 → 市场网格）。

    优先按《责任田》的市场网格聚合；若一条都没匹配上（未上传责任田），
    退化为「小区维度 TOP 12」，避免整块图只剩一个「未归属网格」格子。
    """
    rows = conn.execute(
        """
        SELECT community, COUNT(*) AS weak_count,
               SUM(CASE WHEN IFNULL(valley_power, 0) < -30 THEN 1 ELSE 0 END) AS severe_cnt
        FROM weak_light_detail WHERE batch_id = ?
        GROUP BY community
        """,
        (batch_id,),
    ).fetchall()

    agg, matched, unmatched_weak, unmatched_comm = {}, 0, 0, 0
    for r in rows:
        rec = person_map.get((r["community"] or "").strip()) or {}
        grid = (rec.get("grid") or "").strip()
        if grid:
            matched += 1
        else:
            grid = "未归属网格"
            unmatched_weak += r["weak_count"]
            unmatched_comm += 1
        a = agg.setdefault(grid, {
            "name": grid, "weak_count": 0, "severe_cnt": 0, "community_cnt": 0,
        })
        a["weak_count"] += r["weak_count"]
        a["severe_cnt"] += r["severe_cnt"] or 0
        a["community_cnt"] += 1

    total = sum(c["weak_count"] for c in agg.values()) or 0

    if matched:
        mode = "grid"
        cells = sorted(agg.values(), key=lambda x: (-x["weak_count"], x["name"]))
    else:
        mode = "community"
        cells = [{
            "name": r["community"] or "未知小区",
            "weak_count": r["weak_count"],
            "severe_cnt": r["severe_cnt"] or 0,
            "community_cnt": 1,
        } for r in rows]
        cells.sort(key=lambda x: (-x["weak_count"], x["name"]))
        cells = cells[:12]

    peak = max((c["weak_count"] for c in cells), default=0) or 1
    for c in cells:
        name = c["name"]
        c["short"] = name[len(GRID_NAME_PREFIX):] if name.startswith(GRID_NAME_PREFIX) else name
        c["ratio"] = round(c["weak_count"] / total, 4) if total else 0
        heat = c["weak_count"] / peak
        c["level"] = "high" if heat >= 0.66 else "mid" if heat >= 0.33 else "low"

    return {
        "mode": mode,
        "cells": cells,
        "total": total,
        "grid_cnt": len(cells) if mode == "grid" else 0,
        "cell_cnt": len(cells),
        "unmatched_weak": unmatched_weak,
        "unmatched_comm": unmatched_comm,
    }


# ---------------------------------------------------------------------------
# 持续弱光追踪：同一网关 SN 跨批次反复弱光
# ---------------------------------------------------------------------------
SUSTAINED_MIN_BATCHES = 3   # 累计出现该批次数即判定为持续弱光
SUSTAINED_LOOKBACK = 10     # 回溯窗口（批次）
HIGH_FREQ_UNFIXED = 2       # 未整改次数阈值（出现 3 次即 2 次未整改）
HIGH_FREQ_DAYS = 7          # 持续天数阈值


def _batch_window(conn, lookback=SUSTAINED_LOOKBACK, upto_batch_id=None):
    """取最近 lookback 个批次（同一 data_date 只取 id 最大者），按日期升序返回。

    upto_batch_id 用于回溯历史批次：窗口截止到该批次的数据日期，
    保证查看历史批次时「持续/复发」判定与当时口径一致。
    """
    sql = ("SELECT id, data_date FROM weak_light_upload "
           "WHERE data_date IS NOT NULL AND data_date != ''")
    params = []
    if upto_batch_id:
        row = conn.execute(
            "SELECT data_date FROM weak_light_upload WHERE id = ?", (upto_batch_id,)
        ).fetchone()
        if row and (row["data_date"] or ""):
            sql += " AND data_date <= ?"
            params.append(row["data_date"])
    sql += " ORDER BY data_date DESC, id DESC"
    rows = conn.execute(sql, params).fetchall()
    picked, seen = [], set()
    for r in rows:
        d = r["data_date"]
        if d in seen:
            continue
        seen.add(d)
        picked.append({"id": r["id"], "data_date": d})
        if len(picked) >= lookback:
            break
    picked.sort(key=lambda x: x["data_date"])
    return picked


def _empty_sustained(min_batches=SUSTAINED_MIN_BATCHES, lookback=SUSTAINED_LOOKBACK):
    """无批次时的空结构（前端据此显示「需 ≥N 个批次」提示）。"""
    return {
        "ok": True,
        "has_data": False,
        "batches_used": [],
        "summary": {
            "sustained_cnt": 0, "high_freq_cnt": 0, "closed_cnt": 0,
            "revived_cnt": 0, "max_span_days": 0, "community_cnt": 0, "sn_missing": 0,
            "batch_cnt": 0, "min_batches": min_batches, "lookback": lookback,
        },
        "items": [],
        "closed": [],
    }


def sustained_tracking(min_batches=SUSTAINED_MIN_BATCHES,
                       lookback=SUSTAINED_LOOKBACK,
                       limit=200,
                       person_map=None,
                       upto_batch_id=None):
    """跨批次持续弱光追踪（按网关 SN）。

    口径：
    - 窗口：最近 lookback 个批次（同一 data_date 取 id 最大者）；
    - 持续弱光：窗口内累计出现 >= min_batches 个批次，且最新批次仍存在；
      不要求批次日期连续（漏传一天不会丢记录，缺批计入 gaps）；
    - 未整改次数 = 出现批次数 - 1（首次发现不计入未整改）；
    - 高频未整改：未整改次数 >= 2 或 持续天数 >= 7；
    - 已闭环：最新批次不再出现（视为已整改，无法区分修复/拆机停机）。
    """
    min_batches = max(2, int(min_batches or SUSTAINED_MIN_BATCHES))
    lookback = max(2, int(lookback or SUSTAINED_LOOKBACK))
    limit = max(1, int(limit or 200))

    conn = get_conn()
    try:
        batches = _batch_window(conn, lookback, upto_batch_id)
        if not batches:
            return _empty_sustained(min_batches, lookback)
        ids = [b["id"] for b in batches]
        date_of = {b["id"]: b["data_date"] for b in batches}
        order_of = {b["id"]: i for i, b in enumerate(batches)}
        rows = conn.execute(
            "SELECT batch_id, gateway_sn, account, community, valley_power, "
            "quality_type, pon FROM weak_light_detail WHERE batch_id IN (%s)"
            % ",".join("?" * len(ids)),
            ids,
        ).fetchall()
    finally:
        conn.close()

    if person_map is None:
        person_map = get_person_map()

    sn_missing, agg = 0, {}
    for r in rows:
        sn = (r["gateway_sn"] or "").strip()
        if not sn:
            sn_missing += 1
            continue
        bid = r["batch_id"]
        d = date_of.get(bid, "")
        rec = agg.get(sn)
        if rec is None:
            rec = agg[sn] = {
                "gateway_sn": sn, "batches": set(), "idx": set(), "valleys": [],
                "community": "", "account": "", "quality_type": "", "pon": "",
                "last_date": "", "last_valley": None,
            }
        rec["batches"].add(bid)
        rec["idx"].add(order_of.get(bid, 0))
        if r["valley_power"] is not None:
            rec["valleys"].append(float(r["valley_power"]))
        if d >= rec["last_date"]:
            rec["last_date"] = d
            rec["community"] = (r["community"] or "").strip()
            rec["account"] = (r["account"] or "").strip()
            rec["quality_type"] = (r["quality_type"] or "").strip()
            rec["pon"] = (r["pon"] or "").strip()
            rec["last_valley"] = r["valley_power"]

    latest_id = batches[-1]["id"]
    items, closed = [], []
    for sn, rec in agg.items():
        dates = sorted(date_of[b] for b in rec["batches"])
        first_date, last_date = dates[0], dates[-1]
        try:
            span_days = (datetime.strptime(last_date, "%Y-%m-%d")
                         - datetime.strptime(first_date, "%Y-%m-%d")).days
        except ValueError:
            span_days = 0
        appear = len(rec["batches"])
        min_valley = min(rec["valleys"]) if rec["valleys"] else None
        person = person_map.get(rec["community"]) or {}
        base = {
            "gateway_sn": sn,
            "account": rec["account"],
            "community": rec["community"],
            "person": person.get("person") or "",
            "phone": person.get("phone") or "",
            "appear_batches": appear,
            "span_days": max(0, span_days),
            "first_date": first_date,
            "last_date": last_date,
            "min_valley": round(min_valley, 2) if min_valley is not None else None,
            "last_valley": round(float(rec["last_valley"]), 2) if rec["last_valley"] is not None else None,
            "quality_type": rec["quality_type"],
            "pon": rec["pon"],
        }
        if latest_id not in rec["batches"]:
            # 只把「曾复现过」的设备计入已闭环，避免把历史一次性弱光全算作已整改
            if appear >= 2:
                base["state"] = "closed"
                closed.append(base)
            continue
        if appear < min_batches:
            continue
        unfixed = appear - 1
        # 复发：窗口内曾中断（批次下标不连续）且最新批次再次出现
        idxs = sorted(rec["idx"])
        revived = bool(idxs) and idxs[-1] == len(batches) - 1 and any(
            b - a > 1 for a, b in zip(idxs, idxs[1:])
        )
        base.update({
            "unfixed_times": unfixed,
            "gaps": max(0, len(batches) - appear),
            "is_high_freq": unfixed >= HIGH_FREQ_UNFIXED or base["span_days"] >= HIGH_FREQ_DAYS,
            "revived": revived,
            "state": "ongoing",
        })
        items.append(base)

    items.sort(key=lambda x: (-x["unfixed_times"], -x["span_days"],
                              x["min_valley"] if x["min_valley"] is not None else 0))
    closed.sort(key=lambda x: (x["last_date"], x["gateway_sn"]), reverse=True)

    summary = {
        "sustained_cnt": len(items),
        "high_freq_cnt": sum(1 for i in items if i["is_high_freq"]),
        "revived_cnt": sum(1 for i in items if i.get("revived")),
        "closed_cnt": len(closed),
        "max_span_days": max((i["span_days"] for i in items), default=0),
        "community_cnt": len({i["community"] for i in items if i["community"]}),
        "sn_missing": sn_missing,
        "batch_cnt": len(batches),
        "min_batches": min_batches,
        "lookback": lookback,
    }
    return {
        "ok": True,
        "has_data": True,
        "batches_used": batches,
        "summary": summary,
        "items": items[:limit],
        "closed": closed[:50],
    }


# ---------------------------------------------------------------------------
# 智能总结：结构化问题清单 + 优先级排序（纯规则，LLM 仅做措辞润色）
# ---------------------------------------------------------------------------
INSIGHT_OVERDUE_DAYS = 14          # 超期未闭环阈值（天）
INSIGHT_WEIGHTS = {"conc": 0.32, "sev": 0.24, "dur": 0.20, "over": 0.14, "cov": 0.10}


def _priority_of(score):
    if score >= 75:
        return "P0"
    if score >= 55:
        return "P1"
    if score >= 35:
        return "P2"
    return "P3"


def _short_pon(name):
    """PON 全路径压缩为可读短名（保留端口定位段）。"""
    s = (name or "").strip()
    if not s:
        return ""
    parts = [p for p in re.split(r"[\\/]", s) if p]
    tail = "/".join(parts[-2:]) if len(parts) >= 2 else s
    return tail if len(tail) <= 28 else tail[-28:]


def _sn_evidence(items, person_map=None, limit=5):
    """把持续弱光明细压缩成可展开的证据列表（按持续天数、出现批次降序）。"""
    picked = sorted(items, key=lambda x: (x.get("span_days") or 0,
                                          x.get("appear_batches") or 0),
                    reverse=True)[:limit]
    out = []
    for i in picked:
        person = (person_map or {}).get(i.get("community") or "") or {}
        out.append({
            "sn": i.get("gateway_sn"),
            "community": i.get("community"),
            "person": i.get("person") or person.get("person") or "",
            "appear_batches": i.get("appear_batches"),
            "span_days": i.get("span_days"),
            "valley_power": i.get("last_valley"),
        })
    return out


def _empty_insights():
    return {
        "ok": True,
        "has_data": False,
        "batch": None,
        "summary": {"total": 0, "p0": 0, "p1": 0, "p2": 0, "p3": 0,
                    "overdue_cnt": 0, "revived_cnt": 0,
                    "data_date": None, "compare_date": None},
        "items": [],
    }


def build_insights(batch_id=None, overdue_days=INSIGHT_OVERDUE_DAYS):
    """生成结构化问题清单（6 类）+ 优先级评分。

    口径：
    - 集中度：条目涉及户数 / 本批次存量弱光户数；
    - 严重度：条目中谷值 < -30dBm 的户数占比；
    - 持续复发：条目内设备在追踪窗口的平均出现批次 / 10（复发项 ×1.15）；
    - 超期：条目内最长持续天数 / 30；覆盖面：涉及小区数 / 最大涉及小区数；
    - 闭环：明细无整改字段，只能按「最新批次是否仍弱光」推断，state 恒为 open/overdue。
    """
    overdue_days = max(1, int(overdue_days or INSIGHT_OVERDUE_DAYS))
    conn = get_conn()
    try:
        if batch_id:
            row = conn.execute(
                "SELECT id, data_date, weak_total FROM weak_light_upload WHERE id = ?",
                (batch_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, data_date, weak_total FROM weak_light_upload "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return _empty_insights()

        batch = dict(row)
        bid = batch["id"]
        prev_batch, _ = _prev_batch_and_sns(conn, bid)
        details = [dict(r) for r in conn.execute(
            "SELECT gateway_sn, community, pon, valley_power, quality_type "
            "FROM weak_light_detail WHERE batch_id = ?", (bid,)
        ).fetchall()]
        communities = [dict(r) for r in conn.execute(
            "SELECT community, weak_count FROM weak_light_community "
            "WHERE batch_id = ? ORDER BY weak_count DESC", (bid,)
        ).fetchall()]
        pons = [dict(r) for r in conn.execute(
            "SELECT pon, weak_count, community FROM weak_light_pon "
            "WHERE batch_id = ? ORDER BY weak_count DESC", (bid,)
        ).fetchall()]
        person_map = get_person_map()
    finally:
        conn.close()

    sustained = sustained_tracking(person_map=person_map, upto_batch_id=bid)
    sus_items = sustained.get("items") or []
    sus_by_sn = {i["gateway_sn"]: i for i in sus_items}
    min_batches = sustained.get("summary", {}).get("min_batches") or SUSTAINED_MIN_BATCHES

    total = len(details) or 1
    raw = []

    # ---- A 质差类型集中 ----
    qgroups = {}
    for d in details:
        qt = (d.get("quality_type") or "").strip() or "未分类"
        g = qgroups.setdefault(qt, {
            "count": 0, "severe": 0, "communities": {}, "pons": {}, "sns": [],
        })
        g["count"] += 1
        if d.get("valley_power") is not None and d["valley_power"] < -30:
            g["severe"] += 1
        c = (d.get("community") or "").strip()
        if c:
            g["communities"][c] = g["communities"].get(c, 0) + 1
        p = (d.get("pon") or "").strip()
        if p:
            g["pons"][p] = g["pons"].get(p, 0) + 1
        if d.get("gateway_sn"):
            g["sns"].append(d["gateway_sn"])

    for qt, g in sorted(qgroups.items(), key=lambda kv: -kv[1]["count"]):
        # 「未分类」等价于全部存量弱光，归因无意义，不产出条目
        if qt == "未分类":
            continue
        sus = [sus_by_sn[sn] for sn in g["sns"] if sn in sus_by_sn]
        span = max([s["span_days"] for s in sus], default=0)
        appear = max([s["appear_batches"] for s in sus], default=1)
        raw.append({
            "id": "quality:" + qt,
            "category": "质差集中",
            "title": "质差类型「%s」涉及 %d 户、%d 个小区" % (qt, g["count"], len(g["communities"])),
            "conc_value": g["count"],
            "conc_label": qt,
            "dimension": "quality_type",
            "sev": g["severe"] / g["count"] if g["count"] else 0,
            "dur": min(1.0, appear / 10.0),
            "over": min(1.0, span / 30.0),
            "cov_value": len(g["communities"]),
            "span_days": span,
            "first_seen": min([s["first_date"] for s in sus], default=batch["data_date"]),
            "appear_batches": appear,
            "gaps": max([s.get("gaps", 0) for s in sus], default=0),
            "revived": any(s.get("revived") for s in sus),
            "open": g["count"],
            "evidence": {
                "communities": [{"name": k, "count": v} for k, v in
                                sorted(g["communities"].items(), key=lambda kv: -kv[1])[:3]],
                "pons": [{"pon": k, "count": v} for k, v in
                         sorted(g["pons"].items(), key=lambda kv: -kv[1])[:3]],
                "sn": _sn_evidence(sus, person_map),
            },
            "suggestion": "核查所涉 PON 分光器与皮线，按小区集中上门，避免逐户重复派单",
        })

    # ---- B 小区集中（TOP 小区汇总为 1 条，证据列前 5） ----
    comm_sev = {}
    for d in details:
        if d.get("valley_power") is not None and d["valley_power"] < -30:
            c = (d.get("community") or "").strip()
            comm_sev[c] = comm_sev.get(c, 0) + 1
    hot_comms = [c for c in communities if (c.get("weak_count") or 0) > 0][:5]
    if hot_comms:
        top1 = hot_comms[0]
        top_name = top1["community"]
        top_cnt = top1.get("weak_count") or 0
        names = {c["community"] for c in hot_comms}
        top_sum = sum((c.get("weak_count") or 0) for c in hot_comms)
        sev_sum = sum(comm_sev.get(c["community"], 0) for c in hot_comms)
        sus = [i for i in sus_items if i["community"] in names]
        span = max([s["span_days"] for s in sus], default=0)
        appear = max([s["appear_batches"] for s in sus], default=1)
        raw.append({
            "id": "community:top",
            "category": "小区集中",
            "title": "TOP%d 小区合计弱光 %d 户（占全区 %.0f%%），最集中「%s」%d 户" % (
                len(hot_comms), top_sum, 100.0 * top_sum / total, top_name, top_cnt),
            "conc_value": top_sum,
            "conc_label": "TOP%d 小区" % len(hot_comms),
            "dimension": "community",
            "sev": (sev_sum / top_sum) if top_sum else 0,
            "dur": min(1.0, appear / 10.0),
            "over": min(1.0, span / 30.0),
            "cov_value": len(hot_comms),
            "span_days": span,
            "first_seen": min([s["first_date"] for s in sus], default=batch["data_date"]),
            "appear_batches": appear,
            "gaps": max([s.get("gaps", 0) for s in sus], default=0),
            "revived": any(s.get("revived") for s in sus),
            "open": top_sum,
            "evidence": {
                "communities": [{"name": c["community"], "count": c.get("weak_count") or 0}
                                for c in hot_comms],
                "pons": [],
                "sn": _sn_evidence(sus, person_map),
            },
            "suggestion": "以小区为单位组织专项，优先「%s」，同步核对该小区分光器与入户皮线" % top_name,
        })

    # ---- C PON 口集中（≥3 户，汇总为 1 条） ----
    pon_sev = {}
    for d in details:
        if d.get("valley_power") is not None and d["valley_power"] < -30:
            p = (d.get("pon") or "").strip()
            if p:
                pon_sev[p] = pon_sev.get(p, 0) + 1
    hot_pons = [p for p in pons if (p.get("weak_count") or 0) >= 3][:5]
    if hot_pons:
        top1 = hot_pons[0]
        pon = top1["pon"]
        pon_short = _short_pon(pon)
        count = top1.get("weak_count") or 0
        sus = [i for i in sus_items if i.get("pon") == pon]
        span = max([s["span_days"] for s in sus], default=0)
        appear = max([s["appear_batches"] for s in sus], default=1)
        raw.append({
            "id": "pon:top",
            "category": "PON 口集中",
            "title": "%d 个 PON 口弱光 ≥3 户，最集中 %s（%d 户）" % (len(hot_pons), pon_short, count),
            "conc_value": count,
            "conc_label": pon_short,
            "dimension": "pon",
            "sev": (pon_sev.get(pon, 0) / count) if count else 0,
            "dur": min(1.0, appear / 10.0),
            "over": min(1.0, span / 30.0),
            "cov_value": len(hot_pons),
            "span_days": span,
            "first_seen": min([s["first_date"] for s in sus], default=batch["data_date"]),
            "appear_batches": appear,
            "gaps": max([s.get("gaps", 0) for s in sus], default=0),
            "revived": any(s.get("revived") for s in sus),
            "open": sum((p.get("weak_count") or 0) for p in hot_pons),
            "evidence": {
                "communities": [],
                "pons": [{"pon": p["pon"], "short": _short_pon(p["pon"]),
                          "count": p.get("weak_count") or 0, "community": p.get("community")}
                         for p in hot_pons],
                "sn": _sn_evidence(sus, person_map),
            },
            "suggestion": "优先排查 %s 的分光器与主干光缆，一次性解决同 PON 多户弱光" % pon_short,
        })

    # ---- D 持续未闭环 / E 超期未解决 / F 复发 ----
    if sus_items:
        s_cnt = len(sus_items)
        s_sev = sum(1 for i in sus_items if (i.get("min_valley") or 0) < -30)
        s_span = max([i.get("span_days") or 0 for i in sus_items], default=0)
        s_appear = sum(i.get("appear_batches") or 0 for i in sus_items) / s_cnt
        s_first = min([i.get("first_date") for i in sus_items if i.get("first_date")],
                      default=batch["data_date"])
        raw.append({
            "id": "sustained",
            "category": "持续未闭环",
            "title": "%d 台设备跨批次反复弱光（累计出现 ≥%d 个批次）" % (s_cnt, min_batches),
            "conc_value": s_cnt,
            "conc_label": "持续弱光设备",
            "dimension": "gateway_sn",
            "sev": s_sev / s_cnt,
            "dur": min(1.0, s_appear / 10.0),
            "over": min(1.0, s_span / 30.0),
            "cov_value": len({i.get("community") for i in sus_items if i.get("community")}),
            "span_days": s_span,
            "first_seen": s_first,
            "appear_batches": round(s_appear, 1),
            "gaps": max([i.get("gaps") or 0 for i in sus_items], default=0),
            "revived": any(i.get("revived") for i in sus_items),
            "open": s_cnt,
            "evidence": {"communities": [], "pons": [], "sn": _sn_evidence(sus_items, person_map)},
            "suggestion": "逐户销号：明确责任人与完成时限，超过 7 天未闭环的升级督办",
        })

        overdue = [i for i in sus_items if (i.get("span_days") or 0) >= overdue_days]
        if overdue:
            o_span = max(i.get("span_days") or 0 for i in overdue)
            raw.append({
                "id": "overdue",
                "category": "超期未解决",
                "title": "%d 台设备弱光持续 ≥%d 天仍未闭环（最长 %d 天）" % (
                    len(overdue), overdue_days, o_span),
                "conc_value": len(overdue),
                "conc_label": "超期设备",
                "dimension": "gateway_sn",
                "sev": sum(1 for i in overdue if (i.get("min_valley") or 0) < -30) / len(overdue),
                "dur": min(1.0, sum(i.get("appear_batches") or 0 for i in overdue) / len(overdue) / 10.0),
                "over": min(1.0, o_span / 30.0),
                "cov_value": len({i.get("community") for i in overdue if i.get("community")}),
                "span_days": o_span,
                "first_seen": min([i.get("first_date") for i in overdue if i.get("first_date")],
                                  default=batch["data_date"]),
                "appear_batches": round(sum(i.get("appear_batches") or 0 for i in overdue) / len(overdue), 1),
                "gaps": max([i.get("gaps") or 0 for i in overdue], default=0),
                "revived": any(i.get("revived") for i in overdue),
                "open": len(overdue),
                "evidence": {"communities": [], "pons": [], "sn": _sn_evidence(overdue, person_map)},
                "suggestion": "按超期天数倒排工期，逐台回访并复核光功率，必要时更换皮线或 ONU",
            })

        revived = [i for i in sus_items if i.get("revived")]
        if revived:
            r_span = max(i.get("span_days") or 0 for i in revived)
            raw.append({
                "id": "revived",
                "category": "复发（曾修复后再现）",
                "title": "%d 台设备曾中断弱光后再次出现" % len(revived),
                "conc_value": len(revived),
                "conc_label": "复发设备",
                "dimension": "gateway_sn",
                "sev": sum(1 for i in revived if (i.get("min_valley") or 0) < -30) / len(revived),
                "dur": min(1.0, sum(i.get("appear_batches") or 0 for i in revived) / len(revived) / 10.0),
                "over": min(1.0, r_span / 30.0),
                "cov_value": len({i.get("community") for i in revived if i.get("community")}),
                "span_days": r_span,
                "first_seen": min([i.get("first_date") for i in revived if i.get("first_date")],
                                  default=batch["data_date"]),
                "appear_batches": round(sum(i.get("appear_batches") or 0 for i in revived) / len(revived), 1),
                "gaps": max([i.get("gaps") or 0 for i in revived], default=0),
                "revived": True,
                "open": len(revived),
                "evidence": {"communities": [], "pons": [], "sn": _sn_evidence(revived, person_map)},
                "suggestion": "复盘前期处置措施（是否仅重启/临时加固），复发设备需根治性整治并留痕",
            })

    # ---- 评分与分级 ----
    max_conc = max([r["conc_value"] for r in raw], default=1) or 1
    max_cov = max([r["cov_value"] for r in raw], default=1) or 1
    items = []
    for r in raw:
        conc = min(1.0, r["conc_value"] / max_conc)
        cov = min(1.0, r["cov_value"] / max_cov)
        sev = min(1.0, max(0.0, r["sev"]))
        # 复发项（F 类）在持续维度上加成，其余类别不因包含复发设备而抬分
        boost = 1.15 if r.get("id") == "revived" else 1.0
        dur = min(1.0, r["dur"] * boost)
        over = min(1.0, r["over"])
        score = round(100 * (
            INSIGHT_WEIGHTS["conc"] * conc + INSIGHT_WEIGHTS["sev"] * sev
            + INSIGHT_WEIGHTS["dur"] * dur + INSIGHT_WEIGHTS["over"] * over
            + INSIGHT_WEIGHTS["cov"] * cov
        ), 1)
        items.append({
            "id": r["id"],
            "category": r["category"],
            "title": r["title"],
            "concentration": {
                "value": r["conc_value"],
                "share": round(r["conc_value"] / total, 4),
                "label": r["conc_label"],
                "dimension": r["dimension"],
            },
            "status": {
                "open": r["open"],
                "closed": 0,
                "closed_inferred": False,
                "overdue_days": r["span_days"],
                "state": "overdue" if r["span_days"] >= overdue_days else "open",
            },
            "history": {
                "first_seen": r["first_seen"],
                "appear_batches": r["appear_batches"],
                "gaps": r["gaps"],
                "revived": r["revived"],
            },
            "factors": {
                "conc": round(conc, 3), "sev": round(sev, 3), "dur": round(dur, 3),
                "over": round(over, 3), "cov": round(cov, 3),
            },
            "score": score,
            "priority": _priority_of(score),
            "suggestion": r["suggestion"],
            "evidence": r["evidence"],
        })

    items.sort(key=lambda x: (-x["score"], -x["concentration"]["value"]))
    summary = {
        "total": len(items),
        "p0": sum(1 for i in items if i["priority"] == "P0"),
        "p1": sum(1 for i in items if i["priority"] == "P1"),
        "p2": sum(1 for i in items if i["priority"] == "P2"),
        "p3": sum(1 for i in items if i["priority"] == "P3"),
        "overdue_cnt": len([i for i in sus_items if (i.get("span_days") or 0) >= overdue_days]),
        "revived_cnt": len([i for i in sus_items if i.get("revived")]),
        "overdue_days": overdue_days,
        "data_date": batch["data_date"],
        "compare_date": (prev_batch or {}).get("data_date"),
        "batch_id": bid,
        "source": "rule",
        # 本批明细缺失质差类型时前端给出提示，避免误以为无质差集中问题
        "quality_missing": all(not (d.get("quality_type") or "").strip() for d in details),
    }
    return {"ok": True, "has_data": bool(details), "batch": batch,
            "summary": summary, "items": items}


def weak_light_dashboard():
    """组装弱光看板所需全部数据（基于最新批次）。

    增强：
    - 小区/明细/新增弱光均回填「对应人员」（来自人员映射表，解决最新批次人员为空）；
    - 新增弱光对比上一次上传：标识该用户是否为「较上一批次新增」；
    - 人员整治排行：统计每个人员名下待整治弱光户数。
    """
    conn = get_conn()
    try:
        latest = latest_weak_light()
        if not latest:
            return {"has_data": False, "latest": None, "kpis": [], "communities": [],
                    "pons": [], "new_weaks": [], "sustained_users": [], "severe_users": [],
                    "stats": [], "enterprises": [], "quality_cells": [], "ai_analysis": [],
                    "community_top": [], "pon_top": [], "person_ranking": [], "person_map": {},
                    "prev_batch": None, "new_weaks_summary": {},
                    "sustained_summary": _empty_sustained()["summary"],
                    "insights_summary": _empty_insights()["summary"],
                    "overview": {
                        "trend": _overview_trend(conn, None),
                        "grid": {"mode": "grid", "cells": [], "total": 0, "grid_cnt": 0,
                                 "cell_cnt": 0, "unmatched_weak": 0, "unmatched_comm": 0},
                    }}
        batch_id = latest["id"]

        person_map = get_person_map()  # {community: {person, grid, phone}}
        def _resolve_person(community, fallback=""):
            """按小区解析对应人员（优先映射表，其次落库 technician 归一化）。"""
            rec = person_map.get(community or "")
            if rec and rec["person"]:
                return rec["person"]
            if fallback:
                return _normalize_person(fallback)
            return ""

        # 小区排行（按弱光数降序，回填对应人员）
        communities = [
            dict(r) for r in conn.execute(
                """
                SELECT community, weak_count, prev_count, change_val, quality_type
                FROM weak_light_community WHERE batch_id = ?
                ORDER BY weak_count DESC, community
                """,
                (batch_id,),
            ).fetchall()
        ]
        for c in communities:
            c["technician"] = _resolve_person(c.get("community"))

        # PON 口排行（按弱光数降序，≥3 标红）
        pons = [
            dict(r) for r in conn.execute(
                """
                SELECT pon, weak_count, prev_count, change_val, community, weak_mark, quality_type
                FROM weak_light_pon WHERE batch_id = ?
                ORDER BY weak_count DESC, pon
                """,
                (batch_id,),
            ).fetchall()
        ]

        # 新增弱光：当前批次网关SN 与「上一个数据批次」的差集（实时计算）
        prev_batch, prev_sns = _prev_batch_and_sns(conn, batch_id)
        new_weaks = _collect_new_weaks(conn, batch_id, prev_sns, _resolve_person)

        # 持续弱光用户清单（回填对应人员）
        sustained_users = [
            dict(r) for r in conn.execute(
                """
                SELECT gateway_sn, account, community, valley_power, peak_power, olt, onu, quality_type
                FROM weak_light_detail WHERE batch_id = ? AND sustained = 1
                ORDER BY valley_power ASC
                """,
                (batch_id,),
            ).fetchall()
        ]
        for s in sustained_users:
            s["technician"] = _resolve_person(s.get("community"))

        # 严重弱光用户清单（谷值 <-30dBm，回填对应人员）
        severe_users = [
            dict(r) for r in conn.execute(
                """
                SELECT gateway_sn, account, community, valley_power, peak_power, olt, pon, onu,
                       sustained, quality_type
                FROM weak_light_detail WHERE batch_id = ? AND valley_power < -30
                ORDER BY valley_power ASC
                """,
                (batch_id,),
            ).fetchall()
        ]
        for s in severe_users:
            s["technician"] = _resolve_person(s.get("community"))

        # 企宽弱光
        enterprises = [
            dict(r) for r in conn.execute(
                """
                SELECT gateway_sn, account, community, valley_power, peak_power, olt, pon, onu
                FROM weak_light_enterprise WHERE batch_id = ?
                ORDER BY valley_power ASC
                """,
                (batch_id,),
            ).fetchall()
        ]

        # 区县统计
        stats = [
            dict(r) for r in conn.execute(
                """
                SELECT district, weak_count, weak_rate, prev_count, active_users,
                       change_count, change_rate, avg_rate
                FROM weak_light_stat WHERE batch_id = ?
                ORDER BY weak_rate DESC
                """,
                (batch_id,),
            ).fetchall()
        ]

        # 质差小区类型清单（严重/重复/严重且重复）
        quality_cells = [
            dict(r) for r in conn.execute(
                """
                SELECT community, weak_count, quality_type, olt
                FROM weak_light_detail
                WHERE batch_id = ? AND quality_type IS NOT NULL AND quality_type != ''
                GROUP BY community, quality_type
                ORDER BY weak_count DESC
                """,
                (batch_id,),
            ).fetchall()
        ]

        # 人员整治排行：按「对应人员」聚合本批次存量弱光（需整治户数）
        person_ranking = _build_person_ranking(conn, batch_id, person_map)

        # 持续弱光追踪（跨批次按 SN）：KPI 与入口卡共用同一份汇总
        sustained = sustained_tracking(person_map=person_map)

        # 统一使用实时口径，覆盖批次表中可能失真的历史汇总值：
        # - new_weak_cnt：与上一数据批次对比的 SN 差集
        # - sustained_cnt：跨批次持续弱光台数（报表该列在新格式中恒为 0）
        latest["new_weak_cnt"] = len(new_weaks)
        latest["sustained_cnt"] = int((sustained.get("summary") or {}).get("sustained_cnt") or 0)

        # 智能总结（结构化问题清单）：纯规则计算，供入口卡与「智能总结」面板使用
        insights = build_insights(batch_id)

        # 智能总结：优先让大模型结合历史批次经验输出，未配置/失败自动降级规则模板
        history = _recent_history(conn, batch_id, limit=4)
        ai_summary = llm_service.gen_weaklight_summary({
            "latest": latest,
            "prev_batch": prev_batch,
            "history": history,
            "communities": communities,
            "pons": pons,
            "person_ranking": person_ranking,
            "new_weaks": new_weaks,
        }) or _gen_intelligent_summary(
            latest, communities, pons, person_ranking, new_weaks, prev_batch,
        )

        return {
            "has_data": True,
            "latest": latest,
            "kpis": _build_kpis(latest, sustained.get("summary"), prev_batch),
            "sustained_summary": sustained.get("summary") or {},
            "communities": communities,
            "pons": pons,
            "new_weaks": new_weaks,
            "sustained_users": sustained_users,
            "severe_users": severe_users,
            "enterprises": enterprises,
            "stats": stats,
            "quality_cells": quality_cells,
            "community_top": communities[:10],
            "pon_top": pons[:10],
            "person_ranking": person_ranking,
            "person_map": person_map,
            "prev_batch": prev_batch,
            "new_weaks_summary": _new_weaks_summary(new_weaks),
            "overview": {
                "trend": _overview_trend(conn, latest),
                "grid": _overview_grids(conn, batch_id, person_map),
            },
            "ai_analysis": _gen_dashboard_analysis(latest, communities, pons),
            "ai_summary": ai_summary,
            "insights_summary": insights.get("summary") or {},
        }
    finally:
        conn.close()


def _build_person_ranking(conn, batch_id, person_map):
    """按对应人员聚合本批次待整治弱光，返回人员整治排行。

    口径：以「存量弱光总明细」为基准（本批次实际待整治的弱光用户），
    逐条按小区回填对应人员，统计每人名下需整治户数及其子类（持续/严重/新增）。
    """
    details = conn.execute(
        """
        SELECT gateway_sn, account, community, valley_power, sustained, is_new, quality_type
        FROM weak_light_detail WHERE batch_id = ?
        """,
        (batch_id,),
    ).fetchall()

    agg = {}
    person_phone = {}
    for r in details:
        community = r["community"] or ""
        rec = person_map.get(community)
        person = rec["person"] if rec else ""
        if not person:
            person = "未分配"
        phone = rec.get("phone", "") if rec else ""
        person_phone[person] = phone or person_phone.get(person, "")
        agg.setdefault(person, {"count": 0, "sustained": 0, "severe": 0,
                                "new": 0, "communities": set()})
        agg[person]["count"] += 1
        if r["sustained"]:
            agg[person]["sustained"] += 1
        if (r["valley_power"] or 0) < -30:
            agg[person]["severe"] += 1
        if r["is_new"]:
            agg[person]["new"] += 1
        if community:
            agg[person]["communities"].add(community)

    ranking = []
    for person, v in agg.items():
        ranking.append({
            "person": person,
            "phone": person_phone.get(person, ""),
            "count": v["count"],
            "sustained": v["sustained"],
            "severe": v["severe"],
            "new": v["new"],
            "community_cnt": len(v["communities"]),
            "communities": sorted(v["communities"])[:5],
        })
    ranking.sort(key=lambda x: x["count"], reverse=True)
    return ranking


def _new_weaks_summary(new_weaks):
    """新增弱光汇总：总数 / 未整改数 / 较上次新增数 / 涉及人员数。"""
    total = len(new_weaks)
    unfixed = sum(1 for n in new_weaks if not n.get("is_rectified"))
    new_vs_prev = sum(1 for n in new_weaks if n.get("is_new_vs_prev"))
    persons = {n.get("technician") for n in new_weaks if n.get("technician")}
    return {
        "total": total,
        "unfixed": unfixed,
        "new_vs_prev": new_vs_prev,
        "prev_existed": total - new_vs_prev,
        "person_cnt": len(persons),
    }


def _build_kpis(latest, sustained_summary=None, prev_batch=None):
    """根据批次汇总构建核心指标卡。

    sustained_summary 为跨批次持续弱光汇总；批次不足 min_batches 时
    该 KPI 显示「—」，避免用「0 户」误导（无法判定 ≠ 没有）。
    """
    weak_total = latest.get("weak_total")
    # 弱光率口径：默认取「平均弱光率」avg_rate（武汉当月平均弱光率），无则回退 weak_rate
    weak_rate = latest.get("avg_rate") if latest.get("avg_rate") is not None else latest.get("weak_rate")
    prev = latest.get("weak_total", 0)
    # 较前日变化（暂无前日数据源时置 None，前端按无变化显示）
    change = None
    poor = latest.get("poor_cell_cnt") or 0
    severe = latest.get("severe_cnt") or 0
    new_cnt = latest.get("new_weak_cnt") or 0
    prev_date = (prev_batch or {}).get("data_date") or ""

    # 持续弱光：以跨批次 SN 追踪为准（新格式报表本身无「持续弱光」标记）
    st = sustained_summary or {}
    st_batches = int(st.get("batch_cnt") or 0)
    st_min = int(st.get("min_batches") or SUSTAINED_MIN_BATCHES)
    if st_batches >= st_min:
        sus_value = int(st.get("sustained_cnt") or 0)
        sus_status = "red" if sus_value > 0 else "green"
        sus_detail = "高频未整改 %d 台 · 最长持续 %d 天" % (
            int(st.get("high_freq_cnt") or 0), int(st.get("max_span_days") or 0))
    else:
        sus_value = "—"
        sus_status = "green"
        sus_detail = "需 ≥%d 个批次（当前 %d 个）" % (st_min, st_batches)
    # 月份随数据日期动态取（如 2026-09-27 → 9月），避免硬编码
    month_label = ""
    dd = str(latest.get("data_date") or "")
    if len(dd) >= 7 and dd[5:7].isdigit():
        month_label = f"{int(dd[5:7])}月"

    kpis = [
        {
            "label": "存量弱光户数",
            "value": weak_total if weak_total is not None else "-",
            "unit": "户",
            "status": "red" if (weak_total or 0) > 0 else "green",
            "detail": "新洲区当前存量弱光",
        },
        {
            "label": "平均弱光率",
            "value": round(weak_rate * 100, 3) if weak_rate is not None else "-",
            "unit": "%",
            "status": "red" if weak_rate is not None else "green",
            "detail": f"弱光户数 / 新洲区活跃用户数({XINZHOU_ACTIVE_USERS})",
        },
        {
            "label": "持续弱光户数",
            "value": sus_value,
            "unit": "户",
            "status": sus_status,
            "detail": sus_detail,
        },
        {
            "label": "质差小区户数",
            "value": poor if poor else 0,
            "unit": "户",
            "status": "yellow" if poor > 0 else "green",
            "detail": "严重/重复/严重且重复",
        },
        {
            "label": "严重弱光户数",
            "value": severe if severe else 0,
            "unit": "户",
            "status": "red" if severe > 0 else "green",
            "detail": "谷值光功率<-30dBm",
        },
        {
            "label": f"{month_label}新增弱光" if month_label else "新增弱光",
            "value": new_cnt if new_cnt else 0,
            "unit": "台",
            "status": "yellow" if new_cnt > 0 else "green",
            "detail": (f"与上一批次（{prev_date}）对比新增网关SN"
                       if prev_date else "首次导入，无上一批次可比"),
        },
    ]
    return kpis


def _gen_dashboard_analysis(latest, communities, pons):
    """生成弱光督办 AI 分析结论。"""
    tips = []
    d = latest.get("data_date", "本期")
    avg_rate = latest.get("avg_rate") if latest.get("avg_rate") is not None else latest.get("weak_rate")
    tips.append(f"【{d} 新洲区】存量弱光 {latest.get('weak_total', 0)} 户、"
                f"平均弱光率 {round((avg_rate or 0) * 100, 3)}%，"
                f"持续弱光 {latest.get('sustained_cnt', 0)} 户，指标高于挑战值需持续督办压降。")
    if communities:
        top = communities[0]
        tips.append(f"小区集中度 TOP1：{top['community']}（{top['weak_count']} 户），"
                    f"TOP5 小区合计占比较高，建议优先集中整治。")
    if pons:
        hot = [p for p in pons if p["weak_count"] >= 3]
        if hot:
            tips.append(f"有 {len(hot)} 个 PON 口弱光数≥3 户（可能分光器/主干光缆问题），"
                        f"最集中为 {hot[0]['pon']}（{hot[0]['weak_count']} 户）。")
        else:
            tips.append("当前无 PON 口弱光数达到 3 户预警线。")
    return tips


def _gen_intelligent_summary(latest, communities, pons, person_ranking, new_weaks, prev_batch):
    """生成弱光督办「智能总结」（自然语言，供前端在数据日期旁展示）。

    输出结构化字段：
      - title        : 一句话概括当前整体情况
      - trend        : 较上次上传的存量弱光变化（上升/下降/持平）
      - problems     : 问题所在（自然语言清单）
      - focus_person : 片区弱光最集中的人员（含重点小区），及其整治重点
      - priority     : 集中整治优先级排序（自然语言）
    """
    d = latest.get("data_date") or "本期"
    weak_total = latest.get("weak_total") or 0
    avg_rate = latest.get("avg_rate") if latest.get("avg_rate") is not None else latest.get("weak_rate")
    rate_pct = round((avg_rate or 0) * 100, 3)
    sustained = latest.get("sustained_cnt") or 0
    severe = latest.get("severe_cnt") or 0
    new_cnt = latest.get("new_weak_cnt") or 0

    # ---- 1) 整体情况 ----
    trend_txt = ""
    if prev_batch and prev_batch.get("weak_total") is not None:
        prev_total = prev_batch["weak_total"]
        delta = (weak_total or 0) - prev_total
        if delta > 0:
            trend_txt = f"较上次（{prev_batch.get('data_date')}）回升 {delta} 户，须警惕反弹"
        elif delta < 0:
            trend_txt = f"较上次（{prev_batch.get('data_date')}）压降 {abs(delta)} 户，治理初见成效"
        else:
            trend_txt = f"较上次（{prev_batch.get('data_date')}）持平"
    title = (f"【{d}】新洲区存量弱光 {weak_total} 户、平均弱光率 {rate_pct}%，"
             f"持续 {sustained} 户、严重 {severe} 户、本月新增 {new_cnt} 台。{trend_txt}".rstrip("。") + "。")

    # ---- 2) 问题所在 ----
    problems = []
    # 小区集中
    if communities:
        top_c = communities[0]
        # 累计 TOP3 弱光数占总量比例
        top3_sum = sum(c["weak_count"] for c in communities[:3])
        ratio = round(top3_sum / weak_total * 100, 1) if weak_total else 0
        problems.append(f"小区集中度高：TOP1「{top_c['community']}」弱光 {top_c['weak_count']} 户，"
                        f"TOP3 小区合计 {top3_sum} 户、占存量 {ratio}%，建议按小区集中整治。")
    # PON 集中
    hot_pons = [p for p in pons if p["weak_count"] >= 3]
    if hot_pons:
        top_p = hot_pons[0]
        problems.append(f"存在 {len(hot_pons)} 个热点 PON 口（弱光≥3户），最集中「{short_pon(top_p.get('pon'))}」"
                        f"关联 {top_p.get('weak_count')} 户（{top_p.get('community') or '多小区'}），"
                        f"疑似分光器/主干光缆质差，建议优先核查。")
    # 持续 / 严重
    if sustained:
        problems.append(f"持续弱光 {sustained} 户长期未闭环，属顽固性问题，需逐户攻坚销号。")
    if severe:
        problems.append(f"严重弱光 {severe} 户（谷值<-30dBm），光衰过大，影响用户感知，建议优先上门处置。")
    # 新增
    if new_cnt:
        problems.append(f"本月新增弱光 {new_cnt} 台，存在边整改边新增现象，需前移装维调测质量管控。")

    # ---- 3) 谁的片区多（按对应人员聚合） ----
    focus_person = ""
    if person_ranking:
        top_person = person_ranking[0]
        ck = "、".join(top_person.get("communities", [])[:2]) or "多小区"
        focus_person = (f"片区弱光最集中人员：{top_person['person']}"
                        f"{'（' + top_person.get('phone', '') + '）' if top_person.get('phone') else ''}"
                        f"，名下待整治 {top_person['count']} 户（持续 {top_person.get('sustained', 0)}、"
                        f"严重 {top_person.get('severe', 0)}、新增 {top_person.get('new', 0)}），"
                        f"重点片区为「{ck}」，应列为第一整改责任人。")

    # ---- 4) 集中整治优先级 ----
    priority = _gen_priority(person_ranking, communities, pons, new_weaks)
    if not priority:
        priority = "当前存量弱光治理平稳，建议保持台账跟踪、固化整治标准，防止反弹。"

    return {
        "title": title,
        "trend": trend_txt,
        "problems": problems,
        "focus_person": focus_person,
        "priority": priority,
    }


def short_pon(pon):
    """PON 口名简写（与前端 shortPon 对齐），无则返回原文。"""
    if not pon:
        return ""
    s = str(pon)
    # 取 OLT 名（如 武汉/新洲区/双柳-OLT003-...）简写为 双柳-OLT003，再加 框/槽/端口
    m = re.search(r"/([^/]+?)-(OLT\d+)", s)
    olt = f"{m.group(1)}-{m.group(2)}" if m else s[-30:]
    parts = s.split("_")
    pos = parts[1] if len(parts) > 1 else ""
    return f"{olt} {pos}".strip()


def _gen_priority(person_ranking, communities, pons, new_weaks):
    """按「影响户数 × 严重程度」给出集中整治优先级排序（自然语言，序号自动连续）。"""
    lines = []

    # 1) 严重弱光优先：基于 person_ranking，severe 数量多的人员优先
    person_hot = [p for p in person_ranking if p.get("severe") or p.get("sustained")]
    person_hot.sort(key=lambda p: (p.get("severe", 0), p.get("sustained", 0)), reverse=True)
    if person_hot:
        top = person_hot[0]
        lines.append(f"优先整治「{top['person']}」片区：严重 {top.get('severe', 0)} 户、持续 {top.get('sustained', 0)} 户，"
                     f"合计 {top.get('count', 0)} 户，投入产出最高，建议今日派单。")

    # 2) 新增未整改且弱光天数长的
    urgent_new = [n for n in new_weaks if not n.get("is_rectified") and (n.get("weak_days") or 0) > 7]
    if urgent_new:
        top_new = urgent_new[0]
        lines.append(f"新增弱光中「{top_new.get('community') or '—'}」弱光 {top_new.get('weak_days')} 天未整改"
                     f"{'（对应 ' + top_new.get('technician', '') + '）' if top_new.get('technician') else ''}，"
                     f"超期风险高，需限期清零。")

    # 3) 热点 PON 集中整治
    hot_pons = [p for p in pons if p["weak_count"] >= 3]
    if hot_pons:
        top_p = hot_pons[0]
        lines.append(f"热点 PON「{short_pon(top_p.get('pon'))}」（{top_p.get('weak_count')} 户，"
                     f"{top_p.get('community') or '多小区'}）集中攻坚，可一次解决多户。")

    # 4) 高集中度小区
    if communities and communities[0].get("weak_count") >= 5:
        top_c = communities[0]
        lines.append(f"集中整治「{top_c['community']}」等 TOP 小区，"
                     f"对应人员「{top_c.get('technician') or '—'}」，按小区整片推进。")

    # 自动连续编号
    circled = "①②③④⑤⑥⑦⑧⑨⑩"
    if not lines:
        return ""
    return "；".join(f"{circled[i]} {ln}" for i, ln in enumerate(lines))


# ---------------------------------------------------------------------------
# 读取：历史批次列表 / 指定批次
# ---------------------------------------------------------------------------
def weak_light_batches():
    """返回全部历史批次列表（供切换查看）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, filename, data_date, weak_total, weak_rate, avg_rate, sustained_cnt,
                   upload_date, created_at
            FROM weak_light_upload
            ORDER BY created_at DESC
            """
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["avg_rate"] = _resolve_avg_rate(conn, d["id"], d.get("avg_rate"))
            out.append(d)
        return out
    finally:
        conn.close()


def weak_light_batch_detail(batch_id):
    """读取指定批次的完整数据（历史数据不变，可切换查看）。"""
    conn = get_conn()
    try:
        batch = conn.execute(
            """
            SELECT id, filename, data_date, weak_total, weak_rate, avg_rate, sustained_cnt,
                   poor_cell_cnt, severe_cnt, pon_cnt, new_weak_cnt, upload_date, created_at
            FROM weak_light_upload WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            return {"ok": False, "error": "批次不存在"}
        batch = dict(batch)
        batch["avg_rate"] = _resolve_avg_rate(conn, batch_id, batch.get("avg_rate"))

        def _all(sql):
            return [dict(r) for r in conn.execute(sql, (batch_id,)).fetchall()]

        person_map = get_person_map()
        def _rp(community, fallback=""):
            rec = person_map.get(community or "")
            if rec and rec["person"]:
                return rec["person"]
            if fallback:
                return _normalize_person(fallback)
            return ""

        communities = _all("SELECT community, weak_count, prev_count, change_val, quality_type FROM weak_light_community WHERE batch_id = ? ORDER BY weak_count DESC")
        for c in communities:
            c["technician"] = _rp(c.get("community"))
        # 新增弱光：与首页一致，按网关SN 对比上一数据批次实时判定
        prev_batch, prev_sns = _prev_batch_and_sns(conn, batch_id)
        new_weaks = _collect_new_weaks(conn, batch_id, prev_sns, _rp)
        batch["new_weak_cnt"] = len(new_weaks)
        sustained_users = _all("SELECT gateway_sn, account, community, valley_power, peak_power, olt, onu, quality_type FROM weak_light_detail WHERE batch_id = ? AND sustained = 1 ORDER BY valley_power ASC")
        for s in sustained_users:
            s["technician"] = _rp(s.get("community"))
        severe_users = _all("SELECT gateway_sn, account, community, valley_power, peak_power, olt, pon, onu, sustained, quality_type FROM weak_light_detail WHERE batch_id = ? AND valley_power < -30 ORDER BY valley_power ASC")
        for s in severe_users:
            s["technician"] = _rp(s.get("community"))

        return {
            "ok": True,
            "batch": batch,
            "prev_batch": prev_batch,
            "communities": communities,
            "pons": _all("SELECT pon, weak_count, prev_count, change_val, community, weak_mark, quality_type FROM weak_light_pon WHERE batch_id = ? ORDER BY weak_count DESC"),
            "new_weaks": new_weaks,
            "sustained_users": sustained_users,
            "severe_users": severe_users,
            "enterprises": _all("SELECT gateway_sn, account, community, valley_power, peak_power, olt, pon, onu FROM weak_light_enterprise WHERE batch_id = ? ORDER BY valley_power ASC"),
            "stats": _all("SELECT district, weak_count, weak_rate, prev_count, active_users, change_count, change_rate, avg_rate FROM weak_light_stat WHERE batch_id = ? ORDER BY weak_rate DESC"),
            "person_ranking": _build_person_ranking(conn, batch_id, person_map),
            "person_map": person_map,
            "new_weaks_summary": _new_weaks_summary(new_weaks),
        }
    finally:
        conn.close()
