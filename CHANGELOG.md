# Changelog

## 0.1.3

插件界面跟随 QGIS 语言（中文 / 英文），**无算法改动**。

- 新增 `qgis_camarkov/i18n.py` + `i18n_en.py`：中文即键、未命中回退中文，与引擎的
  `lang_en.py` 同构。界面语言按 `QgsApplication.translation()` →
  `QgsApplication.locale()` → `locale/userLocale` → 系统 locale 依次推断，
  可用 `CAMARKOV_LANG` 强制覆盖（测试与 CI 用）。
- 覆盖约 160 条文案：工具箱参数标签、算法名、分组名、帮助正文、校验与运行错误、
  结果面板页签 / 表头 / 提示、菜单与工具栏按钮、消息框。
- 三处防冻结处理：`TRANSITION_LABELS` 等五个模块常量改为函数；`GROUP` 保留中文键，
  翻译放进 `group()`；`FIGURE_TITLES` 保留中文值，在 `figure_paths()` 里翻译。
  写成 `LABELS = [T(...)]` 会在导入时把语言固化，这是刻意避开的。
- 数据与界面分离：`metrics.json` 的类别名始终写中文，只在结果面板显示时翻译，
  保证同一输入在不同界面语言下产出完全一致。
- `LANG` 参数改为三态：跟随界面（默认）/ English / 中文。索引 1 仍是 English，
  兼容旧模型；索引 0 从「中文」变为「跟随界面」，这是行为变化。
- `metadata.txt` 的 `name` 改为英文 `CA-Markov Land Change Prediction`
  （该字段不支持按语言本地化）。
- 顺手修复：`provider.versionInfo()` 此前写死 `0.1.0`，现在读 `metadata.txt`。
- 验证：`scripts/check_i18n.py` 零违规（160 条译文 / 139 处调用）；
  pytest 58 passed / 6 skipped；QGIS 3.40.15 实测 `qgis_process help camarkov:predict`
  在中英文下分别输出对应标签；结果面板英文渲染无中文残留；
  bandit 0、detect-secrets 0。

## 0.1.2

QGIS 4 / Qt 6 兼容：消除官方 Qt6 Check 报出的全部 21 处问题，**无功能改动**。

- 三个文件里的扁平枚举改为 scoped 写法：`Qt.AlignmentFlag.*`（10 处）、
  `Qt.TransformationMode.SmoothTransformation`、`Qt.DockWidgetArea.RightDockWidgetArea`、
  `QTableWidget.EditTrigger.NoEditTriggers`（3 处）、`QHeaderView.ResizeMode.*`（4 处）、
  `QgsProcessing.SourceType.TypeRaster`（2 处）。
- `plugin.py` 的 `QAction` 改从 `qgis.PyQt.QtGui` 导入：Qt6 已把它移出 `QtWidgets`
  （官方检查器未列此项，但真实 Qt6 下会 ImportError）。Qt5 / Qt6 双端均实测可导入。
- `metadata.txt`：`qgisMaximumVersion=4.99`（进入 QGIS 4 Ready 列表），
  删除已废弃且从 QGIS core 移除的 `supportsQt6=True`。
- 关键前提：QGIS 3.40 (PyQt5) **同样支持 scoped 枚举**，所以直接按官方建议改即可双版本兼容，
  不需要运行时兼容层（官方迁移脚本默认就是「保持 QGIS 3 兼容」的改法）。
- 验证：QGIS 3.40.15 真实环境三模块导入 + 11 个 scoped 枚举与扁平值相等 +
  真实构造 `QgsProcessingParameterMultipleLayers` 全过；PyQt6 6.12 下 10 个 Qt 枚举全部可解析；
  本地 AST 等价检查 21 → 0（文件/行/列与官方清单完全一致）；pytest 47 passed / 5 skipped；
  bandit 0、detect-secrets 0。
- `metadata.txt`：`author` 改为 GitHub 用户名 `LQC20504-collab`
  （`gh api user` 确认的登录名，与仓库 owner / 插件 Maintainer 一致）；
  `about` 删去末尾中文行，简介全篇英文。
- `QgsProcessing.SourceType.TypeRaster` 只能在 QGIS 4 运行时最终确认，
  其 scope 名取自官方检查器输出；QGIS 3.40 上已实测与扁平写法等价。
