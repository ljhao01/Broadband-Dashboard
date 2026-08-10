# -*- coding: utf-8 -*-
"""
运营商 AI 可视化智能管控平台（WEB 技术架构版）
入口：创建 Flask 应用 + 注册蓝图 + 启动

架构（分而治之）：
  config.py            全局配置
  db/                  数据层（连接/建表/DAO）
  services/            业务服务层（AI 分析、报表解析）
  routes/              路由层（页面路由 + 数据接口蓝图）
  templates/ static/   表现层
"""
from flask import Flask

from config import SECRET_KEY
from db import init_db
from routes.dashboard import dashboard_bp
from routes.api import api_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.register_blueprint(dashboard_bp)
app.register_blueprint(api_bp)


if __name__ == "__main__":
    # 确保表与种子数据存在（已存在则自动跳过）
    init_db()
    print("=" * 50)
    print("运营商 AI 可视化智能管控平台")
    print("浏览器访问: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
