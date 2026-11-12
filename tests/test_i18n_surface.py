# -*- coding: utf-8 -*-
"""真实 QGIS 环境下的英文渲染（需要 qgis.gui，用 ``pytest -m qgis`` 跑）。"""

from types import SimpleNamespace

import pytest

pytest.importorskip("qgis.gui")

from qgis_camarkov import i18n  # noqa: E402
from qgis_camarkov.core import metrics as metrics_mod  # noqa: E402
from qgis_camarkov.gui.result_dock import CamarkovResultDock  # noqa: E402
from qgis_camarkov.provider import CamarkovProvider  # noqa: E402


def sample_metrics():
    """一份最小可渲染的 metrics。"""
    return {
        "mode": "predict",
        "classes": [
            {"name": "耕地", "base": 1.5, "end": 2.0, "pred": 3.0, "change_pct": 50.0},
            {"name": "类别 2", "base": 1.0, "end": 1.0, "pred": 1.0, "change_pct": 0.0},
        ],
        "accuracy": {"oa": 0.9, "kappa": 0.8},
        "pixel_area_km2": 0,
        "warnings": ["demo"],
        "figures": {},
    }


@pytest.mark.qgis
def test_dock_overview_is_english(monkeypatch):
    """概览 HTML 全部英文，类别名也在显示层翻译。"""
    monkeypatch.setenv("CAMARKOV_LANG", "en")
    i18n.reset()
    try:
        html = CamarkovResultDock._overview_html(SimpleNamespace(data=sample_metrics()))
        assert "Area statistics" in html
        assert "Cropland" in html
        assert "Class 2" in html
        assert "Overall accuracy" in html
        assert "类别" not in html
        assert "基期" not in html
    finally:
        i18n.reset()


@pytest.mark.qgis
def test_summary_is_english(monkeypatch):
    """摘要行按英文拼装。"""
    monkeypatch.setenv("CAMARKOV_LANG", "en")
    i18n.reset()
    try:
        text = metrics_mod.summary(sample_metrics())
        assert text.startswith("Prediction")
        assert "Accuracy OA=" in text
    finally:
        i18n.reset()


@pytest.mark.qgis
def test_provider_version_matches_metadata():
    """算法面板显示的版本号必须跟 metadata.txt 一致。"""
    assert CamarkovProvider().versionInfo() == "0.1.3"
