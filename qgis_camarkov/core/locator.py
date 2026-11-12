# -*- coding: utf-8 -*-
"""定位可用的 Python 解释器，并校验引擎依赖。

顺序（本机实测只有 QGIS 自带的最省事）：

1. 用户上次选定（``QgsSettings: camarkov/python`` / 或显式传入 ``saved``）
2. 环境变量 ``CAMARKOV_PYTHON``
3. **QGIS 自带的解释器** ``<qgis_prefix>/apps/Python312/python.exe``
4. conda / 系统常见路径（含非系统盘）
5. ``PATH`` 里的 python

为什么 QGIS 自带的排这么前：本机实测它的 numpy/scipy/sklearn/rasterio/matplotlib
五个包全部可用，且版本与 QGIS 自身一致，用户无需再装 conda。引擎跑在**子进程**里，
因此即便它 import rasterio 也不会污染 QGIS 进程内的 GDAL。

校验只做 ``importlib.util.find_spec``（几毫秒），不真正 import，避免启动时卡顿。

本模块不 import QGIS，qgis 前缀由调用方传入，因此可脱离 QGIS 单测。
"""

import os
import subprocess  # nosec B404
import sys
from ..i18n import T

#: 引擎 import 的第三方包（顺序与错误提示保持一致）。
REQUIRED_PACKAGES = ("numpy", "scipy", "sklearn", "rasterio", "matplotlib")

PROBE_TIMEOUT = 10


class PythonEnvironment:
    """一次探测的结果。"""

    def __init__(self, exe_path=""):
        """:param exe_path: 解释器路径。"""
        self.exe_path = exe_path or ""
        self.version = ""
        self.missing = []
        self.error = ""

    @property
    def usable(self):
        """是否可以直接拿来跑引擎（存在、能启动、依赖齐全）。"""
        return bool(self.exe_path) and not self.error and not self.missing

    @property
    def install_hint(self):
        """缺失依赖时可直接复制执行的安装命令。"""
        exe = self.exe_path or "python"
        return '"%s" -m pip install %s' % (exe, " ".join(self.missing))

    def describe(self):
        """一行中文摘要，用于界面提示。"""
        if self.error:
            return self.error
        if not self.exe_path:
            return T("未找到可用的 Python 解释器")
        if self.missing:
            return T("Python %s 缺少依赖：%s\n可在命令行执行：\n%s") % (
                self.version,
                "、".join(self.missing),
                self.install_hint,
            )
        return "Python %s · %s" % (self.version, self.exe_path)


def candidates(qgis_prefix=None, saved=None):
    """按优先级列出候选解释器路径（去重、只保留存在的）。

    :param qgis_prefix: ``QgsApplication.prefixPath()``，用于定位 QGIS 自带 Python。
    :param saved: 用户上次选定的路径。
    :returns: 路径列表。
    """
    raw = []

    if saved:
        raw.append(saved)

    env_value = os.environ.get("CAMARKOV_PYTHON")
    if env_value:
        raw.append(env_value)

    # 正在运行 QGIS 的那个解释器。最可靠：它一定具备 QGIS 所需的全部依赖，
    # 而且路径无需推断（QgsApplication.prefixPath() 给的是 <root>/apps/qgis-ltr，
    # 不是安装根目录，按它拼 "apps/Python3xx" 会拼错一层）。
    if sys.executable and "python" in os.path.basename(sys.executable).lower():
        raw.append(sys.executable)

    # QGIS 自带：<root>/apps/Python3xx/python.exe（两种前缀形态都试一次）
    if qgis_prefix:
        for root in (os.path.dirname(os.path.dirname(qgis_prefix)), os.path.dirname(qgis_prefix)):
            apps = os.path.join(root, "apps")
            if not os.path.isdir(apps):
                continue
            for name in sorted(os.listdir(apps), reverse=True):
                if not name.lower().startswith("python"):
                    continue
                exe = os.path.join(apps, name, "python.exe")
                if os.path.isfile(exe):
                    raw.append(exe)

    # conda / 系统安装
    home = os.path.expanduser("~")
    for root in (
        os.path.join(home, "miniconda3"),
        os.path.join(home, "anaconda3"),
        r"C:\ProgramData\miniconda3",
        r"C:\ProgramData\anaconda3",
        r"C:\Python314",
        r"C:\Python313",
        r"C:\Python312",
        r"C:\Python311",
        r"C:\Python310",
    ):
        raw.append(os.path.join(root, "python.exe"))
        raw.extend(_env_pythons(os.path.join(root, "envs")))

    # 非系统盘的 conda（本项目历史上装在 D:\Users\<user>\miniconda3）
    for drive in _fixed_drives():
        for suffix in ("miniconda3", "anaconda3"):
            base = os.path.join(drive, suffix)
            raw.append(os.path.join(base, "python.exe"))
            raw.extend(_env_pythons(os.path.join(base, "envs")))
        user_base = os.path.join(drive, "Users", os.environ.get("USERNAME", ""))
        for suffix in ("miniconda3", "anaconda3"):
            base = os.path.join(user_base, suffix)
            raw.append(os.path.join(base, "python.exe"))
            raw.extend(_env_pythons(os.path.join(base, "envs")))

    # PATH
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if folder:
            raw.append(os.path.join(folder, "python.exe"))

    return _dedup_existing(raw)


