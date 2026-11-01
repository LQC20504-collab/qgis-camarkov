# -*- coding: utf-8 -*-
"""参数 → job.json 的组装。

这里是整个插件最容易出错的地方，因为引擎的输入契约有几处**反直觉之处**。
下面把踩过的坑逐条写在代码里，``tests/test_job_schema.py`` 会断言它们。

引擎实际读取的键（`camarkov_engine.py`）：

    mode, lang, periods, nodata, class_count, class_names, transition_source,
    steps, neighborhood_size, recompute_neighborhood, modulate_by_probability,
    suitability_mode, weights, normalize, factors, external, constraint, rf,
    validation, outputs, write_compare_image, write_hotspot_image, chunk

**死键（写了也不会被读，不要写）**：

* ``periods[].year`` —— 只用于桌面版界面显示，引擎完全不读；
* 顶层 ``seed`` —— 引擎只读 ``rf.train.seed``；
* ``rf.train.predict_drivers`` —— 引擎只读 **``rf.predict_drivers``**；
* ``external.band`` —— 引擎只用 ``band_mode`` 决定波段与类别的对应关系。

**致命细节**：``periods[].path`` 缺失时引擎抛 ``KeyError``（不是 ``JobError``），
落进兜底 ``except`` 后**退出码是 2**（运行时异常）而不是 1（参数错误），
用户只会看到一段裸 traceback。所以这里永远不写出缺少 ``path`` 的时期。

本模块**不依赖 QGIS**，可以脱离 QGIS 单测。
"""

TRANSITION_SOURCES = ("last_interval", "last_two_average", "all_periods")
SUITABILITY_MODES = ("rf", "factor", "external", "none")
NORMALIZE_METHODS = ("minmax", "quantile")
BAND_MODES = ("order", "class_value")

#: 引擎内置的 9 个 CLCD 类别名，用于按类别数生成默认标签。
CLCD_NAMES_ZH = ["无效值", "耕地", "森林", "草地", "灌木", "水体", "冰雪", "裸地", "不透水面"]

#: 因子矩阵的列数与含义（路径 / 波段 / 权重 / 方向）。
FACTOR_COLUMNS = 4


def default_class_names(class_count, nodata=0):
    """按类别数生成一套默认标签。

    为什么不直接用引擎的兜底：引擎在 ``class_names`` 缺失时会按 CLCD 列表
    **按序号硬套**——4 类会得到「无效值/耕地/森林/草地」，第 4 类明明可能是
    水体却被叫成草地，报告和图例会全部错位。

    这里只在类别数正好等于 CLCD 的 9 类时才套用 CLCD 类名，其余一律用
    「类别 N」，宁可朴素也不误导；用户可以在「类别名称」表里逐行覆盖。

    :param class_count: 类别数（<=0 表示让引擎自动推断，返回空列表）。
    :param nodata: 无效值对应的类别值，其标签写作「无效值」。
    :returns: 长度为 ``class_count`` 的名称列表。
    """
    if not class_count or class_count < 1:
        return []
    # 只有「正好 9 类」才敢套用 CLCD 的类名：那正是 CLCD 的类别体系，
    # 报告与图例能直接读懂。其它类别数下强行套用会张冠李戴——
    # 例如 4 类里第 3 类多半是水体，却被叫成「草地」。
    looks_like_clcd = class_count == len(CLCD_NAMES_ZH)
    names = []
    for value in range(class_count):
        if value == nodata:
            names.append("无效值")
        elif looks_like_clcd:
            names.append(CLCD_NAMES_ZH[value])
        else:
            names.append("类别 %d" % value)
    return names


def parse_class_names(text, class_count, nodata=0):
    """把用户输入的类别名解析成列表。

    支持中英文逗号、分号与顿号分隔。数量不足时用 :func:`default_class_names`
    补齐；多余的部分截断（与引擎行为一致，但这里会显式补而不是静默）。

    :param text: 用户输入，如 ``"无效值,耕地,森林,水体"``。
    :param class_count: 目标类别数。
    :param nodata: 无效值对应的类别值。
    :returns: 长度恰为 ``class_count`` 的列表；``class_count<=0`` 时返回空列表。
    """
    if not class_count or class_count < 1:
        return []
    raw = (text or "").replace("，", ",").replace("；", ",").replace(";", ",").replace("、", ",")
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return default_class_names(class_count, nodata)
    if len(parts) < class_count:
        parts.extend(default_class_names(class_count, nodata)[len(parts):])
    return parts[:class_count]


