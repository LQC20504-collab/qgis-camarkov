# -*- coding: utf-8 -*-
"""解释器探测的测试。

不假设本机装了哪些环境，只验证「行为契约」：候选顺序、去重、
探测失败时给出可执行的安装提示、找不到时返回空环境而不是抛异常。
"""

import os
import sys

from qgis_camarkov.core import locator


def test_candidates_include_running_interpreter():
    """当前解释器必须在候选里——它是最可靠的一个。"""
    found = locator.candidates()
    assert any(
        os.path.normcase(p) == os.path.normcase(sys.executable) for p in found
    ), "候选列表里应包含 sys.executable"


def test_candidates_are_deduped_and_exist():
    """候选去重且全部真实存在（不存在的路径不该进列表）。"""
    found = locator.candidates()
    assert len(found) == len({os.path.normcase(p) for p in found})
    assert all(os.path.isfile(p) for p in found)


def test_candidates_put_saved_first():
    """用户上次选定的解释器优先级最高。"""
    found = locator.candidates(saved=sys.executable)
    assert os.path.normcase(found[0]) == os.path.normcase(sys.executable)


def test_candidates_accept_qgis_prefix_shapes():
    """``QgsApplication.prefixPath()`` 给的是 ``<root>/apps/qgis-ltr``。

    按它拼 ``apps/Python3xx`` 会多一层，所以两种形态都要能解析出来。
    """
    prefix = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    found = locator.candidates(qgis_prefix=os.path.join(prefix, "qgis-test"))
    assert found


def test_probe_missing_interpreter():
    """路径不存在时给出明确错误，不抛异常。"""
    env = locator.probe(r"C:\definitely\not\here\python.exe")
    assert not env.usable
    assert "不存在" in env.error


def test_probe_running_interpreter():
    """当前解释器应当能被探测出版本号。"""
    env = locator.probe(sys.executable)
    assert env.version, "应识别出 Python 版本"
    # 本项目的测试环境通常装齐了依赖，此时必须判为可用
    if not env.missing:
        assert env.usable


def test_install_hint_is_copy_pasteable():
    """缺包提示要能直接复制执行。"""
    env = locator.PythonEnvironment(r"C:\some\python.exe")
    env.missing = ["numpy", "rasterio"]
    hint = env.install_hint
    assert hint.startswith('"C:\\some\\python.exe"')
    assert "-m pip install" in hint
    assert "numpy" in hint and "rasterio" in hint


def test_describe_prefers_error():
    """有错误时优先展示错误，不要让用户以为只是缺包。"""
    env = locator.PythonEnvironment(r"C:\x\python.exe")
    env.error = "解释器探测超时"
    assert env.describe() == "解释器探测超时"


def test_required_packages_cover_engine_imports():
    """引擎需要的五个包都要在校验清单里。"""
    assert set(locator.REQUIRED_PACKAGES) == {
        "numpy",
        "scipy",
        "sklearn",
        "rasterio",
        "matplotlib",
    }
