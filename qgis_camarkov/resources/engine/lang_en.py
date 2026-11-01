# -*- coding: utf-8 -*-
"""SharpGIS CA-Markov 引擎的英文译文表。

键是引擎源码里的中文原文（必须逐字一致），值是对应的英文。
camarkov_engine.py 用 L(text) 取值：命中则返回英文，未命中则原样返回中文。

带 % 占位符的条目，译文里的占位符必须与原文数量、顺序、类型完全一致，
因为调用处写成 L("...") % args —— 先翻译、再套参数。
"""

EN = {
    # ---------------- 类别名（CLCD 兜底名） ----------------
    "无效值": "NoData",
    "耕地": "Cropland",
    "森林": "Forest",
    "草地": "Grassland",
    "灌木": "Shrubland",
    "水体": "Water",
    "冰雪": "Snow and ice",
    "裸地": "Bare land",
    "不透水面": "Impervious surface",

    # ---------------- 数据读取与校验错误 ----------------
    "缺少 Python 依赖 rasterio。请执行：\n  pip install rasterio":
        "Missing Python dependency rasterio. Run:\n  pip install rasterio",
    "文件不存在：": "File not found: ",
    "波段号 %d 越界：%s 只有 %d 个波段":
        "Band %d out of range: %s has only %d band(s)",
    "尺寸不同（%d×%d ≠ %d×%d）": "Different size (%d×%d ≠ %d×%d)",
    "仿射系数 %d 不一致（%.10g ≠ %.10g）":
        "Geo-transform coefficient %d differs (%.10g ≠ %.10g)",
    "%s 含有非整数值，不适合作为土地利用分类栅格：%s":
        "%s contains non-integer values and cannot be used as a land-use class raster: %s",
    "%s 有 %d 个像元取值超出类别范围 0..%d（例如 %s），已按无效值处理":
        "%s has %d pixels outside the class range 0..%d (e.g. %s); they were treated as NoData",
    "至少需要两期数据才能统计转移矩阵":
        "At least two periods are required to compute the transition matrix",
    "缺少 Python 依赖 scikit-learn。请执行：\n  pip install scikit-learn":
        "Missing Python dependency scikit-learn. Run:\n  pip install scikit-learn",
    "训练样本不足（只有 %d 个），请检查两期数据的有效像元":
        "Not enough training samples (%d); check the valid pixels of the two periods",
    "模型内部类别数与概率列数不一致（%d vs %d）":
        "Model class count does not match the probability columns (%d vs %d)",
    "模型文件不存在：": "Model file not found: ",
    "因子权重之和为 0，请至少给一个正权重":
        "The factor weights sum to zero; give at least one a positive weight",
    "适宜性图集波段号需等于类别值，缺少类别 %s 对应波段":
        "Suitability atlas band number must equal the class value; band for class %s is missing",
    "适宜性图集只有 %d 个波段，但有 %d 个有效类别":
        "The suitability atlas has only %d band(s) but %d valid class(es) exist",
    "适宜性图集未覆盖类别：%s": "Suitability atlas does not cover these classes: %s",

    # ---------------- 随机森林 ----------------
    "训练随机森林：%d 棵树 · 深度 %s · %d 个特征 · %d 个样本 · sklearn %s":
        "Training random forest: %d trees · depth %s · %d features · %d samples · sklearn %s",
    "无限制": "unlimited",
    "载入随机森林模型：": "Loading random forest model: ",
    "模型类别数 %d 与当前 %d 不一致":
        "Model has %d classes but the current data uses %d",
    "载入模型（%d 棵树）": "Model loaded (%d trees)",
    "预测用驱动因子有 %d 个，但模型需要 %d 个（%s）":
        "%d prediction driver(s) given but the model needs %d (%s)",
    "驱动因子 %s 与基期网格不一致：%s":
        "Driver %s does not match the base grid: %s",
    "随机森林适宜性": "Random-forest suitability",
    "因子加权模式至少需要一个驱动因子":
        "The factor-weighted mode needs at least one driver",
    "合成 %d 个因子的加权适宜性图":
        "Building the weighted suitability map from %d factor(s)",
    "外部适宜性图集模式需要指定图集文件":
        "The external suitability atlas mode requires an atlas file",
    "适宜性图集与基期网格不一致：%s":
        "Suitability atlas does not match the base grid: %s",
    "载入外部适宜性图集：": "Loading external suitability atlas: ",
    "未知的适宜性模式：": "Unknown suitability mode: ",

    # ---------------- 图表标签 ----------------
    "目标类别": "Target class",
    "源类别": "Source class",
    "Markov 转移概率矩阵（行归一化）":
        "Markov transition probabilities (row-normalised)",
    "基期": "Base",
    "末期实测": "Observed last",
    "预测": "Predicted",
    "面积（km²）": "Area (km²)",
    "像元数": "Pixels",
    "各类面积变化": "Area by class",
    "预测类别": "Predicted class",
    "实测类别": "Observed class",
    "混淆矩阵（像元数）": "Confusion matrix (pixels)",
    "重要性": "Importance",
    "随机森林特征重要性": "Random-forest feature importance",
    "%s（1/%d 抽样）": "%s (1/%d sampled)",
    "差异（红色=分类不一致）": "Difference (red = disagreement)",
    "土地利用类别": "Land-use class",
    "变化热点（1/%d 抽样，按转移类型着色）":
        "Change hotspots (1/%d sampled, coloured by transition)",
    "未变化": "Unchanged",
    "无变化": "No change",
    "其他变化": "Other change",

    # ---------------- 报告 ----------------
    "SharpGIS · 土地利用变化预测报告":
        "SharpGIS · Land-use Change Prediction Report",
    "生成时间：": "Generated: ",
    "一、输入数据": "1. Input data",
    "  第 %d 期：%s（波段 %d）": "  Period %d: %s (band %d)",
    "  无效值：%s": "  NoData: %s",
    "  类别数：%d": "  Classes: %d",
    "  像元尺寸：%s（每像元 %s）": "  Pixel size: %s (per pixel %s)",
    "未知（地理坐标系）": "unknown (geographic CRS)",
    "  坐标系：%s": "  CRS: %s",
    "无": "none",
    "  网格：%d × %d": "  Grid: %d × %d",
    "二、建模参数": "2. Modelling parameters",
    "  转移矩阵来源：%s（区间 %s）": "  Transition source: %s (intervals %s)",
    "  预测步数：%d": "  Forecast steps: %d",
    "  适宜性模式：%s": "  Suitability mode: %s",
    "  随机森林：%s": "  Random forest: %s",
    "  评分权重：适宜性 %.3f / 邻域 %.3f（归一化后 %.3f / %.3f）":
        "  Weights: suitability %.3f / neighbourhood %.3f (normalised %.3f / %.3f)",
    "  邻域窗口：%d × %d": "  Neighbourhood window: %d × %d",
    "  转移概率调制：%s": "  Probability modulation: %s",
    "开": "on",
    "关": "off",
    "三、转移矩阵（像元计数）": "3. Transition matrix (pixel counts)",
    "四、转移概率矩阵（行归一化）": "4. Transition probabilities (row-normalised)",
    "五、转移预算矩阵（行和 = 当期像元数）":
        "5. Transition budget (row sum = pixel count of that class)",
    "六、面积统计": "6. Area statistics",
    "类别": "Class",
    "末期": "Last",
    "变化率": "Change",
    "像元": "pixels",
    "  （单位：%s）": "  (unit: %s)",
    "七、精度评价": "7. Accuracy assessment",
    "  方案：%s": "  Scheme: %s",
    "  总体精度 OA：%.4f": "  Overall accuracy (OA): %.4f",
    "  Kappa 系数：%.4f": "  Kappa coefficient: %.4f",
    "  未变化基线 OA：%.4f": "  No-change baseline OA: %.4f",
    "  有效验证像元：%d": "  Validated pixels: %d",
    "八、警告": "8. Warnings",
    "九、输出": "9. Outputs",
    "  耗时：%.1f 秒": "  Elapsed: %.1f s",

    # ---------------- 进度与状态消息 ----------------
    "CA 分配 第 %d/%d 步": "CA allocation step %d/%d",
    "第 %d 步有 %d 个转移预算无法落实（受限或候选不足）":
        "Step %d could not place %d transition budget(s) (constrained or not enough candidates)",
    "统计转移矩阵": "Counting transitions",
    "转移矩阵图生成失败：%s": "Failed to draw the transition matrix: %s",
    "统计完成": "Statistics done",
    "至少需要两期土地利用数据（当前 %d 期）":
        "At least two land-use periods are required (%d given)",
    "第 %d 期 %s 与第 1 期网格不一致：%s":
        "Period %d (%s) does not match the grid of period 1: %s",
    "第 %d 期": "Period %d",
    "读取第 %d 期": "Reading period %d",
    "类别数必须 ≥ 2": "The number of classes must be ≥ 2",
    "类别 %d": "Class %d",
    "只有 %d 个区间，'最近两期平均'退化为最近一个区间":
        "Only %d interval(s): 'average of the last two periods' falls back to the last interval",
    "存在没有任何有效像元的一期，请检查无效值设置":
        "One period has no valid pixel at all; check the NoData setting",
    "限制性条件图与基期网格不一致：%s":
        "The constraint map does not match the base grid: %s",
    "限制性条件图：%d 个像元禁止转变":
        "Constraint map: %d pixel(s) are locked from transition",
    "随机森林模式需要提供训练用驱动因子":
        "The random-forest mode needs training drivers",
    "载入驱动因子": "Loading drivers",
    "抽取训练样本 %d 个": "Sampling %d training pixels",
    "%d 棵树 · 深度 %s · 样本 %d": "%d trees · depth %s · %d samples",
    "保存模型：": "Saving model: ",
    "模型已保存（%d 棵树）": "Model saved (%d trees)",
    "模型保存失败：%s": "Failed to save the model: %s",
    "训练完成：": "Training finished: ",
    "未做精度评价": "No accuracy assessment",
    "写出预测栅格": "Writing the prediction raster",
    "生成图表": "Drawing figures",
    "面积变化图生成失败：%s": "Failed to draw the area-change chart: %s",
    "混淆矩阵图生成失败：%s": "Failed to draw the confusion matrix: %s",
    "特征重要性图生成失败：%s": "Failed to draw the feature-importance chart: %s",
    "对比图生成失败：%s": "Failed to draw the comparison image: %s",
    "变化热点图生成失败：%s": "Failed to draw the change-hotspot image: %s",
    "生成报告": "Writing the report",
    "同期 in-sample 检验（只有两期数据，无法做时间外推；指标会偏乐观）":
        "In-sample check (only two periods, so no temporal extrapolation is possible; scores are optimistic)",
    "精度评价使用同期 in-sample 方案，OA/Kappa 偏乐观":
        "The accuracy assessment used the in-sample scheme, so OA/Kappa are optimistic",
    "同期 in-sample 检验（用户显式指定，指标偏乐观）":
        "In-sample check (explicitly requested; scores are optimistic)",
    "精度评价被显式设为同期 in-sample，OA/Kappa 偏乐观":
        "The accuracy assessment was explicitly set to in-sample, so OA/Kappa are optimistic",
    "时间外推检验：用 %d→%d 区间建模，预测第 %d 期并与实测比较":
        "Temporal extrapolation: trained on interval %d→%d, predicted period %d and compared with observations",
    "精度评价：": "Accuracy assessment: ",
    "精度评价：预测改动 %d 个像元；错误 %d 个（未变化基线 %d 个）":
        "Accuracy assessment: the prediction changed %d pixel(s); %d error(s) (no-change baseline %d)",
    "精度评价阶段的 CA 分配有 %d 个预算未落实":
        "%d budget(s) could not be placed during the CA allocation of the accuracy assessment",
    "精度：OA=%.4f  Kappa=%.4f（未变化基线 OA=%.4f）":
        "Accuracy: OA=%.4f  Kappa=%.4f (no-change baseline OA=%.4f)",
    "训练需要至少一个驱动因子": "Training needs at least one driver",
    "训练样本 %d 个，变化像元占比 %.2f%%":
        "%d training sample(s), %.2f%% of pixels changed",
    "训练随机森林": "Training the random forest",
    "训练模式需要指定模型输出路径":
        "The training mode needs an output path for the model",
    "导出模型": "Exporting the model",
    "模型已保存：%s（%.1f MB，%d 棵树）":
        "Model saved: %s (%.1f MB, %d trees)",
    "%d 棵树 · 深度 %s · 样本 %d · %.1f MB":
        "%d trees · depth %s · %d samples · %.1f MB",
    "未做精度评价（训练模式）": "No accuracy assessment (training mode)",

    # ---------------- 引擎自检输出 ----------------
    "  [通过] %s %s": "  [PASS] %s %s",
    "  [失败] %s %s": "  [FAIL] %s %s",
    "== 转移矩阵 ==": "== Transition matrix ==",
    "计数矩阵": "count matrix",
    "NoData 行恒为 0": "the NoData row stays 0",
    "概率行和=1": "probability rows sum to 1",
    "空行保持全 0": "empty rows stay 0",
    "== 转移预算 ==": "== Transition budget ==",
    "每行和=当期像元数": "each row sums to the pixel count of that class",
    "预算数值": "budget values",
    "预算总量≈Markov 目标": "total budget ≈ the Markov target",
    "== 最大余数 ==": "== Largest remainder ==",
    "全概率行整体搬移": "a fully probabilistic row moves as a whole",
    "按余数分配": "remainders decide the distribution",
    "== 邻域 ==": "== Neighbourhood ==",
    "中心 5×5 占比": "share of the central 5×5",
    "中心 3×3 占比": "share of the central 3×3",
    "边界补 0": "zero padding at the border",
    "== 精度指标 ==": "== Accuracy metrics ==",
    "== 预算守恒（随机） ==": "== Budget conservation (random) ==",
    "随机概率下行和精确": "row sums are exact for random probabilities",
    "自检：%d 项通过，%d 项失败": "Self-test: %d passed, %d failed",
    "失败项：": "Failed items: ",

    # ---------------- 命令行 ----------------
    "SharpGIS CA-Markov 引擎": "SharpGIS CA-Markov engine",
    "参数 JSON 路径": "path to the parameter JSON",
    "运行纯函数自检": "run the pure-function self-test",
    "用法：camarkov_engine.py --job job.json 或 --selftest":
        "Usage: camarkov_engine.py --job job.json or --selftest",
    "无法读取参数文件：%s": "Cannot read the parameter file: %s",
    "未知模式：": "Unknown mode: ",
    "参数或数据错误：%s": "Parameter or data error: %s",

    # ---------------- 模式 / 来源的显示名 ----------------
    "最近一期": "Last interval",
    "最近两期平均": "Average of the last two intervals",
    "全部时期累计": "All intervals pooled",
    "不使用适宜性": "No suitability",
    "随机森林": "Random forest",
    "因子加权": "Factor-weighted",
    "外部适宜性图集": "External suitability atlas",
}
