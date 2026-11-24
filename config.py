# -*- coding: utf-8 -*-
"""
全局配置：路径、武汉区县口径等
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "ai_dashboard.db")
SECRET_KEY = "ai-dashboard-internal-secret-key-2026"

# --------------------------------------------------------------------------
# 武汉行政区划口径
# 武汉共 13 个行政区 + 若干功能区（东湖高新区、武汉经开区等常作独立统计单元）
# 运营商报表中"15 个区"通常指 13 行政区 + 东湖高新区 + 武汉经开区
# --------------------------------------------------------------------------
WHAN_ADMIN_DISTRICTS = [
    "江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区", "洪山区",
    "东西湖区", "汉南区", "蔡甸区", "江夏区", "黄陂区", "新洲区",
]
WHAN_FUNCTION_ZONES = [
    "东湖高新区", "武汉经开区", "长江新区",
]
# 用于展示/校验的武汉全量口径（动态识别优先，此清单仅作辅助提示）
WHAN_ALL_KNOWN = set(WHAN_ADMIN_DISTRICTS + WHAN_FUNCTION_ZONES)
# 汇总行标识（非具体区县）
WHAN_SUMMARY_NAMES = {"武汉市", "武汉", "全市"}

# --------------------------------------------------------------------------
# 弱光率计算口径
# 新洲区参考活跃用户数：作为「平均弱光率 = 弱光户数 / 活跃用户数」的分母。
# 新格式《智能网关用户详情报表》不含活跃用户数与官方弱光率，故统一使用该常量。
# --------------------------------------------------------------------------
XINZHOU_ACTIVE_USERS = int(os.environ.get("XINZHOU_ACTIVE_USERS", "63698"))


# --------------------------------------------------------------------------
# 大模型（LLM）配置：OpenAI 兼容协议，环境变量注入，未配置自动降级规则模板
# --------------------------------------------------------------------------
LLM_BASE_URL = os.environ.get("AI_LLM_BASE_URL", "")    # 如 https://api.deepseek.com/v1
LLM_API_KEY  = os.environ.get("AI_LLM_API_KEY", "")     # 如 sk-xxxx
LLM_MODEL    = os.environ.get("AI_LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT  = int(os.environ.get("AI_LLM_TIMEOUT", "20"))


# --------------------------------------------------------------------------
# 弱光推送配置：企业微信群机器人（webhook），环境变量注入
# 未配置 WECOM_WEBHOOK_URL 时推送面板只做「预览 + 导出清单」，不真正发送
# --------------------------------------------------------------------------
PUSH_ENABLED = os.environ.get("PUSH_ENABLED", "1") != "0"
PUSH_CHANNEL = os.environ.get("PUSH_CHANNEL", "wecom")           # wecom / export
PUSH_WECOM_WEBHOOK = os.environ.get("PUSH_WECOM_WEBHOOK", "").strip()
# 企微机器人消息类型：markdown（排版清晰，@不到人） / text（可 @ 手机号强提醒）
PUSH_WECOM_MSG_TYPE = os.environ.get("PUSH_WECOM_MSG_TYPE", "markdown").strip().lower()
# 每两条消息之间的间隔秒数：群机器人限 20 条/分钟，默认 3 秒
PUSH_SEND_INTERVAL = float(os.environ.get("PUSH_SEND_INTERVAL", "3"))
# 整改时限（工作日）
PUSH_DEADLINE_DAYS = int(os.environ.get("PUSH_DEADLINE_DAYS", "3"))
# 回执页面地址前缀（面板链接用；留空则用请求 Host 自动拼接）
PUSH_ACK_BASE_URL = os.environ.get("PUSH_ACK_BASE_URL", "").strip()
# 无网格长时的区级兜底督办人
PUSH_ESCALATION_NAME = os.environ.get("PUSH_ESCALATION_NAME", "区级弱光督办")
PUSH_ESCALATION_PHONE = os.environ.get("PUSH_ESCALATION_PHONE", "").strip()
# 单次任务最多推送网格数 / 单条消息最多列出的明细户数
PUSH_MAX_GRIDS = int(os.environ.get("PUSH_MAX_GRIDS", "50"))
PUSH_DETAIL_LIMIT = int(os.environ.get("PUSH_DETAIL_LIMIT", "5"))
# 已确认超时小时数（面板标红催办）
PUSH_ACK_TIMEOUT_HOURS = int(os.environ.get("PUSH_ACK_TIMEOUT_HOURS", "24"))
