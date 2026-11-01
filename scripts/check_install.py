# -*- coding: utf-8 -*-
"""体检已安装的 QGIS 插件，专治「装了源码包」这一类问题。

最常见的安装事故：在 GitHub 仓库首页点了绿色 **Code → Download ZIP**。
那个压缩包的顶层目录是 ``qgis-camarkov-master/``（GitHub 用「仓库名-分支」命名归档），
里面才是真正的插件包。QGIS 的 ZIP 安装会取**最短的 metadata.txt 的目录**当插件 id，
于是把 ``qgis-camarkov-master/qgis_camarkov`` 当成模块名去 ``__import__`` ——
含斜杠又含连字符，必然报::

    ModuleNotFoundError: No module named 'qgis-camarkov-master/qgis_camarkov'

本脚本不改任何东西，只做检查并给出可以直接复制执行的修复命令。

用法::

    python scripts/check_install.py
    python scripts/check_install.py --profile=default
    python scripts/check_install.py --plugins="D:\\some\\plugins"
"""

import argparse
import configparser
import os
import sys

PACKAGE = "qgis_camarkov"
REQUIRED_META = ("name", "description", "version", "qgisMinimumVersion")


def profile_root(profile="default"):
    """返回 profile 目录（``.../QGIS3/profiles/<profile>``）。

    :param profile: profile 名。
    :returns: 绝对路径。
    """
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "QGIS", "QGIS3", "profiles", profile)


def find_installed(plugins_dir):
    """在插件目录里找出所有与 CA-Markov 有关的 metadata.txt。

    :param plugins_dir: 插件根目录。
    :returns: ``[(相对路径, 绝对路径), ...]``。
    """
    found = []
    if not os.path.isdir(plugins_dir):
        return found
    for name in sorted(os.listdir(plugins_dir)):
        if "camarkov" not in name.lower():
            continue
        candidate = os.path.join(plugins_dir, name, "metadata.txt")
        if os.path.isfile(candidate):
            found.append((name, candidate))
            continue
        # 深度 2：捕获 qgis-camarkov-master/qgis_camarkov/metadata.txt 这种嵌套
        for sub in sorted(os.listdir(os.path.join(plugins_dir, name))):
            nested = os.path.join(plugins_dir, name, sub, "metadata.txt")
            if os.path.isfile(nested):
                found.append((name + "/" + sub, nested))
    return found


def check_metadata(metadata_path):
    """检查 metadata.txt 能否被 QGIS 解析。

    QGIS 用 configparser 读取，且默认允许 ``%`` 插值——正文里出现 ``%`` 会直接
    抛异常，表现是「插件在管理器里显示为损坏」。

    :param metadata_path: metadata.txt 路径。
    :returns: ``(问题列表, 是否启用 Processing)``。
    """
    problems = []
    with open(metadata_path, "r", encoding="utf-8") as handle:
        raw = handle.read()

    if "%" in raw:
        problems.append("metadata.txt 含百分号，configparser 插值会失败（QGIS 读不到元数据）")

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(raw)
    except configparser.Error as exc:
        problems.append("metadata.txt 解析失败：%s" % exc)
        return problems, False

    if not parser.has_section("general"):
        problems.append("metadata.txt 缺少 [general] 段")
        return problems, False

    for key in REQUIRED_META:
        if not parser.get("general", key, fallback=""):
            problems.append("metadata.txt 缺少必需项 %s" % key)

    has_provider = parser.get("general", "hasProcessingProvider", fallback="").strip().lower()
    if has_provider not in ("yes", "true", "1"):
        problems.append(
            "metadata.txt 的 hasProcessingProvider 不是 True —— "
            "无头模式（qgis_process）里算法将不可见"
        )
        return problems, False
    return problems, True


