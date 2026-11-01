# -*- coding: utf-8 -*-
"""行协议解析与进度单调化的测试。"""

from qgis_camarkov.core import protocol


def test_parse_progress():
    """进度行要拆成浮点小数与阶段文本。"""
    kind, payload = protocol.parse_line("@@PROGRESS 0.1234 CA 分配 第 1/3 步\n")
    assert kind == protocol.PROGRESS
    frac, message = payload
    assert abs(frac - 0.1234) < 1e-9
    # 阶段文本自身可以含空格，只按第一个空格切
    assert message == "CA 分配 第 1/3 步"


def test_parse_progress_without_text():
    """没有阶段文本时消息为空串，不能报错。"""
    kind, payload = protocol.parse_line("@@PROGRESS 0.5000 ")
    assert kind == protocol.PROGRESS
    assert payload == (0.5, "")


def test_parse_info_warn_done():
    """INFO/WARN/DONE 各自识别，且去掉前缀与空白。"""
    assert protocol.parse_line("@@INFO 读取第 1 期\n") == (protocol.INFO, "读取第 1 期")
    assert protocol.parse_line("@@WARN 预算未落实") == (protocol.WARN, "预算未落实")
    kind, payload = protocol.parse_line("@@DONE 12.3")
    assert kind == protocol.DONE
    assert payload == "12.3"


def test_parse_other():
    """普通输出（例如 traceback 的一行）归为 other，不参与进度。"""
    kind, payload = protocol.parse_line("Traceback (most recent call last):")
    assert kind == protocol.OTHER
    assert payload.startswith("Traceback")


def test_parse_bad_progress_number():
    """进度数字解析失败时不能崩，降级为 other。"""
    kind, _ = protocol.parse_line("@@PROGRESS abc 阶段")
    assert kind == protocol.OTHER


def test_progress_never_goes_backwards():
    """引擎在多期数据下会先报 0.23 再报 0.10，进度必须单调不减。

    这是真实存在的引擎行为：读盘阶段报 ``0.05 + 0.06*(k+1)``（3 期到 0.23），
    之后统计矩阵又从 0.10 开始。直接透传会让 QGIS 进度条回跳。
    """
    tracker = protocol.ProgressTracker()
    assert tracker.feed(0.17) == (17, False)
    assert tracker.feed(0.23) == (23, False)
    # 倒退的一条不应拉低进度
    assert tracker.feed(0.10, "统计转移矩阵") == (23, True)
    assert tracker.feed(0.50)[0] == 50


def test_progress_clamps_out_of_range():
    """超出 0..1 的值被夹紧，负数不会把进度条拉回去。"""
    tracker = protocol.ProgressTracker()
    assert tracker.feed(-1.0)[0] == 0
    assert tracker.feed(2.0)[0] == 100


def test_progress_text_only_reports_change():
    """同一阶段文本重复出现时返回 False，避免刷日志。"""
    tracker = protocol.ProgressTracker()
    assert tracker.feed(0.1, "读盘") == (10, True)
    assert tracker.feed(0.2, "读盘") == (20, False)
    assert tracker.feed(0.3, "训练") == (30, True)
