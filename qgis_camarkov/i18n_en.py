# -*- coding: utf-8 -*-
"""插件界面的英文译文表。

键是源码里的中文原文，必须逐字一致（含全角标点、``%d``/``%s`` 占位符、换行）。
结构与引擎的 ``resources/engine/lang_en.py`` 相同，但**独立维护**：那份由
``scripts/sync_engine.py`` 单向同步，不能耦合。

约定：

* 译文的占位符数量、顺序、类型必须与原文完全一致，``T()`` 会按 ``%`` 套参数。
* 值里不出现汉字；``≤ ≥ ≠ × →`` 这类符号可以用。
* 类别名只在界面显示时翻译，``metrics.json`` 里始终是中文。
"""

EN = {
    # ------------------------------------------------------------------ 类别名
    "无效值": "NoData",
    "耕地": "Cropland",
    "森林": "Forest",
    "草地": "Grassland",
    "灌木": "Shrubland",
    "水体": "Water",
    "冰雪": "Snow and ice",
    "裸地": "Bare land",
    "不透水面": "Impervious surface",
    "类别 %d": "Class %d",
    # ------------------------------------------------------------------ 分组与算法名
    "输入与统计": "Input and statistics",
    "建模": "Modelling",
    "变化预测": "Prediction",
    "转移分析（只看矩阵，不写栅格）": "Transition analysis (matrix only, no raster)",
    "训练转移潜力模型（随机森林）": "Train transition potential model (random forest)",
    "变化预测（CA-Markov）": "Land-use prediction (CA-Markov)",
    "CA-Markov 土地利用变化预测": "CA-Markov Land Change Prediction",
    # ------------------------------------------------------------------ 下拉选项
    "最近一个区间": "Most recent interval",
    "最近两期平均（推荐）": "Average of two most recent intervals (recommended)",
    "全部区间累计": "Cumulative over all intervals",
    "随机森林转移潜力（推荐）": "Random-forest transition potential (recommended)",
    "因子加权（MCE）": "Factor weighting (MCE)",
    "外部适宜性图集": "External suitability stack",
    "不使用适宜性": "No suitability",
    "分位数 2%–98%（推荐）": "Quantile 2nd-98th percentile (recommended)",
    "最小-最大值": "Min-max",
    "按顺序（波段 1 = 类别 0）": "By order (band 1 = class 0)",
    "按类别值（波段号 = 类别值）": "By class value (band number = class value)",
    "跟随界面": "Follow UI language",
    "中文": "Chinese",
    # ------------------------------------------------------------------ 参数标签
    "土地利用分期栅格（按时间从旧到新，至少两期）":
        "Land-use period rasters (oldest to newest, at least two)",
    "各期使用的波段号": "Band number used for each period",
    "无效值（0~65535；>255 时输出为 uint16 且不含类别色彩表）":
        "NoData value (0-65535; above 255 the output is uint16 with no class colour table)",
    "类别数（0 = 按数据自动推断）": "Class count (0 = infer from data)",
    "转移矩阵来源": "Transition matrix source",
    "适宜性来源": "Suitability source",
    "训练驱动因子栅格（顺序即特征顺序；随机森林模式必需）":
        "Training driver rasters (order defines feature order; required in random-forest mode)",
    "复用已训练的模型（.npz，可留空表示当场训练）":
        "Reuse a trained model (.npz; leave empty to train now)",
    "即使给了模型也强制重训": "Retrain even if a model is supplied",
    "树的数量": "Number of trees",
    "最大深度（0 = 不限制）": "Maximum depth (0 = unlimited)",
    "不变像元采样倍数（变化像元的几倍）":
        "Unchanged-pixel sampling ratio (multiple of changed pixels)",
    "随机种子（保证可复现）": "Random seed (for reproducibility)",
    "加权因子（随机森林模式忽略；每行：路径 / 波段 / 权重 / 方向）":
        "Weighted factors (ignored in random-forest mode; each row: path / band / weight / direction)",
    "方向(1正向/-1负向)": "Direction (1 positive / -1 negative)",
    "路径": "Path",
    "波段": "Band",
    "权重": "Weight",
    "外部适宜性图集（多波段，仅外部模式用）":
        "External suitability stack (multiband, external mode only)",
    "图集波段与类别的对应关系": "Mapping between stack bands and classes",
    "限制性条件图（>0.5 可转变，0 禁止；可选）":
        "Constraint raster (above 0.5 allows change, 0 forbids; optional)",
    "预测步数（每步用同一转移矩阵重新分配）":
        "Number of steps (each step reallocates with the same transition matrix)",
    "邻域窗口（3/5/7，奇数）": "Neighbourhood window (3/5/7, odd)",
    "每一步都重算邻域": "Recompute the neighbourhood at every step",
    "因子标准化方法": "Factor normalisation method",
    "适宜性权重": "Suitability weight",
    "邻域权重": "Neighbourhood weight",
    "用转移概率调制适宜性（区分目标类）":
        "Modulate suitability by transition probability (target-class aware)",
    "输出精度评价": "Output accuracy assessment",
    "改用同期自检（in-sample，指标偏乐观）":
        "Use in-sample validation instead (optimistic metrics)",
    "报告与图表语言": "Report and figure language",
    "推理分块大小（像元）": "Inference chunk size (pixels)",
    "类别名称（可选；每行一个：序号 / 名称）":
        "Class names (optional; one per row: index / name)",
    "序号": "Index",
    "名称": "Name",
    "指标 JSON（必需）": "Metrics JSON (required)",
    "JSON 文件 (*.json)": "JSON file (*.json)",
    "文本报告（可选）": "Text report (optional)",
    "文本文件 (*.txt)": "Text file (*.txt)",
    "图表目录（可选；留空则不出图）":
        "Figures folder (optional; leave empty for no figures)",
    "预测栅格（仅支持 .tif/.tiff）": "Prediction raster (.tif/.tiff only)",
    "模型文件（.npz）": "Model file (.npz)",
    "NumPy 模型 (*.npz)": "NumPy model (*.npz)",
    # ------------------------------------------------------------------ 参数校验
    "至少需要两期土地利用栅格（当前 %d 期）。":
        "At least two land-use rasters are required (got %d).",
    "第 %d 期图层无效。": "Period %d layer is invalid.",
    "第 %d 期不是本地栅格文件，引擎无法读取：%s":
        "Period %d is not a local raster file and cannot be read by the engine: %s",
    "无效值必须是 0~65535 的整数。":
        "The NoData value must be an integer between 0 and 65535.",
    "随机森林模式需要提供训练驱动因子，或指定一个已训练的模型文件。\n"
    "如果只想快速看转移矩阵，请把「适宜性来源」改成「不使用适宜性」。":
        "Random-forest mode needs training driver rasters or a pre-trained model file.\n"
        "To inspect the transition matrix only, set 'Suitability source' to 'No suitability'.",
    "因子加权模式至少需要一行有效因子（路径不能为空）。":
        "Factor-weighting mode needs at least one valid factor (path must not be empty).",
    "外部适宜性图集模式需要指定一个多波段栅格。":
        "External suitability mode needs a multiband raster.",
    "适宜性权重与邻域权重不能同时为 0。":
        "Suitability weight and neighbourhood weight cannot both be zero.",
    "预测栅格只支持 .tif/.tiff。\n引擎固定写出 GeoTIFF，其它扩展名会得到名实不符的文件。":
        "The prediction raster must be .tif or .tiff.\n"
        "The engine always writes GeoTIFF, so other extensions would produce a misleading file.",
    "第 %d 期尺寸不一致：%d×%d ≠ %d×%d。":
        "Period %d has a different size: %d×%d ≠ %d×%d.",
    "第 %d 期坐标系与第 1 期不一致。\n引擎不会自动重投影，请先统一坐标系再运行。":
        "Period %d CRS differs from period 1.\n"
        "The engine does not reproject; unify the CRS first.",
    "第 %d 期的范围与第 1 期不一致（同一网格应完全重合）。\n请先对齐网格再运行。":
        "Period %d extent differs from period 1 (same grid must match exactly).\n"
        "Align the grids first.",
    # ------------------------------------------------------------------ 运行时消息
    "准备 CA-Markov 运行环境…": "Preparing the CA-Markov runtime…",
    "找不到可用的 Python 解释器，或缺少依赖：\n\n%s\n\n"
    "可以在「设置 → 选项 → 处理」之外手动指定；也可以直接执行上面的 pip 命令安装。":
        "No usable Python interpreter was found, or dependencies are missing:\n\n%s\n\n"
        "You can point it at another interpreter via Settings → Options → Processing, "
        "or run the pip command above.",
    "解释器：%s": "Interpreter: %s",
    "找不到引擎脚本：%s": "Engine script not found: %s",
    "已取消。": "Cancelled.",
    "引擎没有生成指标文件，可能被提前中断：\n%s":
        "The engine did not produce a metrics file; it may have been interrupted:\n%s",
    "CA-Markov 完成：%s": "CA-Markov finished: %s",
    "指标文件：%s": "Metrics file: %s",
    # ------------------------------------------------------------------ job schema
    "未知模式：%s": "Unknown mode: %s",
    "未知的转移矩阵来源：%s": "Unknown transition matrix source: %s",
    "未知的适宜性模式：%s": "Unknown suitability mode: %s",
    "未知的标准化方法：%s": "Unknown normalisation method: %s",
    "第 %d 期缺少文件路径": "Period %d has no file path",
    "至少需要两期土地利用数据": "At least two land-use periods are required",
    # ------------------------------------------------------------------ locator
    "未找到可用的 Python 解释器": "No usable Python interpreter found",
    "Python %s 缺少依赖：%s\n可在命令行执行：\n%s":
        "Python %s is missing dependencies: %s\nRun this on the command line:\n%s",
    "解释器不存在：%s": "Interpreter does not exist: %s",
    "解释器探测超时：%s": "Interpreter probe timed out: %s",
    "无法启动解释器：%s\n%s": "Cannot start the interpreter: %s\n%s",
    # ------------------------------------------------------------------ metrics
    "转移概率矩阵": "Transition probability matrix",
    "各类面积变化": "Area change by class",
    "混淆矩阵": "Confusion matrix",
    "驱动因子重要性": "Driver importance",
    "三联对比": "Three-way comparison",
    "变化热点": "Change hotspots",
    "metrics.json 不是合法 JSON：%s": "metrics.json is not valid JSON: %s",
    "metrics.json 缺少字段：%s": "metrics.json is missing fields: %s",
    "metrics.json 没有类别统计，可能被提前中断":
        "metrics.json has no class statistics; the run may have been interrupted",
    "转移分析": "Transition analysis",
    "模型训练": "Model training",
    "未知模式": "Unknown mode",
    "精度 OA=%.4f Kappa=%.4f": "Accuracy OA=%.4f Kappa=%.4f",
    "无精度评价": "no accuracy assessment",
    "%d 条警告": "%d warning(s)",
    "耗时 %.1f 秒": "took %.1f s",
    # ------------------------------------------------------------------ runner
    "操作已取消": "Operation cancelled",
    "CA-Markov 参数或数据有误": "CA-Markov parameters or data are invalid",
    "CA-Markov 引擎运行失败（退出码 %s）":
        "CA-Markov engine failed (exit code %s)",
    "无法启动 Python 进程：%s": "Cannot start the Python process: %s",
    "运行超过 %d 秒，已强制结束。": "Exceeded %d s and was terminated.",
    # ------------------------------------------------------------------ 结果面板
    "（未生成这张图）": "(figure not generated)",
    "CA-Markov 结果": "CA-Markov Results",
    "读取结果失败：\n\n%s\n\n文件：%s": "Failed to load results:\n\n%s\n\nFile: %s",
    "概览": "Overview",
    "转移矩阵": "Transition matrix",
    "精度": "Accuracy",
    "特征重要性": "Feature importance",
    "图集": "Figures",
    "像元": "pixels",
    "<p><b>警告（%d）</b></p><ul>%s</ul>": "<p><b>Warnings (%d)</b></p><ul>%s</ul>",
    "总体精度 OA = %.4f，Kappa = %.4f": "Overall accuracy OA = %.4f, Kappa = %.4f",
    "本次没有做精度评价": "No accuracy assessment was performed",
    "面积统计（%s）": "Area statistics (%s)",
    "类别": "Class",
    "基期": "Base",
    "末期": "End",
    "预测": "Predicted",
    "变化率": "Change",
    "转移计数": "Transition counts",
    "转移概率": "Transition probability",
    "转移预算": "Transition budget",
    "本次运行没有做精度评价。\n\n%s": "This run has no accuracy assessment.\n\n%s",
    "总体精度 OA = %.4f\u3000\u3000Kappa = %.4f\u3000\u3000有效像元 = %d":
        "Overall accuracy OA = %.4f\u3000\u3000Kappa = %.4f\u3000\u3000Valid pixels = %d",
    "重要性": "Importance",
    "驱动因子": "Driver",
    "本次没有训练随机森林（或复用了外部模型），因此没有特征重要性。":
        "No random forest was trained in this run (or an external model was reused), "
        "so there is no feature importance.",
    "本次没有生成图表。\n\n提示：把「图表目录」留空会导致引擎一张图都不出。":
        "No figures were generated.\n\nTip: leaving the figures folder empty means "
        "the engine produces none.",
    "\u3000\u3000未变化基线 OA = %.4f（预测改动越少，越接近这个值）":
        "\u3000\u3000No-change baseline OA = %.4f (the fewer changes predicted, "
        "the closer to this value)",
    # ------------------------------------------------------------------ 菜单与提示
    "CA-Markov 结果…": "CA-Markov Results…",
    "打开最近一次 CA-Markov 运行的结果面板": "Open the result panel of the latest run",
    "还没有可显示的结果。\n\n请先在处理工具箱里运行 "
    "「CA-Markov → 变化预测」或「转移分析」。":
        "No results to show yet.\n\nRun 'CA-Markov → Land-use prediction' or "
        "'Transition analysis' in the Processing Toolbox first.",
    # ------------------------------------------------------------------ 帮助正文
    "调用内置的 CA-Markov 引擎完成土地利用变化分析与预测。\n\n"
    "引擎以子进程运行，使用独立的 Python 解释器，不占用 QGIS 进程。\n"
    "各期栅格必须**同网格、同坐标系**（程序会检查），不做自动重采样。\n\n"
    "转移矩阵来源建议先用「最近一个区间」跑一次转移分析看矩阵，"
    "确认数据与无效值设置无误后再做预测。":
        "Runs land-use change analysis and prediction with the bundled CA-Markov engine.\n\n"
        "The engine runs in a child process with its own Python interpreter, so it never "
        "occupies the QGIS process.\n"
        "All period rasters must share **the same grid and CRS** (this is checked); "
        "no automatic resampling is done.\n\n"
        "Tip: run a transition analysis with 'Most recent interval' first to inspect the "
        "matrix and confirm the data and NoData value before predicting.",
    "只统计转移矩阵、转移概率与转移预算，并输出面积变化表，"
    "**不训练模型、不写预测栅格**，通常几秒完成。\n\n"
    "建议在正式预测前先跑一次：\n"
    "· 时期顺序是否从旧到新；\n"
    "· 无效值是否设对（设错会把大片有效像元当无效）；\n"
    "· 类别名是否正确——类别值超过类别数会被当成无效值。\n\n"
    "「适宜性来源」在此模式下不参与计算，可以忽略。":
        "Computes only the transition matrix, probabilities and budget, plus an "
        "area-change table. **No model training and no prediction raster**; usually seconds.\n\n"
        "Run it before a real prediction to check:\n"
        "· periods are ordered oldest to newest;\n"
        "· the NoData value is right (a wrong one turns large valid areas into NoData);\n"
        "· class names are right - values above the class count are treated as NoData.\n\n"
        "'Suitability source' is ignored in this mode.",
    "用各期的驱动因子（高程、坡度、距道路距离、人口等）训练随机森林，"
    "学习「哪里更容易发生转移」，输出可复用的模型文件（.npz）。\n\n"
    "训练样本来自相邻两期的变化像元：变化像元全保留，不变像元按"
    "「不变像元采样倍数」抽样，避免类别极度不平衡。\n\n"
    "训练完成后，预测算法里指定这个模型即可跳过训练，节省几分钟。":
        "Trains a random forest on the driver rasters (elevation, slope, distance to roads, "
        "population, ...) to learn where transitions are likely, and writes a reusable "
        "model file (.npz).\n\n"
        "Training samples come from changed pixels between adjacent periods: all changed "
        "pixels are kept and unchanged ones are sampled by the 'unchanged-pixel sampling "
        "ratio' to avoid extreme class imbalance.\n\n"
        "Once trained, point the prediction algorithm at this model to skip training.",
    "从最后一期出发，按 Markov 转移预算与适宜性/邻域约束做元胞自动机分配，"
    "预测未来若干步的土地利用格局。\n\n"
    "输出：预测栅格（GeoTIFF，≤255 类时内嵌类别色彩表）、文本报告、"
    "混淆矩阵/转移矩阵/面积变化/对比图/变化热点等图表、指标 JSON。\n\n"
    "精度评价默认采用**时间外推**：把最后一期当作未知，只用更早的区间建模去"
    "预测它，再与实测比较——这样得到的 OA/Kappa 才代表预测能力。"
    "只有两期数据时无法外推，会自动退回同期自检（指标偏乐观），报告里会注明。\n\n"
    "提示：先用「转移分析」确认数据无误，再跑本算法。":
        "Starts from the last period and allocates cells with a CA driven by the Markov "
        "transition budget plus suitability and neighbourhood constraints, predicting "
        "land-use patterns several steps ahead.\n\n"
        "Outputs: prediction raster (GeoTIFF, with an embedded class colour table when there "
        "are at most 255 classes), text report, figures (confusion matrix, transition matrix, "
        "area change, comparison, change hotspots) and a metrics JSON.\n\n"
        "Accuracy assessment uses **temporal hold-out** by default: the last period is treated "
        "as unknown and predicted from earlier intervals, then compared with observations - "
        "only that OA/Kappa reflects predictive skill. With two periods hold-out is impossible, "
        "so it falls back to in-sample validation (optimistic) and the report says so.\n\n"
        "Tip: run 'Transition analysis' first to confirm the data, then run this algorithm.",
}
