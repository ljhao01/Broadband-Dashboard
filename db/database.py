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

-- 每日投诉明细（从报表「明细/重投用户」sheet 解析，按日期+区县聚合）
CREATE TABLE IF NOT EXISTS complaint_daily_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    stat_date TEXT NOT NULL,          -- 投诉日期 YYYY-MM-DD
    district TEXT NOT NULL,           -- 区县名（含功能区）
    complaint_count INTEGER DEFAULT 0,   -- 当日投诉量
    repeat_count INTEGER DEFAULT 0,      -- 当日重复投诉量
    UNIQUE(batch_id, stat_date, district)
);

-- ================= 评分规则配置（各模块考核指标 + 权重 + 基准/挑战值） =================
CREATE TABLE IF NOT EXISTS score_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator TEXT UNIQUE NOT NULL,   -- 模块标识：satisfaction/workorder/complaint/fttr/terminal
    label TEXT NOT NULL,              -- 模块名称
    weight REAL NOT NULL,             -- 考核权重（季度/年度累计加权）
    period TEXT NOT NULL,             -- 打分方式：季度/月度
    base_value REAL NOT NULL,         -- 基准值（未达不得分）
    challenge_value REAL NOT NULL,    -- 挑战值（达到得满分）
    good_is_high INTEGER DEFAULT 1,   -- 1=数值越高越好，0=越低越好
    scoring TEXT NOT NULL,            -- 计分方式说明
    criteria TEXT NOT NULL,           -- 考核指标说明
    sort_order INTEGER DEFAULT 0      -- 显示顺序
);

-- ================= 看板数据快照（缓存"上次数据"，打开即展示） =================
CREATE TABLE IF NOT EXISTS dashboard_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    view TEXT UNIQUE NOT NULL,           -- 看板标识 workorder/fttr/gigabit/satisfaction/terminal
    data TEXT NOT NULL,                  -- JSON 序列化数据
    updated_at TEXT NOT NULL             -- 采集时间
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

-- ================= 7. 弱光督办（新洲区弱光指标提升） =================
-- 上传批次主表（每次上传一条，永久留存、不覆盖）
CREATE TABLE IF NOT EXISTS weak_light_upload (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    data_date TEXT,                          -- 数据日期（从文件名识别，如 2026-08-17）
    weak_total INTEGER DEFAULT 0,            -- 新洲区存量弱光总数
    weak_rate REAL DEFAULT 0,                -- 新洲区弱光率 %（当日/次日弱光占比）
    avg_rate REAL DEFAULT 0,                 -- 平均弱光率 %（武汉8月平均弱光率，口径取平均弱光）
    sustained_cnt INTEGER DEFAULT 0,         -- 持续弱光户数
    poor_cell_cnt INTEGER DEFAULT 0,         -- 质差小区涉及户数
    severe_cnt INTEGER DEFAULT 0,            -- 严重弱光户数(谷值<-30dBm)
    pon_cnt INTEGER DEFAULT 0,               -- 涉及弱光PON口数
    new_weak_cnt INTEGER DEFAULT 0,          -- 新增弱光台数
    upload_date TEXT NOT NULL,               -- 上传日期
    created_at TEXT NOT NULL
);

-- 存量弱光总明细（归属区县=新洲区 的记录）
CREATE TABLE IF NOT EXISTS weak_light_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    gateway_sn TEXT,                         -- 网关SN
    account TEXT,                            -- 上网账号
    mac TEXT,                                -- MAC地址
    active_count INTEGER DEFAULT 0,          -- 用户活跃次数
    valley_power REAL,                       -- 谷值接收光功率(dbm)
    peak_power REAL,                         -- 峰值接收光功率(dbm)
    weak_count INTEGER DEFAULT 0,            -- 接收光功率弱光次数
    community TEXT,                          -- 归属小区
    technician TEXT,                         -- 对应师傅
    olt TEXT,                                -- 归属OLT
    pon TEXT,                                -- 归属PON
    onu TEXT,                                -- 归属ONU
    sustained INTEGER DEFAULT 0,             -- 是否持续弱光
    enterprise INTEGER DEFAULT 0,            -- 是否企宽弱光
    is_new INTEGER DEFAULT 0,                -- 是否新增弱光
    quality_type TEXT                        -- 质差小区类型
);

-- 存量弱光小区分析（新洲区）
CREATE TABLE IF NOT EXISTS weak_light_community (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    community TEXT NOT NULL,                 -- 归属小区
    weak_count INTEGER DEFAULT 0,            -- 弱光数
    prev_count INTEGER DEFAULT 0,            -- 前日弱光数
    change_val INTEGER DEFAULT 0,            -- 变化
    quality_type TEXT                        -- 质差小区类型
);

