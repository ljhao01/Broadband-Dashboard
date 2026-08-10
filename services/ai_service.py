# -*- coding: utf-8 -*-
"""
AI 分析层：阈值判断、异常识别、趋势分析、问题归类、优化建议
"""
from db import classify


def analyze_kpi(value, cfg, decimals=1):
    """对单个指标做阈值分析，返回 (value, level)"""
    if isinstance(value, float):
        value = round(value, decimals)
    level = classify(value, cfg)
    return value, level


def trend_analysis(series):
    """
    趋势分析：输入 [(label, value)...]，返回趋势方向与波动
    series 为时间序列字典 {"labels": [...], "values": [...]}
    返回 {direction: 上升/下降/平稳, last, prev, delta}
    """
    vals = series["values"]
    labels = series["labels"]
    if len(vals) < 2:
        return {"direction": "平稳", "last": vals[-1] if vals else 0,
                "prev": None, "delta": 0, "label": labels[-1] if labels else ""}
    last = vals[-1]
    prev = vals[0]
    delta = round(last - prev, 1)
    recent = vals[-3:] if len(vals) >= 3 else vals
    base = vals[:3] if len(vals) >= 3 else vals
    direction = "上升" if delta > 0.5 else ("下降" if delta < -0.5 else "平稳")
    return {"direction": direction, "last": last, "prev": prev,
            "delta": delta, "recent_avg": round(sum(recent) / len(recent), 1),
            "base_avg": round(sum(base) / len(base), 1) if base else 0,
            "label": labels[-1]}


def gen_workorder_suggestions(grid_eff, timely_level, refund_rate, rework_rate):
    """装维工单 AI 建议"""
    tips = []
    worst = min(grid_eff, key=lambda g: g["eff"]) if grid_eff else None
    if worst and worst["eff"] < 90:
        tips.append(f"{worst['grid']}效能偏低（{worst['eff']:.1f}%），建议调度骨干班组支援，预计3日内回升至90%以上。")
    if timely_level == "danger":
        tips.append("工单及时率低于达标线，重点核查排班与物料储备，压降超时工单。")
    if refund_rate > 6:
        tips.append(f"退单率{refund_rate:.1f}%偏高，建议核查受理口径与一线退单原因。")
    if rework_rate > 5:
        tips.append(f"返工率{rework_rate:.1f}%偏高，疑似装维调测不规范，推送SOP复训任务。")
    if not tips:
        tips.append("当前装维工单运行整体平稳，请持续盯控网格效能波动。")
    return tips


def gen_fttr_suggestions(area_list, success_level):
    tips = []
    bad = [a for a in area_list if a["score"] < 90]
    if bad:
        names = "、".join(a["area"] for a in bad[:2])
        tips.append(f"区域质量落后（{names}等），建议上门复测并实施主从光猫信道优化。")
    if success_level == "danger":
        tips.append("连接成功率低于达标线，晚高峰时段(18-22点)建议错峰调度AP功率。")
    if not tips:
        tips.append("FTTR网络整体运行良好，持续监测时段波动与异常点位。")
    return tips


def gen_gigabit_suggestions(cells):
    tips = []
    unfixed = [c for c in cells if c["repair_status"] != "已修复"]
    if unfixed:
        tips.append(f"尚有{len(unfixed)}个质差小区未闭环，其中{unfixed[0]['cell']}时延{unfixed[0]['latency']:.0f}ms，建议优先整治。")
    if any(c["latency"] >= 30 for c in cells):
        tips.append("高时延小区疑似OLT上联拥塞，建议扩容上行链路并复核PON口。")
    if not tips:
        tips.append("千兆质差小区治理进展良好，保持台账闭环跟踪。")
    return tips


def gen_complaint_suggestions(overdue_count, top_problem):
    tips = []
    if overdue_count:
        tips.append(f"存在{overdue_count}条超时未闭环投诉，已自动升级至对应网格长督办。")
    if top_problem:
        tips.append(f"重复投诉TOP问题为「{top_problem}」，建议开展根因治理并固化整改措施。")
    if not tips:
        tips.append("重复投诉指标处于可控范围，继续跟踪顽固性问题销号进度。")
    return tips


def gen_satisfaction_suggestions(cats, teams):
    tips = []
    if cats:
        top = max(cats, key=lambda c: c["cnt"])
        tips.append(f"不满意问题集中于「{top['category']}」，建议强化相应服务培训与流程优化。")
    weak = [t for t in teams if t["score"] < 85]
    if weak:
        tips.append(f"装维班组口碑落后：{weak[0]['team']}（{weak[0]['score']:.1f}分），建议对标标杆班组开展帮扶。")
    if not tips:
        tips.append("用户满意度稳步提升，持续关注差评分类变化。")
    return tips


def gen_terminal_suggestions(terminals, fixed_level):
    tips = []
    if terminals:
        tips.append(f"存在{len(terminals)}条逾期未处置终端，已升级至网格长督办，限期清零。")
    if fixed_level == "danger":
        tips.append("终端整改完成率低于达标线，建议加快迭代替换批次与物料调度。")
    if not tips:
        tips.append("问题终端治理进展良好，保持台账动态盯控与闭环整改。")
    return tips