- 清理 `metadata.txt`、两份 `LICENSE`、`SOURCE.txt`、README、CHANGELOG、
  `scripts/sync_engine.py` 及引擎副本中的品牌与来源文字，使插件完全独立；
  版权声明保留，权利人改为 `LQC20504-collab`。引擎副本的两个中文 i18n 键
  与 `lang_en.py` 译文表已同步更新。
- 修复处理工具箱图标：`provider.py` 的 `PLUGIN_DIR` 多算了一层 `dirname`，
  分组图标指向不存在的 `仓库根/resources/icon.svg`（实测 `QIcon.isNull=True`）；
  `algorithms/base.py` 只覆写了 `svgIconPath()`，而工具箱的 DecorationRole 取的是
  `icon()`（`qgsprocessingtoolboxmodel.cpp:511/516`），所以三个算法一直显示 QGIS
  自带的通用齿轮图标。现两处补齐，插件管理器 / 工具栏按钮 / 工具箱分组 /
  三个算法这四个位置共用同一张 `resources/icon.svg`，QGIS 3.40 实测四处均加载成功。
- 新增三张算法专用小图标 `icon_analyze.svg` / `icon_train.svg` / `icon_predict.svg`，
  沿用主图标配色，主形分别为方形矩阵 / 分叉节点 / 右向箭头，保证 16px 下靠剪影可辨。
  `algorithms/base.py` 增加 `ICON_FILE` 类属性，三个算法类各自覆盖，
  `icon()` / `svgIconPath()` 按它取值；分组、工具栏、插件管理器仍用主 `icon.svg`。
  QGIS 3.40 实测四处图标均加载成功且指向 4 个不同文件。

## 0.1.1

解除 plugins.qgis.org 的 **Blocked** 状态，无功能改动：

- 在 14 行加上精准的 `# nosec Bxxx` 行内标注：B110（清理临时文件/进程树时的
  try/except/pass）、B404/B603（子进程隔离引擎所必需的 subprocess 调用）、
  B607（Windows 下 `taskkill` 回退）。官方扫描器用 `bandit -t <启用规则>` 且
  **省略 `-ll`**，因此本地默认扫描里的 LOW 也会全部报出；而 Bandit 检查的 severity
  固定为 critical、`issues_found == 0` 才算通过，任一 finding 都会让版本被 Blocked。
- `resources/engine/camarkov_engine.py` 的两处标注属于打包适配。该文件是随包附带的
  引擎副本，下次执行 `scripts/sync_engine.py` 同步时需一并带上这两行注释。

以下为此前为上架 QGIS 官方插件仓库（plugins.qgis.org）做的准备，插件包内容有变动：

- `metadata.txt` 的 `description` / `about` 补齐英文描述（官方上传清单硬性要求）。
- 插件包根目录新增 `LICENSE`：此前它只存在于仓库根，不会被 `build_zip.py` 打进包，
  而官方校验要求 zip 内插件根目录必须有名为 `LICENSE` 的文件。
- 插件包根目录新增简短 `README.md`；完整文档仍见仓库根 `README.md`。

以下为仓库侧的安装防呆改进（无代码改动）：

- 新增 `scripts/check_install.py`：体检安装位置、metadata 可解析性、引擎副本与启用状态。
- README 增加醒目提示：**必须用 Releases 里的 `qgis_camarkov-<版本>.zip`**，
  不要用仓库首页的 Code → Download ZIP（其顶层目录 `qgis-camarkov-master/` 会导致
  `ModuleNotFoundError`）。
- README 增加「故障排查」一节，覆盖有头/无头两种安装失败的常见原因。

## 0.1.0

首个版本。

- 三个处理算法：`camarkov:analyze`（转移分析）、`camarkov:train`（训练模型）、
  `camarkov:predict`（变化预测）。
- 引擎以子进程运行，自动定位可用的 Python 解释器并校验依赖。
- 开跑前校验：期数、本地文件、同网格、同坐标系、输出后缀、无效值范围。
- 进度单调化（引擎在多期数据下会倒退进度），取消时杀整棵进程树。
- 结果停靠面板：概览 / 转移矩阵 / 精度 / 特征重要性 / 图集。
- 报告与图表支持中英文（跟随 `lang` 参数）。
