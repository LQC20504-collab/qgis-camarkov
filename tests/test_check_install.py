# -*- coding: utf-8 -*-
"""``scripts/check_install.py`` 的测试。

这个脚本是给用户排查安装问题用的，一旦它自己判断错了，反而会把人带偏，
所以这里把它那几个判据都钉住。
"""

import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check_install.py")


@pytest.fixture(scope="module")
def check():
    """按路径加载脚本模块（它不在包内，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location("check_install", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_plugin(root, relative, metadata_text):
    """在 ``root/relative`` 下造一个最小插件目录。"""
    directory = os.path.join(str(root), *relative.split("/"))
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "metadata.txt"), "w", encoding="utf-8") as handle:
        handle.write(metadata_text)
    engine_dir = os.path.join(directory, "resources", "engine")
    os.makedirs(engine_dir, exist_ok=True)
    open(os.path.join(engine_dir, "camarkov_engine.py"), "w", encoding="utf-8").close()
    return directory


GOOD_META = """[general]
name=CA-Markov
description=test
version=0.1.0
qgisMinimumVersion=3.28
hasProcessingProvider=True
"""


def test_find_installed_detects_correct_layout(check, tmp_path):
    """正常布局（顶层就是 qgis_camarkov）应被识别。"""
    _make_plugin(tmp_path, "qgis_camarkov", GOOD_META)
    found = check.find_installed(str(tmp_path))
    assert [name for name, _ in found] == ["qgis_camarkov"]


def test_find_installed_detects_nested_layout(check, tmp_path):
    """源码包布局（多一层 qgis-camarkov-master）必须也能被发现。

    这正是用户踩到的坑：如果脚本只找顶层，就会报「没有安装」，反而误导。
    """
    _make_plugin(tmp_path, "qgis-camarkov-master/qgis_camarkov", GOOD_META)
    found = check.find_installed(str(tmp_path))
    assert [name for name, _ in found] == ["qgis-camarkov-master/qgis_camarkov"]


def test_main_fails_on_nested_layout(check, tmp_path, capsys):
    """嵌套布局应判定为失败，并打印出该删哪个目录。"""
    _make_plugin(tmp_path, "qgis-camarkov-master/qgis_camarkov", GOOD_META)
    code = check.main(["--plugins", str(tmp_path)])
    output = capsys.readouterr().out
    assert code == 1
    assert "安装位置不对" in output
    assert "rmdir" in output


def test_main_passes_on_correct_layout(check, tmp_path, capsys):
    """正确布局且已启用时，结论应是「安装正确」。"""
    plugins = tmp_path / "plugins"
    _make_plugin(plugins, "qgis_camarkov", GOOD_META)

    profile = tmp_path / "profile"
    (profile / "QGIS").mkdir(parents=True)
    (profile / "QGIS" / "QGIS3.ini").write_text(
        "[PythonPlugins]\nqgis_camarkov=true\n", encoding="utf-8"
    )

    code = check.main(["--plugins", str(plugins), "--profile", str(profile)])
    output = capsys.readouterr().out
    assert code == 0, output
    assert "安装正确" in output


def test_metadata_with_percent_is_rejected(check, tmp_path):
    """metadata.txt 含 % 会让 configparser 插值失败，必须报出来。"""
    path = _make_plugin(
        tmp_path, "qgis_camarkov", GOOD_META.replace("description=test", "description=50% 覆盖")
    )
    metadata = os.path.join(path, "metadata.txt")
    problems, has_provider = check.check_metadata(metadata)
    assert problems
    assert any("百分号" in p for p in problems)


def test_metadata_without_provider_flag_is_rejected(check, tmp_path):
    """缺 hasProcessingProvider 时无头模式看不到算法，必须提示。"""
    text = GOOD_META.replace("hasProcessingProvider=True\n", "")
    path = _make_plugin(tmp_path, "qgis_camarkov", text)
    problems, has_provider = check.check_metadata(os.path.join(path, "metadata.txt"))
    assert has_provider is False
    assert any("hasProcessingProvider" in p for p in problems)
