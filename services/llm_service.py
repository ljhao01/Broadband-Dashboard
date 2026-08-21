# -*- coding: utf-8 -*-
"""
LLM 接入服务（业务服务层）。

设计原则：
- 统一走 OpenAI 兼容协议 /chat/completions，适配 DeepSeek / 通义千问 / OpenAI / Ollama / vLLM；
- 配置全走环境变量（config.LLM_*），key 不写进代码；
- 未配置 key / 网络失败 / 解析失败 → 返回 None，调用方降级为规则模板，看板永不挂；
- 仅用标准库 urllib，不引入第三方依赖。
"""
import json
import re
import urllib.request

from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT


def llm_enabled():
    return bool(LLM_BASE_URL and LLM_API_KEY)


def _post_chat(messages, temperature=0.6, timeout=None):
    url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {LLM_API_KEY}")
    with urllib.request.urlopen(req, timeout=timeout or LLM_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _extract_json(text):
    """从模型输出提取 JSON（容忍 ```json 包裹 / 前后杂文本）。"""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def gen_weaklight_summary(context):
    """让大模型结合【历史批次经验】生成智能总结。

    返回结构（与现有规则模板一致，前端无需改动）：
      { title, trend, problems[], focus_person, priority }
    未配置 / 失败返回 None，调用方降级。
    """
    if not llm_enabled():
        return None
    latest = context.get("latest") or {}
    prev = context.get("prev_batch") or {}
    history = context.get("history") or []   # 近几批「以前的经验」
    communities = context.get("communities") or []
    pons = context.get("pons") or []
    person_ranking = context.get("person_ranking") or []

    rate = latest.get("avg_rate")
    if rate is None:
        rate = latest.get("weak_rate")

    hist_lines = []
    for h in history:
        r = round((h.get("avg_rate") or h.get("weak_rate") or 0) * 100, 3)
        hist_lines.append(f"  - {h.get('data_date')}：存量弱光 {h.get('weak_total', 0)} 户、"
                          f"弱光率 {r}%、持续 {h.get('sustained_cnt', 0)} 户")
    person_lines = [
        f"  - {p.get('person')}（{p.get('phone', '')}）：待整治 {p.get('count', 0)} 户"
        f"（持续 {p.get('sustained', 0)}、严重 {p.get('severe', 0)}、新增 {p.get('new', 0)}），"
        f"重点片区 {p.get('communities', [])[:2]}"
        for p in person_ranking[:5]
    ]
    comm_lines = [f"  - {c.get('community')}：{c.get('weak_count')} 户（{c.get('technician', '')}）"
                  for c in communities[:8]]
    pon_lines = [f"  - {c.get('pon')}：{c.get('weak_count')} 户（{c.get('community', '')}）"
                 for c in pons[:8]]

    sys_prompt = (
        "你是武汉移动家宽「新洲区弱光指标提升督办」的资深网络质量专家。"
        "基于本期数据与历史批次数据输出客观、可执行的分析总结。注意："
        "1) 优先结合历史批次趋势判断是反弹还是持续压降，给出针对性结论；"
        "2) 点名谁的责任片区最集中、应先整治谁，并说明理由；"
        "3) 解决方案要具体到派单、核查光路、按小区集中整治、防止边改边新增等可执行动作；"
        "4) 语气为运营商内部督办通报风格，简洁有力，不编造数据。"
    )
    user_prompt = f"""请根据以下新洲区弱光督办数据，输出 JSON（不要输出其他内容）：
{{
  "title": "一句话概括本期整体情况（含日期、存量弱光户数、弱光率、趋势）",
  "trend": "较上期/历史批次的趋势判断（上升/下降/持平，引用具体数字）",
  "problems": ["问题所在清单，3-5条，覆盖小区集中、热点PON、持续/严重、新增反弹等"],
  "focus_person": "谁的责任片区弱光最集中，应列为第一整改责任人（含户数与理由）",
  "priority": "集中整治优先级，用①②③编号的连续句子，结合历史经验说明为什么这么排"
}}

【本期数据】{latest.get('data_date') or '本期'}
- 存量弱光 {latest.get('weak_total', 0)} 户、弱光率 {rate}%、持续 {latest.get('sustained_cnt', 0)} 户、
  严重 {latest.get('severe_cnt', 0)} 户、新增 {latest.get('new_weak_cnt', 0)} 台
- 上期：{prev.get('data_date', '-')}，存量弱光 {prev.get('weak_total', '-')} 户

【历史批次（以前的经验）】
{chr(10).join(hist_lines) if hist_lines else '  - 无历史批次'}

【小区弱光 TOP】
{chr(10).join(comm_lines) if comm_lines else '  - 无'}

【热点 PON】
{chr(10).join(pon_lines) if pon_lines else '  - 无'}

【人员整治排行】
{chr(10).join(person_lines) if person_lines else '  - 无'}
"""
    try:
        raw = _post_chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.5)
        obj = _extract_json(raw)
        if not obj:
            return None
        return {
            "title": str(obj.get("title", "")),
            "trend": str(obj.get("trend", "")),
            "problems": [str(x) for x in obj.get("problems", [])],
            "focus_person": str(obj.get("focus_person", "")),
            "priority": str(obj.get("priority", "")),
        }
    except Exception:
        return None
