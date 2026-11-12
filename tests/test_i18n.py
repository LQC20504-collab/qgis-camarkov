# -*- coding: utf-8 -*-
"""界面翻译层的行为：切换、回退、格式化与字典完整性。"""

import os
import subprocess
import sys

import pytest

from qgis_camarkov import i18n
from qgis_camarkov.i18n_en import EN

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def english(monkeypatch):
    """把进程切到英文，结束后清缓存。"""
    monkeypatch.setenv("CAMARKOV_LANG", "en")
    i18n.reset()
    yield
    i18n.reset()


def test_chinese_under_pin():
    """conftest 固定中文时，翻译层原样返回。"""
    assert i18n.current() == "zh"
    assert i18n.T("概览") == "概览"


def test_switch_to_english(english):
    assert i18n.current() == "en"
    assert i18n.T("概览") == "Overview"
    assert i18n.T("特征重要性") == "Feature importance"


def test_unknown_key_falls_back(english):
    assert i18n.T("这条没有翻译") == "这条没有翻译"
    assert i18n.T("") == ""


def test_non_string_passthrough(english):
    assert i18n.T(None) is None
    assert i18n.T(3) == 3


def test_format_arguments_preserved(english):
    assert i18n.T("第 %d 期图层无效。", 3) == "Period 3 layer is invalid."
    assert i18n.T("精度 OA=%.4f Kappa=%.4f", 0.9, 0.8) == "Accuracy OA=0.9000 Kappa=0.8000"


def test_percent_literal_safe(english):
    """选项标签里有裸 %，不带参数时不能去格式化。"""
    assert i18n.T("分位数 2%–98%（推荐）").startswith("Quantile")


def test_bad_format_does_not_raise(english):
    """参数个数不对时返回模板，绝不让 QGIS 抛异常。"""
    assert i18n.T("第 %d 期图层无效。", 1, 2) == "Period %d layer is invalid."


def test_class_name_translation(english):
    assert i18n.translate_class_name("类别 3") == "Class 3"
    assert i18n.translate_class_name("耕地") == "Cropland"
    assert i18n.translate_class_name("自定义类") == "自定义类"


def test_class_name_untouched_in_chinese():
    """数据层不翻译：中文界面下类别名保持原样。"""
    assert i18n.translate_class_name("类别 3") == "类别 3"


def test_dictionary_shape():
    """条目够多、没有空值、译文里不残留汉字。"""
    assert len(EN) >= 150
    for key, value in EN.items():
        assert value, key
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in value), key


def test_scanner_reports_clean():
    """静态检查器必须零违规。"""
    result = subprocess.run(
        [sys.executable, os.path.join(REPO, "scripts", "check_i18n.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
