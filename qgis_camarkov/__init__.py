# -*- coding: utf-8 -*-
"""CA-Markov 土地利用变化预测 —— QGIS 插件入口。

QGIS 只要求这里暴露 classFactory。真正的初始化在 plugin.CamarkovPlugin 里，
其中 initProcessing() 是**无头模式（qgis_process）唯一的注册入口**。
"""


def classFactory(iface):  # noqa: N802  (QGIS 约定的驼峰名)
    """QGIS 加载插件时调用。

    :param iface: QgisInterface 实例；qgis_process 无头模式下为 None。
    :returns: 插件实例。
    """
    from .plugin import CamarkovPlugin

    return CamarkovPlugin(iface)
