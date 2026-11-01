# -*- coding: utf-8 -*-
"""引擎标准输出行协议解析。

引擎（``camarkov_engine.py``）向 stdout 逐行输出四类记录：

    @@PROGRESS <0..1 四位小数> <阶段文本>
    @@INFO <文本>
    @@WARN <文本>
    @@DONE <总耗时秒>

其余行一律忽略（引擎正常情况下不会有别的输出；异常栈走 stderr）。

本模块**不依赖 QGIS**，可以脱离 QGIS 单测。
"""

PROGRESS = "progress"
INFO = "info"
WARN = "warn"
DONE = "done"
OTHER = "other"

_PREFIX = "@@"


def parse_line(line):
    """解析一行引擎输出。

    :param line: 原始行（可含结尾换行）。
    :returns: ``(kind, payload)``。``kind`` 为上面的常量之一；
        进度记录的 ``payload`` 是 ``(frac, message)``，其余是去掉前缀的文本。
    """
    if line is None:
        return OTHER, ""
    text = line.rstrip("\r\n")
    if not text.startswith(_PREFIX):
        return OTHER, text

    if text.startswith("@@PROGRESS "):
        rest = text[11:].strip()
        # 只按第一个空格切分：阶段文本自身可以含空格
        frac_text, _, message = rest.partition(" ")
        try:
            frac = float(frac_text)
        except ValueError:
            return OTHER, text
        return PROGRESS, (frac, message.strip())

    if text.startswith("@@INFO "):
        return INFO, text[7:].strip()

    if text.startswith("@@WARN "):
        return WARN, text[7:].strip()

    if text.startswith("@@DONE"):
        return DONE, text[6:].strip()

    return OTHER, text


class ProgressTracker:
    """把引擎的进度换算成 QGIS 需要的 0..100 整数，并保证单调。

    引擎在参与统计的区间 ≥2 个（即数据 ≥3 期）时会**先报读盘 0.17/0.23，
    随后统计矩阵又报 0.10**，进度条因此会倒退。QGIS 的进度条对倒退的处理
    是直接回跳，观感很差，所以这里做单调化。
    """

    def __init__(self):
        """初始进度为 0。"""
        self._last = 0.0
        self._text = ""

    @property
    def fraction(self):
        """当前进度（0..1，单调不减）。"""
        return self._last

    @property
    def text(self):
        """当前阶段文本。"""
        return self._text

    def feed(self, frac, message=None):
        """喂入一条进度，返回 ``(percent, changed_text)``。

        :param frac: 引擎给的 0..1 进度。
        :param message: 阶段文本，可为空。
        :returns: ``(0..100 的整数, 是否是新阶段文本)``。
        """
        try:
            value = float(frac)
        except (TypeError, ValueError):
            value = self._last
        value = min(1.0, max(0.0, value))
        if value > self._last:
            self._last = value

        changed = False
        if message and message != self._text:
            self._text = message
            changed = True
        return int(round(self._last * 100)), changed
