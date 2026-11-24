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


def _idnum(v):
    """把 Excel 中的数字型编号安全转为字符串（去掉 .0 尾巴）。"""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        return str(int(v)) if v.is_integer() else str(v)
    s = str(v).strip()
    return "" if s == "nan" else s


def _to_int(v):
    """安全转整数（失败返回 0）。"""
    try:
        if v is None or (isinstance(v, float) and v != v):
            return 0
        return int(float(v))
    except Exception:
        return 0


# 责任田文件列名映射（按关键词动态识别，不硬编码列号）
FIELD_COLMAP = {
    "city": ("地市", "城市"),
    "district": ("区县",),
    "grid_code": ("市场网格编码", "网格编码"),
    "grid": ("市场网格名称", "网格名称"),
    "community_code": ("小区编码",),
    "community": ("小区名称",),
    "user_count": ("小区用户数",),
    "install_persons": ("装机人员清单",),
    "complain_persons": ("投诉人员清单",),
    "is_standard": ("是否达标",),
    "update_date": ("更新日期",),
    "scene_category": ("场景归类",),
    "scene": ("场景",),
    "asset_owner": ("资产归属人",),
    "emp_no": ("工号", "员工编号"),
    "person": ("责任人",),
}


def _pick_cols(cols, colmap):
    """按 colmap 关键词定位列索引；长关键词优先，避免「场景」误命中「场景归类」。"""
    picked = {}
    used = set()
    for key, kws in colmap.items():
        for kw in sorted(kws, key=len, reverse=True):
            idx = None
            for i, c in enumerate(cols):
                if i in used:
                    continue
                if str(c).strip() == kw:
                    idx = i
                    break
            if idx is None:
                for i, c in enumerate(cols):
                    if i in used:
                        continue
                    if kw in str(c):
                        idx = i
                        break
            if idx is not None:
                picked[key] = idx
                used.add(idx)
                break
    return picked


def is_field_format(cols):
    """判断表头是否为《责任田》格式（含「责任人」+「小区名称」）。"""
    names = [str(c).strip() for c in cols]
    return any("责任人" in n for n in names) and any("小区名称" in n for n in names)


def parse_field_report(path, filename="", df=None):
    """解析《责任田》表（小区级责任田 → 责任人），返回逐条责任田记录。

    输入列（实际文件为准，按关键词动态识别）：
      地市 / 区县 / 市场网格编码 / 市场网格名称 / 小区编码 / 小区名称 / 小区用户数 /
      装机人员清单 / 投诉人员清单 / 是否达标 / 更新日期 / 场景 / 场景归类 / 资产归属人 / 工号 / 责任人

    返回：
    {
        "ok": True, "error": "", "filename": "", "format": "field",
        "fields": [ {city, district, grid_code, grid, community_code, community,
                     user_count, install_persons, complain_persons, is_standard,
                     update_date, scene, scene_category, asset_owner,
                     person, phone, emp_no} ],
        "personnel": [ {name, raw_name, grid, phone, emp_no} ],
        "community_map": {小区名: 责任人},
        "grid_map": {网格名: 责任人},
        "count": 责任田条数,
        "update_date": 业务更新日期,
    }
    """
    import pandas as pd

    result = {
        "ok": True, "error": "", "filename": filename, "format": "field",
        "fields": [], "personnel": [], "community_map": {}, "grid_map": {},
        "count": 0, "update_date": "",
    }

    try:
        if df is None:
            # 不按扩展名指定 engine，交由 pandas 按文件内容识别 xls/xlsx（避免扩展名与内容不符）
            try:
                df = pd.read_excel(path, sheet_name=0)
            except Exception:
                df = pd.read_excel(path, sheet_name=0,
                                   engine="xlrd" if str(path).lower().endswith(".xls") else "openpyxl")
    except Exception as e:
        result["ok"] = False
        result["error"] = f"读取失败：{e}"
        return result

    if df is None or len(df) == 0:
        result["ok"] = False
        result["error"] = "文件无数据行"
        return result

    cols = list(df.columns)
    if not is_field_format(cols):
        result["ok"] = False
        result["error"] = "未识别为责任田格式（需包含「责任人」「小区名称」列）"
        return result

    picked = _pick_cols(cols, FIELD_COLMAP)
    missing = [k for k in ("community", "person") if k not in picked]
    if missing:
        result["ok"] = False
        result["error"] = f"缺少必要列：{missing}"
        return result

    def cell(row, key):
        idx = picked.get(key)
        return None if idx is None else row.iloc[idx]

    update_dates = set()
    person_seen = {}
    for _, row in df.iterrows():
        community = _s(cell(row, "community"))
        if not community:
            continue
        person = normalize_person(cell(row, "person"))
        if not person:
            continue
        raw_install = _s(cell(row, "install_persons"))
        # 工号列在本表中为装机人员手机号；末尾段（如 -7005）作为员工编号
        emp_from_install = raw_install.split("-")[-1].strip() if "-" in raw_install else ""
        phone = _idnum(cell(row, "emp_no"))
        update_date = _s(cell(row, "update_date"))[:10]
        if update_date:
            update_dates.add(update_date)

        rec = {
            "city": _s(cell(row, "city")),
            "district": _s(cell(row, "district")),
            "grid_code": _idnum(cell(row, "grid_code")),
            "grid": _s(cell(row, "grid")),
            "community_code": _idnum(cell(row, "community_code")),
            "community": community,
            "user_count": _to_int(cell(row, "user_count")),
            "install_persons": raw_install,
            "complain_persons": _s(cell(row, "complain_persons")),
            "is_standard": _s(cell(row, "is_standard")),
            "update_date": update_date,
            "scene": _s(cell(row, "scene")),
            "scene_category": _s(cell(row, "scene_category")),
            "asset_owner": _s(cell(row, "asset_owner")),
            "person": person,
            "phone": phone,
            "emp_no": emp_from_install or phone,
        }
        result["fields"].append(rec)
        result["community_map"][community] = person
        if rec["grid"]:
            result["grid_map"][rec["grid"]] = person
        # 人员档案（去重，优先保留有手机号/网格的记录）
        if person not in person_seen or (not person_seen[person]["phone"] and rec["phone"]):
            person_seen[person] = {
                "name": person,
                "raw_name": _s(cell(row, "person")),
                "grid": rec["grid"],
                "phone": rec["phone"],
                "emp_no": rec["emp_no"],
            }

    result["personnel"] = list(person_seen.values())
    result["count"] = len(result["fields"])
    result["update_date"] = max(update_dates) if update_dates else ""
    return result


def _parse_person_roster(path, filename=""):
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
            # 优先按文件内容自动识别格式，避免扩展名与真实格式不符导致读取失败
            try:
                return pd.read_excel(path, sheet_name=sheet)
            except Exception:
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
    result["format"] = "roster"
    return result


def parse_person_report(path, filename=""):
    """人员与责任田统一入口：自动识别《责任田》或《人员录》格式后解析。

    - 《责任田》（单 sheet，含「责任人」「小区名称」）→ parse_field_report
    - 《人员录》（多 sheet，人员表 + 小区表）      → _parse_person_roster
    """
    try:
        import pandas as pd
        try:
            df0 = pd.read_excel(path, sheet_name=0)  # 按内容自动识别 xls/xlsx
        except Exception:
            engine = "xlrd" if str(path).lower().endswith(".xls") else "openpyxl"
            df0 = pd.read_excel(path, sheet_name=0, engine=engine)
        if is_field_format(list(df0.columns)):
            return parse_field_report(path, filename, df=df0)
    except Exception:
        pass
    return _parse_person_roster(path, filename)
