# -*- coding: utf-8 -*-
"""页面路由：看板主页 + 账号/阈值管理页"""
from flask import Blueprint, render_template, request

from db import get_conn

dashboard_bp = Blueprint("dashboard", __name__)

# 前端运行时配置（由 templates/dashboard.html 注入到 window.*）
REFRESH = 0  # 0 表示关闭自动刷新
FEATURES = {"showUpload": True}


@dashboard_bp.route("/")
def index():
    view = request.args.get("view", "workorder")
    return render_template("dashboard.html", active=view, REFRESH=REFRESH, FEATURES=FEATURES)


@dashboard_bp.route("/admin/users")
def admin_users():
    conn = get_conn()
    users = conn.execute("SELECT id,username,role,display_name FROM users").fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@dashboard_bp.route("/admin/thresholds")
def admin_thresholds():
    conn = get_conn()
    thrs = conn.execute("SELECT * FROM thresholds").fetchall()
    conn.close()
    return render_template("admin_thresholds.html", thrs=thrs)
