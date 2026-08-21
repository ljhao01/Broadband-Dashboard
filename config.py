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
# 报表中存在的「别名 / 拆分写法」统一归并到标准名称，避免出现重复统计项
# 例：经开区 / 武汉经济技术开发区 实为同一功能区，合并为「武汉经开区」
WHAN_MERGE_MAP = {
    "经开区": "武汉经开区",
    "武汉经济技术开发区": "武汉经开区",
}
# 用于展示/校验的武汉全量口径（动态识别优先，此清单仅作辅助提示）
WHAN_ALL_KNOWN = set(WHAN_ADMIN_DISTRICTS + WHAN_FUNCTION_ZONES)
# 汇总行标识（非具体区县）
WHAN_SUMMARY_NAMES = {"武汉市", "武汉", "全市"}

# 应用合并映射：把报表中可能出现的别名归一到标准名称
def merge_wuhan_district(name):
    if not name:
        return name
    return WHAN_MERGE_MAP.get(name.strip(), name.strip())


# --------------------------------------------------------------------------
# 大模型（LLM）配置：OpenAI 兼容协议，环境变量注入，未配置自动降级规则模板
# --------------------------------------------------------------------------
LLM_BASE_URL = os.environ.get("AI_LLM_BASE_URL", "")    # 如 https://api.deepseek.com/v1
LLM_API_KEY  = os.environ.get("AI_LLM_API_KEY", "")     # 如 sk-xxxx
LLM_MODEL    = os.environ.get("AI_LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT  = int(os.environ.get("AI_LLM_TIMEOUT", "20"))
