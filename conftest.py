# -*- coding: utf-8 -*-
"""让测试能 import qgis_camarkov，无需安装成包。

另外把界面语言固定为中文：本机系统 locale 通常是 en_US，不固定的话
那些断言中文文案的测试会全部失败。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qgis_camarkov import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def pin_language(monkeypatch):
    """每个测试都跑在中文界面下，结束后清掉缓存。"""
    monkeypatch.setenv("CAMARKOV_LANG", "zh")
    i18n.reset()
    yield
    i18n.reset()
