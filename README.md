# 弱光督办智能管控平台

面向**新洲区弱光指标提升**的 Web 督办看板。系统**仅包含弱光督办单一业务模块**，通过上传《存量及新增弱光》Excel 报表自动解析入库，提供存量/新增/持续/严重弱光的多维分析与督办视图。B/S 架构，内网部署，无构建工具。

> 视觉风格：中国移动风格**深色科技大屏**（TDesign 设计令牌 + 自研深色主题），ECharts 图表、异常高亮、历史批次回溯。

---

## 一、模块功能边界

### 1.1 在范围内（本系统负责）

| 能力 | 说明 |
| --- | --- |
| 弱光报表解析 | 解析《存量及新增弱光》Excel，**仅保留归属区县 = 新洲区 的数据入库** |
| 存量弱光管理 | 存量弱光明细、小区维度聚合排行、PON 口维度聚合排行 |
| 新增弱光判定 | 不读取 Excel 的「新增弱光」sheet，改为**以网关 SN 对比上一数据批次**判定新增；同一天重复上传不作为基线，看板读取时按差集实时计算，不依赖批次表存量值 |
| 持续 / 严重弱光 | 持续弱光用户清单、严重弱光用户清单（谷值光功率 < -30 dBm） |
| 企宽弱光 | 企业宽带弱光用户明细 |
| 区县统计 | 新洲区及武汉各区的弱光数、弱光率、活跃用户、压降、平均弱光率 |
| 人员映射与督办 | 上传《人员录》建立「小区 → 装维人员」映射，回填明细/小区/清单的对应人员，并生成人员整治排行 |
| 历史批次回溯 | 每次上传永久留存为独立批次，可切换查看任意历史批次 |
| AI 督办摘要 | 调用 LLM（OpenAI 兼容协议）生成弱光督办摘要；未配置 key 时自动降级为规则模板 |
| 报表导出 | 导出弱光督办 CSV（小区排行 / PON 口 / 新增 / 持续 / 严重） |
| 首屏概览可视化 | 近 7 次导入弱光变化折线（存量 / 严重两条线，取最近 7 个批次，同一数据日期只取最新一次上传；批次不足有几批画几批，不按自然日补零）+ 当日弱光区域分布网格（按市场网格即责任田聚合小区弱光户数，色阶标识高低、附占比条） |
| 持续弱光追踪 | 按网关 SN 跨批次追踪：同一 SN 在最近 10 个批次内累计出现 ≥3 个批次且最新批次仍存在即判定持续弱光；输出出现批次、未整改次数（出现批次-1）、持续天数、最低谷值，高频未整改（未整改 ≥2 次或持续 ≥7 天）红色标记；最新批次消失视为已闭环 |
| 网格长推送督办 | 弱光数据按「小区 → 责任田（市场网格）→ 网格长」匹配后，一键推送弱光情况与整改要求至企业微信群机器人，支持网格长 H5 回执确认、失败重推与推送清单导出 |

### 1.2 不在范围内（已彻底移除）

原「家宽 AI 可视化智能管控平台」中的**装维工单、FTTR 无线连接率、千兆质差小区、重复投诉率、用户满意度、三类问题终端**六大看板，以及账号权限管理、阈值配置、综合评分等配套模块均已删除，其代码、配置、依赖与数据表已全部清理，无残留引用。

**地图模块已整体移除**：原「弱光空间分布地图」（Leaflet 引擎、新洲区 GeoJSON 底图、点位/热力/街道聚合图层、信息窗体、浏览器定位、路线规划、坐标台账导入、`/api/map/*` 接口、`weak_light_geo` 表）因实现存在缺陷，已连同前端资源、后端服务、路由、配置与建表语句一并移除，计划后续重新设计。当前版本不含任何地图、定位、坐标相关代码与依赖，其余弱光督办功能不受影响。

---

## 二、输入与输出

### 2.1 输入

#### 输入 A：弱光报表（支持新旧两种格式，自动识别）

