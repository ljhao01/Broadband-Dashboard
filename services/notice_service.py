# -*- coding: utf-8 -*-
"""
通报文稿生成服务（业务服务层）。

职责：
- 将看板数据 / 自定义建议整理为一段结构化的「工作通报」文字；
- 提供两种输入模式：
    1) auto：按看板名自动采集数据 → 调用 ai_service.gen_*_suggestions 生成建议 → 汇总为通报；
    2) custom：直接接收调用方传入的建议文本 → 规范化为通报。
- 输出 { title, date, sections:[{heading, items:[...]}], content }，content 为可直接发布的纯文本。
"""
from datetime import datetime

from db import get_conn
from db.models import COLLECTORS
from db.repositories import complaint_repository, weak_light_repository
from services import ai_service

# 通报导语 / 结尾模板
_OPENING = "现将{date}全区家宽网络质量管控相关工作情况通报如下："
_CLOSING = "请各责任单位对照问题清单，逐项明确整改责任人与完成时限，按期闭环销号；涉及多部门协同的，由牵头单位统筹推进，确保各项指标持续向好。"


def _fmt_rate(v):
    """弱光率等小数字段转百分比（v 为小数，如 0.002867 → 0.2867%）。"""
    if v is None:
        return "-"
    return f"{round(float(v) * 100, 3)}%"


# ---------------------------------------------------------------------------
# 各看板「建议准备」：采集看板数据 → 得到建议生成函数所需入参 + 汇总 KPI
# ---------------------------------------------------------------------------
def _prepare_workorder(conn):
    data = COLLECTORS["workorder"](conn)
    grids = data.get("grids", [])
    kpis = {k.get("label"): k.get("value") for k in data.get("kpis", [])}
    # 超时工单 > 0 视为及时率预警
    timely_level = "danger" if (kpis.get("超时工单") or 0) > 0 else "normal"
    tips = ai_service.gen_workorder_suggestions(grids, timely_level, 0, 0)
    return {
        "heading": "一、装维工单效能",
        "tips": tips,
        "summary": f"全区平均装机效能 {kpis.get('平均装机效能', '-')}%，"
                   f"超时工单 {kpis.get('超时工单', '-')} 单。",
    }


def _prepare_fttr(conn):
    data = COLLECTORS["fttr"](conn)
    areas = data.get("areas", [])
    kpis = {k.get("label"): k.get("value") for k in data.get("kpis", [])}
    success_level = "danger" if (kpis.get("弱覆盖房间") or 0) > 0 else "normal"
    tips = ai_service.gen_fttr_suggestions(areas, success_level)
    return {
        "heading": "二、FTTR 无线连接率",
        "tips": tips,
        "summary": f"全区平均连接率 {kpis.get('平均连接率', '-')}%，"
                   f"弱覆盖房间 {kpis.get('弱覆盖房间', '-')} 个。",
    }


def _prepare_gigabit(conn):
    data = COLLECTORS["gigabit"](conn)
    cells = data.get("cells", [])
    tips = ai_service.gen_gigabit_suggestions(cells)
    return {
        "heading": "三、千兆质差小区",
        "tips": tips,
        "summary": f"当前质差小区 {len(cells)} 个，"
                   f"平均时延 {data.get('kpis', [{}])[0].get('value', '-')} ms。",
    }


def _prepare_complaint(conn):
    latest = complaint_repository.latest_complaint_report()
    # 各区重复投诉率最高者作为 TOP 问题
    top = None
    if latest and latest.get("districts"):
        top = latest["districts"][0]  # 已按 repeat_rate 降序
    overdue = 0  # 暂无超时字段，置 0
    tips = ai_service.gen_complaint_suggestions(overdue, (top or {}).get("district"))
    summary = f"武汉整体重复投诉 {latest.get('city_users', '-')} 单、"
    if latest and latest.get("city_rate") is not None:
        summary += f"重复投诉占比 {latest['city_rate']}%。"
    else:
        summary += "占比暂未上传。"
    if top:
        summary += f"其中 {top['district']} 重复投诉占比最高（{top.get('repeat_rate', '-')}%）。"
    return {
        "heading": "四、重复投诉率",
        "tips": tips,
        "summary": summary,
    }


def _prepare_satisfaction(conn):
    data = COLLECTORS["satisfaction"](conn)
    cats = data.get("cats", [])
    teams = data.get("teams", [])
    tips = ai_service.gen_satisfaction_suggestions(cats, teams)
    return {
        "heading": "五、用户满意度",
        "tips": tips,
        "summary": f"全区综合满意度 {data.get('kpis', [{}])[0].get('value', '-')} 分。",
    }


