# -*- coding: utf-8 -*-
"""Processing Provider：把三个 CA-Markov 算法挂到 QGIS 处理工具箱。

算法 id 形如 ``camarkov:predict``，在 ``qgis_process`` 里也用这一串。
"""

import os

from qgis.core import QgsProcessingProvider

from .algorithms.analyze import AnalyzeAlgorithm
from .algorithms.predict import PredictAlgorithm
from .algorithms.train import TrainAlgorithm
from .i18n import T

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def metadata_version():
    """读 ``metadata.txt`` 里的 ``version=``。

    以前这里写死 ``0.1.0``，插件升到 0.1.2 后算法面板仍显示旧号；
    改成读文件后不会再和 metadata 脱节。

    :returns: 版本号；文件缺失或没有该键时返回 ``0.0.0``。
    """
    path = os.path.join(PLUGIN_DIR, "metadata.txt")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("version="):
                    return line.split("=", 1)[1].strip() or "0.0.0"
    except OSError:
        return "0.0.0"
    return "0.0.0"


class CamarkovProvider(QgsProcessingProvider):
    """QGIS 处理工具箱里的「CA-Markov」分组。"""

    def id(self):  # noqa: A003  (QGIS 约定)
        """Provider 标识，决定算法 id 的前缀。"""
        return "camarkov"

    def name(self):
        """工具箱里显示的短名。"""
        return "CA-Markov"

    def longName(self):  # noqa: N802  (QGIS 约定)
        """工具箱里显示的长名。"""
        return T("CA-Markov 土地利用变化预测")

    def versionInfo(self):  # noqa: N802  (QGIS 约定)
        """版本号，显示在算法面板底部。"""
        return metadata_version()

    def icon(self):
        """工具箱分组图标。"""
        from qgis.PyQt.QtGui import QIcon

        return QIcon(os.path.join(PLUGIN_DIR, "resources", "icon.svg"))

    def svgIconPath(self):  # noqa: N802  (QGIS 约定)
        """SVG 图标路径，QGIS 优先用它以便缩放。"""
        return os.path.join(PLUGIN_DIR, "resources", "icon.svg")

    def loadAlgorithms(self):
        """注册全部算法。QGIS 调用 addProvider 时会自动触达这里。"""
        for algorithm in (AnalyzeAlgorithm(), TrainAlgorithm(), PredictAlgorithm()):
            self.addAlgorithm(algorithm)