- **入口**：页面「上传弱光报表」→ `POST /api/upload_weaklight`
- **格式识别**：扩展名 `.csv` → 新格式；`.xlsx/.xls` → 旧格式
- **区县标识**：两种格式均以「归属区县」= `新洲区` 过滤，**仅新洲区数据入库**
- **新增弱光判定**：与「上一个数据日期更早的批次」做网关 SN 差集；同一天重复上传只取最新一份、且不会被当作基线；无上一批次基线时不做新增判定（避免把存量误标为新增）

**格式 A1（新）：《智能网关用户详情报表MM.DD.csv》**

- 单表 **38 列**、**GBK 编码**、无 Sheet
- **数据日期**：取表内 `数据开始时间`（如 `20260927` → `2026-09-27`），比文件名可靠
- **弱光口径校验**：谷值接收光功率 < -27 dBm 或 接收光功率弱光次数 > 0
- **字段使用与落库去向**：

| CSV 列 | 落库字段 / 去向 | 说明 |
| --- | --- | --- |
| 归属区县 | — | **区县标识**，仅保留「新洲区」 |
| 网关SN / 上网账号 / MAC地址 | `weak_light_detail` | 用户唯一标识 |
| 用户活跃次数 | `active_count` | |
| 谷值/峰值接收光功率(dbm) | `valley_power` / `peak_power` | 弱光与严重弱光判定依据 |
| 接收光功率弱光次数 | `weak_count` | |
| 归属小区 | `community` | 同时按小区 `groupby` 生成 `weak_light_community` |
| 归属OLT / 归属PON / 归属ONU | `olt` / `pon` / `onu` | PON 按 `groupby` 生成 `weak_light_pon`（弱光数≥3 标红） |
| 数据开始时间 | `data_date` | 批次数据日期 |
| —（聚合派生） | `weak_light_stat` | 仅新洲区一行（弱光户数） |
| —（对比派生） | `weak_light_new` | 与上一批次网关 SN 对比 |
| —（主表） | `weak_light_upload` | 每次上传一条批次记录，永久留存 |

> ⚠️ 新格式**不含**「持续弱光 / 企宽弱光 / 质差小区类型 / 对应师傅 / 统计表」，因此
> `sustained_cnt`、`poor_cell_cnt`、`weak_light_enterprise` 为 0/空；对应人员仍由《责任田》按小区回填。
>
> 🔢 **弱光率口径**：新格式无官方弱光率，统一按 **平均弱光率 = 弱光户数 / 新洲区活跃用户数** 计算，
> 活跃用户数取 `config.XINZHOU_ACTIVE_USERS`（当前 **63698**，可用环境变量 `XINZHOU_ACTIVE_USERS` 覆盖）。
> 例：116 户 / 63698 = **0.182%**。口径调整后可调用 `weak_light_repository.recalc_weak_rate()` 直接回写历史批次，无需重新上传。

**格式 A2（旧）：《存量及新增弱光》.xlsx**

- 多 Sheet；**数据日期**：从文件名识别（如「8月17日」→ `2026-08-17`）

| Excel Sheet | 落库表 | 说明 |
| --- | --- | --- |
| 存量弱光总明细 | `weak_light_detail` | 新洲区过滤；也是「新增弱光」判定基准 |
| 存量弱光小区分析 | `weak_light_community` | 新洲区小区聚合 |
| 存量弱光pon口分析 | `weak_light_pon` | 新洲区 PON 聚合 |
| 企宽弱光 | `weak_light_enterprise` | 新洲区企宽 |
| 统计 | `weak_light_stat` | 新洲区及武汉各区弱光率/活跃/压降/平均弱光率 |
| —（派生） | `weak_light_new` | 由网关 SN 与上一批次对比判定新增 |
| —（主表） | `weak_light_upload` | 每次上传一条批次记录，永久留存 |

#### 输入 B：《责任田》（或《人员录》）

- **格式**：`.xlsx` / `.xls`（系统按文件内容自动识别，不依赖扩展名）
- **入口**：页面「上传责任田 / 人员录」→ `POST /api/upload_weaklight_person`（两种格式自动识别）
- **《责任田》格式**（单 sheet，含「责任人」「小区名称」列）：

