# -*- coding: utf-8 -*-
"""以子进程方式运行 CA-Markov 引擎。

三个必须做对的点：

1. **两个 reader 线程**。引擎在随机森林训练期间可能几分钟不打一行输出，
   若主线程阻塞在 ``readline()``，就永远轮不到检查取消；而只读 stdout 不读
   stderr 又会让 traceback 写满管道缓冲、子进程卡死。
2. **进度单调化**。引擎在数据 ≥3 期时会先报 0.17/0.23（读盘）再报 0.10
   （统计矩阵），直接透传会让进度条倒退。
3. **杀进程树**。引擎用 ``n_jobs=-1`` 训练随机森林，joblib 会派生 worker；
   只 kill 父进程会留下孤儿。Windows 用 ``taskkill /T /F``。

本模块不 import QGIS：进度/日志/取消都通过回调注入，因此可脱离 QGIS 用假
feedback 做端到端测试。
"""

import os
import queue
import subprocess
import sys
import threading

from . import protocol


class EngineRunResult:
    """一次引擎调用结束后拿到的全部信息。"""

    def __init__(self):
        self.exit_code = None
        self.cancelled = False
        self.infos = []
        self.warnings = []
        self.stderr_tail = ""
        self.elapsed_seconds = None

    @property
    def ok(self):
        """是否成功（未取消且退出码为 0）。"""
        return not self.cancelled and self.exit_code == 0

    def error_message(self):
        """把非零退出码翻译成用户能看懂的一句话。

        引擎约定：1 = 参数或数据错误，2 = 运行时异常（含 ``KeyError`` 之类的裸栈）。
        """
        if self.cancelled:
            return "操作已取消"
        if self.exit_code == 0:
            return ""
        if self.exit_code == 1:
            head = "CA-Markov 参数或数据有误"
        else:
            head = "CA-Markov 引擎运行失败（退出码 %s）" % self.exit_code
        tail = self.stderr_tail.strip()
        return head if not tail else head + "\n\n" + tail


def run_engine(
    python_exe,
    engine_script,
    job_path,
    on_progress=None,
    on_info=None,
    on_warn=None,
    is_cancelled=None,
    poll_interval=0.2,
    timeout_seconds=0,
):
    """运行一次引擎。

    :param python_exe: 解释器路径。
    :param engine_script: ``camarkov_engine.py`` 的绝对路径。
    :param job_path: job.json 的绝对路径。
    :param on_progress: 回调 ``(percent:int, text:str)``。
    :param on_info: 回调 ``(text)``。
    :param on_warn: 回调 ``(text)``。
    :param is_cancelled: 回调 ``() -> bool``，返回 True 时杀进程并返回。
    :param poll_interval: 轮询间隔秒数；越小取消越快，默认 0.2。
    :param timeout_seconds: 超时秒数，0 表示不限。
    :returns: :class:`EngineRunResult`。
    """
    result = EngineRunResult()
    tracker = protocol.ProgressTracker()
    started = _now()

    env = os.environ.copy()
    # QGIS 的 GDAL/PROJ 环境变量会与 rasterio 自带的 GDAL 抢数据目录，
    # 清掉它们；引擎跑在独立子进程里，不需要 QGIS 的那一套。
    for key in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA", "GDAL_DRIVER_PATH"):
        env.pop(key, None)
    # QGIS 的启动脚本会设置 PYTHONHOME/PYTHONPATH 指向它自带的 stdlib。
    # 若子进程实际用的是另一个解释器（例如 conda），两者混用会让
    # platform.python_implementation() 之类的 stdlib 代码直接抛 ValueError。
    # 引擎只需要第三方包，不需要 QGIS 的绑定，因此统一清掉更安全。
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"

    command = [python_exe, "-u", engine_script, "--job", job_path]
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    try:
        process = subprocess.Popen(
            command,
            cwd=os.path.dirname(engine_script),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
    except OSError as exc:
        result.exit_code = -1
        result.stderr_tail = "无法启动 Python 进程：%s" % exc
        return result

    lines = queue.Queue()

    def pump(stream, tag):
        """在子线程里阻塞读一行，塞进队列；流结束时塞一个 None 作为哨兵。"""
        try:
            for line in stream:
                lines.put((tag, line))
        except Exception:  # 进程被杀时读管道会抛，忽略即可
            pass
        finally:
            lines.put((tag, None))

    threading.Thread(target=pump, args=(process.stdout, "out"), daemon=True).start()
    threading.Thread(target=pump, args=(process.stderr, "err"), daemon=True).start()

    open_streams = 2
    stderr_parts = []
    cancelled = False

    while open_streams > 0:
        if is_cancelled is not None and is_cancelled():
            cancelled = True
            _kill_tree(process)
            break
        if timeout_seconds and (_now() - started) > timeout_seconds:
            _kill_tree(process)
            result.exit_code = -2
            result.stderr_tail = "运行超过 %d 秒，已强制结束。" % timeout_seconds
            result.elapsed_seconds = _now() - started
            return result
        try:
            tag, line = lines.get(timeout=poll_interval)
        except queue.Empty:
            if process.poll() is not None:
                # 进程已退出但队列暂时没数据：再等一轮把残留读完
                continue
            continue

        if line is None:
            open_streams -= 1
            continue

        if tag == "err":
            stderr_parts.append(line)
            # 只保留尾部，避免 traceback 无限增长
            if len(stderr_parts) > 400:
                del stderr_parts[:200]
            continue
        _dispatch(line, tracker, on_progress, on_info, on_warn)

    try:
        result.exit_code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        result.exit_code = -2

    # 显式关掉管道：否则每次运行都会漏两个文件句柄
    for stream in (process.stdout, process.stderr):
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass

    result.elapsed_seconds = _now() - started
    result.cancelled = cancelled
    result.stderr_tail = _tail("\n".join(p.strip() for p in stderr_parts if p.strip()), 4000)

    if cancelled:
        result.exit_code = None
    else:
        # 收尾时补满进度，避免停在 99%
        if on_progress is not None:
            on_progress(100, "")
    return result


def _dispatch(line, tracker, on_progress, on_info, on_warn):
    """把一行原始输出分派给对应回调。"""
    kind, payload = protocol.parse_line(line)
    if kind == protocol.PROGRESS:
        frac, message = payload
        percent, changed = tracker.feed(frac, message)
        if on_progress is not None:
            on_progress(percent, message if changed else "")
    elif kind == protocol.INFO:
        if on_info is not None and payload:
            on_info(payload)
    elif kind == protocol.WARN:
        if on_warn is not None and payload:
            on_warn(payload)
    # DONE 与其它行忽略：进度条已由最后一条 PROGRESS 收尾


def _kill_tree(process):
    """杀掉进程树。

    引擎的 joblib 会用多进程训练随机森林，只 kill 父进程会留下孤儿，
    所以 Windows 上走 ``taskkill /T /F``，其它平台杀进程组。
    """
    if process is None:
        return
    if sys.platform.startswith("win"):
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), 9)
        except Exception:
            pass
    try:
        process.kill()
    except Exception:
        pass
    try:
        process.wait(timeout=10)
    except Exception:
        pass


def _tail(text, limit):
    """取文本末尾若干字符，保留报错最有价值的部分。"""
    if not text:
        return ""
    return text if len(text) <= limit else "..." + text[-limit:]


def _now():
    """单调时钟秒数。"""
    import time

    return time.monotonic()
