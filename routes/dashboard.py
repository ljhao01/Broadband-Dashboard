# -*- coding: utf-8 -*-
"""页面路由：弱光督办看板"""
from flask import Blueprint, render_template

dashboard_bp = Blueprint("dashboard", __name__)

# 前端运行时配置（由 templates/dashboard.html 注入到 window.*）
REFRESH = 0  # 0 表示关闭自动刷新
FEATURES = {"showWeakLightUpload": True}


@dashboard_bp.route("/")
def index():
    return render_template("dashboard.html", REFRESH=REFRESH, FEATURES=FEATURES)
