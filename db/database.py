# -*- coding: utf-8 -*-
"""
数据库模块：SQLite 初始化 + 种子数据
六大专项看板对应数据表 + 用户权限表 + 阈值配置表 + 报表上传表
"""
import os
import sqlite3
from datetime import datetime, timedelta

from config import DB_PATH


def get_conn():
    """获取数据库连接（返回带 row 工厂的字典游标）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --------------------------------------------------------------------------
# Schema 定义
# --------------------------------------------------------------------------
SCHEMA = """
-- 用户表（多账号、分权限）
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,          -- 演示用明文；生产环境应加密
    role TEXT NOT NULL DEFAULT 'viewer',   -- admin / manager / viewer
    display_name TEXT NOT NULL
);

-- 阈值配置表（AI 智能阈值预警，可自定义）
CREATE TABLE IF NOT EXISTS thresholds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator TEXT UNIQUE NOT NULL,   -- 指标 key
    label TEXT NOT NULL,              -- 指标名称
    min_ok REAL,                      -- 达标下限
    max_ok REAL,                      -- 达标上限
    warn_min REAL,                    -- 预警下限
    warn_max REAL,                    -- 预警上限
    good_is_high INTEGER DEFAULT 1    -- 1=数值越高越好，0=越低越好
);

-- ================= 1. 装维工单 =================
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT UNIQUE NOT NULL,
    grid TEXT NOT NULL,              -- 网格
    address TEXT NOT NULL,
    create_time TEXT NOT NULL,
    status TEXT NOT NULL,            -- processing / done / overtime
    overtime_hours REAL DEFAULT 0,
    team TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_order_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT UNIQUE NOT NULL,
    accepted INTEGER NOT NULL,       -- 受理量
    closed INTEGER NOT NULL,         -- 办结量
    timely_rate REAL NOT NULL,       -- 及时率 %
    refund_rate REAL NOT NULL,       -- 退单率 %
    rework_rate REAL NOT NULL        -- 返工率 %
);

-- 网格效能
CREATE TABLE IF NOT EXISTS grid_eff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grid TEXT UNIQUE NOT NULL,
    eff REAL NOT NULL                -- 效能 %
);

-- ================= 2. FTTR =================
CREATE TABLE IF NOT EXISTS fttr_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT UNIQUE NOT NULL,
    success_rate REAL NOT NULL,      -- 连接成功率 %
    fail_freq INTEGER NOT NULL,      -- 失败频次
    dropout_rate REAL NOT NULL       -- 掉线率 %
);

CREATE TABLE IF NOT EXISTS fttr_area (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area TEXT UNIQUE NOT NULL,
    score REAL NOT NULL,             -- 区域质量分
    issue TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fttr_abnormal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_addr TEXT NOT NULL,
    issue TEXT NOT NULL,
    cnt INTEGER NOT NULL,
    level TEXT NOT NULL              -- danger / warn / ok
);

-- ================= 3. 千兆质差小区 =================
CREATE TABLE IF NOT EXISTS gigabit_cells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cell TEXT UNIQUE NOT NULL,
    latency REAL NOT NULL,           -- 时延 ms
    jitter REAL NOT NULL,            -- 抖动 ms
    low_speed_users INTEGER NOT NULL,-- 速率不达标用户
    repair_status TEXT NOT NULL,     -- 已修复 / 整治中 / 未修复
    progress REAL NOT NULL           -- 整改进度 %
);

CREATE TABLE IF NOT EXISTS gigabit_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT UNIQUE NOT NULL,
    total_cells INTEGER NOT NULL,
    poor_cells INTEGER NOT NULL,
    qualify_rate REAL NOT NULL       -- 测速合格率 %
);

-- ================= 4. 重复投诉 =================
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no TEXT UNIQUE NOT NULL,
    area TEXT NOT NULL,
    problem TEXT NOT NULL,
    days_overdue INTEGER DEFAULT 0,
    team TEXT NOT NULL,
    status TEXT NOT NULL             -- 超时 / 临期 / 正常
);

