# -*- coding: utf-8 -*-
"""读取引擎写出的 ``metrics.json`` 并生成摘要。

引擎把指标写成 UTF-8、``ensure_ascii=False``，键集合见下表的必需项。
本模块不依赖 QGIS，可单测。
"""

import json

#: 引擎必定写出的顶层键（``analyze`` / ``train`` 模式下部分值为 null）。
REQUIRED_KEYS = (
    "mode",
    "classes",
    "matrix_counts",
    "matrix_probability",
    "matrix_budget",
    "accuracy",
    "baseline_oa",
    "validation_note",
    "feature_importance",
    "rf_summary",
    "warnings",
    "weights",
    "neighborhood_size",
    "steps",
    "pixel_area_km2",
    "timing",
    "outputs",
    "figures",
    "skipped_steps",
)

#: 图表键 → 中文标题（图集页签用）。
FIGURE_TITLES = {
    "transition": "转移概率矩阵",
    "area": "各类面积变化",
    "confusion": "混淆矩阵",
    "importance": "驱动因子重要性",
    "compare": "三联对比",
    "hotspot": "变化热点",
}


class MetricsError(Exception):
    """metrics.json 读不出来或格式不符。"""


def load(path):
    """加载并做最基本的形状校验。

    :param path: metrics.json 路径。
    :returns: 解析后的字典。
    :raises MetricsError: 文件缺失、JSON 非法或缺少必需键。
    """
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except ValueError as exc:
            raise MetricsError("metrics.json 不是合法 JSON：%s" % exc)
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise MetricsError("metrics.json 缺少字段：%s" % "、".join(missing))
    if not data.get("classes"):
        raise MetricsError("metrics.json 没有类别统计，可能被提前中断")
    return data


def summary(data):
    """生成一行中文摘要，用于日志面板。

    :param data: :func:`load` 的返回值。
    :returns: 形如「预测 · 精度 OA=0.9453 Kappa=0.9205 · 1 条警告」。
    """
    mode_text = {"analyze": "转移分析", "train": "模型训练", "predict": "变化预测"}
    parts = [mode_text.get(data.get("mode"), data.get("mode") or "未知模式")]

    accuracy = data.get("accuracy")
    if accuracy:
        parts.append("精度 OA=%.4f Kappa=%.4f" % (accuracy.get("oa", 0), accuracy.get("kappa", 0)))
    else:
        parts.append("无精度评价")

    warnings = data.get("warnings") or []
    if warnings:
        parts.append("%d 条警告" % len(warnings))

    elapsed = (data.get("timing") or {}).get("total_s")
    if elapsed:
        parts.append("耗时 %.1f 秒" % elapsed)

    return " · ".join(parts)


def class_names(data):
    """按类别值顺序取出类别名列表。"""
    rows = data.get("classes") or []
    return [row.get("name") or ("类别 %d" % row.get("value", i)) for i, row in enumerate(rows)]


def figure_paths(data):
    """取出实际生成的图表路径，按 :data:`FIGURE_TITLES` 的顺序排列。

    :param data: :func:`load` 的返回值。
    :returns: ``[(标题, 路径), ...]``，缺失的图不返回。
    """
    figures = data.get("figures") or {}
    result = []
    for key, title in FIGURE_TITLES.items():
        path = figures.get(key)
        if path:
            result.append((title, path))
    return result