def read_enabled(profile_dir):
    """读 QGIS3.ini 里的 ``[PythonPlugins] qgis_camarkov``。

    :param profile_dir: profile 目录。
    :returns: True/False/None（None 表示没配置）。
    """
    ini = os.path.join(profile_dir, "QGIS", "QGIS3.ini")
    if not os.path.isfile(ini):
        return None
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with open(ini, "r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except Exception:
        return None
    if not parser.has_section("PythonPlugins"):
        return None
    value = parser.get("PythonPlugins", PACKAGE, fallback="")
    if not value:
        return None
    return value.strip().lower() in ("true", "yes", "1")


def main(argv=None):
    """执行体检并打印结论。

    :param argv: 命令行参数。
    :returns: 0 表示一切正常，1 表示发现问题。
    """
    parser = argparse.ArgumentParser(description="体检 QGIS CA-Markov 插件的安装")
    parser.add_argument("--profile", default="default", help="QGIS profile 名，默认 default")
    parser.add_argument("--plugins", default="", help="直接指定插件目录（覆盖 profile 推导）")
    args = parser.parse_args(argv)

    profile_dir = profile_root(args.profile)
    plugins_dir = args.plugins or os.path.join(profile_dir, "python", "plugins")

    print("插件目录：%s" % plugins_dir)
    if not os.path.isdir(plugins_dir):
        print("× 插件目录不存在，QGIS 可能还没初始化过 profile")
        return 1

    found = find_installed(plugins_dir)
    if not found:
        print("× 没有找到已安装的 qgis_camarkov")
        print("  修复：从 Releases 下载 qgis_camarkov-<版本>.zip，用「从 ZIP 安装」装上")
        return 1

    ok = True
    expected = os.path.join(plugins_dir, PACKAGE)

    for relative, metadata in found:
        print("\n发现：%s" % relative)
        print("  metadata：%s" % metadata)
        directory = os.path.dirname(metadata)

        # 1) 目录名必须是合法 Python 标识符，且不能多一层
        leaf = os.path.basename(directory)
        if leaf != PACKAGE or os.path.normcase(directory) != os.path.normcase(expected):
            ok = False
            print("  × 安装位置不对：QGIS 会把它当模块名导入，含斜杠或连字符必然失败")
            print("    正确位置应为：%s" % expected)
            print("    多半是装了 GitHub 首页的「Code → Download ZIP」源码包，")
            print("    那个压缩包的顶层目录是 qgis-camarkov-master/")
            print("    修复（删除多余的一层）：")
            print('      rmdir /S /Q "%s"' % os.path.join(plugins_dir, relative.split("/")[0]))
        elif not leaf.isidentifier():
            ok = False
            print("  × 目录名不是合法 Python 标识符：%s" % leaf)
        else:
            print("  √ 安装位置正确")

        # 2) metadata 可解析、Processing 开关在位
        problems, has_provider = check_metadata(metadata)
        if problems:
            ok = False
            for problem in problems:
                print("  × %s" % problem)
        else:
            print("  √ metadata.txt 可解析，hasProcessingProvider 已开启")

        # 3) 引擎是否随包带上
        engine = os.path.join(directory, "resources", "engine", "camarkov_engine.py")
        if os.path.isfile(engine):
            print("  √ 引擎副本在位")
        else:
            ok = False
            print("  × 缺少 resources/engine/camarkov_engine.py，插件无法运行")

    # 4) 启用状态
    enabled = read_enabled(profile_dir)
    print()
    if enabled is True:
        print("√ 已在 QGIS3.ini 里启用（[PythonPlugins] %s=true）" % PACKAGE)
    elif enabled is False:
        print("× 在 QGIS3.ini 里被显式禁用")
        print("  修复：python scripts/enable_plugin.py  （或插件管理器里勾选）")
        ok = False
    else:
        print("! QGIS3.ini 里没有启用记录（无头模式下插件默认不加载）")
        print("  修复：python scripts/enable_plugin.py")

    print()
    print("结论：%s" % ("安装正确" if ok else "发现问题，请按上面的提示修复"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
