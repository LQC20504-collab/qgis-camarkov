# -*- coding: utf-8 -*-
"""QGIS 集成测试：通过 ``qgis_process`` 真正跑一遍算法。

需要本机装了 QGIS。找不到 ``qgis_process`` 时整组跳过，不会让 CI 误判失败。

运行方式::

    pytest -m qgis
    # 或显式指定 QGIS 路径
    set QGIS_PROCESS=C:\\Program Files\\QGIS 3.40.15\\bin\\qgis_process-qgis-ltr.bat
"""

import glob
import json
import os
import subprocess

import pytest

pytestmark = pytest.mark.qgis

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _qgis_process():
    """定位 qgis_process 包装脚本。

    优先读环境变量，其次在常见安装位置里找。
    """
    explicit = os.environ.get("QGIS_PROCESS")
    if explicit and os.path.isfile(explicit):
        return explicit
    patterns = [
        r"C:\Program Files\QGIS *\bin\qgis_process-qgis-ltr.bat",
        r"C:\Program Files\QGIS *\bin\qgis_process.bat",
        r"C:\OSGeo4W\bin\qgis_process-qgis-ltr.bat",
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    return ""


def _env():
    """构造子进程环境：把仓库根加进 QGIS_PLUGINPATH。

    必须清掉 ``PYTHONHOME`` / ``PYTHONPATH``：如果 pytest 本身跑在 conda 里，
    这两个变量会指向 conda 的 stdlib，而 qgis_process 用的是 QGIS 自带解释器。
    两者混用会让 QGIS 在初始化时直接以 0xC0000409 崩溃（不是 Python 异常，
    没有 traceback，只有退出码）。
    """
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
        env.pop(key, None)
    existing = env.get("QGIS_PLUGINPATH", "")
    env["QGIS_PLUGINPATH"] = REPO + (";" + existing if existing else "")
    return env


@pytest.fixture(scope="module")
def qp():
    """返回可用的 qgis_process 路径，没有就跳过整组。"""
    path = _qgis_process()
    if not path:
        pytest.skip("未找到 qgis_process，跳过 QGIS 集成测试")
    return path


@pytest.fixture(scope="module")
def algorithms(qp):
    """取算法清单；插件不可见时给出明确原因并跳过。"""
    completed = subprocess.run(
        [qp, "list", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(),
        timeout=300,
    )
    output = _decode(completed.stdout) + _decode(completed.stderr)
    if "camarkov:" not in output:
        pytest.skip(
            "qgis_process 看不到 camarkov 算法。多半是插件未启用：\n"
            "  python scripts/enable_plugin.py\n" + output[-800:]
        )
    return output


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    """生成三期合成分类栅格。"""
    rasterio = pytest.importorskip("rasterio")
    from tests import fixtures as fx  # noqa: F401  (确保模块可导入)
    import sys

    sys.path.insert(0, REPO)
    from tests.fixtures import make_fixtures

    directory = tmp_path_factory.mktemp("camk_fx")
    return make_fixtures(str(directory))


def _decode(raw):
    """解码 qgis_process 的输出。

    ``--json`` 的 stdout 是 UTF-8，但**错误信息走的是控制台代码页**（中文 Windows
    上是 GBK）。先按 UTF-8 解，出现替换字符再按本地代码页重解一次。
    """
    text = raw.decode("utf-8", "replace")
    if "\ufffd" in text:
        try:
            text = raw.decode("mbcs", "replace")
        except LookupError:
            text = raw.decode("gbk", "replace")
    return text


def _run(qp, algorithm, inputs, timeout=1800):
    """用 stdin JSON 跑一个算法（矩阵类参数只能这么传）。"""
    payload = json.dumps({"inputs": inputs}, ensure_ascii=False)
    completed = subprocess.run(
        [qp, "run", algorithm, "-"],
        input=payload.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(),
        timeout=timeout,
    )
    return completed.returncode, _decode(completed.stdout), _decode(completed.stderr)


def test_three_algorithms_visible(algorithms):
    """三个算法 id 都要出现在 list 里。"""
    for algorithm in ("camarkov:analyze", "camarkov:train", "camarkov:predict"):
        assert algorithm in algorithms, "缺少算法 %s" % algorithm


def test_analyze_writes_metrics(qp, algorithms, fixtures, tmp_path):
    """转移分析：产出 metrics.json，且关键键齐全。"""
    metrics = tmp_path / "metrics.json"
    code, output, errors = _run(
        qp,
        "camarkov:analyze",
        {
            "PERIODS": fixtures,
            "NODATA": 0,
            "CLASS_COUNT": 4,
            "TRANSITION_SOURCE": 1,
            "OUTPUT_METRICS": str(metrics),
        },
    )
    assert code == 0, output[-2000:] + errors[-2000:]
    data = json.loads(metrics.read_text(encoding="utf-8"))

    for key in (
        "mode",
        "classes",
        "matrix_counts",
        "matrix_probability",
        "matrix_budget",
        "accuracy",
        "figures",
    ):
        assert key in data
    assert data["mode"] == "analyze"
    # analyze 不做精度评价
    assert data["accuracy"] is None
    # 4 类时不应硬套 CLCD 类名（第 3 类真值是水体，不能叫「草地」）
    names = [row["name"] for row in data["classes"]]
    assert names[0] == "无效值"
    assert names[3] == "类别 3"


def test_predict_writes_raster_and_figures(qp, algorithms, fixtures, tmp_path):
    """变化预测：栅格 + 报告 + 图表 + 指标，且栅格带类别色表。"""
    raster = tmp_path / "pred.tif"
    metrics = tmp_path / "metrics.json"
    report = tmp_path / "report.txt"
    figs = tmp_path / "figs"

    code, output, errors = _run(
        qp,
        "camarkov:predict",
        {
            "PERIODS": fixtures,
            "NODATA": 0,
            "CLASS_COUNT": 4,
            "TRANSITION_SOURCE": 1,
            "SUITABILITY_MODE": 3,
            "STEPS": 1,
            "OUTPUT_RASTER": str(raster),
            "OUTPUT_METRICS": str(metrics),
            "OUTPUT_REPORT": str(report),
            "OUTPUT_FIG_DIR": str(figs),
        },
    )
    assert code == 0, output[-2000:] + errors[-2000:]

    assert raster.is_file() and metrics.is_file() and report.is_file()
    assert len(list(figs.glob("*.png"))) >= 4

    data = json.loads(metrics.read_text(encoding="utf-8"))
    assert data["mode"] == "predict"
    assert data["accuracy"] is not None

    rasterio = pytest.importorskip("rasterio")
    with rasterio.open(str(raster)) as dataset:
        assert dataset.width == 100 and dataset.height == 80
        assert dataset.count == 1
        # ≤255 类时引擎写 uint8 并内嵌色彩表，QGIS 加载后直接按类别着色
        assert dataset.dtypes[0] == "uint8"
        assert len(dataset.colormap(1)) == 256


def test_predict_rejects_non_tiff_extension(qp, algorithms, fixtures, tmp_path):
    """输出后缀不是 .tif 时必须在开跑前就被拒绝。"""
    code, output, errors = _run(
        qp,
        "camarkov:predict",
        {
            "PERIODS": fixtures,
            "NODATA": 0,
            "CLASS_COUNT": 4,
            "SUITABILITY_MODE": 3,
            "OUTPUT_RASTER": str(tmp_path / "pred.img"),
            "OUTPUT_METRICS": str(tmp_path / "metrics.json"),
        },
    )
    assert code != 0
    combined = output + errors
    assert ".tif" in combined or "tif" in combined


def test_mismatched_grid_rejected(qp, algorithms, fixtures, tmp_path):
    """网格不一致要在开跑前拒绝，而不是让引擎跑一半才报错。"""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    import numpy as np

    other = tmp_path / "other.tif"
    with rasterio.open(
        str(other),
        "w",
        driver="GTiff",
        height=40,
        width=50,
        count=1,
        dtype="uint8",
        nodata=0,
        transform=from_origin(500000, 3500000, 60, 60),
        crs="EPSG:32650",
    ) as dataset:
        dataset.write(np.ones((40, 50), "uint8"), 1)

    code, output, errors = _run(
        qp,
        "camarkov:predict",
        {
            "PERIODS": [fixtures[0], str(other)],
            "NODATA": 0,
            "CLASS_COUNT": 4,
            "SUITABILITY_MODE": 3,
            "OUTPUT_RASTER": str(tmp_path / "pred.tif"),
            "OUTPUT_METRICS": str(tmp_path / "metrics.json"),
        },
    )
    assert code != 0
    assert "尺寸" in output + errors or "网格" in output + errors
