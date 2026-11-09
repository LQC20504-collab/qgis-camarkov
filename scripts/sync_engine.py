# -*- coding: utf-8 -*-
"""从指定的引擎源目录同步引擎副本。

方向是**单向**的：以源目录为准，本仓库只保存副本。不要在
``qgis_camarkov/resources/engine/`` 里直接改引擎——改了会在下次同步时被覆盖，
而且两边行为会悄悄漂移。

用法::

    python scripts/sync_engine.py --from <engine-source-dir>
    python scripts/sync_engine.py --from <dir> --dry-run
"""

import argparse
import hashlib
import os
import shutil
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


def main(argv=None):
    """执行同步。

    :param argv: 命令行参数；默认取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    """
    parser = argparse.ArgumentParser(description="同步 CA-Markov 引擎副本")
    parser.add_argument("--from", dest="source", required=True, help="引擎源目录")
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

    source_txt = os.path.join(TARGET, "SOURCE.txt")
    with open(source_txt, "w", encoding="utf-8") as handle:
        handle.write(
            "本目录下的 camarkov_engine.py 与 lang_en.py 以 MIT 许可证授权，\n"
            "全文见同目录的 LICENSE 文件。\n\n"
            "Copyright (c) 2026 LQC20504-collab\n\n"
            "插件的其它部分采用 GPL-2.0-or-later。MIT 与 GPL 兼容，\n"
            "合并分发不产生冲突。\n"
        )
    print("已写入 %s" % source_txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