def parse_factor_matrix(values, columns=FACTOR_COLUMNS):
    """把 ``QgsProcessingParameterMatrix`` 的扁平列表切成因子字典。

    QGIS 的矩阵参数返回的是**一维扁平列表**（C++ 侧注释：*Tables are collapsed
    to a 1 dimensional list*），长度 = 行数 × 列数，行优先。表头不在值里。

    :param values: 扁平值列表，如 ``["a.tif", 1, 0.6, 1, "b.tif", 1, 0.4, -1]``。
    :param columns: 列数，默认 4（路径/波段/权重/方向）。
    :returns: ``[{"path":..., "band":..., "weight":..., "direction":...}, ...]``。
        单元格为空的行会被跳过（矩阵允许用户留空行）。
    """
    if not values:
        return []
    items = list(values)
    factors = []
    for start in range(0, len(items) - columns + 1, columns):
        row = items[start:start + columns]
        path = row[0]
        if path is None or str(path).strip() == "":
            continue
        factors.append(
            {
                "path": str(path).strip(),
                "band": _as_int(row[1], 1),
                "weight": _as_float(row[2], 1.0),
                "direction": _as_direction(row[3]),
            }
        )
    return factors


def build_job(
    mode,
    periods,
    nodata=0,
    class_count=0,
    class_names=None,
    transition_source="last_two_average",
    steps=1,
    neighborhood_size=5,
    recompute_neighborhood=True,
    suitability_mode="none",
    normalize_method="quantile",
    normalize_low=2.0,
    normalize_high=98.0,
    factors=None,
    weights=None,
    modulate_by_probability=True,
    validation_enabled=True,
    validation_same_period=False,
    outputs=None,
    write_compare_image=True,
    write_hotspot_image=True,
    chunk=200000,
    lang="zh",
    rf_model=None,
    rf_force_train=False,
    train_drivers=None,
    predict_drivers=None,
    n_estimators=200,
    max_depth=20,
    imbalance=2.0,
    min_samples=200,
    seed=42,
    save_model=None,
    constraint_path=None,
    constraint_band=1,
    external_path=None,
    external_band_mode="order",
):
    """组装引擎的 job 字典。

    :param mode: ``analyze`` / ``train`` / ``predict``。
    :param periods: ``[{"path": str, "band": int}, ...]``，顺序即时间序。
    :param nodata: 无效值，必须是 0..65535 的整数（负数会被引擎写坏）。
    :param class_count: 类别数，0 表示让引擎自动推断。
    :param class_names: 类别名列表，索引 == 类别值；None 时按 ``class_count`` 生成。
    :param transition_source: 见 :data:`TRANSITION_SOURCES`。
    :param suitability_mode: 见 :data:`SUITABILITY_MODES`。
    :param factors: :func:`parse_factor_matrix` 的结果（仅 factor 模式用）。
    :param outputs: ``{"raster":..., "metrics":..., "report":..., "fig_dir":..., "model":...}``。
    :param train_drivers: ``[{"name":..., "path":..., "band":...}, ...]``，顺序即特征顺序。
    :param predict_drivers: 同上；会被写到 **``rf.predict_drivers``**（引擎唯一读取的层级）。
    :returns: 可直接 ``json.dump`` 的字典。
    :raises ValueError: 参数组合非法（例如时期少于两期、模式未知）。
    """
    if mode not in ("analyze", "train", "predict"):
        raise ValueError("未知模式：%s" % mode)
    if transition_source not in TRANSITION_SOURCES:
        raise ValueError("未知的转移矩阵来源：%s" % transition_source)
    if suitability_mode not in SUITABILITY_MODES:
        raise ValueError("未知的适宜性模式：%s" % suitability_mode)
    if normalize_method not in NORMALIZE_METHODS:
        raise ValueError("未知的标准化方法：%s" % normalize_method)

    period_list = []
    for index, period in enumerate(periods or []):
        path = (period or {}).get("path")
        if not path:
            # 宁可在这里报错，也不要让引擎抛 KeyError 变成退出码 2
            raise ValueError("第 %d 期缺少文件路径" % (index + 1))
        period_list.append({"path": str(path), "band": _as_int(period.get("band"), 1)})
    if len(period_list) < 2:
        raise ValueError("至少需要两期土地利用数据")

    count = _as_int(class_count, 0)
    names = list(class_names) if class_names else default_class_names(count, _as_int(nodata, 0))

    weights = weights or {}
    suit_weight = _as_float(weights.get("suitability"), 0.6)
    neigh_weight = _as_float(weights.get("neighborhood"), 0.4)

    job = {
        "mode": mode,
        "periods": period_list,
        "nodata": _as_int(nodata, 0),
        "class_count": count,
        "class_names": names,
        "transition_source": transition_source,
        "steps": max(1, _as_int(steps, 1)),
        "neighborhood_size": max(1, _as_int(neighborhood_size, 5)),
        "recompute_neighborhood": bool(recompute_neighborhood),
        "suitability_mode": suitability_mode,
        "normalize": {
            "method": normalize_method,
            "low": _as_float(normalize_low, 2.0),
            "high": _as_float(normalize_high, 98.0),
        },
        "weights": {"suitability": suit_weight, "neighborhood": neigh_weight},
        "modulate_by_probability": bool(modulate_by_probability),
        "validation": {
            "enabled": bool(validation_enabled),
            "same_period": bool(validation_same_period),
        },
        "outputs": _clean_outputs(outputs),
        "write_compare_image": bool(write_compare_image),
        "write_hotspot_image": bool(write_hotspot_image),
        "chunk": max(1000, _as_int(chunk, 200000)),
        "lang": "en" if str(lang).lower().startswith("en") else "zh",
    }

    # 只有 factor 模式才写 factors：其它模式下引擎不读，写了徒增噪音
    if suitability_mode == "factor":
        job["factors"] = list(factors or [])
    else:
        job["factors"] = []

    rf = {
        "model": str(rf_model) if rf_model else None,
        "force_train": bool(rf_force_train),
        # 引擎读的是 rf.predict_drivers；写进 rf.train 下会被静默忽略
        "predict_drivers": _drivers_json(predict_drivers) if predict_drivers else None,
        "train": {
            "drivers": _drivers_json(train_drivers),
            "n_estimators": max(1, _as_int(n_estimators, 200)),
            "max_depth": max(0, _as_int(max_depth, 20)),
            "imbalance": _as_float(imbalance, 2.0),
            "min_samples": max(1, _as_int(min_samples, 200)),
            # 顶层 seed 是死键，真正生效的是这里
            "seed": _as_int(seed, 42),
            "save_model": str(save_model) if save_model else None,
            "intervals": None,
        },
    }
    job["rf"] = rf

    if constraint_path:
        job["constraint"] = {
            "path": str(constraint_path),
            "band": _as_int(constraint_band, 1),
        }
    if external_path and suitability_mode == "external":
        job["external"] = {
            "path": str(external_path),
            # band 是死键，不写；波段与类别的对应关系由 band_mode 决定
            "band_mode": external_band_mode if external_band_mode in BAND_MODES else "order",
        }

    return job