-- 存量弱光 PON 口分析（新洲区）
CREATE TABLE IF NOT EXISTS weak_light_pon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    pon TEXT NOT NULL,                       -- 归属PON
    weak_count INTEGER DEFAULT 0,            -- 弱光数
    prev_count INTEGER DEFAULT 0,            -- 前日弱光数
    change_val INTEGER DEFAULT 0,            -- 变化
    community TEXT,                          -- 小区
    weak_mark INTEGER DEFAULT 0,             -- 是否弱光质差
    quality_type TEXT                        -- 质差小区类型
);

-- 新增弱光（新洲区）
CREATE TABLE IF NOT EXISTS weak_light_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    weak_days INTEGER,                       -- 弱光天数
    rectification TEXT,                      -- 整改情况
    weak_date TEXT,                          -- 弱光日期
    install_date TEXT,                       -- 装机日期
    gateway_sn TEXT,                         -- 网关SN
    account TEXT,                            -- 上网账号
    mac TEXT,                                -- MAC地址
    active_count INTEGER DEFAULT 0,          -- 用户活跃次数
    valley_power REAL,                       -- 谷值接收光功率
    peak_power REAL,                         -- 峰值接收光功率
    weak_count INTEGER DEFAULT 0,            -- 接收光功率弱光次数
    community TEXT,                          -- 归属小区
    olt TEXT,                                -- 归属OLT
    pon TEXT,                                -- 归属PON
    onu TEXT,                                -- 归属ONU
    technician TEXT,                         -- 回单人员
    technician_no TEXT,                      -- 回单人员工号
    is_rectified INTEGER DEFAULT 0           -- 是否整改
);

-- 企宽弱光（新洲区）
CREATE TABLE IF NOT EXISTS weak_light_enterprise (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    gateway_sn TEXT,
    account TEXT,
    mac TEXT,
    active_count INTEGER DEFAULT 0,
    valley_power REAL,
    peak_power REAL,
    weak_count INTEGER DEFAULT 0,
    community TEXT,
    olt TEXT,
    pon TEXT,
    onu TEXT
);

-- 区县统计（各弱光率、活跃用户、压降）
CREATE TABLE IF NOT EXISTS weak_light_stat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    district TEXT NOT NULL,                  -- 区县
    weak_count INTEGER DEFAULT 0,            -- 弱光数
    weak_rate REAL DEFAULT 0,                -- 弱光占比
    prev_count INTEGER DEFAULT 0,            -- 前日弱光数
    active_users INTEGER DEFAULT 0,          -- 参考活跃用户数
    change_count INTEGER DEFAULT 0,          -- 压降数
    change_rate REAL DEFAULT 0,              -- 压降占比
    avg_rate REAL DEFAULT 0                  -- 武汉8月平均弱光率
);

-- 人员映射（《人员录》上传，小区/网格 → 对应装维人员）
CREATE TABLE IF NOT EXISTS weak_light_person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,                           -- 来源文件名
    community TEXT,                          -- 小区名称
    person TEXT,                             -- 对应人员（归一化）
    grid TEXT,                               -- 网格
    phone TEXT,                              -- 手机号
    emp_no TEXT,                             -- 工号
    upload_date TEXT NOT NULL,               -- 上传日期
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weak_light_person_community ON weak_light_person(community);
CREATE INDEX IF NOT EXISTS idx_weak_light_person_person ON weak_light_person(person);
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


