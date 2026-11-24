# -*- coding: utf-8 -*-
"""
数据库模块：SQLite 初始化 + 弱光督办模块建表。

系统当前仅包含「弱光督办」单一业务模块，数据表全部以 weak_light_ 前缀命名：
  weak_light_upload      上传批次主表（每次上传一条，永久留存不覆盖）
  weak_light_detail      存量弱光总明细（新洲区）
  weak_light_community   存量弱光小区分析（新洲区）
  weak_light_pon         存量弱光 PON 口分析（新洲区）
  weak_light_new         新增弱光（按网关SN 与上一批次对比判定）
  weak_light_enterprise  企宽弱光（新洲区）
  weak_light_stat        区县统计（弱光率/活跃用户/压降）
  weak_light_person      人员映射（《责任田》/《人员录》上传，小区 → 责任人）
  grid_leader            网格长名单（推送督办用，覆盖式更新）
  push_task              推送任务（一次一键触发 = 一条）
  push_target            推送明细（网格 × 网格长，含发送/回执状态）
"""
import os
import sqlite3

from config import DB_PATH


def get_conn():
    """获取数据库连接（返回带 row 工厂的字典游标）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --------------------------------------------------------------------------
# Schema 定义：弱光督办模块（唯一业务模块）
# --------------------------------------------------------------------------
SCHEMA = """
-- ================= 弱光督办（新洲区弱光指标提升） =================
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

-- 人员与责任田（《责任田》/《人员录》上传，小区 → 责任人，全量覆盖式更新）
CREATE TABLE IF NOT EXISTS weak_light_person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,                           -- 来源文件名
    community TEXT,                          -- 小区名称（= 责任田）
    person TEXT,                             -- 责任人（归一化姓名）
    grid TEXT,                               -- 市场网格名称
    phone TEXT,                              -- 联系电话（责任田表「工号」列实为手机号）
    emp_no TEXT,                             -- 工号
    -- ===== 责任田扩展字段（2026-11-24 新增，《责任田》表） =====
    city TEXT,                               -- 地市
    district TEXT,                           -- 区县
    grid_code TEXT,                          -- 市场网格编码
    community_code TEXT,                     -- 小区编码（= 责任田编号）
    user_count INTEGER DEFAULT 0,            -- 小区用户数
    install_persons TEXT,                    -- 装机人员清单（原始文本）
    complain_persons TEXT,                   -- 投诉人员清单（原始文本）
    is_standard TEXT,                       -- 是否达标
    scene TEXT,                              -- 场景（乡镇/自然村/县城/市区/行政村）
    scene_category TEXT,                     -- 场景归类（乡镇/城区）
    asset_owner TEXT,                        -- 资产归属人
    update_date TEXT,                        -- 业务更新日期（责任田数据日期，非上传时间）
    upload_date TEXT NOT NULL,               -- 系统上传日期
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weak_light_person_community ON weak_light_person(community);
CREATE INDEX IF NOT EXISTS idx_weak_light_person_person ON weak_light_person(person);
CREATE INDEX IF NOT EXISTS idx_weak_light_person_grid ON weak_light_person(grid);

