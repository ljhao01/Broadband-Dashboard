# -*- coding: utf-8 -*-
"""
弱光督办模块数据访问对象（Repository）。

职责：
- 封装 weak_light_upload / weak_light_detail / weak_light_community /
  weak_light_pon / weak_light_new / weak_light_enterprise / weak_light_stat
  七张表的读写逻辑；
- 为路由层与业务服务层提供高阶查询接口；
- 不直接处理 HTTP 请求或 Excel 解析。
"""
import json
import re
from datetime import datetime

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
            is_new = bool(sn) and sn not in prev_sns
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
# 人员映射（小区/网格 → 对应装维人员）
# ---------------------------------------------------------------------------
def save_person_map(res, filename=""):
    """把《人员录》解析结果落库（全量覆盖式更新人员映射）。"""
    conn = get_conn()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        upload_date = datetime.now().strftime("%Y-%m-%d")
        conn.execute("DELETE FROM weak_light_person")  # 人员映射每次全量覆盖
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
                    filename or res.get("filename", ""), community, person,
                    grid_map.get(person, ""), phone_map.get(person, ""),
                    emp_map.get(person, ""), upload_date, now,
                ),
            )
        conn.commit()
        return {"ok": True, "count": len(community_map), "personnel": len(personnel)}
    finally:
        conn.close()


def get_person_map():
    """返回小区→人员 映射字典 {community: {person, grid, phone}}。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT community, person, grid, phone, emp_no FROM weak_light_person"
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
    prev = conn.execute(
        """
        SELECT id, data_date FROM weak_light_upload
        WHERE id < ? ORDER BY id DESC LIMIT 1
        """,
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


def _mark_new_vs_prev(conn, new_weaks, batch_id):
    """按网关SN 为「新增弱光」列表逐条打上 较上次新增/上次已有 标记。

    - 返回 (new_weaks, prev_batch)；
    - 每条 new_weak 增加 is_new_vs_prev / prev_existed 字段：
      网关SN 不在上一批次存量明细 → 新增；在 → 上次已有；无网关SN → 均 False。
    """
    prev_batch, prev_sns = _prev_batch_and_sns(conn, batch_id)
    for n in new_weaks:
        sn = n.get("gateway_sn")
        n["is_new_vs_prev"] = bool(sn) and sn not in prev_sns
        n["prev_existed"] = bool(sn) and sn in prev_sns
    return new_weaks, prev_batch


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
                    "prev_batch": None, "new_weaks_summary": {}}
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

        # 新增弱光（回填对应人员 + 较上一批次对比）
        new_weaks = [
            dict(r) for r in conn.execute(
                """
                SELECT weak_days, rectification, weak_date, install_date, gateway_sn,
                       account, mac, active_count, valley_power, peak_power, weak_count,
                       community, olt, pon, onu, technician, technician_no, is_rectified
                FROM weak_light_new WHERE batch_id = ?
                ORDER BY is_rectified ASC, weak_days DESC
                """,
                (batch_id,),
            ).fetchall()
        ]
        for n in new_weaks:
            n["technician"] = _resolve_person(n.get("community"), n.get("technician"))
        # 按网关SN 对比上一批次，标记「较上次新增 / 上次已有」
        new_weaks, prev_batch = _mark_new_vs_prev(conn, new_weaks, batch_id)

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
            "kpis": _build_kpis(latest),
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
            "ai_analysis": _gen_dashboard_analysis(latest, communities, pons),
            "ai_summary": ai_summary,
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


def _build_kpis(latest):
    """根据批次汇总构建核心指标卡。"""
    weak_total = latest.get("weak_total")
    # 弱光率口径：默认取「平均弱光率」avg_rate（武汉8月平均弱光率），无则回退 weak_rate
    weak_rate = latest.get("avg_rate") if latest.get("avg_rate") is not None else latest.get("weak_rate")
    prev = latest.get("weak_total", 0)
    # 较前日变化（暂无前日数据源时置 None，前端按无变化显示）
    change = None
    sustained = latest.get("sustained_cnt") or 0
    poor = latest.get("poor_cell_cnt") or 0
    severe = latest.get("severe_cnt") or 0
    new_cnt = latest.get("new_weak_cnt") or 0

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
            "detail": "武汉8月平均弱光率口径，高于挑战值需督办",
        },
        {
            "label": "持续弱光户数",
            "value": sustained if sustained else 0,
            "unit": "户",
            "status": "red" if sustained > 0 else "green",
            "detail": "长期未解决重点督办",
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
            "label": "8月新增弱光",
            "value": new_cnt if new_cnt else 0,
            "unit": "台",
            "status": "yellow" if new_cnt > 0 else "green",
            "detail": "本月新增弱光设备",
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
        new_weaks = _all("SELECT weak_days, rectification, weak_date, install_date, gateway_sn, account, mac, active_count, valley_power, peak_power, weak_count, community, olt, pon, onu, technician, technician_no, is_rectified FROM weak_light_new WHERE batch_id = ? ORDER BY is_rectified ASC, weak_days DESC")
        for n in new_weaks:
            n["technician"] = _rp(n.get("community"), n.get("technician"))
        # 按网关SN 对比上一批次，标记「较上次新增 / 上次已有」
        new_weaks, prev_batch = _mark_new_vs_prev(conn, new_weaks, batch_id)
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
