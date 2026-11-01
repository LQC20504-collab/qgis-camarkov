# -*- coding: utf-8 -*-
"""训练模型：把 81 类转移潜力的随机森林训练好并存成 .npz。

训练产物可以在多次预测之间复用，避免每次预测都重跑几分钟的训练。
"""

from .base import CamarkovAlgorithmBase


class TrainAlgorithm(CamarkovAlgorithmBase):
    """``camarkov:train``。"""

    MODE = "train"
    GROUP = "建模"
    GROUP_ID = "model"
    NEEDS_MODEL_OUTPUT = True
    # 引擎的 train 只产出模型与指标，不写文本报告
    SUPPORTS_REPORT = False

    def createInstance(self):  # noqa: N802  (QGIS 约定)
        """QGIS 每次执行都会要一个新实例，必须返回新对象而不是 self。"""
        return TrainAlgorithm()

    def name(self):  # noqa: A003  (QGIS 约定)
        """算法 id。"""
        return "train"

    def displayName(self):  # noqa: N802  (QGIS 约定)
        """工具箱里显示的名字。"""
        return "训练转移潜力模型（随机森林）"

    def shortHelpString(self):  # noqa: N802  (QGIS 约定)
        """帮助页正文。"""
        return (
            "用各期的驱动因子（高程、坡度、距道路距离、人口等）训练随机森林，"
            "学习「哪里更容易发生转移」，输出可复用的模型文件（.npz）。\n\n"
            "训练样本来自相邻两期的变化像元：变化像元全保留，不变像元按"
            "「不变像元采样倍数」抽样，避免类别极度不平衡。\n\n"
            "训练完成后，预测算法里指定这个模型即可跳过训练，节省几分钟。"
        )
