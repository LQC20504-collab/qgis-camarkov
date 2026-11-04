# Changelog

## 未发布

为上架 QGIS 官方插件仓库（plugins.qgis.org）做准备，插件包内容有变动：

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