def probe(exe_path):
    """探测一个解释器：版本号 + 缺失的依赖包。

    :param exe_path: 解释器路径。
    :returns: :class:`PythonEnvironment`。
    """
    env = PythonEnvironment(exe_path)
    if not os.path.isfile(exe_path):
        env.error = T("解释器不存在：%s") % exe_path
        return env

    code = (
        "import sys, importlib.util as u\n"
        "mods = %r\n"
        "miss = [m for m in mods if u.find_spec(m) is None]\n"
        "print('VERSION=' + sys.version.split()[0])\n"
        "print('MISSING=' + ','.join(miss))\n" % (list(REQUIRED_PACKAGES),)
    )
    try:
        completed = subprocess.run(  # nosec B603
            [exe_path, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT,
            # 子进程输出强制按 UTF-8 解，避免 Windows 默认 GBK 解不开
            encoding="utf-8",
            errors="replace",
            creationflags=_no_window_flag(),
        )
    except subprocess.TimeoutExpired:
        env.error = T("解释器探测超时：%s") % exe_path
        return env
    except OSError as exc:
        env.error = T("无法启动解释器：%s\n%s") % (exe_path, exc)
        return env

    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.startswith("VERSION="):
            env.version = line[8:].strip()
        elif line.startswith("MISSING="):
            value = line[8:].strip()
            env.missing = [m for m in value.split(",") if m]

    if not env.version:
        tail = (completed.stderr or "").strip()[-300:]
        env.error = T("无法启动解释器：%s\n%s") % (exe_path, tail)
    return env


def find(qgis_prefix=None, saved=None):
    """按优先级找到第一个可用的解释器。

    :param qgis_prefix: QGIS 安装前缀。
    :param saved: 用户上次选定的路径。
    :returns: :class:`PythonEnvironment`；都不可用时返回第一个候选的探测结果
        （带有 ``missing`` 或 ``error``，界面可据此给出安装提示）。
    """
    fallback = None
    for exe in candidates(qgis_prefix, saved):
        env = probe(exe)
        if env.usable:
            return env
        if fallback is None and env.exe_path:
            fallback = env
    return fallback or PythonEnvironment()


# ---------------------------------------------------------------------- 内部


def _env_pythons(envs_dir):
    """列出 ``envs/<name>/python.exe``，按名称排序保证可复现。"""
    result = []
    if not os.path.isdir(envs_dir):
        return result
    try:
        names = sorted(os.listdir(envs_dir), key=str.lower)
    except OSError:
        return result
    for name in names:
        exe = os.path.join(envs_dir, name, "python.exe")
        if os.path.isfile(exe):
            result.append(exe)
    return result


def _fixed_drives():
    """列出本机固定磁盘根（Windows）。"""
    if not sys.platform.startswith("win"):
        return []
    drives = []
    for letter in "CDEFGH":
        root = letter + ":\\"
        if os.path.isdir(root):
            drives.append(root)
    return drives


def _dedup_existing(paths):
    """去重（忽略大小写）并只保留存在的文件。"""
    seen = set()
    result = []
    for path in paths:
        if not path:
            continue
        cleaned = os.path.expanduser(path.strip().strip('"'))
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(cleaned):
            result.append(cleaned)
    return result


def _no_window_flag():
    """Windows 下避免弹黑框；其它平台返回 0。"""
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0
