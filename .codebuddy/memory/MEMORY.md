# 项目长期记忆

## 家宽 AI 可视化智能管控平台（Flask WEB 方案）
- **项目定位**：运营商 AI 可视化智能管控创新项目（WEB 技术架构版），六大专项指标看板，B/S 架构内网部署。
- **技术栈（已定）**：Python 3.9 + Flask 3.0.3 + SQLite（标准库）+ ECharts + Tailwind CDN + Material Symbols。运行命令 `py app.py`（注意：`python` 命令是 Windows 商店占位符，须用 `py`）。
- **环境要点**：本机**无 `py` 启动器、PATH 里也无 `python`/`python3`**；实际解释器在 `D:\py3.11\python.exe`（Python 3.11.2，PATH 已含 `D:\py3.11\`）。运行命令用 `D:\py3.11\python.exe app.py`（或 `python app.py`）。Flask 2.3.3 已装；pandas/openpyxl 需额外 `pip install`（requirements.txt 未列，但上传解析依赖）。PowerShell 会吞掉 stderr，判断成功要看 exitCode 或写文件再读；node 未安装，无法用 node 校验 JS。
- **用户偏好（重要）**：**不需要登录模块**（已移除鉴权，直接访问）；**要求模块解耦、分而治之、目录清晰**；**武汉区县口径**须准确（不要硬编码错漏，按报表实际口径动态识别）。
- **解耦后的目录结构（分层架构）**：
  - `app.py`：薄入口，仅创建 Flask app + 注册蓝图 + `init_db()` + 启动。
  - `config.py`：全局配置（DB_PATH、武汉行政区/功能区清单 `WHAN_ADMIN_DISTRICTS`/`WHAN_FUNCTION_ZONES`/`WHAN_ALL_KNOWN`/`WHAN_SUMMARY_NAMES`/`WHAN_MERGE_MAP` + `merge_wuhan_district()`）。
  - `static/js/`（前端分层，普通 `<script>` 顺序加载，命名空间 `window.Reports`）：`components.js`(公共组件)、`view_workorder.js`/`view_fttr.js`/`view_gigabit.js`/`view_complaint.js`/`view_satisfaction.js`/`view_terminal.js`/`view_weaklight.js`(七看板)、`complaint_upload.js`(投诉上传+柱状图)、`weaklight_upload.js`(弱光上传+批次)、`app.js`(入口/Tab/刷新/注入FEATURES+REFRESH)。`echartsInstances` 全局数组统一 resize。
  - `db/` 包：**数据层**，已按 Repository 模式解耦：
    - `__init__.py`(re-export get_conn/init_db/classify/get_thresholds_map/load_snapshot/save_snapshot/SCHEMA)
    - `database.py`(建表SCHEMA+种子数据+dashboard_snapshot快照表+load/save_snapshot)
    - `models.py`(各看板通用 `collect_*` + `COLLECTORS` 映射，保持轻量)
    - `repositories/complaint_repository.py`(投诉模块专用 Repository：save/latest/month_summary/batch_detail/district_daily_trend)
    - `repositories/weak_light_repository.py`(弱光模块专用 Repository：save/weak_light_dashboard/batches/batch_detail)
  - `services/` 包：**业务服务层**。`ai_service.py`(阈值分类/趋势/看板建议)、`complaint_report.py`(重复投诉 xlsx 解析)、`weak_light_report.py`(弱光 xlsx 解析)。
  - `routes/` 包：**路由层**。`dashboard_bp`(页面/、/admin/users、/admin/thresholds)、`api_bp`(/api/data/<view>、/api/upload_report、/api/report_cache、/api/complaint_chart、/export/<view>、/admin/thresholds/update)。
  - `templates/`：base.html、dashboard.html（统一看板容器）、admin_users.html、admin_thresholds.html。
  - `ai_dashboard.db`：SQLite 数据库。
- **六大看板**：装维/FTTR/千兆/重复投诉/满意度/终端；实时刷新15s、异常高亮、阈值预警、环比、趋势图(ECharts)、报表导出CSV、阈值可配置。
- **重复投诉率上传分析（留存+按月清零）**：`/api/upload_report` 解析《广义重投统计》xlsx → 落库 `complaint_upload`(批次) + `complaint_upload_district`(每区) + `complaint_daily_detail`(每日+区县明细)，**数据永久留存不变**。接口：`/api/complaint_chart`(按月累计: batch_count/daily_new/latest/history/`district_daily`各区分日趋势/`daily_districts`/`all_batches`跨月批次/`has_data`)、`/api/complaint_batch?id=`。DB 层由 `db/repositories/complaint_repository.py` 统一封装。**15 区县动态选择**：前端 `complaint_upload.js` 有区县下拉（默认武汉整体），选中区展示该区 KPI + 每日趋势双线图（`renderDistrictDailyChart`）；选区 KPI 优先从 `district_daily` 汇总，无每日明细回退 `latest.districts` 该区批次汇总。**武汉整体「重复投诉总量」「重复投诉占比」置顶**。`view_complaint.js` 武汉整体 KPI 置顶 + 上传分析块放其后。武汉区县用 `WHAN_ALL_KNOWN` 动态识别。**注意**：`latest.districts` 字段为 `repeat_users`/`total_orders`/`repeat_rate`；`complaint_month_summary` 返回 `has_data` 标志（前端据此判断）。
- **弱光督办看板（新洲区弱光指标提升，2026-08-19 新增）**：依据 PRD《新洲区弱光指标提升督办看板》实现，沿用 complaint 模块「上传解析+落库+看板+历史批次」模式。
  - 上传：`/api/upload_weaklight` 解析《存量及新增弱光》xlsx 的 6 个 sheet（存量弱光总明细/小区分析/pon口分析/企宽弱光/新增弱光/统计），仅过滤归属区县=新洲区入库。文件名识别数据日期（8月17日→2026-08-17）。接口：`/api/data/weaklight`（走直接读DB不走快照）、`/api/weaklight_dashboard`、`/api/weaklight_batches`、`/api/weaklight_batch?id=`、`/export/weaklight`。
  - DB 表 7 张：`weak_light_upload`(批次主表: data_date/weak_total/weak_rate/sustained_cnt/poor_cell_cnt/severe_cnt/pon_cnt/new_weak_cnt) + `weak_light_detail`(存量明细) + `weak_light_community`(小区) + `weak_light_pon`(PON口) + `weak_light_new`(新增) + `weak_light_enterprise`(企宽) + `weak_light_stat`(区县统计)。`_migrate`→`_ensure_weak_light_tables` 自动建表。
  - 验收通过：弱光177户、弱光率0.287%、持续34、质差13、严重53(谷值<-30dBm)、PON 101、新增6；蔡濠社区8户TOP1；双柳OLT003端口3=4户质差标红(孔雀城航天府滨江苑)。
  - 前端 `view_weaklight.js`（总览KPI+小区/PON图表+新增督办+持续/严重弱光+质差+区县统计）+ `weaklight_upload.js`（上传+历史批次）。FEATURES 加 `showWeakLightUpload`。
  - **关键字段注意**：`weak_light_stat` 表 `weak_rate`/`avg_rate` 为小数（如0.002867）；弱光率前端需 ×100 显示（`_build_kpis` 已处理）。
  - **人员对应/整治排行（2026-08-19 增强）**：新增 `services/person_map.py` 解析《人员录》xls（Sheet1人员表+Sheet2小区→装机人员，1190条）→ 落库 `weak_light_person` 表（上传接口 `/api/upload_weaklight_person`，全量覆盖）。看板 `weak_light_dashboard`/`batch_detail` 按小区回填 `technician`（解决最新批次 technician 为空的"人员排行无数据"根因）、新增弱光对比上一批次（`is_new_vs_prev`/`new_weaks_summary`/`prev_batch`）、并输出 `person_ranking`（按人员聚合需整治户数）。前端 `view_weaklight.js` 加「人员整治排行」卡 + 新增弱光摘要/对应人员/对比标签，小区排行加对应人员列；`weaklight_upload.js` 加「上传人员录」区。**注意**：`weak_light_person` 是覆盖式更新；`requirements.txt` 需含 `xlrd` 以读 .xls。
- **导出中文文件名 bug（2026-08-19 修复）**：`routes/api.py` 导出 `Content-Disposition` 含中文文件名触发 latin-1 `UnicodeEncodeError`（此前所有看板导出都报错）。已改用 RFC5987：`filename*=UTF-8''{quote(fname)}`。
- **各模块缓存（打开即上次数据）**：新增 `dashboard_snapshot` 表。`/api/data/<view>` 除 complaint 外（数据已落库直接读最新）的 5 个看板（workorder/fttr/gigabit/satisfaction/terminal）**优先读快照**返回，无快照才调 `collect_*` 生成并存快照；带 `?refresh=1` 强制重新采集。前端 `load(refresh)` 传 `?refresh=1`，页面"刷新全部数据"按钮触发 `loadAll(true)`。**注意**：5 个看板数据本为 random 假数据，快照后打开页面显示上次采集结果，需手动点刷新才更新。
- **顶部模块（新洲汇总 + 综合评分）**：dashboard.html main 顶部 `<section id="top-summary">` 包含：
  1. **新洲区·本月汇总 KPI 卡**：从 `/api/complaint_chart` 取新洲（district_daily 优先，回退 latest.districts）
  2. **六大模块综合评分卡**：从 `/api/scoring` 取 5 个模块（satisfaction 6 + workorder 3 + complaint 3 + fttr 3 + terminal 3 = 总权重 18），按 base/challenge 线性打分（good_is_high 区分方向）。当前值映射：satisfaction=综合满意度、workorder=100-装机效能（近似质差率）、complaint=city_rate（已落库真实值）、fttr=平均连接率/100、terminal=故障率%。前端 `summary.js` 渲染进度条+得分；总得分/得分率显示在标题右侧。
- **评分规则表 `score_rule`**：indicator + label + weight + period + base_value + challenge_value + good_is_high + scoring + criteria + sort_order。db 提供 `get_score_rules`/`compute_module_score(rule, current)`。
- **武汉15区口径**：`WHAN_FUNCTION_ZONES = [东湖高新区, 武汉经开区, 长江新区]`，`WHAN_ADMIN_DISTRICTS` 13个行政区，合计 `WHAN_ALL_KNOWN` 含16项。报表实际命中合并后为 **15区**（经开区/武汉经济技术开发区 经 `WHAN_MERGE_MAP` 归并为「武汉经开区」）。`complaint_report.py` 解析时按标准名聚合（用户/工单累加，重复率按工单量加权）。
- **踩坑**：①`save_complaint_report` 字段名曾拼错 `wuahan_districts`（应为 `wuhan_districts`）导致落库0区；②`complaint_report.py` 漏 import `WHAN_ALL_KNOWN`；③`save_report_to_db` 三元组参数写法触发 AST unmatched ')'，拆 sql/params 两变量修复；④openpyxl 部分 sheet 因 AutoFilter 含非法字符报错，用 pandas 逐 sheet 容错读取。
- **原始原型 HTML**（6个英文文件）保留作设计参考。
- **UI 视觉风格（已定，2026-08-10）**：用户要求「中国移动大屏看板」观感，已重制为**深色科技大屏**。设计令牌在 `templates/dashboard.html` 的 `:root`（TDesign 品牌色 + 大屏科技色 `--accent #2ea6ff`/`--accent-2 #19e0ff`/`--accent-3 #00d3a8`；深色层 `--bg-0 #060d1f`/`--bg-1`/`--bg-2 #0e1c3d`/`--bg-3`/`--panel-border rgba(46,166,255,.22)`；文字 `--ink-1 #eaf2ff`/`--ink-2 #a9c2e6`/`--ink-3 #6c87b3`）。特征：深蓝径向渐变+网格点阵背景、顶部渐变发光标题栏（带 CHINA MOBILE 副标）、胶囊 Tab 导航、毛玻璃发光面板 `.card`、超大渐变数字 KPI `.kpi`（`.u` 包裹单位）、深色 ECharts 主题（`components.js` 的 `CHART_PALETTE`/`CHART_AXIS` + 渐变柱/面积线）。新增/复用文案用 `style="color:var(--ink-3)"` 等变量类，**避免再用 Tailwind 的 `text-slate-*`/`bg-white` 浅色类**（已在深色底不可见）。
- **TDesign 使用约定（2026-08-10）**：用户指定 UI 库为 **TDesign**。因项目为无构建工具、内网部署、原生 JS + ECharts 架构，采用**混合策略**：① 头部引入 TDesign Web Components CDN（`https://cdn.jsdelivr.net/npm/@tdesign/web-components@1.0.0/dist/tdesign.min.js`，type=module），可用于 `<t-dialog>`/`<t-loading>` 等交互组件；② 主要视觉用 TDesign 设计令牌（CSS 变量体系，对齐官方蓝 `#0052d9`）自定义实现，保证内网可用、与 ECharts 共存、不受 Shadow DOM 限制。后续若用 TDesign 组件，注意自定义元素 + 原生 innerHTML 渲染的兼容性。
- **内网 CDN 风险**：Tailwind(`cdn.tailwindcss.com`)、ECharts、TDesign、Google Fonts 均走公网 CDN。内网若无法访问，需改为本地静态资源（目前用户未要求，保持 CDN）。