| Excel 列 | 落库字段 | 说明 |
| --- | --- | --- |
| 地市 / 区县 | `city` / `district` | 武汉 / 新洲区 |
| 市场网格编码 / 名称 | `grid_code` / `grid` | 如 G-WH-XZ-13 / 新洲邾城网格 |
| 小区编码 | `community_code` | **责任田编号** |
| 小区名称 | `community` | **责任田名称**（与弱光明细按小区名join） |
| 小区用户数 | `user_count` | 责任田覆盖用户数 |
| 责任人 | `person` | **责任田归属人**（以该列为准） |
| 工号 | `phone` / `emp_no` | 该行装机人员手机号；员工编号取「装机人员清单」末段 |
| 装机人员清单 / 投诉人员清单 | `install_persons` / `complain_persons` | 原始文本保留 |
| 是否达标 / 场景 / 场景归类 / 资产归属人 | `is_standard` / `scene` / `scene_category` / `asset_owner` | 督办口径 |
| 更新日期 | `update_date` | **业务更新日期**（与系统 `upload_date` 分开保存） |

- **《人员录》格式**（多 sheet：人员表 + 小区表）：按「小区 → 人员」兼容写入。
- **产出**：`weak_light_person` 表，**全量覆盖式替换旧记录**；解析结果为空时拒绝覆盖，避免误清空。

#### 输入 C：环境变量（LLM，可选）

```
AI_LLM_BASE_URL   如 https://api.deepseek.com/v1
AI_LLM_API_KEY    如 sk-xxxx
AI_LLM_MODEL      默认 deepseek-chat
AI_LLM_TIMEOUT    默认 20（秒）
```

未配置时 AI 摘要自动降级为规则模板，功能不中断。

#### 输入 D：网格长名单（推送督办用，可选）

- **入口**：推送督办面板 →「上传名单」→ `POST /api/upload_grid_leader`
- **格式**：`.csv`（UTF-8/GBK 自动识别）或 `.xlsx / .xls`
- **列名**（按关键词动态识别）：

| 列 | 是否必需 | 说明 |
| --- | --- | --- |
| 市场网格编码 | 建议 | 与 `weak_light_person.grid_code` 对齐，缺失时按「责任田责任人」派生兜底 |
| 市场网格名称 | 可选 | 消息抬头展示 |
| 网格长姓名 | **必需** | 推送对象 |
| 手机号 | **必需** | 企微 text 消息用于 @ 提醒；markdown 消息仅展示打码尾号 |
| 工号 / 角色 | 可选 | 角色含「副」视为副网格长 |
| 更新日期 | 可选 | 名单业务日期 |

- **产出**：`grid_leader` 表，**全量覆盖式替换**；解析为空时拒绝覆盖，避免误清空。
- **配置**（环境变量，全部可选）：

```
PUSH_ENABLED=1                    # 0 关闭推送
PUSH_CHANNEL=wecom
PUSH_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
PUSH_WECOM_MSG_TYPE=markdown      # markdown（排版清晰）/ text（可 @ 手机号强提醒）
PUSH_SEND_INTERVAL=3              # 群机器人限 20 条/分钟，默认 3 秒/条
PUSH_DEADLINE_DAYS=3              # 整改时限（工作日）
PUSH_ACK_BASE_URL=                # 回执链接前缀，留空用当前请求 Host
PUSH_ESCALATION_NAME=区级弱光督办
PUSH_ESCALATION_PHONE=            # 无网格长时的兜底手机号
PUSH_MAX_GRIDS=50                 # 单次任务网格上限
PUSH_DETAIL_LIMIT=5               # 消息内重点户条数
```

> 未配置 `PUSH_WECOM_WEBHOOK` 时，推送面板只提供「预览 + 导出推送清单」，不产生发送任务。

