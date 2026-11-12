# -*- coding: utf-8 -*-
"""插件界面的双语支持：中文即键，英文见 ``i18n_en.py``；查不到原样返回中文。

约定与引擎的 ``L()`` 一致：

* 键是源码里的中文原文，必须逐字一致（含全角标点、``%d``/``%s``、换行）。
* 先取译文，再套 ``%`` 参数；译文占位符的数量、顺序、类型必须与原文一致。
* **禁止在模块级 / 类级初始化里调用 ``T()``**，否则语言会在探测之前被冻结。
  需要延迟求值时就写成函数或属性。

界面语言按 QGIS 的实际翻译状态推断，可用 ``CAMARKOV_LANG`` 强制覆盖
（测试与 CI 用，避免机器 locale 影响断言）。
"""

import os
import re

ZH = "zh"
EN = "en"

_current = None
_map = None
_CLASS_NUMBER = re.compile(r"^类别 (\d+)$")


def current():
    """当前界面语言（``zh``/``en``），进程内只探测一次。"""
    global _current
    if _current is None:
        _current = _detect()
    return _current


def reset():
    """清空缓存。测试切换语言后必须调用。"""
    global _current, _map
    _current = None
    _map = None


def warm():
    """提前完成探测与字典加载，让插件加载阶段就确定语言。"""
    if current() == EN:
        _english()


def T(text, *args):
    """取译文，并可套 ``%`` 参数。

    :param text: 中文原文；非字符串原样返回。
    :param args: ``%`` 格式化参数。
    :returns: 当前语言下的文本；未收录时回退中文原文。
    """
    if not isinstance(text, str):
        return text
    translated = _english().get(text, text) if current() == EN else text
    if not args:
        return translated
    try:
        return translated % args
    except (TypeError, ValueError):
        # 译文占位符写错时宁可显示模板，也不要让 QGIS 抛异常
        return translated


def translate_class_name(name):
    """类别名的显示层翻译。

    ``metrics.json`` 里始终写中文，只在界面显示时按当前语言翻译——
    这样同一份输入在不同界面语言下产出的数据完全一致。

    :param name: 类别名，可能来自 metrics.json，也可能自动生成。
    :returns: 当前语言下的显示名。
    """
    if not isinstance(name, str) or not name or current() != EN:
        return name
    table = _english()
    if name in table:
        return table[name]
    match = _CLASS_NUMBER.match(name)
    if match:
        return T("类别 %d", int(match.group(1)))
    return name


def _english():
    """延迟加载英文表：中文界面下不解析这份字典。"""
    global _map
    if _map is None:
        try:
            from .i18n_en import EN as table
        except ImportError:
            table = {}
        _map = table
    return _map


def _detect():
    """按优先级探测界面语言。"""
    forced = os.environ.get("CAMARKOV_LANG", "").strip().lower()
    if forced.startswith(EN):
        return EN
    if forced.startswith(ZH):
        return ZH
    for code in _locale_codes():
        lang = _classify(code)
        if lang:
            return lang
    return ZH


def _classify(code):
    """把 locale 代码归一为 ``zh``/``en``；无法判断时返回 ``None``。

    ``C`` 表示 QGIS 没加载任何翻译，即英文界面。
    """
    code = (code or "").strip().lower()
    if not code:
        return None
    if code == "c":
        return EN
    return ZH if code.startswith(ZH) else EN


def _locale_codes():
    """按可信度收集可能表示界面语言的代码。"""
    try:
        from qgis.core import QgsApplication
    except ImportError:
        return ()
    codes = []
    app = _safe(QgsApplication.instance)
    if app is not None:
        # 真正加载的翻译，最贴近用户看到的界面语言
        codes.append(_safe(app.translation, ""))
    codes.append(_safe(QgsApplication.locale, ""))
    codes.append(_safe(_user_locale, ""))
    codes.extend(_qt_locale_codes())
    return codes


def _user_locale():
    """QGIS 设置里保存的界面语言（用户手动切换时写在这里）。"""
    from qgis.core import QgsSettings

    return QgsSettings().value("locale/userLocale", "", type=str)


def _qt_locale_codes():
    """系统与 Qt 默认 locale，作为最后兜底。"""
    try:
        from qgis.PyQt.QtCore import QLocale
    except ImportError:
        return []
    return [_safe(QLocale.system().name, ""), _safe(QLocale().name, "")]


def _safe(call, default=""):
    """调用可能不存在的 Qt/QGIS API，失败时返回默认值。

    不写 ``except ...: pass``，避免触发 bandit B110。
    """
    try:
        return call()
    except Exception:
        return default
