# -*- coding: utf-8 -*-
"""打包成可「从 ZIP 安装」的插件包。

QGIS 的 ZIP 安装只认一个规则：压缩包内**路径最短的那个 metadata.txt**，
它所在目录名就是插件 id。所以 zip 里必须只有一个 ``qgis_camarkov/`` 顶层目录，
且该目录名是合法 Python 标识符（不能有连字符）。

用法::

    python scripts/build_zip.py
    python scripts/build_zip.py --out dist
"""

import argparse
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PACKAGE = "qgis_camarkov"

#: 不打包的内容：开发产物与测试。
EXCLUDE_DIRS = {"__pycache__", ".git", ".pytest_cache", "tests", "scripts", "dist", "build"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".zip"}


def read_version(package_dir):
    """从 metadata.txt 里读 version，用于命名产物。

    :param package_dir: 插件包目录。
    :returns: 版本号字符串。
    """
    path = os.path.join(package_dir, "metadata.txt")
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    return "0.0.0"


def collect(package_dir):
    """列出要打包的文件（相对于仓库根）。

    :param package_dir: 插件包目录。
    :returns: 相对路径列表。
    """
    files = []
    for root, dirs, names in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in names:
            if os.path.splitext(name)[1].lower() in EXCLUDE_SUFFIX:
                continue
            files.append(os.path.relpath(os.path.join(root, name), REPO))
    return sorted(files)


def main(argv=None):
    """执行打包。

    :param argv: 命令行参数。
    :returns: 进程退出码。
    """
    parser = argparse.ArgumentParser(description="打包 QGIS 插件为 ZIP")
    parser.add_argument("--out", default="dist", help="输出目录，默认 dist")
    args = parser.parse_args(argv)

    package_dir = os.path.join(REPO, PACKAGE)
    if not os.path.isdir(package_dir):
        print("找不到插件目录：%s" % package_dir)
        return 2

    metadata = os.path.join(package_dir, "metadata.txt")
    if not os.path.isfile(metadata):
        print("缺少 metadata.txt：%s" % metadata)
        return 2

    # metadata.txt 里出现 % 会让 configparser 的插值抛异常，QGIS 就读不到元数据
    with open(metadata, "r", encoding="utf-8") as handle:
        if "%" in handle.read():
            print("metadata.txt 里不能出现百分号（configparser 会尝试插值并失败）")
            return 2

    version = read_version(package_dir)
    out_dir = os.path.join(REPO, args.out)
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "%s-%s.zip" % (PACKAGE, version))

    files = collect(package_dir)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            archive.write(os.path.join(REPO, relative), relative)

    size = os.path.getsize(target) / 1024.0
    print("已生成：%s（%d 个文件，%.1f KB）" % (target, len(files), size))
    print("安装方式：QGIS → 插件 → 管理并安装插件 → 从 ZIP 安装")
    return 0


if __name__ == "__main__":
    sys.exit(main())