**页面配置更优先**：推送督办面板顶部的「企微群机器人」徽标可点开配置窗口，填写
Webhook / 消息类型 / 发送间隔 / 整改时限 / 兜底督办人，并可「测试发送」验证连通性。
页面配置写入 `app_setting` 表，**优先于环境变量且保存立即生效**（无需重启）；
Webhook 含密钥，接口与页面只回显掩码（如 `…key=••••567890`），输入框留空保存表示不修改。

### 2.2 输出

| 输出 | 形态 | 说明 |
| --- | --- | --- |
| 弱光督办看板 | Web 页面 `/` | 概览条 + 核心 KPI + 模块入口卡；明细模块在子窗口中独立展示 |
| 看板数据 | JSON `GET /api/data/weaklight` | 基于最新批次的全部看板数据 |
| 历史批次列表 | JSON `GET /api/weaklight_batches` | 全部历史批次 |
| 指定批次数据 | JSON `GET /api/weaklight_batch?id=` | 任意历史批次完整数据 |
| 报表导出 | CSV `GET /export/weaklight` | 带 BOM，Excel 直接打开不乱码 |
| 推送预览 | JSON `GET /api/push_preview` | 网格 × 网格长匹配结果、未匹配池、已推状态 |
| 网格长推送 | 企微群机器人 | 一键触发后按网格发送 markdown/text 消息（后台线程串行、节流） |
| 推送清单导出 | CSV `GET /export/push_list` | 无通道时的兜底，人工转发 |
| 回执确认 | H5 `GET /push/ack?t=<token>` | 网格长填姓名确认接收，写 `ack_at / ack_by / ack_note` |

**核心 KPI 输出**：存量弱光户数、平均弱光率、持续弱光户数、严重弱光户数、本月新增弱光。

---

## 三、技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.9+ / Flask 3.0.3 |
| 数据库 | SQLite（Python 标准库，零外部依赖） |
| 报表解析 | pandas + openpyxl（xlsx）/ xlrd（xls） |
| AI 摘要 | OpenAI 兼容协议，仅用标准库 `urllib`，未配置自动降级 |
| 前端 | 原生 JavaScript + ECharts 5（本地）+ Tailwind CSS（CDN）+ TDesign Web Components（CDN） |
| 部署 | 内网 B/S，无需构建工具 |

> ⚠️ **内网部署提示**：ECharts 已本地化；页面仍保留 Tailwind、TDesign、Google Fonts 的公网 CDN（原有依赖），如需彻底离线需另行把这些资源本地化。

---

## 四、目录结构

```
Broadband-Dashboard/
├── app.py                      # 入口：创建 Flask app + 注册蓝图 + 启动
├── config.py                   # 全局配置（DB 路径、武汉区县口径、LLM 配置）
├── requirements.txt            # 依赖（Flask / pandas / openpyxl / xlrd）
├── db/                         # 数据层
│   ├── __init__.py             # 对外暴露 get_conn / init_db / weak_light_repository
│   ├── database.py             # 弱光 8 张表 SCHEMA + 迁移 + 遗留表清理
│   └── repositories/
│       └── weak_light_repository.py   # 弱光数据访问对象（唯一 Repository）
├── services/                   # 业务服务层
│   ├── weak_light_report.py    # 《存量及新增弱光》解析
│   ├── person_map.py           # 《责任田》/《人员录》解析
│   ├── push_service.py         # 网格长匹配 / 消息渲染 / 企微机器人发送 / 回执
│   └── llm_service.py          # LLM 摘要生成（自动降级）
├── routes/                     # 路由层
│   ├── dashboard.py            # 页面路由（/）
│   ├── api.py                  # 弱光数据接口（/api/*、/export/weaklight）
│   └── push.py                 # 推送接口（/api/push_*、/export/push_list、/push/ack）
├── templates/
│   └── dashboard.html          # 弱光看板单页（含子窗口样式）
├── static/
│   ├── js/                     # 前端（顺序加载，命名空间 window.Reports）
│   │   ├── components.js       # 公共组件（KPI / 图表 / 状态色 / 表格）
│   │   ├── panel.js            # 通用子窗口管理器（注册/打开/切换/关闭/焦点/深链接）
│   │   ├── view_weaklight.js   # 弱光看板视图（概览 + 模块入口 + 模块定义）
│   │   ├── weaklight_upload.js # 弱光报表 / 责任田上传
│   │   └── app.js              # 单页入口（加载 + 刷新 + 深链接恢复）
│   └── vendor/
│       └── echarts.min.js      # ECharts 5（本地，离线可用）
└── ai_dashboard.db             # SQLite 数据库（运行时生成）
```

