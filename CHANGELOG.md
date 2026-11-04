# Changelog

## 0.1.1

解除 plugins.qgis.org 的 **Blocked** 状态，无功能改动：

- 在 14 行加上精准的 `# nosec Bxxx` 行内标注：B110（清理临时文件/进程树时的
  try/except/pass）、B404/B603（子进程隔离引擎所必需的 subprocess 调用）、
  B607（Windows 下 `taskkill` 回退）。官方扫描器用 `bandit -t <启用规则>` 且
  **省略 `-ll`**，因此本地默认扫描里的 LOW 也会全部报出；而 Bandit 检查的 severity
  固定为 critical、`issues_found == 0` 才算通过，任一 finding 都会让版本被 Blocked。
- `resources/engine/camarkov_engine.py` 的两处标注属于打包适配。该文件是 vendored 副本，
  下次执行 `scripts/sync_engine.py` 时需把这两行注释带到 SharpGIS 上游。

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
