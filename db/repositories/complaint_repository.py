# -*- coding: utf-8 -*-
"""
投诉/重复投诉模块数据访问对象（Repository）。

职责：
- 封装 complaint_upload / complaint_upload_district / complaint_daily_detail
  三张表的所有读写逻辑；
- 为路由层与业务服务层提供高阶查询接口；
- 不直接处理 HTTP 请求或 Excel 解析。
"""
from datetime import datetime

from db import get_conn


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _status(v, min_ok=None, max_ok=None, warn_min=None, warn_max=None, good_is_high=True):
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


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def save_complaint_report(res, filename):
    """把解析后的报表结果写入数据库（批次 + 分区 + 每日明细）。"""
    conn = get_conn()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        stat_month = res.get("stat_month") or datetime.now().strftime("%Y-%m")
        city = res.get("city", {})
        period = res.get("period", {})

        cur = conn.execute(
            """
            INSERT INTO complaint_upload
              (filename, upload_date, stat_month, city_users, city_orders,
               city_rate, period_start, period_end, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                period.get("start") or now,
                stat_month,
                city.get("repeat_users"),
                city.get("total_orders"),
                city.get("repeat_rate"),
                period.get("start"),
                period.get("end"),
                now,
            ),
        )
        batch_id = cur.lastrowid

        # 武汉各区汇总
        wuhan_districts = res.get("wuhan_districts", [])
        for d in wuhan_districts:
            conn.execute(
                """
                INSERT INTO complaint_upload_district
                  (batch_id, district, repeat_users, total_orders, repeat_rate, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    d.get("district"),
                    d.get("repeat_users"),
                    d.get("total_orders"),
                    d.get("repeat_rate"),
                    now,
                ),
            )

        # 每日明细（新洲区重点关注）
        daily_details = res.get("daily_details", [])
        for row in daily_details:
            conn.execute(
                """
                INSERT OR IGNORE INTO complaint_daily_detail
                  (batch_id, stat_date, district, complaint_count, repeat_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    row.get("stat_date"),
                    row.get("district"),
                    row.get("complaint_count", 0),
                    row.get("repeat_count", 0),
                ),
            )

        conn.commit()
        return batch_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 读取：最新批次
# ---------------------------------------------------------------------------
def latest_complaint_report():
    """返回最近一次上传的批次汇总。"""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT id, filename, upload_date, stat_month, city_users,
                   city_orders, city_rate, period_start, period_end
            FROM complaint_upload
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        latest = dict(row)
        districts = conn.execute(
            """
            SELECT district, repeat_users, total_orders, repeat_rate
            FROM complaint_upload_district
            WHERE batch_id = ?
            ORDER BY repeat_rate DESC
            """,
            (row["id"],),
        ).fetchall()
        latest["districts"] = [dict(d) for d in districts]
        return latest
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 读取：按月汇总（核心接口，供 /api/complaint_chart 使用）
# ---------------------------------------------------------------------------
def complaint_month_summary(month=None):
    """按月累计汇总：本月批次数、每日新增、最新整体与各区明细、历史批次列表。"""
    conn = get_conn()
    try:
        if not month:
            month = datetime.now().strftime("%Y-%m")

        # 1) 当月所有批次
        batches = conn.execute(
            """
            SELECT id, filename, upload_date, stat_month, city_users,
                   city_orders, city_rate, period_start, period_end
            FROM complaint_upload
            WHERE stat_month = ?
            ORDER BY created_at DESC
            """,
            (month,),
        ).fetchall()

        # 2) 最新批次详情
        latest = None
        if batches:
            latest = dict(batches[0])
            districts = conn.execute(
                """
                SELECT district, repeat_users, total_orders, repeat_rate
                FROM complaint_upload_district
                WHERE batch_id = ?
                ORDER BY repeat_rate DESC
                """,
                (latest["id"],),
            ).fetchall()
            latest["districts"] = [dict(d) for d in districts]

        # 3) 每日新增批次（保留字段，前端如需展示仍可用）
        daily_new = []
        for b in batches:
            d = dict(b)
            d["districts"] = []
            daily_new.append(d)

        # 4) 历史月份列表 + 全部批次（供下拉跨月切换）
        history_months = [
            r["stat_month"]
            for r in conn.execute(
                """
                SELECT DISTINCT stat_month FROM complaint_upload
                ORDER BY stat_month DESC
                """
            ).fetchall()
        ]
        all_batches = [
            dict(r) for r in conn.execute(
                """
                SELECT id, filename, upload_date, stat_month, city_users,
                       city_orders, city_rate, period_start, period_end
                FROM complaint_upload
                ORDER BY created_at DESC
                """
            ).fetchall()
        ]

        # 5) 各区每日趋势（按明细表聚合，供前端按区县动态切换）
        district_daily = {}
        for district in _districts_with_daily(conn, month):
            district_daily[district] = _district_daily_trend(conn, month, district)

        return {
            "month": month,
            "has_data": len(batches) > 0,
            "batch_count": len(batches),
            "daily_new": daily_new,
            "latest": latest,
            "history": history_months,
            "all_batches": all_batches,
            # 兼容旧字段名（前端可能仍引用）
            "xinzhou_daily": district_daily.get("新洲区", []),
            "district_daily": district_daily,
            # 当前月有每日明细的区县清单（用于动态选择下拉）
            "daily_districts": sorted(district_daily.keys()),
        }
    finally:
        conn.close()


def _districts_with_daily(conn, month):
    """返回指定月份在每日明细表中有数据的区县清单。"""
    rows = conn.execute(
        """
        SELECT DISTINCT d.district
        FROM complaint_daily_detail d
        JOIN complaint_upload u ON u.id = d.batch_id
        WHERE u.stat_month = ?
        ORDER BY d.district
        """,
        (month,),
    ).fetchall()
    return [r["district"] for r in rows]


def _district_daily_trend(conn, month, district):
    """按月聚合 complaint_daily_detail，返回指定区县每日投诉量与重复量。"""
    rows = conn.execute(
        """
        SELECT d.stat_date,
               SUM(d.complaint_count) AS complaint_count,
               SUM(d.repeat_count)    AS repeat_count
        FROM complaint_daily_detail d
        JOIN complaint_upload u ON u.id = d.batch_id
        WHERE u.stat_month = ? AND d.district = ?
        GROUP BY d.stat_date
        ORDER BY d.stat_date
        """,
        (month, district),
    ).fetchall()

    return [
        {
            "date": r["stat_date"],
            "complaint_count": int(r["complaint_count"] or 0),
            "repeat_count": int(r["repeat_count"] or 0),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 读取：指定批次明细
# ---------------------------------------------------------------------------
def complaint_batch_detail(batch_id):
    """读取指定批次的完整明细（数据不变，可切换查看任意历史批次）。"""
    conn = get_conn()
    try:
        batch = conn.execute(
            """
            SELECT id, filename, upload_date, stat_month, city_users,
                   city_orders, city_rate, period_start, period_end
            FROM complaint_upload
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            return {"ok": False, "error": "批次不存在"}

        batch = dict(batch)
        districts = conn.execute(
            """
            SELECT district, repeat_users, total_orders, repeat_rate
            FROM complaint_upload_district
            WHERE batch_id = ?
            ORDER BY repeat_rate DESC
            """,
            (batch_id,),
        ).fetchall()
        batch["districts"] = [dict(d) for d in districts]

        daily = conn.execute(
            """
            SELECT stat_date, district, complaint_count, repeat_count
            FROM complaint_daily_detail
            WHERE batch_id = ?
            ORDER BY stat_date, district
            """,
            (batch_id,),
        ).fetchall()
        batch["daily_details"] = [dict(d) for d in daily]

        return {"ok": True, "batch": batch}
    finally:
        conn.close()