---

## 五、快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> Windows 环境若 `python` 为商店占位符，请使用实际解释器路径，例如：
> `D:\py3.11\python.exe -m pip install -r requirements.txt`

### 2. 启动服务

```bash
python app.py
```

启动后访问：**http://127.0.0.1:5000**

首次启动会自动建表；若库中残留已移除模块的数据表，会在启动时自动清理并打印日志（幂等）。

### 3. 使用流程

1. 打开页面 →「上传弱光报表」上传《存量及新增弱光》Excel（或《智能网关用户详情报表》CSV）
2. （可选）「上传责任田 / 人员录」，自动回填各清单的「对应人员」
3. 看板自动展示最新批次的 KPI、排行与清单；可切换历史批次回溯
4. （可选）推送督办面板上传「网格长名单」→ 查看预览（网格 × 网格长 × 户数、未匹配池）→ 勾选网格「一键推送」→ 在任务记录中查看发送状态与网格长回执

### 4. 停止

`Ctrl + C` 终止进程。

---

## 六、接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 弱光督办看板页面 |
| GET | `/api/data/weaklight` | 弱光看板数据（最新批次，前端主接口） |
| GET | `/api/weaklight_dashboard` | 同上（语义化别名） |
| GET | `/api/weaklight_batches` | 全部历史批次列表 |
| GET | `/api/weaklight_batch?id=` | 指定批次完整数据 |
| GET | `/api/weaklight_field` | 责任田清单（责任人 → 负责责任田明细） |
| GET | `/api/weaklight_field?person=` | 指定责任人的责任田 |
| GET | `/api/weaklight_field?summary=1` | 责任田汇总（不含逐条明细） |
| POST | `/api/upload_weaklight` | 上传《存量及新增弱光》Excel |
| POST | `/api/upload_weaklight_person` | 上传《责任田》或《人员录》 |
| GET | `/api/weaklight_sustained` | 持续弱光追踪（`?min_batches=` 默认 3、`?lookback=` 默认 10、`?limit=` 默认 200） |
| GET | `/export/weaklight` | 导出弱光督办 CSV |
| GET | `/api/push_preview` | 推送预览：网格 × 网格长、未匹配池、已推状态 |
| POST | `/api/push_trigger` | 一键触发推送（`{batch_id, grid_codes[], force}`，返回 task_id） |
| GET | `/api/push_tasks` | 推送任务列表（`?limit=` 默认 20） |
| GET | `/api/push_task?id=` | 任务明细（前端 2 秒轮询发送进度） |
| GET | `/api/push_summary` | 推送摘要（入口卡 / 面板顶部） |
| GET | `/api/push_config` | 读取推送配置（webhook 掩码） |
| POST | `/api/push_config` | 保存推送配置（页面配置优先于环境变量，立即生效） |
| POST | `/api/push_test` | 发送测试消息验证 webhook |
| POST | `/api/push_retry` | 失败条目重推（`{ids[]}`） |
| POST | `/api/upload_grid_leader` | 上传网格长名单（CSV/XLSX，覆盖式） |
| GET | `/export/push_list` | 导出推送清单 CSV（无通道兜底） |
| GET | `/push/ack?t=<token>` | 网格长回执确认页（H5） |
| POST | `/api/push_ack` | 提交确认（`{token, name, note}`） |

---

## 七、数据表