CREATE TABLE IF NOT EXISTS complaint_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT UNIQUE NOT NULL,
    total INTEGER NOT NULL,
    repeat_cnt INTEGER NOT NULL,
    closed_rate REAL NOT NULL        -- 销号率 %
);

-- 上传报表批次（每次上传一条主记录，永久留存、不变）
CREATE TABLE IF NOT EXISTS complaint_upload (
    id INTEGER PRIMARY KEY AUTOINCREMENT,   -- 即 batch_id
    filename TEXT NOT NULL,
    report_date TEXT,                       -- 报表日期
    period_start TEXT,                      -- 数据开始日期
    period_end TEXT,                        -- 数据结束日期
    city_rate REAL,                         -- 武汉整体重复投诉率
    city_users INTEGER,                     -- 武汉整体重复投诉用户
    city_orders INTEGER,                    -- 武汉整体投诉工单
    upload_date TEXT NOT NULL,              -- 上传日期(YYYY-MM-DD)，用于"每日新增"统计
    stat_month TEXT NOT NULL,               -- 账期月份(YYYY-MM)，用于"每月清零"隔离
    created_at TEXT NOT NULL
);

-- 上传报表批次明细（每个武汉区县/功能区一行）
CREATE TABLE IF NOT EXISTS complaint_upload_district (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    district TEXT NOT NULL,
    repeat_users INTEGER DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    repeat_rate REAL DEFAULT 0
);

-- ================= 5. 用户满意度 =================
CREATE TABLE IF NOT EXISTS satisfaction_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT UNIQUE NOT NULL,
    score REAL NOT NULL,             -- 满意度得分
    good_rate REAL NOT NULL,         -- 好评率 %
    bad_rate REAL NOT NULL           -- 差评率 %
);

CREATE TABLE IF NOT EXISTS satisfaction_cat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT UNIQUE NOT NULL,
    cnt INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS satisfaction_team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team TEXT UNIQUE NOT NULL,
    score REAL NOT NULL
);

