# -*- coding: utf-8 -*-
"""从 SharpGIS 上游同步引擎副本。

方向是**单向**的：SharpGIS 是上游，本仓库只是消费方。不要在
``qgis_camarkov/resources/engine/`` 里直接改引擎——改了会在下次同步时被覆盖，
而且两边行为会悄悄漂移。

用法::

    python scripts/sync_engine.py --from D:\\Develop\\SharpGIS\\Engine
    python scripts/sync_engine.py --from <dir> --dry-run
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TARGET = os.path.join(REPO, "qgis_camarkov", "resources", "engine")

#: 需要同步的文件（``__pycache__`` 之类的产物一律不带）。
FILES = ("camarkov_engine.py", "lang_en.py")


def sha256(path):
    """算文件哈希，用于写进 SOURCE.txt 供人工比对。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upstream_commit(engine_dir):
    """尽量取上游仓库的当前提交；取不到返回空串。"""
    try:
        return subprocess.check_output(
            ["git", "-C", engine_dir, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


def main(argv=None):
    """执行同步。

    :param argv: 命令行参数；默认取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    """
    parser = argparse.ArgumentParser(description="从 SharpGIS 同步 CA-Markov 引擎")
    parser.add_argument("--from", dest="source", required=True, help="SharpGIS 的 Engine 目录")
    parser.add_argument("--dry-run", action="store_true", help="只报告差异，不写文件")
    args = parser.parse_args(argv)

    source = os.path.abspath(args.source)
    if not os.path.isdir(source):
        print("源目录不存在：%s" % source)
        return 2

    missing = [name for name in FILES if not os.path.isfile(os.path.join(source, name))]
    if missing:
        print("源目录缺少文件：%s" % "、".join(missing))
        return 2

    changed = []
    for name in FILES:
        src = os.path.join(source, name)
        dst = os.path.join(TARGET, name)
        if os.path.isfile(dst) and sha256(src) == sha256(dst):
            print("未变化：%s" % name)
            continue
        changed.append(name)
        print("%s：%s → %s" % ("将更新" if args.dry_run else "更新", src, dst))
        if not args.dry_run:
            os.makedirs(TARGET, exist_ok=True)
            shutil.copy2(src, dst)

    if args.dry_run:
        return 0 if changed else 0

    commit = upstream_commit(source)
    source_txt = os.path.join(TARGET, "SOURCE.txt")
    with open(source_txt, "w", encoding="utf-8") as handle:
        handle.write(
            "本目录下的 camarkov_engine.py 与 lang_en.py 来自 SharpGIS 项目，原样复制，未做修改。\n\n"
            "来源仓库：https://github.com/LQC20504-collab/SharpGIS\n"
            "来源路径：Engine/camarkov_engine.py、Engine/lang_en.py\n"
            "来源提交：%s\n"
            "同步日期：%s\n\n"
            "文件哈希（sha256）：\n%s\n\n"
            "上游许可证：MIT\n"
            "Copyright (c) 2026 SharpGIS contributors\n\n"
            "按照 MIT 许可证，这两个文件在本仓库中继续以 MIT 授权；本仓库其它部分为\n"
            "GPL-2.0-or-later。MIT 与 GPL 兼容，合并分发不产生冲突。\n\n"
            "不要在本目录直接修改引擎：改动请提到 SharpGIS 上游，再用\n"
            "scripts/sync_engine.py 同步过来，否则两边会漂移。\n"
            % (
                commit or "(未知)",
                __import__("datetime").date.today().isoformat(),
                "\n".join("  %s  %s" % (sha256(os.path.join(TARGET, n)), n) for n in FILES),
            )
        )
    print("已写入 %s" % source_txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
