# -*- coding: utf-8 -*-
"""结果停靠面板：把 metrics.json 与图表摆成可浏览的界面。

用 ``QgsDockWidget`` 而不是模态对话框：
* 可与图层面板并存，不遮挡画布；
* 批处理/模型器里算法不会走到这里（只有工具栏动作或手工点开才创建）。

主题适配原则：不写死样式表与背景色，一律走 ``self.palette()``，
这样在亮色/暗色主题下都不会出现突兀的色块。
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qgis.gui import QgsDockWidget

from ..core import metrics as metrics_mod
from ..i18n import T, translate_class_name


class _ScaledImage(QWidget):
    """按控件宽度等比缩放的图片块（PNG 只有 900px 级，QLabel 足够）。"""

    def __init__(self, title, path, parent=None):
        """保存原始像素图，窗口尺寸变化时按比例重绘。

        :param title: 图片上方标题。
        :param path: PNG 路径；不存在时显示占位提示。
        """
        super().__init__(parent)
        self._pixmap = QPixmap(path) if path and os.path.isfile(path) else QPixmap()

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        # 白底 PNG 在暗色主题下会刺眼，加一圈边框把它框住即可，不改图本身
        self._label.setStyleSheet("border: 1px solid palette(mid); padding: 2px;")

        self._title = QLabel(title, self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 8)
        layout.addWidget(self._title)
        layout.addWidget(self._label)

        if self._pixmap.isNull():
            self._label.setText(T("（未生成这张图）"))
        else:
            self._rescale()

    def _rescale(self):
        """按当前宽度等比缩放；宽度未知时先不动。"""
        width = max(self._label.width(), 200)
        self._label.setPixmap(
            self._pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        )

    def resizeEvent(self, event):  # noqa: N802  (Qt 约定)
        """容器变宽变窄时重新缩放。"""
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self._rescale()


class CamarkovResultDock(QgsDockWidget):
    """CA-Markov 结果面板。"""

    def __init__(self, iface, metrics_path, parent=None):
        """载入 metrics.json 并搭建页签。

        :param iface: QgisInterface，用于取主窗口作为父级。
        :param metrics_path: 引擎写出的 metrics.json 路径。
        :param parent: 父窗口，默认取 ``iface.mainWindow()``。
        """
        super().__init__(T("CA-Markov 结果"), parent or (iface.mainWindow() if iface else None))
        # objectName 必须有，QGIS 靠它持久化 dock 布局
        self.setObjectName("CamarkovResultDock")

        self.metrics_path = metrics_path
        self.data = None
        self.error = ""

        try:
            self.data = metrics_mod.load(metrics_path)
        except Exception as exc:  # 指标读不出来也要把窗口开出来，好让用户看到原因
            self.error = str(exc)

        self._build()

    # ------------------------------------------------------------------ 构建

    def _build(self):
        """搭出页签结构。"""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)

        if self.data is None:
            label = QLabel(T("读取结果失败：\n\n%s\n\n文件：%s") % (self.error, self.metrics_path))
            label.setWordWrap(True)
            layout.addWidget(label)
            self.setWidget(container)
            return

        tabs = QTabWidget(container)
        tabs.addTab(self._tab_overview(), T("概览"))
        tabs.addTab(self._tab_matrix(), T("转移矩阵"))
        tabs.addTab(self._tab_accuracy(), T("精度"))
        tabs.addTab(self._tab_importance(), T("特征重要性"))
        tabs.addTab(self._tab_figures(), T("图集"))
        layout.addWidget(tabs)

        self.setWidget(container)

    def _tab_overview(self):
        """概览页：参数摘要 + 面积表 + 警告。"""
        view = QTextBrowser()
        view.setHtml(self._overview_html())
        return view

    def _overview_html(self):
        """拼概览页的 HTML。颜色全部走调色板，避免暗色主题下看不清。"""
        data = self.data
        accuracy = data.get("accuracy")
        unit = "km²" if data.get("pixel_area_km2") else T("像元")

        rows = []
        for row in data.get("classes") or []:
            rows.append(
                "<tr><td>%s</td><td align='right'>%.4f</td>"
                "<td align='right'>%.4f</td><td align='right'>%.4f</td>"
                "<td align='right'>%+.2f%%</td></tr>"
                % (
                    translate_class_name(row.get("name", "")),
                    row.get("base") or 0,
                    row.get("end") or 0,
                    row.get("pred") or 0,
                    row.get("change_pct") or 0,
                )
            )

        warnings = data.get("warnings") or []
        warning_html = ""
        if warnings:
            warning_html = T("<p><b>警告（%d）</b></p><ul>%s</ul>") % (
                len(warnings),
                "".join("<li>%s</li>" % w for w in warnings),
            )

        if accuracy:
            accuracy_line = T("总体精度 OA = %.4f，Kappa = %.4f") % (
                accuracy.get("oa", 0),
                accuracy.get("kappa", 0),
            )
        else:
            accuracy_line = T("本次没有做精度评价")

        headers = "".join(
            "<th>%s</th>" % T(label) for label in ("类别", "基期", "末期", "预测", "变化率")
        )
        return """
        <style>
          body {{ color: palette(text); }}
          table {{ border-collapse: collapse; }}
          td, th {{ padding: 2px 8px; }}
          th {{ border-bottom: 1px solid palette(mid); }}
        </style>
        <p><b>{summary}</b></p>
        <p>{scheme}</p>
        <p>{accuracy}</p>
        <p><b>{area_title}</b></p>
        <table>
          <tr>{headers}</tr>
          {rows}
        </table>
        {warnings}
        """.format(
            summary=metrics_mod.summary(data),
            scheme=data.get("validation_note") or "",
            accuracy=accuracy_line,
            area_title=T("面积统计（%s）") % unit,
            headers=headers,
            rows="".join(rows),
            warnings=warning_html,
        )

    def _tab_matrix(self):
        """转移矩阵页：计数 / 概率 / 预算三选一。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)

        chooser = QComboBox()
        chooser.addItems([T("转移计数"), T("转移概率"), T("转移预算")])
        layout.addWidget(chooser)

        table = QTableWidget()
        layout.addWidget(table)

        def refresh(index):
            """按选择切换显示的矩阵。"""
            key = ("matrix_counts", "matrix_probability", "matrix_budget")[index]
            self._fill_matrix(table, self.data.get(key) or [], index == 1)

        chooser.currentIndexChanged.connect(refresh)
        refresh(0)
        return page

    def _fill_matrix(self, table, matrix, as_probability):
        """把二维矩阵填进表格，首行首列为类别名。"""
        names = [translate_class_name(n) for n in metrics_mod.class_names(self.data)]
        size = len(names)
        table.clear()
        table.setRowCount(size)
        table.setColumnCount(size)
        table.setHorizontalHeaderLabels(names)
        table.setVerticalHeaderLabels(names)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for i in range(size):
            row = matrix[i] if i < len(matrix) else []
            for j in range(size):
                value = row[j] if j < len(row) else 0
                text = ("%.4f" % value) if as_probability else ("%d" % int(round(value)))
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(i, j, item)

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def _tab_accuracy(self):
        """精度页：OA/Kappa + 各类 PA/UA/F1 + 混淆矩阵。"""
        accuracy = self.data.get("accuracy")
        if not accuracy:
            label = QLabel(T("本次运行没有做精度评价。\n\n%s")
                           % (self.data.get("validation_note") or ""))
            label.setWordWrap(True)
            return label

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)

        headline = QLabel(
            T("总体精度 OA = %.4f　　Kappa = %.4f　　有效像元 = %d")
            % (accuracy.get("oa", 0), accuracy.get("kappa", 0), accuracy.get("total", 0))
        )
        headline.setStyleSheet("font-weight: bold;")
        layout.addWidget(headline)

        note = QLabel(accuracy_note(self.data))
        note.setWordWrap(True)
        layout.addWidget(note)

        names = [translate_class_name(n) for n in metrics_mod.class_names(self.data)]
        by_class = QTableWidget(len(names), 4)
        by_class.setHorizontalHeaderLabels([T("类别"), "PA", "UA", "F1"])
        by_class.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, name in enumerate(names):
            values = [name]
            for key in ("pa", "ua", "f1"):
                series = accuracy.get(key) or []
                values.append("%.4f" % (series[i] if i < len(series) else 0))
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter if column else Qt.AlignmentFlag.AlignLeft)
                by_class.setItem(i, column, item)
        by_class.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(by_class)

        confusion = QTableWidget()
        layout.addWidget(confusion)
        self._fill_matrix(confusion, accuracy.get("confusion") or [], False)
        return page

    def _tab_importance(self):
        """特征重要性页：按降序排表。"""
        items = self.data.get("feature_importance") or []
        if not items:
            label = QLabel(T("本次没有训练随机森林（或复用了外部模型），因此没有特征重要性。"))
            label.setWordWrap(True)
            return label

        table = QTableWidget(len(items), 2)
        table.setHorizontalHeaderLabels([T("驱动因子"), T("重要性")])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, item in enumerate(items):
            name = QTableWidgetItem(str(item.get("name", "")))
            value = QTableWidgetItem("%.4f" % (item.get("importance") or 0))
            value.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 0, name)
            table.setItem(i, 1, value)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _tab_figures(self):
        """图集页：所有生成的 PNG 竖排，按宽度自适应缩放。"""
        figures = metrics_mod.figure_paths(self.data)
        if not figures:
            label = QLabel(
            T("本次没有生成图表。\n\n提示：把「图表目录」留空会导致引擎一张图都不出。")
        )
            label.setWordWrap(True)
            return label

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        for title, path in figures:
            layout.addWidget(_ScaledImage(title, path))
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll


def accuracy_note(data):
    """把精度评价的口径说明成人话。

    :param data: metrics 字典。
    :returns: 一句说明。
    """
    note = data.get("validation_note") or ""
    baseline = data.get("baseline_oa")
    if baseline is not None:
        note += T("　　未变化基线 OA = %.4f（预测改动越少，越接近这个值）") % baseline
    return note
