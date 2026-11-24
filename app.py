# -*- coding: utf-8 -*-
"""
弱光督办智能管控平台（WEB 技术架构版）

系统仅包含「弱光督办」单一业务模块，聚焦新洲区弱光指标提升。

架构（分而治之）：
  config.py            全局配置（武汉区县口径、LLM 配置）
  db/                  数据层（连接 / 弱光建表 / 遗留表清理 / Repository）
  services/            业务服务层（弱光报表解析、人员录解析、LLM 摘要）
  routes/              路由层（页面路由 + 弱光数据接口蓝图）
  templates/ static/   表现层
"""
from flask import Flask

from config import SECRET_KEY
from db import ensure_schema, init_db
from routes.dashboard import dashboard_bp
from routes.api import api_bp
from routes.push import push_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 幂等建表/补列（不清理遗留表）：保证 flask run / WSGI 等非 __main__ 启动方式
# 同样具备弱光模块全部数据表。
ensure_schema()

app.register_blueprint(dashboard_bp)
app.register_blueprint(api_bp)
app.register_blueprint(push_bp)


if __name__ == "__main__":
    # 确保弱光表存在并清理遗留表（幂等）
    init_db()
    print("=" * 56)
    print("弱光督办智能管控平台 · 新洲区弱光指标提升")
    print("浏览器访问: http://127.0.0.1:5000")
    print("=" * 56)
    app.run(host="0.0.0.0", port=5000, debug=True)
