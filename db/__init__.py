# -*- coding: utf-8 -*-
"""数据库包：对外暴露连接、初始化、阈值分类等工具"""
from .database import (
    get_conn, init_db, classify, get_thresholds_map,
    get_score_rules, compute_module_score,
    load_snapshot, save_snapshot, DB_PATH, SCHEMA,
)

# 弱光督办 Repository（re-export，兼容路由层 from db import ...）
from .repositories import weak_light_repository

__all__ = ["get_conn", "init_db", "classify", "get_thresholds_map",
           "get_score_rules", "compute_module_score",
           "load_snapshot", "save_snapshot", "DB_PATH", "SCHEMA",
           "weak_light_repository"]
