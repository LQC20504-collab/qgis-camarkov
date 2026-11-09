# -*- coding: utf-8 -*-
"""变化预测：完整链路，输出预测栅格 + 报告 + 图表。

链路：转移矩阵 → 转移预算 → 适宜性 → 邻域 → 元胞自动机分配 → 多步 → 精度评价 → 出图。
"""

from .base import CamarkovAlgorithmBase


class PredictAlgorithm(CamarkovAlgorithmBase):
    """``camarkov:predict``。"""

    MODE = "predict"
    GROUP = "变化预测"
    GROUP_ID = "predict"
    NEEDS_RASTER_OUTPUT = True
    ICON_FILE = "icon_predict.svg"

    def createInstance(self):  # noqa: N802  (QGIS 约定)
        """QGIS 每次执行都会要一个新实例，必须返回新对象而不是 self。"""
        return PredictAlgorithm()

    def name(self):  # noqa: A003  (QGIS 约定)
        """算法 id。"""
        return "predict"

    def displayName(self):  # noqa: N802  (QGIS 约定)
        """工具箱里显示的名字。"""
        return "变化预测（CA-Markov）"

    def shortHelpString(self):  # noqa: N802  (QGIS 约定)
        """帮助页正文。"""
        return (
            "从最后一期出发，按 Markov 转移预算与适宜性/邻域约束做元胞自动机分配，"
            "预测未来若干步的土地利用格局。\n\n"
            "输出：预测栅格（GeoTIFF，≤255 类时内嵌类别色彩表）、文本报告、"
            "混淆矩阵/转移矩阵/面积变化/对比图/变化热点等图表、指标 JSON。\n\n"
            "精度评价默认采用**时间外推**：把最后一期当作未知，只用更早的区间建模去"
            "预测它，再与实测比较——这样得到的 OA/Kappa 才代表预测能力。"
            "只有两期数据时无法外推，会自动退回同期自检（指标偏乐观），报告里会注明。\n\n"
            "提示：先用「转移分析」确认数据无误，再跑本算法。"
        )
