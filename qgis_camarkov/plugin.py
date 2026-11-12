# -*- coding: utf-8 -*-
"""插件生命周期：注册 Processing Provider、工具栏/菜单入口与结果面板。

有两条硬约束决定了这里的结构：

1. ``qgis_process`` 无头模式只调用 ``classFactory`` + ``initProcessing``，
   **不会调用 ``initGui``**。所以 Provider 必须在 ``initProcessing`` 里注册；
   而 GUI 启动只调 ``initGui``，因此后者内部也要补调一次。
2. ``iface`` 在无头模式下是 None，任何 ``self.iface.xxx`` 都必须先判空，
   否则插件会在 ``qgis_process`` 里加载失败、算法完全不可见。
"""

import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtGui import QAction
from .i18n import T, warm

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
MENU_NAME = "&CA-Markov"


class CamarkovPlugin:
    """插件主类。Provider 与 GUI 动作的生命周期都在这里管理。"""

    def __init__(self, iface):
        """保存 QGIS 接口对象。

        :param iface: QgisInterface；无头模式下为 None。
        """
        self.iface = iface
        self.provider = None
        self.action = None
        self.result_dock = None

    # ------------------------------------------------------------------ 注册

    def initProcessing(self):  # noqa: N802  (QGIS 约定)
        """注册 Processing Provider。这是无头模式下算法可见的唯一入口。"""
        if self.provider is not None:
            return
        # 语言要先定下来：initAlgorithm 里的参数标签在这一刻就翻译好了
        warm()
        from .provider import CamarkovProvider

        self.provider = CamarkovProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):  # noqa: N802  (QGIS 约定)
        """GUI 启动时调用：先补注册 Provider，再加工具栏与菜单入口。"""
        self.initProcessing()
        if self.iface is None:
            # 无头模式不应该走到这里；真走到了也只注册 Provider，不碰 iface。
            return

        icon = QIcon(os.path.join(PLUGIN_DIR, "resources", "icon.svg"))
        self.action = QAction(icon, T("CA-Markov 结果…"), self.iface.mainWindow())
        self.action.setToolTip(T("打开最近一次 CA-Markov 运行的结果面板"))
        self.action.triggered.connect(self.show_last_result)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(MENU_NAME, self.action)

    def unload(self):
        """反注册全部资源。漏掉任何一项都会导致「重载插件」后出现重复 Provider。"""
        if self.iface is not None and self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(MENU_NAME, self.action)
        self.action = None

        if self.result_dock is not None:
            self.result_dock.deleteLater()
            self.result_dock = None

        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    # ------------------------------------------------------------------ 界面

    def show_last_result(self):
        """打开最近一次运行的结果面板；没有记录时提示先运行算法。"""
        from qgis.core import QgsSettings
        from qgis.PyQt.QtWidgets import QMessageBox

        metrics_path = QgsSettings().value("camarkov/last_metrics", "", type=str)
        if not metrics_path or not os.path.isfile(metrics_path):
            QMessageBox.information(
                self.iface.mainWindow(),
                "CA-Markov",
                T("还没有可显示的结果。\n\n请先在处理工具箱里运行 "
                "「CA-Markov → 变化预测」或「转移分析」。"),
            )
            return
        self.open_result_dock(metrics_path)

    def open_result_dock(self, metrics_path):
        """打开（或复用）结果停靠面板并载入指定 metrics.json。

        :param metrics_path: 引擎写出的 metrics.json 路径。
        """
        from qgis.PyQt.QtCore import Qt

        from .gui.result_dock import CamarkovResultDock

        if self.result_dock is not None:
            self.result_dock.close()
            self.result_dock.deleteLater()

        self.result_dock = CamarkovResultDock(self.iface, metrics_path)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.result_dock)
        self.result_dock.show()
