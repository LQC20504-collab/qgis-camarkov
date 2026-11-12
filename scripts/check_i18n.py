# -*- coding: utf-8 -*-
"""检查插件界面文案的 i18n 完整性。

四类问题，任一出现即返回 1：

1. 未包 ``T()`` 的中文字面量（漏翻）。
2. ``T()`` 用到的键不在 ``i18n_en.EN`` 里（缺译）。
3. ``EN`` 里有用不到的键（改名后残留）。
4. 键与译文的 ``%`` 占位符数量、顺序或类型不一致。

规则说明：未包 ``T()`` 的中文字面量，如果本身就是 ``EN`` 的键，视为「类属性/
模块常量作为键」的写法（``GROUP = "变化预测"``、``FIGURE_TITLES`` 等），放行。
真正漏翻的新文案不会出现在字典里，因此仍会被抓出来。

用法::

    python scripts/check_i18n.py
"""

import ast
import glob
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

SKIP_PATHS = ("resources/engine/", "i18n.py", "i18n_en.py")

CJK = re.compile(r"[\u4e00-\u9fff]")
PLACEHOLDER = re.compile(r"%(?:\([^)]+\))?[-+ #0]*\d*(?:\.\d+)?[diouxXeEfFgGcrsa]")

#: 不是界面文案、也不进字典的输入同义词。
ALLOW_LITERALS = {"负", "负向"}


def load_table():
    """导入英文表（不依赖 QGIS）。"""
    from qgis_camarkov.i18n_en import EN

    return EN


def placeholders(text):
    """提取 ``%`` 转换序列，忽略 ``%%``。"""
    return PLACEHOLDER.findall(text.replace("%%", ""))


def scan_file(path, rel):
    """返回 (违规列表, 用到的键集合)。"""
    source = open(path, encoding="utf-8").read()
    tree = ast.parse(source, filename=path)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    wrapped = set()
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_t = (isinstance(func, ast.Name) and func.id == "T") or (
                isinstance(func, ast.Attribute) and func.attr == "T"
            )
            if is_t and node.args and isinstance(node.args[0], ast.Constant):
                wrapped.add(id(node.args[0]))
                value = node.args[0].value
                if isinstance(value, str):
                    used.add(value)

    violations = []
    allowed = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if not CJK.search(node.value):
            continue
        if id(node) in docstrings or id(node) in wrapped:
            continue
        if node.value in ALLOW_LITERALS:
            allowed.add(node.value)
            continue
        allowed.add(node.value)
        violations.append((rel, node.lineno, node.value))
    return violations, used, allowed


def main():
    table = load_table()
    violations = []
    used = set()
    allowed = set()
    for path in sorted(glob.glob(os.path.join(REPO, "qgis_camarkov", "**", "*.py"), recursive=True)):
        rel = os.path.relpath(path, REPO).replace("\\", "/")
        if any(token in rel for token in SKIP_PATHS):
            continue
        found, keys, ok = scan_file(path, rel)
        violations.extend(found)
        used |= keys
        allowed |= ok

    missing = sorted(k for k in used if k not in table)
    stale = sorted(k for k in table if k not in used and k not in allowed)

    bad_format = []
    for key, value in table.items():
        if not isinstance(value, str):
            bad_format.append((key, "值不是字符串"))
            continue
        if CJK.search(value):
            bad_format.append((key, "译文里还有中文"))
        left, right = placeholders(key), placeholders(value)
        if left != right:
            bad_format.append((key, "占位符不一致：%s vs %s" % (left, right)))

    # 未包在 T() 里的字面量，若本身的文本就是字典键，视为常量式的键，放行
    real = [v for v in violations if v[2] not in table]

    for rel, line, value in real:
        print("UNWRAPPED %s:%d  %r" % (rel, line, value))
    for key in missing:
        print("MISSING   %r" % key)
    for key in stale:
        print("STALE     %r" % key)
    for key, why in bad_format:
        print("FORMAT    %r  %s" % (key, why))

    print(
        "\nentries=%d used=%d unwrapped=%d missing=%d stale=%d format=%d"
        % (len(table), len(used), len(real), len(missing), len(stale), len(bad_format))
    )
    if real or missing or stale or bad_format:
        return 1
    print("i18n OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
