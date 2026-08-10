# 项目长期记忆

## 家宽 AI 可视化智能管控平台（Flask WEB 方案）
- **项目定位**：运营商 AI 可视化智能管控创新项目（WEB 技术架构版），六大专项指标看板，B/S 架构内网部署。
- **技术栈（已定）**：Python 3.9 + Flask 3.0.3 + SQLite（标准库）+ ECharts + Tailwind CDN + Material Symbols。运行命令 `py app.py`（注意：`python` 命令是 Windows 商店占位符，须用 `py`）。
- **环境要点**：PowerShell 会吞掉 python/flask 的 stderr 输出，判断是否成功要看 exitCode 或写文件再读；node 未安装，无法用 node 校验 JS。
- **用户偏好（重要）**：**不需要登录模块**（已移除鉴权，直接访问）；**要求模块解耦、分而治之、目录清晰**；**武汉区县口径**须准确（不要硬编码错漏，按报表实际口径动态识别）。
- **解耦后的目录结构（分层架构）**：
  - `app.py`：薄入口，仅创建 Flask app + 注册蓝图 + `init_db()` + 启动。
  - `config.py`：全局配置（DB_PATH、武汉行政区/功能区清单 `WHAN_ADMIN_DISTRICTS`/`WHAN_FUNCTION_ZONES`/`WHAN_ALL_KNOWN`/`WHAN_SUMMARY_NAMES`/`WHAN_MERGE_MAP` + `merge_wuhan_district()`）。
  - `static/js/`（前端分层，普通 `<script>` 顺序加载，命名空间 `window.Reports`）：`components.js`(公共组件)、`view_workorder.js`/`view_fttr.js`/`view_gigabit.js`/`view_complaint.js`/`view_satisfaction.js`/`view_terminal.js`(六看板)、`complaint_upload.js`(上传+柱状图)、`app.js`(入口/Tab/刷新/注入FEATURES+REFRESH)。`echartsInstances` 全局数组统一 resize。
  - `db/` 包：**数据层**。`__init__.py`(re-export get_conn/init_db/classify/get_thresholds_map/SCHEMA)、`database.py`(建表SCHEMA+种子数据)、`models.py`(DAO：六个 `collect_*` 查询 + `COLLECTORS` 映射 + `save_complaint_report`/`latest_complaint_report` 落库读取)。
  - `services/` 包：**业务服务层**。`ai_service.py`(阈值分类/趋势/六看板建议)、`complaint_report.py`(xlsx 解析 `parse_complaint_report` + AI分析 `_gen_upload_analysis`)。
  - `routes/` 包：**路由层**。`dashboard_bp`(页面/、/admin/users、/admin/thresholds)、`api_bp`(/api/data/<view>、/api/upload_report、/api/report_cache、/api/complaint_chart、/export/<view>、/admin/thresholds/update)。
  - `templates/`：base.html、dashboard.html（统一看板容器）、admin_users.html、admin_thresholds.html。
  - `ai_dashboard.db`：SQLite 数据库。
- **六大看板**：装维/FTTR/千兆/重复投诉/满意度/终端；实时刷新15s、异常高亮、阈值预警、环比、趋势图(ECharts)、报表导出CSV、阈值可配置。
- **重复投诉率上传分析（留存+按月清零）**：`/api/upload_report` 解析《广义重投统计》xlsx → 落库 `complaint_upload`(批次, 新增 `upload_date`/`stat_month` 字段) + `complaint_upload_district`(每区)，**数据永久留存不变**。接口：`/api/complaint_chart`(按月累计: batch_count/每日新增 daily_new/最新整体/latest/历史 history)、`/api/complaint_batch?id=`(指定批次不变明细)。`save_complaint_report` 用 period.start 的年月作 `stat_month`；`complaint_month_summary(month)` 按 stat_month 过滤实现"每月清零"语义（跨月自动从空白累计）。前端 complaint_upload.js：本月累计卡片+每日新增折线+历史批次下拉切换(数据不变)+柱状图。初始化 `db.init_db` 含 `_migrate` 补列(对已有库 ALTER ADD upload_date/stat_month 并用 created_at 回填)。武汉区县用 `WHAN_ALL_KNOWN` 动态识别，**新洲区重点高亮**。
- **武汉15区口径**：`WHAN_FUNCTION_ZONES = [东湖高新区, 武汉经开区, 长江新区]`，`WHAN_ADMIN_DISTRICTS` 13个行政区，合计 `WHAN_ALL_KNOWN` 含16项。报表实际命中合并后为 **15区**（经开区/武汉经济技术开发区 经 `WHAN_MERGE_MAP` 归并为「武汉经开区」）。`complaint_report.py` 解析时按标准名聚合（用户/工单累加，重复率按工单量加权）。
- **踩坑**：①`save_complaint_report` 字段名曾拼错 `wuahan_districts`（应为 `wuhan_districts`）导致落库0区；②`complaint_report.py` 漏 import `WHAN_ALL_KNOWN`；③`save_report_to_db` 三元组参数写法触发 AST unmatched ')'，拆 sql/params 两变量修复；④openpyxl 部分 sheet 因 AutoFilter 含非法字符报错，用 pandas 逐 sheet 容错读取。
- **原始原型 HTML**（6个英文文件）保留作设计参考。
- **UI 视觉风格（已定，2026-08-10）**：用户要求「中国移动大屏看板」观感，已重制为**深色科技大屏**。设计令牌在 `templates/dashboard.html` 的 `:root`（TDesign 品牌色 + 大屏科技色 `--accent #2ea6ff`/`--accent-2 #19e0ff`/`--accent-3 #00d3a8`；深色层 `--bg-0 #060d1f`/`--bg-1`/`--bg-2 #0e1c3d`/`--bg-3`/`--panel-border rgba(46,166,255,.22)`；文字 `--ink-1 #eaf2ff`/`--ink-2 #a9c2e6`/`--ink-3 #6c87b3`）。特征：深蓝径向渐变+网格点阵背景、顶部渐变发光标题栏（带 CHINA MOBILE 副标）、胶囊 Tab 导航、毛玻璃发光面板 `.card`、超大渐变数字 KPI `.kpi`（`.u` 包裹单位）、深色 ECharts 主题（`components.js` 的 `CHART_PALETTE`/`CHART_AXIS` + 渐变柱/面积线）。新增/复用文案用 `style="color:var(--ink-3)"` 等变量类，**避免再用 Tailwind 的 `text-slate-*`/`bg-white` 浅色类**（已在深色底不可见）。
- **TDesign 使用约定（2026-08-10）**：用户指定 UI 库为 **TDesign**。因项目为无构建工具、内网部署、原生 JS + ECharts 架构，采用**混合策略**：① 头部引入 TDesign Web Components CDN（`https://cdn.jsdelivr.net/npm/@tdesign/web-components@1.0.0/dist/tdesign.min.js`，type=module），可用于 `<t-dialog>`/`<t-loading>` 等交互组件；② 主要视觉用 TDesign 设计令牌（CSS 变量体系，对齐官方蓝 `#0052d9`）自定义实现，保证内网可用、与 ECharts 共存、不受 Shadow DOM 限制。后续若用 TDesign 组件，注意自定义元素 + 原生 innerHTML 渲染的兼容性。
- **内网 CDN 风险**：Tailwind(`cdn.tailwindcss.com`)、ECharts、TDesign、Google Fonts 均走公网 CDN。内网若无法访问，需改为本地静态资源（目前用户未要求，保持 CDN）。
