# -*- coding: utf-8 -*-
"""
人员映射服务（《人员录》xls → 小区/网格对应人员）。

用于弱光督办看板：把「每个小区对应的装维人员」建立映射表，供：
- 弱光明细 / 小区排行 回填对应人员；
- 每个人员「需整治弱光户数」的排行统计；
- 新增弱光对比上一次上传时的责任归属。

文件结构（本服务按实际文件动态识别，不硬编码列号）：
- Sheet1 人员表：姓名 / 网格 / 手机号码 / 工号  → 人员基础档案
- Sheet2 小区表：小区名称 / 装机人员清单        → 小区对应人员
- Sheet3：可为空
"""
import re


def _s(v):
    """安全转字符串。"""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s == "nan" else s


def normalize_person(name):
    """把人员名归一化（去掉装维人员/装维/括号等后缀），用于名称匹配。

    例：'邓康（装维人员）' → '邓康'；'贾磊(装维人员)' → '贾磊'；'黄子华（装维）' → '黄子华'。
    """
    s = _s(name)
    if not s:
        return ""
    s = re.sub(r"[（(]\s*(装维|装维人员|装维师傅)\s*[)）]", "", s)
    s = re.sub(r"[\s（）()]", "", s)
    return s


def _find_col(cols, candidates):
    """在列名列表中查找包含候选关键词的列索引；找不到返回 None。"""
    for idx, c in enumerate(cols):
        cc = str(c)
        if any(k in cc for k in candidates):
            return idx
    return None


def parse_person_report(path, filename=""):
    """解析《人员录》xls，返回人员档案 + 小区→人员映射 + 网格→人员映射。

    返回：
    {
        "ok": True,
        "error": "",
        "filename": "",
        "personnel": [{"name", "raw_name", "grid", "phone", "emp_no"}],  # 人员档案
        "community_map": {小区名: 归一化人员名},                            # 小区→人员
        "grid_map": {网格名: 归一化人员名},                                  # 网格→人员
        "count": 小区映射条数,
    }
    """
    import pandas as pd

    result = {
        "ok": True, "error": "", "filename": filename,
        "personnel": [], "community_map": {}, "grid_map": {},
        "count": 0,
    }

    def _safe_read(sheet):
        try:
            if str(path).lower().endswith(".xls"):
                return pd.read_excel(path, sheet_name=sheet, engine="xlrd")
            return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
        except Exception:
            return None

    try:
        xl = pd.ExcelFile(path)
        names = xl.sheet_names
    except Exception:
        names = ["Sheet1", "Sheet2", "Sheet3"]

    # ---- Sheet1 人员档案（姓名/网格/手机/工号） ----
    df1 = _safe_read(names[0] if names else "Sheet1")
    if df1 is not None and len(df1) > 0:
        # 表头在首行：df1.columns 即列名，用位置索引取值
        cols = list(df1.columns)
        name_col = _find_col(cols, ("姓名", "人员"))
        grid_col = _find_col(cols, ("网格", "营维网格"))
        phone_col = _find_col(cols, ("手机", "电话"))
        emp_col = _find_col(cols, ("工号", "员工编号"))
        for _, row in df1.iterrows():
            def _cell(idx):
                try:
                    return row.iloc[idx] if idx is not None else None
                except Exception:
                    return None
            name = normalize_person(_cell(name_col))
            if not name:
                continue
            rec = {"name": name}
            rec["raw_name"] = _s(_cell(name_col))
            rec["grid"] = _s(_cell(grid_col))
            rec["phone"] = _s(_cell(phone_col))
            rec["emp_no"] = _s(_cell(emp_col))
            result["personnel"].append(rec)
            if rec["grid"]:
                result["grid_map"][rec["grid"]] = name

    # ---- Sheet2 小区→人员（小区名称/装机人员清单） ----
    df2 = _safe_read(names[1] if len(names) > 1 else "Sheet2")
    if df2 is not None and len(df2) > 0:
        cols = list(df2.columns)
        comm_col = _find_col(cols, ("小区名称", "小区名"))
        if comm_col is None:
            # 避免匹配到「小区编码」：排除含"编码"的列
            for idx, c in enumerate(cols):
                cc = str(c)
                if "小区" in cc and "编码" not in cc and "编号" not in cc:
                    comm_col = idx
                    break
        person_col = _find_col(cols, ("装机人员清单", "装机人员"))
        if person_col is None:
            for idx, c in enumerate(cols):
                cc = str(c)
                if ("人员" in cc and "清单" in cc) or "装维" in cc:
                    person_col = idx
                    break
        if comm_col is not None and person_col is not None:
            for _, row in df2.iterrows():
                try:
                    comm = _s(row.iloc[comm_col])
                    person = normalize_person(row.iloc[person_col])
                except Exception:
                    continue
                if comm and person:
                    result["community_map"][comm] = person

    result["count"] = len(result["community_map"])
    return result
