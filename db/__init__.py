# -*- coding: utf-8 -*-
"""数据库包：对外暴露连接、初始化与弱光督办 Repository。"""
from .database import (
    get_conn, init_db, ensure_schema, cleanup_legacy_tables, LEGACY_TABLES, DB_PATH, SCHEMA,
)

# 弱光督办 Repository（re-export，兼容路由层 from db import ...）
# 注意：必须在 get_conn 等基础符号绑定后再导入，避免循环依赖
from .repositories import weak_light_repository

__all__ = [
    "get_conn", "init_db", "ensure_schema", "cleanup_legacy_tables", "LEGACY_TABLES",
    "DB_PATH", "SCHEMA", "weak_light_repository",
]
