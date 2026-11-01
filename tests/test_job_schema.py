# -*- coding: utf-8 -*-
"""job.json 组装的测试。

重点不是「能不能跑」，而是**那些反直觉的契约**：
死键不能出现、预测驱动因子必须在引擎读取的层级、缺路径要在这里就报错。
这些如果写错，引擎不会给友好的错误，而是静默跑偏或抛裸 traceback。
"""

import pytest

from qgis_camarkov.core import job_schema

PERIODS = [
    {"path": r"C:\data\2010.tif", "band": 1},
    {"path": r"C:\data\2015.tif", "band": 1},
    {"path": r"C:\data\2020.tif", "band": 1},
]


def _job(**kwargs):
    """用一份最小合法参数构造 job，便于各用例只覆盖自己关心的字段。"""
    params = dict(
        mode="predict",
        periods=PERIODS,
        class_count=4,
        suitability_mode="none",
    )
    params.update(kwargs)
    return job_schema.build_job(**params)


def test_minimal_job_has_required_keys():
    """最基本的 job 要含引擎读取的全部核心键。"""
    job = _job()
    for key in (
        "mode",
        "periods",
        "nodata",
        "class_count",
        "class_names",
        "transition_source",
        "steps",
        "neighborhood_size",
        "suitability_mode",
        "weights",
        "validation",
        "outputs",
        "rf",
        "lang",
    ):
        assert key in job, "缺少键 %s" % key


def test_dead_keys_are_absent():
    """四个死键一个都不能写。

    * ``periods[].year`` —— 引擎不读，只用于桌面版界面显示；
    * 顶层 ``seed`` —— 引擎只读 ``rf.train.seed``；
    * ``rf.train.predict_drivers`` —— 引擎只读 ``rf.predict_drivers``；
    * ``external.band`` —— 引擎只用 ``band_mode``。
    """
    job = _job(
        class_count=9,
        external_path=r"C:\data\atlas.tif",
        suitability_mode="external",
        seed=7,
    )
    assert all("year" not in period for period in job["periods"])
    assert "seed" not in job
    assert "predict_drivers" not in job["rf"]["train"]
    assert "band" not in job["external"]


def test_predict_drivers_written_at_rf_level():
    """预测驱动因子必须落在 ``rf.predict_drivers``（引擎唯一读取的层级）。"""
    job = _job(
        suitability_mode="rf",
        train_drivers=[{"path": r"C:\data\dem.tif", "band": 1}],
        predict_drivers=[{"path": r"C:\data\dem2029.tif", "band": 1}],
    )
    assert job["rf"]["predict_drivers"][0]["path"].endswith("dem2029.tif")
    assert "predict_drivers" not in job["rf"]["train"]


def test_missing_period_path_raises_early():
    """缺 path 必须在这里报错。

    若放过去，引擎会抛 ``KeyError``，落进兜底 ``except`` 后**退出码是 2**
    而不是 1，用户只会看到一段裸 traceback。
    """
    with pytest.raises(ValueError):
        job_schema.build_job(
            mode="predict",
            periods=[{"path": r"C:\a.tif"}, {"band": 1}],
            class_count=4,
        )


def test_less_than_two_periods_raises():
    """至少两期，否则引擎无法统计转移矩阵。"""
    with pytest.raises(ValueError):
        job_schema.build_job(mode="predict", periods=PERIODS[:1], class_count=4)


def test_unknown_enum_raises():
    """未知的模式/来源要立刻报错，不要留给引擎。"""
    with pytest.raises(ValueError):
        _job(suitability_mode="magic")
    with pytest.raises(ValueError):
        _job(transition_source="magic")


def test_class_names_default_for_non_clcd_count():
    """非 9 类时不要硬套 CLCD 类名。

    4 类里第 3 类很可能是水体，套成「草地」会让报告与图例全部错位。
    """
    names = job_schema.default_class_names(4, 0)
    assert names == ["无效值", "类别 1", "类别 2", "类别 3"]


def test_class_names_use_clcd_when_nine():
    """正好 9 类时才用 CLCD 类名。"""
    names = job_schema.default_class_names(9, 0)
    assert names[0] == "无效值"
    assert names[1] == "耕地"
    assert names[8] == "不透水面"


def test_parse_class_names_fills_and_truncates():
    """用户输入不足时补齐、超出时截断。"""
    assert job_schema.parse_class_names("无效,耕地", 4, 0) == ["无效", "耕地", "类别 2", "类别 3"]
    assert job_schema.parse_class_names("a,b,c,d,e", 3, 0) == ["a", "b", "c"]
    # 空输入回落到默认名
    assert job_schema.parse_class_names("", 4, 0) == job_schema.default_class_names(4, 0)


def test_factor_matrix_is_flat_list():
    """QGIS 的矩阵参数是一维扁平列表，按 4 个一组切。"""
    values = [
        r"C:\data\dem.tif", 1, 0.6, 1,
        r"C:\data\road.tif", 2, 0.4, -1,
    ]
    factors = job_schema.parse_factor_matrix(values)
    assert len(factors) == 2
    assert factors[0] == {"path": r"C:\data\dem.tif", "band": 1, "weight": 0.6, "direction": "+"}
    assert factors[1]["band"] == 2
    assert factors[1]["direction"] == "-"


def test_factor_rows_with_empty_path_are_skipped():
    """矩阵允许留空行，空路径的行直接跳过。"""
    values = ["", 1, 0.5, 1, r"C:\ok.tif", 1, 0.5, 1]
    assert len(job_schema.parse_factor_matrix(values)) == 1


def test_direction_accepts_several_notations():
    """方向列允许 1/-1、+/-、正向/负向。"""
    assert job_schema._as_direction("-1") == "-"
    assert job_schema._as_direction("-") == "-"
    assert job_schema._as_direction("负向") == "-"
    assert job_schema._as_direction("1") == "+"
    assert job_schema._as_direction("") == "+"


def test_factors_only_written_in_factor_mode():
    """非 factor 模式不写因子，避免引擎收到无意义的键。"""
    job = _job(suitability_mode="none", factors=[{"path": "x.tif", "band": 1}])
    assert job["factors"] == []


def test_outputs_drop_empty_values():
    """空输出项要被丢掉，不能把 None 当成路径传给引擎。"""
    job = _job(outputs={"metrics": "m.json", "report": "", "raster": None})
    assert job["outputs"] == {"metrics": "m.json"}


def test_lang_normalised():
    """语言字段归一成 zh/en 两种。"""
    assert _job(lang="en")["lang"] == "en"
    assert _job(lang="en-US")["lang"] == "en"
    assert _job(lang="zh")["lang"] == "zh"
    assert _job(lang="")["lang"] == "zh"
