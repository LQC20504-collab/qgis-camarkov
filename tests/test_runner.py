# -*- coding: utf-8 -*-
"""子进程 runner 的测试：进度回调、退出码映射、取消与杀进程树。

这里用一个「假引擎」脚本代替真实引擎——真实引擎太慢、依赖太重，
而 runner 关心的只是行协议、退出码与进程生命周期。
"""

import os
import sys
import textwrap
import time

from qgis_camarkov.core import runner

#: 一个可配置行为的假引擎：按参数决定输出进度还是卡住。
FAKE_ENGINE = textwrap.dedent(
    '''
    # -*- coding: utf-8 -*-
    import sys, time, json, os

    job = json.load(open(sys.argv[2], encoding="utf-8"))
    behaviour = job.get("behaviour")

    def emit(tag, text):
        sys.stdout.write("@@" + tag + " " + str(text) + "\\n")
        sys.stdout.flush()

    if behaviour == "slow":
        # 一直打进度不退出，用来测取消
        for i in range(200):
            emit("PROGRESS", "%.4f 慢速 %d" % (i / 200.0, i))
            time.sleep(0.05)

    elif behaviour == "backwards":
        # 先报大再报小，模拟引擎在多期数据下的真实行为
        for frac, msg in ((0.17, "读盘"), (0.23, "读盘"), (0.10, "统计矩阵"), (0.90, "写盘")):
            emit("PROGRESS", "%.4f %s" % (frac, msg))
        emit("INFO", "示例信息")
        emit("WARN", "示例警告")
        emit("DONE", "1.2")

    elif behaviour == "fail":
        sys.stderr.write("参数或数据错误：示例\\n")
        sys.exit(1)

    elif behaviour == "crash":
        # 真实引擎对未捕获异常显式返回 2（不是 Python 默认的 1）——
        # 否则 1 会同时代表「参数错误」和「代码崩了」，无法区分。
        import traceback
        traceback.print_exc()
        sys.exit(2)
    '''
)


def _write(tmp_path, name, content):
    """写一个 UTF-8 文件并返回路径。"""
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _start(tmp_path, behaviour):
    """写假引擎与 job，返回 (engine_path, job_path)。"""
    engine = _write(tmp_path, "fake_engine.py", FAKE_ENGINE)
    job = _write(tmp_path, "job.json", '{"behaviour": "%s"}' % behaviour)
    return engine, job


def test_success_emits_progress_and_finishes_at_100(tmp_path):
    """正常结束时进度必须补满 100，且阶段文本与警告被转发。"""
    engine, job = _start(tmp_path, "backwards")
    seen = {"progress": [], "info": [], "warn": []}

    result = runner.run_engine(
        sys.executable,
        engine,
        job,
        on_progress=lambda p, t: seen["progress"].append(p),
        on_info=seen["info"].append,
        on_warn=seen["warn"].append,
    )

    assert result.ok
    assert seen["info"] == ["示例信息"]
    assert seen["warn"] == ["示例警告"]
    # 进度单调不减，且最后一刻补到 100
    assert seen["progress"] == sorted(seen["progress"])
    assert seen["progress"][-1] == 100


def test_progress_does_not_regress(tmp_path):
    """引擎先报 0.23 再报 0.10，runner 不能把进度条拉回去。"""
    engine, job = _start(tmp_path, "backwards")
    seen = []
    runner.run_engine(sys.executable, engine, job, on_progress=lambda p, t: seen.append(p))
    # 23 之后不应再出现小于 23 的值
    after_peak = seen[seen.index(23):] if 23 in seen else seen
    assert all(value >= 23 for value in after_peak)


def test_non_zero_exit_maps_to_parameter_error(tmp_path):
    """退出码 1 表示参数/数据错误，banner 要与之匹配。"""
    engine, job = _start(tmp_path, "fail")
    result = runner.run_engine(sys.executable, engine, job)
    assert not result.ok
    assert result.exit_code == 1
    assert "参数或数据有误" in result.error_message()
    # stderr 内容要被带进错误信息
    assert "示例" in result.error_message()


def test_uncaught_exception_gives_runtime_error(tmp_path):
    """退出码非 1 时按「引擎运行失败」报告，并附 stderr 尾部。"""
    engine, job = _start(tmp_path, "crash")
    result = runner.run_engine(sys.executable, engine, job)
    assert not result.ok
    assert result.exit_code not in (0, 1)
    assert "运行失败" in result.error_message()


def test_cancel_kills_process_quickly(tmp_path):
    """取消要在很短时间内真正结束进程，不能等脚本自己跑完。

    假引擎会跑 200 × 0.05s = 10 秒；取消若在 3 秒内返回，说明杀进程生效。
    """
    engine, job = _start(tmp_path, "slow")
    started = time.time()

    result = runner.run_engine(
        sys.executable,
        engine,
        job,
        is_cancelled=lambda: time.time() - started > 0.6,
        poll_interval=0.1,
    )

    elapsed = time.time() - started
    assert result.cancelled
    assert elapsed < 5.0, "取消后应在数秒内结束，实际耗时 %.1fs" % elapsed
    assert result.error_message() == "操作已取消"


def test_missing_interpreter_reports_failure(tmp_path):
    """解释器不存在时返回错误结果，而不是抛异常。"""
    engine, job = _start(tmp_path, "backwards")
    result = runner.run_engine(r"C:\no\such\python.exe", engine, job)
    assert not result.ok
    assert "无法启动" in result.stderr_tail


def test_timeout_kills_process(tmp_path):
    """超时按强制结束处理，并给出可读原因。"""
    engine, job = _start(tmp_path, "slow")
    result = runner.run_engine(
        sys.executable,
        engine,
        job,
        poll_interval=0.1,
        timeout_seconds=1,
    )
    assert not result.ok
    assert "超时" in result.error_message() or "强制结束" in result.error_message()
