# -*- coding: utf-8 -*-
"""启用/禁用本插件（写 profile 的 ``QGIS3.ini`` 里的 ``[PythonPlugins]``）。

为什么不用 ``QgsSettings``：用一个裸 ``QgsApplication([], False)`` 起进程时，
applicationName 会被推断成脚本名（例如 ``python``），QgsSettings 于是解析到
``%APPDATA%\\python\\profiles\\...`` 这种**不存在的 profile**，写进去的启用状态
``qgis_process`` 根本读不到。直接按路径改 ini 是确定的。

用法::

    "C:\\Program Files\\QGIS 3.40.15\\bin\\python-qgis-ltr.bat" scripts\\enable_plugin.py
    ... scripts\\enable_plugin.py --disable
    ... scripts\\enable_plugin.py --profile=default
"""

import configparser
import os
import sys

PACKAGE = "qgis_camarkov"


def profile_ini(profile="default"):
    """拼出指定 profile 的 ``QGIS3.ini`` 路径。

    :param profile: profile 名，默认 ``default``。
    :returns: ini 文件的绝对路径（不保证存在）。
    """
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "QGIS", "QGIS3", "profiles", profile, "QGIS", "QGIS3.ini")


def set_enabled(path, enabled):
    """把 ``[PythonPlugins]`` 段里的开关写成指定值。

    :param path: ini 路径。
    :param enabled: True 表示启用。
    :returns: 写入后的布尔值。
    """
    if not os.path.isfile(path):
        raise SystemExit("找不到 profile 配置文件：%s" % path)

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    # 保留键名大小写：QGIS 用 /PythonPlugins/<包名>，大小写敏感
    parser.optionxform = str
    with open(path, "r", encoding="utf-8") as handle:
        parser.read_file(handle)

    if not parser.has_section("PythonPlugins"):
        parser.add_section("PythonPlugins")
    parser.set("PythonPlugins", PACKAGE, "true" if enabled else "false")

    with open(path, "w", encoding="utf-8") as handle:
        parser.write(handle, space_around_delimiters=False)

    return parser.getboolean("PythonPlugins", PACKAGE, fallback=False)


def main(argv):
    """解析参数并写开关，最后回读确认。

    :param argv: 命令行参数。
    :returns: 进程退出码。
    """
    disable = "--disable" in argv
    profile = "default"
    for arg in argv:
        if arg.startswith("--profile="):
            profile = arg.split("=", 1)[1]

    path = profile_ini(profile)
    actual = set_enabled(path, not disable)
    print("profile: %s" % path)
    print("[PythonPlugins] %s = %s" % (PACKAGE, actual))
    return 0 if actual == (not disable) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