def _prepare_terminal(conn):
    data = COLLECTORS["terminal"](conn)
    dist = data.get("dist", [])
    kpis = {k.get("label"): k.get("value") for k in data.get("kpis", [])}
    fixed_level = "danger" if (kpis.get("故障率") or 0) > 0 else "normal"
    tips = ai_service.gen_terminal_suggestions(dist, fixed_level)
    return {
        "heading": "六、三类问题终端",
        "tips": tips,
        "summary": f"全区问题终端 {kpis.get('问题终端总数', '-')} 台，"
                   f"故障率 {kpis.get('故障率', '-')}%。",
    }


def _prepare_weaklight(conn):
    data = weak_light_repository.weak_light_dashboard()
    tips = data.get("ai_analysis", []) or []
    latest = data.get("latest") or {}
    weak_rate = latest.get("avg_rate") if latest.get("avg_rate") is not None else latest.get("weak_rate")
    ranking = data.get("person_ranking", []) or []
    if ranking:
        top = ranking[0]
        tips.append(f"人员整治排行 TOP1：{top['person']} 名下待整治 {top['count']} 户"
                    f"（持续 {top.get('sustained', 0)}、严重 {top.get('severe', 0)}、"
                    f"新增 {top.get('new', 0)}），建议优先压降。")
    summary = f"新洲区存量弱光 {latest.get('weak_total', 0)} 户、"
    if weak_rate is not None:
        summary += f"平均弱光率 {_fmt_rate(weak_rate)}"
    else:
        summary += "弱光率暂未采集"
    summary += (f"，持续弱光 {latest.get('sustained_cnt', 0)} 户、"
                f"质差小区 {latest.get('poor_cell_cnt', 0)} 户、"
                f"严重弱光 {latest.get('severe_cnt', 0)} 户、"
                f"8月新增弱光 {latest.get('new_weak_cnt', 0)} 台。")
    return {
        "heading": "七、新洲区弱光督办",
        "tips": tips,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 通报生成主入口
# ---------------------------------------------------------------------------
def generate_notice(payload):
    """生成一份工作通报文稿。

    payload 支持两种模式：
      - auto（默认）：需传 view（看板名），后端采集数据并自动生成建议；
        title 可选。
      - custom：需传 suggestions（字符串或字符串列表），可选 title；
        可选 view（用于填充导语标题）。
    额外字段：extra（补充说明文本，可字符串或列表）。
    返回 { ok, title, date, sections, content, error? }
    """
    mode = payload.get("mode", "auto")
    view = payload.get("view", "workorder")
    title = payload.get("title") or ""
    date_str = payload.get("date") or datetime.now().strftime("%Y-%m-%d")
    extra = payload.get("extra") or []

    conn = get_conn()
    try:
        if mode == "custom":
            raw = payload.get("suggestions") or []
            if isinstance(raw, str):
                raw = [raw]
            # 自定义模式：若给了 view，则附带该看板自动分析
            sections = []
            if view and view in VIEW_META:
                auto = _build_auto_section(conn, view)
                if auto:
                    sections.append(auto)
            items = [str(s).strip() for s in raw if str(s).strip()]
            if items:
                sections.append({
                    "heading": "工作建议",
                    "items": items,
                })
            # 兜底标题
            if not title:
                meta_title = VIEW_META.get(view, (None,))[0]
                title = f"关于{meta_title}的工作通报" if meta_title else "工作通报"
        else:
            if view not in VIEW_META:
                return {"ok": False, "error": f"未知看板：{view}，可选：{list(VIEW_META)}"}
            if not title:
                meta_title = VIEW_META[view][0]
                title = f"关于{meta_title}的工作通报"
            sections = []
            auto = _build_auto_section(conn, view)
            if auto:
                sections.append(auto)
    finally:
        conn.close()

    # 追加补充说明
    extra_items = []
    if isinstance(extra, str):
        extra_items = [extra]
    elif isinstance(extra, list):
        extra_items = [str(e).strip() for e in extra if str(e).strip()]
    if extra_items:
        sections.append({"heading": "其他要求", "items": extra_items})

    # 组稿为纯文本
    lines = [title]
    lines.append("")
    lines.append(_OPENING.format(date=date_str))
    lines.append("")
    for sec in sections:
        lines.append(sec["heading"])
        if sec.get("summary"):
            lines.append("　　" + sec["summary"])
        for it in sec.get("items", []):
            lines.append(f"　　{it}")
        lines.append("")
    lines.append(_CLOSING)

    content = "\n".join(lines)
    return {
        "ok": True,
        "title": title,
        "date": date_str,
        "mode": mode,
        "view": view,
        "sections": sections,
        "content": content,
    }


def _build_auto_section(conn, view):
    """按看板采集数据并生成一段「自动分析」小节；无数据时返回 None。"""
    prepare = VIEW_META[view][1]
    try:
        prepared = prepare(conn)
    except Exception:
        return None
    section = {
        "heading": prepared["heading"],
        "summary": prepared["summary"],
        "items": prepared["tips"],
    }
    return section