def _seed_score_rules(conn):
    """评分规则种子数据：5 大模块，权重合计 18（与图2一致）。"""
    rules = [
        # indicator, label, weight, period, base, challenge, good_is_high, scoring, criteria, sort
        (
            "satisfaction", "家宽满意度表现值", 6, "季度打分",
            85, 95, 1,
            "达到挑战值得满分；未达基准值不得分；介于二者之间按比例线性得分",
            "上网质量后端评满意度×60% + 装机用前评满意度×20% + 投诉用后评满意度×20%（取首一公司通报数据，按报表数据进行月度归集，年度分值由月均值计算）",
            1,
        ),
        (
            "workorder", "装维服务及投诉指标", 3, "月度打分",
            2.0, 1.5, 0,   # 质差小区占比：越低越好；挑战值1.5%（最低） 基准值2%
            "达到挑战值得满分；未达基准值不得分；按比例线性得分",
            "装维服务及投诉指标：广义投诉万比、ONU弱光率、群障等标签（任一标签判定为质量差小质，小区级判定）；质差小区占比=质差小区数/总小区数×100%",
            2,
        ),
        (
            "complaint", "家宽广义重复投诉率", 3, "月度打分",
            1.2, 0.90, 0,  # 重复投诉率：越低越好；挑战值0.90%（最低），基准值1.2%
            "达到挑战值得满分；未达基准值不得分；按比例线性得分",
            "重复投诉率=重复投诉单/工单数；同一用户三个月内针对同一问题重复投诉多次的，记一个重复投诉单；重复投诉率=重复投诉单/总工单数×100%",
            3,
        ),
        (
            "fttr", "FTTR从网关无线连接率", 3, "月度打分",
            0.96, 0.98, 1,  # FTTR连接率：越高越好（用户图2误写0.8%，按表头修正为挑战值）
            "达到挑战值得满分；未达基准值不得分；按比例线性得分",
            "FTTR从网关无线连接率=周期内FTTR网关无线连接次数/周期内FTTR活跃用户数（已累计周用户计Q时取数）",
            4,
        ),
        (
            "terminal", "三类问题终端", 3, "季度打分",
            5.5, 5.0, 0,  # 三类问题终端占比：越低越好；挑战值5%（最低），基准值5.5%
            "达到挑战值得满分；未达基准值不得分；按比例线性得分",
            "三类问题终端占比=三类问题终端数/在用终端数×100%（已通过总部署公司取数）",
            5,
        ),
    ]
    for r in rules:
        conn.execute(
            "INSERT OR IGNORE INTO score_rule "
            "(indicator, label, weight, period, base_value, challenge_value, "
            " good_is_high, scoring, criteria, sort_order) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            r,
        )


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
    _seed_score_rules(conn)
    _seed_work_orders(conn)
    _seed_fttr(conn)
    _seed_gigabit(conn)
    _seed_complaints(conn)
    _seed_satisfaction(conn)
    _seed_terminals(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """对已有数据库补加新列/新表（schema 升级时不会破坏历史数据）"""
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
    # complaint_daily_detail：每日投诉明细表（新增）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaint_daily_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            stat_date TEXT NOT NULL,
            district TEXT NOT NULL,
            complaint_count INTEGER DEFAULT 0,
            repeat_count INTEGER DEFAULT 0,
            UNIQUE(batch_id, stat_date, district)
        )
    """)
    # complaint_repeat_ticket：新洲区重复投诉具体账号单（用于前端单独展示）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaint_repeat_ticket (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            stat_date TEXT DEFAULT '',
            ticket_no TEXT DEFAULT '',
            account TEXT DEFAULT '',
            channel TEXT DEFAULT '',
            UNIQUE(batch_id, ticket_no)
        )
    """)
    # score_rule：评分规则表（新增，schema 升级时自动创建）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS score_rule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            weight REAL NOT NULL,
            period TEXT NOT NULL,
            base_value REAL NOT NULL,
            challenge_value REAL NOT NULL,
            good_is_high INTEGER DEFAULT 1,
            scoring TEXT NOT NULL,
            criteria TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    """)
    # 历史库迁移：补充评分规则种子
    cur = conn.execute("SELECT COUNT(*) AS n FROM score_rule").fetchone()
    if cur["n"] == 0:
        _seed_score_rules(conn)

    # 弱光督办模块：补齐弱光各表（schema 升级时自动创建，不破坏历史数据）
    _ensure_weak_light_tables(conn)
    conn.commit()


def _ensure_weak_light_tables(conn):
    """确保弱光督办模块相关的全部表存在（用于已有库的 schema 升级）。"""
    weak_tables = [
        """CREATE TABLE IF NOT EXISTS weak_light_upload (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            data_date TEXT,
            weak_total INTEGER DEFAULT 0,
            weak_rate REAL DEFAULT 0,
            avg_rate REAL DEFAULT 0,
            sustained_cnt INTEGER DEFAULT 0,
            poor_cell_cnt INTEGER DEFAULT 0,
            severe_cnt INTEGER DEFAULT 0,
            pon_cnt INTEGER DEFAULT 0,
            new_weak_cnt INTEGER DEFAULT 0,
            upload_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            gateway_sn TEXT, account TEXT, mac TEXT,
            active_count INTEGER DEFAULT 0,
            valley_power REAL, peak_power REAL, weak_count INTEGER DEFAULT 0,
            community TEXT, technician TEXT, olt TEXT, pon TEXT, onu TEXT,
            sustained INTEGER DEFAULT 0, enterprise INTEGER DEFAULT 0,
            is_new INTEGER DEFAULT 0, quality_type TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_community (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            community TEXT NOT NULL,
            weak_count INTEGER DEFAULT 0,
            prev_count INTEGER DEFAULT 0,
            change_val INTEGER DEFAULT 0,
            quality_type TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_pon (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            pon TEXT NOT NULL,
            weak_count INTEGER DEFAULT 0,
            prev_count INTEGER DEFAULT 0,
            change_val INTEGER DEFAULT 0,
            community TEXT,
            weak_mark INTEGER DEFAULT 0,
            quality_type TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            weak_days INTEGER, rectification TEXT,
            weak_date TEXT, install_date TEXT,
            gateway_sn TEXT, account TEXT, mac TEXT,
            active_count INTEGER DEFAULT 0,
            valley_power REAL, peak_power REAL, weak_count INTEGER DEFAULT 0,
            community TEXT, olt TEXT, pon TEXT, onu TEXT,
            technician TEXT, technician_no TEXT,
            is_rectified INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_enterprise (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            gateway_sn TEXT, account TEXT, mac TEXT,
            active_count INTEGER DEFAULT 0,
            valley_power REAL, peak_power REAL, weak_count INTEGER DEFAULT 0,
            community TEXT, olt TEXT, pon TEXT, onu TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_stat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            district TEXT NOT NULL,
            weak_count INTEGER DEFAULT 0,
            weak_rate REAL DEFAULT 0,
            prev_count INTEGER DEFAULT 0,
            active_users INTEGER DEFAULT 0,
            change_count INTEGER DEFAULT 0,
            change_rate REAL DEFAULT 0,
            avg_rate REAL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS weak_light_person (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            community TEXT,
            person TEXT,
            grid TEXT,
            phone TEXT,
            emp_no TEXT,
            upload_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
    ]
    for sql in weak_tables:
        conn.execute(sql)
    # 已有库升级：weak_light_upload 表补充 avg_rate 列（平均弱光率）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(weak_light_upload)").fetchall()}
    if "avg_rate" not in cols:
        conn.execute("ALTER TABLE weak_light_upload ADD COLUMN avg_rate REAL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_weak_light_person_community ON weak_light_person(community)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_weak_light_person_person ON weak_light_person(person)")


def get_score_rules(conn):
    """返回评分规则列表（按 sort_order 升序）。"""
    rows = conn.execute(
        "SELECT * FROM score_rule ORDER BY sort_order ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def compute_module_score(rule, current_value):
    """根据评分规则和当前指标值计算该模块加权得分。

    公式（good_is_high=1 时数值越高越好）：
        - 当前值 >= challenge：满分 = weight
        - 当前值 <= base：零分
        - 介于二者间：weight * (current - base) / (challenge - base)

    good_is_high=0 时数值越低越好：
        - 当前值 <= challenge：满分
        - 当前值 >= base：零分
        - 介于二者间：weight * (base - current) / (base - challenge)
    """
    if current_value is None:
        return {"current": None, "score": 0, "ratio": 0, "status": "no_data"}

    base = rule["base_value"]
    challenge = rule["challenge_value"]
    weight = rule["weight"]
    good_high = bool(rule.get("good_is_high", 1))

    if good_high:
        if current_value >= challenge:
            ratio, status = 1.0, "excellent"
        elif current_value <= base:
            ratio, status = 0.0, "below_base"
        else:
            ratio = (current_value - base) / (challenge - base)
            status = "linear"
    else:
        if current_value <= challenge:
            ratio, status = 1.0, "excellent"
        elif current_value >= base:
            ratio, status = 0.0, "below_base"
        else:
            ratio = (base - current_value) / (base - challenge)
            status = "linear"

    return {
        "current": round(float(current_value), 4),
        "score": round(weight * ratio, 2),
        "ratio": round(ratio * 100, 1),
        "status": status,
    }


def load_snapshot(conn, view):
    """读取指定看板的上次数据快照；不存在返回 None。"""
    row = conn.execute(
        "SELECT data FROM dashboard_snapshot WHERE view = ?", (view,)
    ).fetchone()
    return row["data"] if row else None


def save_snapshot(conn, view, data):
    """保存/覆盖指定看板的数据快照（打开页面即展示上次数据）。"""
    conn.execute(
        """
        INSERT INTO dashboard_snapshot (view, data, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(view) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
        """,
        (view, data, datetime.now().isoformat(timespec="seconds")),
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