# ---------------------------------------------------------------------- 内部


def _clean_outputs(outputs):
    """去掉值为空的输出项，避免引擎把 None 当成路径。"""
    cleaned = {}
    for key, value in (outputs or {}).items():
        if value:
            cleaned[key] = str(value)
    return cleaned


def _drivers_json(drivers):
    """把驱动因子规范成引擎要求的 ``{name, path, band}`` 列表。"""
    result = []
    for driver in drivers or []:
        path = (driver or {}).get("path")
        if not path:
            continue
        name = driver.get("name") or _basename_no_ext(path)
        result.append(
            {
                "name": str(name),
                "path": str(path),
                "band": _as_int(driver.get("band"), 1),
            }
        )
    return result


def _basename_no_ext(path):
    """取不含扩展名的文件名，用作驱动因子名（即特征名）。"""
    name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def _as_int(value, fallback):
    """宽容地转 int；失败用回退值。"""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return fallback


def _as_float(value, fallback):
    """宽容地转 float；失败用回退值。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_direction(value):
    """把方向单元格规范成 ``"+"`` / ``"-"``。

    用户可能填 ``1/-1``、``+/-``、``正向/负向``；无法识别时按正向处理。
    """
    text = str(value).strip().lower()
    if text in ("-1", "-", "负", "负向", "negative", "neg"):
        return "-"
    return "+"