| 表 | 说明 |
| --- | --- |
| `weak_light_upload` | 上传批次主表（每次上传一条，永久留存不覆盖） |
| `weak_light_detail` | 存量弱光总明细（新洲区） |
| `weak_light_community` | 存量弱光小区分析（新洲区） |
| `weak_light_pon` | 存量弱光 PON 口分析（新洲区） |
| `weak_light_new` | 新增弱光（按网关 SN 对比上一批次判定） |
| `weak_light_enterprise` | 企宽弱光（新洲区） |
| `weak_light_stat` | 区县统计（弱光率 / 活跃用户 / 压降 / 平均弱光率） |
| `weak_light_person` | 人员与责任田（小区 / 责任田编号 / 用户数 / 网格 / 责任人 / 装机与投诉人员 / 场景 / 是否达标 / 更新日期） |
| `grid_leader` | 网格长名单（网格编码 / 网格名称 / 姓名 / 手机号 / 工号 / 正副角色 / 更新日期），覆盖式替换 |
| `push_task` | 推送任务（批次 / 通道 / 范围 / 网格与对象数 / 状态 / 操作人 / 时间） |
| `push_target` | 推送明细（网格 × 网格长 / 弱光快照 / 消息正文 / 发送状态 / 回执 / 重试次数 / 回执 token） |

---

## 八、部署说明

- 项目无登录鉴权模块，直接访问即可（内网可信环境）。
- 生产环境建议关闭 `debug`（修改 `app.py` 中 `app.run(debug=...)`）。
- 数据持久化于 `ai_dashboard.db`，备份该文件即可保留全部弱光历史批次数据。

---

## 九、页面结构与子窗口交互

### 9.1 主页面（保持简洁）

```
概览条：批次号 · 数据日期 · 文件名 · [数据中心/上传]
KPI 行：存量弱光 / 平均弱光率 / 持续 / 质差 / 严重 / 新增
首屏可视化：近 7 次导入弱光变化折线（存量 / 严重） + 当日弱光区域分布网格（≥1024px 双栏，窄屏自动堆叠）
督办模块入口卡（9 张）：数据中心 / 人员整治 / 小区排行 / PON 口 / 新增弱光 / 持续弱光追踪 / 重点督办 / 推送督办 / 智能总结
每个入口卡直接展示 1 个关键指标 + 1 行摘要，点击进入子窗口
```

### 9.2 子窗口（模块面板）

| 能力 | 说明 |
| --- | --- |
| 打开 | 点击入口卡或概览条按钮 → `R.Panel.open(key)`；同一模块重复点击只聚焦，不重复渲染 |
| 切换 | 面板顶部标签页、右上 ← → 按钮、键盘 ← →，**无需关闭再打开** |
| 关闭 | 右上关闭按钮、点击遮罩空白、`Esc` 三种方式一致 |
| 焦点 | 打开时焦点移入面板、Tab 在面板内循环、关闭后焦点归还触发按钮 |
| 滚动 | 打开时锁定 `body` 滚动，关闭恢复 |
| 深链接 | 地址栏 `#panel=<key>`，刷新页面自动恢复该子窗口；关闭时自动清除 |
| 图表 | 面板切换/关闭前销毁内部 ECharts 实例，避免 0 尺寸与内存泄漏；打开后下一帧统一 resize |

模块清单：`data`（上传 + 历史批次 + AI 摘要）、`sustained`（持续弱光追踪）、`person`、`community`、`pon`、`new`、`focus`、`push`（网格长推送）、`ai`。
新增模块只需在 `view_weaklight.js` 的 `MODULES` 数组增加一项（`key/title/icon/sub/metric/hint/mount`），
入口卡与子窗口标签自动生成。

### 9.3 响应式与可访问性

- ≥1024px：居中弹窗（最大 1120px × 88vh），面板内两栏（图表 + 表格）；
- 640~900px：面板内降为单栏，表格取消内部限高，改由面板整体滚动；
- <640px：子窗口全屏铺满，头部与标签栏压缩内边距；
- `role="dialog"` + `aria-modal` + `aria-labelledby`，入口卡为原生 `button`（支持键盘 `Enter`/`Space`）；
- 尊重 `prefers-reduced-motion`：全局已关闭过渡动画。

---

## 十、许可证

内部创新项目，仅供运营分析使用。
