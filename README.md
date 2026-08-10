# 家宽 AI 可视化智能管控平台

运营商家宽业务 **AI 可视化智能管控** Web 看板，面向装维、FTTR、千兆、重复投诉、用户满意度、终端六大专项指标，提供实时刷新、阈值预警、趋势分析、报表导出等能力。基于 B/S 架构，内网部署。

> 视觉风格：中国移动风格**深色科技大屏**（TDesign 设计令牌 + 自研深色主题），支持六看板联动、异常高亮、阈值可配置。

---

## 功能特性

- **六大专项看板**：装维工单、FTTR 无线质量、千兆劣化、重复投诉、用户满意度、问题终端
- **实时刷新**：看板数据每 15 秒自动刷新，异常指标高亮预警
- **阈值管理**：关键指标阈值可在后台配置，支持动态预警
- **趋势分析**：基于 ECharts 的趋势图、柱状图、分布图
- **报表导出**：各看板一键导出 CSV
- **重复投诉上传分析**：解析《广义重投统计》xlsx 报表，按月累计、数据永久留存
- **深色大屏 UI**：径向渐变背景、网格点阵、毛玻璃发光面板、超大渐变 KPI 数字

---

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.9 + Flask 3.0.3 |
| 数据库 | SQLite（Python 标准库，零外部依赖）|
| 前端 | 原生 JavaScript + ECharts 5 + Tailwind CSS（CDN）+ TDesign Web Components（CDN）|
| 部署 | 内网 B/S，无需构建工具 |

> ⚠️ **内网部署提示**：Tailwind、ECharts、TDesign、Google Fonts 均走公网 CDN。若内网无法访问公网，需将这些资源改为本地静态文件。

---

## 目录结构

```
家宽/
├── app.py                  # 入口：创建 Flask app + 注册蓝图 + 启动
├── config.py               # 全局配置（路径、武汉行政区/功能区口径）
├── requirements.txt        # 依赖（Flask==3.0.3）
├── db/                     # 数据层
│   ├── __init__.py         # re-export 公共接口
│   ├── database.py         # 建表 SCHEMA + 种子数据 + 迁移
│   └── models.py           # DAO：六看板查询 + 投诉报表落库/读取
├── services/               # 业务服务层
│   ├── ai_service.py       # 阈值分类 / 趋势 / 六看板建议
│   └── complaint_report.py # xlsx 解析 + 上传 AI 分析
├── routes/                 # 路由层
│   ├── dashboard.py        # 页面路由（/、后台）
│   └── api.py              # 数据接口（/api/*、/export/*）
├── templates/              # 页面模板（base / dashboard / 后台）
├── static/js/              # 前端分层（顺序加载，命名空间 window.Reports）
│   ├── components.js        # 公共组件（KPI/图表/状态色/表格）
│   ├── app.js              # 入口：Tab 导航 / 刷新 / 注入配置
│   ├── view_*.js           # 六看板视图
│   └── complaint_upload.js  # 投诉报表上传 + 柱状图
└── ai_dashboard.db         # SQLite 数据库（运行时生成）
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> Windows 环境请使用 `py` 命令（而非 `python`，后者可能是商店占位符）：`py -m pip install -r requirements.txt`

### 2. 启动服务

```bash
py app.py
```

启动后访问：**http://127.0.0.1:5000**

首次启动会自动建表并写入种子数据（已存在则跳过）。

### 3. 停止

`Ctrl + C` 终止进程。

---

## 主要接口

| 路径 | 说明 |
| --- | --- |
| `/` | 主看板页面 |
| `/api/data/<view>` | 各看板数据（workorder/fttr/gigabit/complaint/satisfaction/terminal）|
| `/api/upload_report` | 上传《广义重投统计》xlsx 报表 |
| `/api/complaint_chart` | 重复投诉按月累计 / 最新 / 历史 |
| `/api/complaint_batch?id=` | 指定批次明细 |
| `/export/<view>` | 各看板 CSV 导出 |
| `/admin/thresholds` | 阈值配置后台 |

---

## 配置说明

- **武汉区县口径**：`config.py` 中 `WHAN_ADMIN_DISTRICTS`（13 行政区）、`WHAN_FUNCTION_ZONES`（东湖高新区 / 武汉经开区 / 长江新区），合计按报表实际口径动态识别合并为 **15 区**。
- **新洲区**在重复投诉分析中为重点高亮区。
- **阈值**：可在 `/admin/thresholds` 后台配置，或直接在 `config.py` 的阈值表中修改。

---

## 部署说明

- 项目无登录鉴权模块，直接访问即可（内网可信环境）。
- 生产环境建议关闭 `debug`（修改 `app.py` 中 `app.run(debug=...)`）。
- 数据持久化于 `ai_dashboard.db`，备份该文件即可保留全部数据。

---

## 许可证

内部创新项目，仅供运营分析使用。
