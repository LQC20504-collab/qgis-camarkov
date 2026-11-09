# -*- coding: utf-8 -*-
"""转移分析：只算转移矩阵与面积统计，秒级，不写栅格。

典型用法是先用它确认「分期顺序、无效值、类别数」三件事没设错，
再去跑预测——否则几分钟的随机森林训练会白跑。
"""

from .base import CamarkovAlgorithmBase


class AnalyzeAlgorithm(CamarkovAlgorithmBase):
    """``camarkov:analyze``。"""

    MODE = "analyze"
    GROUP = "输入与统计"
    GROUP_ID = "preview"
    # 引擎的 analyze 只产出 metrics.json 与转移矩阵图，不写文本报告
    SUPPORTS_REPORT = False
    ICON_FILE = "icon_analyze.svg"

    def createInstance(self):  # noqa: N802  (QGIS 约定)
        """QGIS 每次执行都会要一个新实例，必须返回新对象而不是 self。"""
        return AnalyzeAlgorithm()

    def name(self):  # noqa: A003  (QGIS 约定)
        """算法 id（``camarkov:`` 之后的部分）。"""
        return "analyze"

    def displayName(self):  # noqa: N802  (QGIS 约定)
        """工具箱里显示的名字。"""
        return "转移分析（只看矩阵，不写栅格）"

    def shortHelpString(self):  # noqa: N802  (QGIS 约定)
        """帮助页正文。"""
        return (
            "只统计转移矩阵、转移概率与转移预算，并输出面积变化表，"
            "**不训练模型、不写预测栅格**，通常几秒完成。\n\n"
            "建议在正式预测前先跑一次：\n"
            "· 时期顺序是否从旧到新；\n"
            "· 无效值是否设对（设错会把大片有效像元当无效）；\n"
            "· 类别名是否正确——类别值超过类别数会被当成无效值。\n\n"
            "「适宜性来源」在此模式下不参与计算，可以忽略。"
        )
