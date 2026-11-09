# -*- coding: utf-8 -*-
"""引擎自检：直接跑随包附带的引擎副本的 ``--selftest``。

这一步能覆盖转移矩阵、最大余数预算、邻域与精度指标等纯函数逻辑，
而且**不需要 rasterio**（引擎在 import rasterio 之前就返回了），
只需要 numpy + scipy。
"""

import os
import subprocess
import sys

import pytest

ENGINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "qgis_camarkov",
    "resources",
    "engine",
    "camarkov_engine.py",
)


@pytest.fixture(scope="module")
def engine_script():
    """确认引擎脚本在仓库里；不在就跳过而不是误判失败。"""
    if not os.path.isfile(ENGINE):
        pytest.skip("找不到引擎脚本：%s" % ENGINE)
    return ENGINE


def _has_runtime():
    """引擎自检至少需要 numpy 与 scipy。"""
    import importlib.util

    return all(importlib.util.find_spec(m) for m in ("numpy", "scipy"))


def test_engine_selftest_passes(engine_script):
    """``--selftest`` 必须 16 项全过、退出码 0。"""
    if not _has_runtime():
        pytest.skip("缺少 numpy/scipy，无法跑引擎自检")

    completed = subprocess.run(
        [sys.executable, "-u", engine_script, "--selftest"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, "引擎自检失败：\n%s" % output
    assert "0 项失败" in output
    assert "[失败]" not in output


def test_engine_rejects_missing_job_argument(engine_script):
    """不给任何参数时应打印用法并返回非零，而不是崩栈。"""
    completed = subprocess.run(
        [sys.executable, "-u", engine_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert completed.returncode == 1
    assert "用法" in (completed.stdout + completed.stderr)