-- ================= 6. 三类问题终端 =================
CREATE TABLE IF NOT EXISTS terminals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sn TEXT UNIQUE NOT NULL,
    area TEXT NOT NULL,
    problem_type TEXT NOT NULL,      -- 在线异常 / 故障终端 / 待替换
    days_overdue INTEGER DEFAULT 0,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS terminal_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT UNIQUE NOT NULL,
    stock INTEGER NOT NULL,          -- 存量
    abnormal INTEGER NOT NULL,       -- 在线异常
    fixed_rate REAL NOT NULL         -- 整改完成率 %
);
"""


# --------------------------------------------------------------------------
# 种子数据
# --------------------------------------------------------------------------
def _seed_users(conn):
    conn.execute("INSERT OR IGNORE INTO users (username,password,role,display_name) VALUES (?,?,?,?)",
                 ("admin", "admin123", "admin", "系统管理员"))
    conn.execute("INSERT OR IGNORE INTO users (username,password,role,display_name) VALUES (?,?,?,?)",
                 ("manager", "123456", "manager", "业务主管"))
    conn.execute("INSERT OR IGNORE INTO users (username,password,role,display_name) VALUES (?,?,?,?)",
                 ("viewer", "123456", "viewer", "普通查看员"))


def _seed_thresholds(conn):
    rows = [
        ("wo_timely_rate", "工单及时率", 95, 100, 92, 95, 1),
        ("wo_complete_rate", "工单办结率", 95, 100, 92, 95, 1),
        ("wo_refund_rate", "工单退单率", None, 6, 6, 8, 0),
        ("wo_rework_rate", "工单返工率", None, 5, 5, 8, 0),
        ("fttr_success_rate", "FTTR连接成功率", 96, 100, 93, 96, 1),
        ("fttr_dropout_rate", "FTTR掉线率", None, 3, 3, 5, 0),
        ("giga_poor_ratio", "千兆质差小区占比", None, 15, 15, 20, 0),
        ("giga_qualify_rate", "千兆测速合格率", 92, 100, 88, 92, 1),
        ("cp_repeat_ratio", "重复投诉占比", None, 15, 15, 20, 0),
        ("cp_closed_rate", "投诉销号率", 90, 100, 85, 90, 1),
        ("sat_score", "满意度得分", 90, 100, 85, 90, 1),
        ("sat_bad_rate", "差评率", None, 5, 5, 8, 0),
        ("term_fixed_rate", "终端整改完成率", 80, 100, 70, 80, 1),
    ]
    for r in rows:
        conn.execute("INSERT OR IGNORE INTO thresholds "
                     "(indicator,label,min_ok,max_ok,warn_min,warn_max,good_is_high) "
                     "VALUES (?,?,?,?,?,?,?)", r)


def _seed_work_orders(conn):
    # 日统计（近14天）
    conn.execute("DELETE FROM work_order_daily")
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        accepted = 2000 - i * 5
        closed = int(accepted * (0.93 - i * 0.001))
        conn.execute("INSERT OR IGNORE INTO work_order_daily "
                     "(stat_date,accepted,closed,timely_rate,refund_rate,rework_rate) "
                     "VALUES (?,?,?,?,?,?)",
                     (d, accepted, closed, round(94.5 - i * 0.15 + (i % 3), 1),
                      round(4.5 + i * 0.1, 1), round(3.8 + i * 0.05, 1)))
    conn.execute("DELETE FROM grid_eff")
    for g, e in [("城东网格", 98.2), ("城西网格", 95.4), ("城南网格", 91.0),
                 ("城北网格", 87.6), ("高新网格", 82.3)]:
        conn.execute("INSERT INTO grid_eff (grid,eff) VALUES (?,?)", (g, e))
    conn.execute("DELETE FROM work_orders")
    samples = [
        ("GD20260810-0382", "高新网格", "高新区·阳光里 3 栋", 12.5, "processing", "overtime"),
        ("GD20260810-0419", "城北网格", "城北·幸福家园 12 栋", 9.8, "processing", "overtime"),
        ("GD20260810-0456", "城南网格", "城南·锦绣花园 7 栋", 6.2, "processing", "overtime"),
        ("GD20260810-0471", "城东网格", "城东·江畔名居 5 栋", 5.1, "processing", "overtime"),
        ("GD20260810-0490", "城西网格", "城西·梧桐苑 9 栋", 3.4, "processing", "overtime"),
        ("GD20260810-0512", "高新网格", "高新区·云栖小镇 8 栋", 0, "done", None),
        ("GD20260810-0513", "城南网格", "城南·金桂花园 2 栋", 0, "done", None),
    ]
    grid_names = ["高新", "城北", "城南", "城东", "城西"]
    for no, grid, addr, ot, status, st in samples:
        team = grid_names[grid_names.index(grid[0:2])] + "装维班"
        conn.execute("INSERT INTO work_orders "
                     "(order_no,grid,address,create_time,status,overtime_hours,team) "
                     "VALUES (?,?,?,?,?,?,?)",
                     (no, grid, addr,
                      (datetime.now() - timedelta(hours=int(ot) + 2)).strftime("%Y-%m-%d %H:%M"),
                      status, ot, team))


def _seed_fttr(conn):
    conn.execute("DELETE FROM fttr_daily")
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO fttr_daily "
                     "(stat_date,success_rate,fail_freq,dropout_rate) VALUES (?,?,?,?)",
                     (d, round(95.8 - i * 0.2 + (i % 2) * 0.8, 1),
                      int(220 + i * 15 - (i % 3) * 20), round(2.4 + i * 0.1, 1)))
    conn.execute("DELETE FROM fttr_area")
    for a, s, i in [("高新区·阳光里", 99.1, ""), ("城东·江畔名居", 97.8, ""),
                    ("城西·梧桐苑", 94.2, "晚高峰连接不稳定"),
                    ("城南·锦绣花园", 89.5, "信号弱"),
                    ("城北·幸福家园", 86.3, "频繁掉线")]:
        conn.execute("INSERT INTO fttr_area (area,score,issue) VALUES (?,?,?)", (a, s, i))
    conn.execute("DELETE FROM fttr_abnormal")
    for u, i, c, l in [("高新·阳光里 3-2-601", "频繁掉线", 23, "danger"),
                       ("城北·幸福家园 12-1-303", "连接不稳定", 17, "danger"),
                       ("城南·锦绣花园 7-3-1202", "信号弱", 12, "warn"),
                       ("城西·梧桐苑 9-2-804", "速率低", 8, "warn"),
                       ("城东·江畔名居 5-1-502", "偶发掉线", 5, "ok")]:
        conn.execute("INSERT INTO fttr_abnormal (user_addr,issue,cnt,level) VALUES (?,?,?,?)",
                     (u, i, c, l))


def _seed_gigabit(conn):
    conn.execute("DELETE FROM gigabit_cells")
    for c, la, ji, lu, st, p in [
        ("锦绣花园", 38, 22, 320, "整治中", 60),
        ("幸福家园", 35, 19, 280, "未修复", 20),
        ("梧桐苑", 28, 14, 150, "已修复", 100),
        ("丽景湾", 25, 12, 120, "整治中", 45),
        ("阳光里", 18, 9, 60, "已修复", 100),
        ("江畔名居", 15, 7, 40, "已修复", 100),
    ]:
        conn.execute("INSERT INTO gigabit_cells "
                     "(cell,latency,jitter,low_speed_users,repair_status,progress) "
                     "VALUES (?,?,?,?,?,?)", (c, la, ji, lu, st, p))
    conn.execute("DELETE FROM gigabit_daily")
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO gigabit_daily "
                     "(stat_date,total_cells,poor_cells,qualify_rate) VALUES (?,?,?,?)",
                     (d, 380, int(55 + i * 2 - (i % 2) * 5), round(92 - i * 0.2 + (i % 3) * 0.6, 1)))


def _seed_complaints(conn):
    conn.execute("DELETE FROM complaints")
    for t, a, p, d, tm, s in [
        ("TS20260805-221", "城北·幸福家园", "宽带频繁掉线", 6, "城北装维班", "超时"),
        ("TS20260806-309", "城南·锦绣花园", "网速不达标", 4, "城南装维班", "临期"),
        ("TS20260807-418", "高新·阳光里", "FTTR覆盖差", 3, "高新装维班", "临期"),
        ("TS20260808-502", "城西·梧桐苑", "装维响应慢", 2, "城西装维班", "临期"),
        ("TS20260809-510", "城东·江畔名居", "账单争议", 0, "城东装维班", "正常"),
    ]:
        conn.execute("INSERT INTO complaints "
                     "(ticket_no,area,problem,days_overdue,team,status) VALUES (?,?,?,?,?,?)",
                     (t, a, p, d, tm, s))
    conn.execute("DELETE FROM complaint_daily")
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO complaint_daily "
                     "(stat_date,total,repeat_cnt,closed_rate) VALUES (?,?,?,?)",
                     (d, 520 - i * 8, int(90 + i * 4 - (i % 3) * 6), round(80 + i * 0.6, 1)))


def _seed_satisfaction(conn):
    conn.execute("DELETE FROM satisfaction_daily")
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO satisfaction_daily "
                     "(stat_date,score,good_rate,bad_rate) VALUES (?,?,?,?)",
                     (d, round(89.5 + i * 0.3, 1), round(91 + i * 0.4, 1), round(4.2 + i * 0.1, 1)))
    conn.execute("DELETE FROM satisfaction_cat")
    for c, n in [("装维服务态度", 142), ("故障处理时效", 98), ("网络稳定性", 76),
                 ("业务办理便捷", 41), ("资费透明度", 23)]:
        conn.execute("INSERT INTO satisfaction_cat (category,cnt) VALUES (?,?)", (c, n))
    conn.execute("DELETE FROM satisfaction_team")
    for t, s in [("城东装维班", 94.2), ("城西装维班", 91.5), ("城南装维班", 88.0),
                 ("高新装维班", 84.6), ("城北装维班", 82.1)]:
        conn.execute("INSERT INTO satisfaction_team (team,score) VALUES (?,?)", (t, s))


def _seed_terminals(conn):
    conn.execute("DELETE FROM terminals")
    for s, a, t, d, st in [
        ("TERM-AC31-00982", "城北·幸福家园", "在线异常", 9, "逾期"),
        ("TERM-B7F2-01453", "城南·锦绣花园", "故障终端", 6, "逾期"),
        ("TERM-C9A1-02017", "高新·阳光里", "待替换", 4, "临期"),
        ("TERM-D4E8-02760", "城西·梧桐苑", "在线异常", 3, "临期"),
        ("TERM-E2B5-03144", "城东·江畔名居", "待替换", 1, "临期"),
    ]:
        conn.execute("INSERT INTO terminals (sn,area,problem_type,days_overdue,status) "
                     "VALUES (?,?,?,?,?)", (s, a, t, d, st))
    conn.execute("DELETE FROM terminal_daily")
    for i in range(13, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO terminal_daily "
                     "(stat_date,stock,abnormal,fixed_rate) VALUES (?,?,?,?)",
                     (d, 1800 + i * 40, int(150 - i * 5 + (i % 3) * 8), round(68 + i * 1.2, 1)))


# --------------------------------------------------------------------------
# 初始化入口
# --------------------------------------------------------------------------
def init_db(reset=False):
    conn = get_conn()
    if reset:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        for t in [r["name"] for r in cur.fetchall()]:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.executescript(SCHEMA)
    _migrate(conn)  # 对已有库补列，避免 schema 升级丢数据
    _seed_users(conn)
    _seed_thresholds(conn)
    _seed_work_orders(conn)
    _seed_fttr(conn)
    _seed_gigabit(conn)
    _seed_complaints(conn)
    _seed_satisfaction(conn)
    _seed_terminals(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """对已有数据库补加新列（schema 升级时不会破坏历史数据）"""
    # complaint_upload：新增 upload_date / stat_month
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(complaint_upload)").fetchall()}
    if "upload_date" not in cols:
        conn.execute("ALTER TABLE complaint_upload ADD COLUMN upload_date TEXT NOT NULL DEFAULT ''")
    if "stat_month" not in cols:
        conn.execute("ALTER TABLE complaint_upload ADD COLUMN stat_month TEXT NOT NULL DEFAULT ''")
    # 用 created_at 回填历史空值（取年月与日期）
    conn.execute(
        "UPDATE complaint_upload SET upload_date = substr(created_at,1,10) WHERE upload_date='' OR upload_date IS NULL"
    )
    conn.execute(
        "UPDATE complaint_upload SET stat_month = substr(coalesce(period_start,created_at),1,7) WHERE stat_month='' OR stat_month IS NULL"
    )
    conn.commit()


def get_thresholds_map(conn):
    """返回 {indicator: {min_ok,max_ok,warn_min,warn_max,good_is_high,label}}"""
    rows = conn.execute("SELECT * FROM thresholds").fetchall()
    return {r["indicator"]: dict(r) for r in rows}


def classify(value, cfg):
    """按阈值配置对数值分类：ok / warn / danger"""
    if cfg["good_is_high"]:
        if cfg["min_ok"] is not None and value < cfg["min_ok"]:
            return "danger"
        if cfg["warn_min"] is not None and value < cfg["warn_min"]:
            return "warn"
        return "ok"
    else:
        if cfg["max_ok"] is not None and value > cfg["max_ok"]:
            return "danger"
        if cfg["warn_max"] is not None and value > cfg["warn_max"]:
            return "warn"
        return "ok"


if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    print("数据库初始化完成:", DB_PATH)