-- ================= 弱光推送（网格长督办，企微群机器人） =================
-- 网格长名单（上传后覆盖式替换；source: roster=名单上传 / derived=责任田派生）
CREATE TABLE IF NOT EXISTS grid_leader (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    grid_code TEXT,                          -- 市场网格编码
    grid TEXT,                               -- 市场网格名称
    leader_name TEXT,                        -- 网格长姓名
    phone TEXT,                              -- 手机号（企微 text 消息 @ 用）
    emp_no TEXT,                             -- 工号
    role TEXT DEFAULT 'leader',              -- leader=网格长 / deputy=副网格长
    source TEXT DEFAULT 'roster',
    update_date TEXT,                        -- 业务更新日期
    upload_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grid_leader_code ON grid_leader(grid_code);
CREATE INDEX IF NOT EXISTS idx_grid_leader_phone ON grid_leader(phone);

-- 推送任务（一次一键触发 = 一条任务）
CREATE TABLE IF NOT EXISTS push_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    data_date TEXT,
    channel TEXT DEFAULT 'wecom',            -- wecom / export
    scope TEXT DEFAULT 'all',                -- all / selected
    total_grids INTEGER DEFAULT 0,
    total_targets INTEGER DEFAULT 0,
    total_users INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',           -- pending / running / done / partial / failed
    operator TEXT,
    remark TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

-- 推送明细（一个网格长 × 一个网格 = 一条）
CREATE TABLE IF NOT EXISTS push_target (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    batch_id INTEGER,
    grid_code TEXT,
    grid TEXT,
    leader_name TEXT,
    phone TEXT,
    source TEXT DEFAULT 'roster',            -- roster / derived / fallback
    community_cnt INTEGER DEFAULT 0,
    weak_cnt INTEGER DEFAULT 0,
    severe_cnt INTEGER DEFAULT 0,
    new_cnt INTEGER DEFAULT 0,
    sustained_cnt INTEGER DEFAULT 0,
    payload_json TEXT,                       -- 渲染用的原始聚合数据
    content TEXT,                            -- 实际发送的文本（便于复现/审计）
    status TEXT DEFAULT 'pending',           -- pending / sent / failed
    error_msg TEXT,
    retry_cnt INTEGER DEFAULT 0,
    token TEXT,                              -- 回执确认令牌
    sent_at TEXT,
    ack_at TEXT,
    ack_by TEXT,
    ack_note TEXT,
    closed_cnt INTEGER DEFAULT 0,
    close_rate REAL,
    UNIQUE(task_id, grid_code, phone)
);
CREATE INDEX IF NOT EXISTS idx_push_target_task ON push_target(task_id);
CREATE INDEX IF NOT EXISTS idx_push_target_batch ON push_target(batch_id);
CREATE INDEX IF NOT EXISTS idx_push_target_token ON push_target(token);

-- 运行时配置（页面可改，优先于环境变量；key 复用配置项名，如 PUSH_WECOM_WEBHOOK）
CREATE TABLE IF NOT EXISTS app_setting (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
"""


# --------------------------------------------------------------------------
# 已被移除的历史模块数据表（重构后不再使用，启动时自动清理）
# --------------------------------------------------------------------------
LEGACY_TABLES = [
    # 用户 / 阈值 / 看板快照 / 评分规则
    "users", "thresholds", "dashboard_snapshot", "score_rule",
    # 装维工单
    "work_orders", "work_order_daily", "grid_eff",
    # FTTR
    "fttr_daily", "fttr_area", "fttr_abnormal",
    # 千兆质差小区
    "gigabit_cells", "gigabit_daily",
    # 重复投诉
    "complaints", "complaint_daily", "complaint_upload",
    "complaint_upload_district", "complaint_daily_detail", "complaint_repeat_ticket",
    # 用户满意度
    "satisfaction_daily", "satisfaction_cat", "satisfaction_team",
    # 三类问题终端
    "terminals", "terminal_daily",
]


def cleanup_legacy_tables(conn):
    """删除已移除模块遗留的数据表，确保数据库无残留（幂等）。

    返回被实际删除的表名列表。弱光督办相关表（weak_light_*）不在清理范围内。
    """
    existing = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    dropped = [t for t in LEGACY_TABLES if t in existing]
    for t in dropped:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    return dropped


# --------------------------------------------------------------------------
# 初始化入口
# --------------------------------------------------------------------------
def ensure_schema():
    """确保弱光模块全部表/列存在（幂等，**不**清理遗留表）。

    与 init_db() 的区别：不做 LEGACY_TABLES 清理，可在应用模块导入时安全调用，
    保证 `flask run`、WSGI、gunicorn 等非 `__main__` 启动方式同样具备完整弱光表。

    返回 True 表示执行成功；数据库不可写时返回 False，不阻断应用启动。
    """
    try:
        conn = get_conn()
        try:
            _ensure_weak_light_tables(conn)
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:  # 防御性：只读目录 / 文件被占用时不阻断启动
        print(f"[ensure_schema] 初始化弱光表失败：{exc}")
        return False


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        dropped = cleanup_legacy_tables(conn)
        if dropped:
            print(f"[init_db] 已清理非弱光模块遗留数据表 {len(dropped)} 张：{', '.join(dropped)}")
        conn.commit()
    finally:
        conn.close()


def _migrate(conn):
    """对已有数据库补加弱光模块新列/新表（不破坏历史弱光数据）。"""
    _ensure_weak_light_tables(conn)
    conn.commit()


def _ensure_weak_light_tables(conn):
    """确保弱光督办模块相关的全部表存在（用于已有库的 schema 升级）。"""
    conn.executescript(SCHEMA)
    # 已有库升级：weak_light_upload 表补充 avg_rate 列（平均弱光率）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(weak_light_upload)").fetchall()}
    if "avg_rate" not in cols:
        conn.execute("ALTER TABLE weak_light_upload ADD COLUMN avg_rate REAL DEFAULT 0")

    # 已有库升级：weak_light_person 补充责任田扩展字段
    person_cols = {r[1] for r in conn.execute("PRAGMA table_info(weak_light_person)").fetchall()}
    for col, ddl in (
        ("city", "TEXT"),
        ("district", "TEXT"),
        ("grid_code", "TEXT"),
        ("community_code", "TEXT"),
        ("user_count", "INTEGER DEFAULT 0"),
        ("install_persons", "TEXT"),
        ("complain_persons", "TEXT"),
        ("is_standard", "TEXT"),
        ("scene", "TEXT"),
        ("scene_category", "TEXT"),
        ("asset_owner", "TEXT"),
        ("update_date", "TEXT"),
    ):
        if col not in person_cols:
            conn.execute(f"ALTER TABLE weak_light_person ADD COLUMN {col} {ddl}")


if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    print("数据库初始化完成:", DB_PATH)
