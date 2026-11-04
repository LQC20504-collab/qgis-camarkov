# -*- coding: utf-8 -*-
"""三个 CA-Markov 算法的共用基类。

职责划分：

* :meth:`initAlgorithm` 定义全部参数（三个算法共用一套，靠 ``MODE`` 区分）；
* :meth:`checkParameterValues` 做**能在 QGIS 侧提前发现**的校验
  （期数、本地文件、同网格、同 CRS、输出后缀、无效值范围）；
* :meth:`processAlgorithm` 组装 job.json → 起子进程 → 读回 metrics；
* :meth:`postProcessAlgorithm` 只做收尾（写设置 + 一行日志摘要），**不弹窗**。

``processAlgorithm`` 跑在 worker 线程，禁止碰任何 QGIS 界面对象；
界面只在 ``postProcessAlgorithm``（主线程）或工具栏动作里创建。
"""

import json
import os
import tempfile

from qgis.core import (
    Qgis,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMatrix,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsSettings,
)

from ..core import job_schema, metrics as metrics_mod, runner
from ..core.locator import find as find_python

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(PLUGIN_DIR, "resources", "engine")
ENGINE_SCRIPT = os.path.join(ENGINE_DIR, "camarkov_engine.py")

TRANSITION_LABELS = ["最近一个区间", "最近两期平均（推荐）", "全部区间累计"]
SUITABILITY_LABELS = [
    "随机森林转移潜力（推荐）",
    "因子加权（MCE）",
    "外部适宜性图集",
    "不使用适宜性",
]
NORMALIZE_LABELS = ["分位数 2%–98%（推荐）", "最小-最大值"]
BAND_MODE_LABELS = ["按顺序（波段 1 = 类别 0）", "按类别值（波段号 = 类别值）"]
LANG_LABELS = ["跟随界面（中文）", "English"]


class CamarkovAlgorithmBase(QgsProcessingAlgorithm):
    """共用参数与执行流程；子类只需给出 ``MODE``、名称与额外输出。"""

    MODE = "predict"
    GROUP = "变化预测"
    GROUP_ID = "predict"

    # 子类覆写：是否显示栅格/模型输出
    NEEDS_RASTER_OUTPUT = False
    NEEDS_MODEL_OUTPUT = False
    # 引擎只在 predict 里写文本报告；analyze/train 不写，因此默认不暴露该输出
    SUPPORTS_REPORT = True

    # ------------------------------------------------------------------ 元信息

    def group(self):
        """工具箱里的分组名。"""
        return self.GROUP

    def groupId(self):  # noqa: N802  (QGIS 约定)
        """分组的稳定标识。"""
        return self.GROUP_ID

    def svgIconPath(self):  # noqa: N802  (QGIS 约定)
        """算法图标。"""
        return os.path.join(PLUGIN_DIR, "resources", "icon.svg")

    def shortHelpString(self):  # noqa: N802  (QGIS 约定)
        """帮助页正文。"""
        return (
            "调用内置的 CA-Markov 引擎完成土地利用变化分析与预测。\n\n"
            "引擎以子进程运行，使用独立的 Python 解释器，不占用 QGIS 进程。\n"
            "各期栅格必须**同网格、同坐标系**（程序会检查），不做自动重采样。\n\n"
            "转移矩阵来源建议先用「最近一个区间」跑一次转移分析看矩阵，"
            "确认数据与无效值设置无误后再做预测。"
        )

    # ------------------------------------------------------------------ 参数

    def initAlgorithm(self, config=None):  # noqa: N802  (QGIS 约定)
        """定义全部参数。"""
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "PERIODS",
                "土地利用分期栅格（按时间从旧到新，至少两期）",
                QgsProcessing.SourceType.TypeRaster,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "PERIOD_BAND",
                "各期使用的波段号",
                Qgis.ProcessingNumberParameterType.Integer,
                1,
                minValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "NODATA",
                "无效值（0~65535；>255 时输出为 uint16 且不含类别色彩表）",
                Qgis.ProcessingNumberParameterType.Integer,
                0,
                minValue=0,
                maxValue=65535,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "CLASS_COUNT",
                "类别数（0 = 按数据自动推断）",
                Qgis.ProcessingNumberParameterType.Integer,
                0,
                minValue=0,
                maxValue=255,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "TRANSITION_SOURCE",
                "转移矩阵来源",
                TRANSITION_LABELS,
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "SUITABILITY_MODE",
                "适宜性来源",
                SUITABILITY_LABELS,
                defaultValue=3,
            )
        )

        self._add_rf_parameters()
        self._add_factor_parameters()
        self._add_advanced_parameters()
        self._add_output_parameters()

    def _add_rf_parameters(self):
        """随机森林相关参数（大部分收进「高级」区）。"""
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "TRAIN_DRIVERS",
                "训练驱动因子栅格（顺序即特征顺序；随机森林模式必需）",
                QgsProcessing.SourceType.TypeRaster,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "RF_MODEL",
                "复用已训练的模型（.npz，可留空表示当场训练）",
                extension="npz",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "RF_FORCE_TRAIN", "即使给了模型也强制重训", defaultValue=False
            )
        )

        advanced = [
            QgsProcessingParameterNumber(
                "TRAIN_TREES",
                "树的数量",
                Qgis.ProcessingNumberParameterType.Integer,
                200,
                minValue=1,
                maxValue=2000,
            ),
            QgsProcessingParameterNumber(
                "TRAIN_DEPTH",
                "最大深度（0 = 不限制）",
                Qgis.ProcessingNumberParameterType.Integer,
                20,
                minValue=0,
                maxValue=200,
            ),
            QgsProcessingParameterNumber(
                "TRAIN_IMBALANCE",
                "不变像元采样倍数（变化像元的几倍）",
                Qgis.ProcessingNumberParameterType.Double,
                2.0,
                minValue=0.1,
                maxValue=20.0,
            ),
            QgsProcessingParameterNumber(
                "TRAIN_SEED",
                "随机种子（保证可复现）",
                Qgis.ProcessingNumberParameterType.Integer,
                42,
                minValue=0,
                maxValue=999999,
            ),
        ]
        for param in advanced:
            param.setFlags(param.flags() | Qgis.ProcessingParameterFlag.Advanced)
            self.addParameter(param)

    def _add_factor_parameters(self):
        """因子加权与外置适宜性图集的参数。"""
        factors = QgsProcessingParameterMatrix(
            "FACTORS",
            "加权因子（随机森林模式忽略；每行：路径 / 波段 / 权重 / 方向）",
            numberRows=0,
            hasFixedNumberRows=False,
            headers=["路径", "波段", "权重", "方向(1正向/-1负向)"],
            optional=True,
        )
        self.addParameter(factors)

        external = QgsProcessingParameterRasterLayer(
            "EXTERNAL_SUITABILITY", "外部适宜性图集（多波段，仅外部模式用）", optional=True
        )
        self.addParameter(external)
        self.addParameter(
            QgsProcessingParameterEnum(
                "EXTERNAL_BAND_MODE", "图集波段与类别的对应关系", BAND_MODE_LABELS, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "CONSTRAINT", "限制性条件图（>0.5 可转变，0 禁止；可选）", optional=True
            )
        )

    def _add_advanced_parameters(self):
        """邻域、权重、精度评价等参数，大部分收进「高级」区。"""
        self.addParameter(
            QgsProcessingParameterNumber(
                "STEPS",
                "预测步数（每步用同一转移矩阵重新分配）",
                Qgis.ProcessingNumberParameterType.Integer,
                1,
                minValue=1,
                maxValue=50,
            )
        )
        advanced = [
            QgsProcessingParameterNumber(
                "NEIGHBORHOOD_SIZE",
                "邻域窗口（3/5/7，奇数）",
                Qgis.ProcessingNumberParameterType.Integer,
                5,
                minValue=3,
                maxValue=99,
            ),
            QgsProcessingParameterBoolean(
                "RECOMPUTE_NEIGHBORHOOD", "每一步都重算邻域", defaultValue=True
            ),
            QgsProcessingParameterEnum(
                "NORMALIZE_METHOD", "因子标准化方法", NORMALIZE_LABELS, defaultValue=0
            ),
            QgsProcessingParameterNumber(
                "WEIGHT_SUITABILITY",
                "适宜性权重",
                Qgis.ProcessingNumberParameterType.Double,
                0.6,
                minValue=0.0,
                maxValue=1.0,
            ),
            QgsProcessingParameterNumber(
                "WEIGHT_NEIGHBORHOOD",
                "邻域权重",
                Qgis.ProcessingNumberParameterType.Double,
                0.4,
                minValue=0.0,
                maxValue=1.0,
            ),
            QgsProcessingParameterBoolean(
                "MODULATE_BY_PROBABILITY", "用转移概率调制适宜性（区分目标类）", defaultValue=True
            ),
            QgsProcessingParameterBoolean("VALIDATION_ENABLED", "输出精度评价", defaultValue=True),
            QgsProcessingParameterBoolean(
                "VALIDATION_SAME_PERIOD",
                "改用同期自检（in-sample，指标偏乐观）",
                defaultValue=False,
            ),
            QgsProcessingParameterEnum("LANG", "报告与图表语言", LANG_LABELS, defaultValue=0),
            QgsProcessingParameterNumber(
                "CHUNK",
                "推理分块大小（像元）",
                Qgis.ProcessingNumberParameterType.Integer,
                200000,
                minValue=10000,
                maxValue=4000000,
            ),
        ]
        for param in advanced:
            param.setFlags(param.flags() | Qgis.ProcessingParameterFlag.Advanced)
            self.addParameter(param)

        # 类别名不做成独立参数：用户多半只想改名字而不想被强制填 ——
        # 默认按类别数自动生成，需要时可在「高级」里覆盖。
        names = QgsProcessingParameterMatrix(
            "CLASS_NAMES",
            "类别名称（可选；每行一个：序号 / 名称）",
            numberRows=0,
            hasFixedNumberRows=False,
            headers=["序号", "名称"],
            optional=True,
        )
        names.setFlags(names.flags() | Qgis.ProcessingParameterFlag.Advanced)
        self.addParameter(names)

    def _add_output_parameters(self):
        """输出。metrics 是必需项：没有它引擎算完也不落盘。"""
        self.addParameter(
            QgsProcessingParameterFileDestination(
                "OUTPUT_METRICS", "指标 JSON（必需）", "JSON 文件 (*.json)"
            )
        )
        if self.SUPPORTS_REPORT:
            self.addParameter(
                QgsProcessingParameterFileDestination(
                    "OUTPUT_REPORT", "文本报告（可选）", "文本文件 (*.txt)", optional=True
                )
            )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                "OUTPUT_FIG_DIR", "图表目录（可选；留空则不出图）", optional=True
            )
        )
        if self.NEEDS_RASTER_OUTPUT:
            self.addParameter(
                QgsProcessingParameterRasterDestination(
                    "OUTPUT_RASTER", "预测栅格（仅支持 .tif/.tiff）"
                )
            )
        if self.NEEDS_MODEL_OUTPUT:
            self.addParameter(
                QgsProcessingParameterFileDestination(
                    "OUTPUT_MODEL", "模型文件（.npz）", "NumPy 模型 (*.npz)"
                )
            )

    # ------------------------------------------------------------------ 校验

    def checkParameterValues(self, parameters, context):  # noqa: N802  (QGIS 约定)
        """在开跑前把能查的都查掉，避免浪费几分钟才报错。"""
        layers = self.parameterAsLayerList(parameters, "PERIODS", context)
        if len(layers) < 2:
            return False, "至少需要两期土地利用栅格（当前 %d 期）。" % len(layers)

        for index, layer in enumerate(layers):
            if layer is None:
                return False, "第 %d 期图层无效。" % (index + 1)
            source = layer.source() or ""
            path = source.split("|")[0]
            if not os.path.isfile(path):
                return False, (
                    "第 %d 期不是本地栅格文件，引擎无法读取：%s" % (index + 1, source)
                )

        grid_error = self._check_grid(layers)
        if grid_error:
            return False, grid_error

        nodata = self.parameterAsInt(parameters, "NODATA", context)
        if nodata < 0 or nodata > 65535:
            return False, "无效值必须是 0~65535 的整数。"

        mode = self._suitability_mode(parameters, context)
        if mode == "rf":
            drivers = self.parameterAsLayerList(parameters, "TRAIN_DRIVERS", context)
            model = self.parameterAsFile(parameters, "RF_MODEL", context)
            if not drivers and not model:
                return False, (
                    "随机森林模式需要提供训练驱动因子，或指定一个已训练的模型文件。\n"
                    "如果只想快速看转移矩阵，请把「适宜性来源」改成「不使用适宜性」。"
                )
        elif mode == "factor":
            values = self.parameterAsMatrix(parameters, "FACTORS", context)
            if not job_schema.parse_factor_matrix(values):
                return False, "因子加权模式至少需要一行有效因子（路径不能为空）。"
        elif mode == "external":
            atlas = self.parameterAsRasterLayer(parameters, "EXTERNAL_SUITABILITY", context)
            if atlas is None:
                return False, "外部适宜性图集模式需要指定一个多波段栅格。"

        weights = self.parameterAsDouble(parameters, "WEIGHT_SUITABILITY", context)
        weights += self.parameterAsDouble(parameters, "WEIGHT_NEIGHBORHOOD", context)
        if weights <= 1e-9:
            return False, "适宜性权重与邻域权重不能同时为 0。"

        if self.NEEDS_RASTER_OUTPUT:
            raster = self.parameterAsOutputLayer(parameters, "OUTPUT_RASTER", context)
            if raster and os.path.splitext(raster)[1].lower() not in (".tif", ".tiff"):
                return False, (
                    "预测栅格只支持 .tif/.tiff。\n"
                    "引擎固定写出 GeoTIFF，其它扩展名会得到名实不符的文件。"
                )
        return True, ""

    def _check_grid(self, layers):
        """检查各期是否同网格同坐标系。

        引擎的判定是「宽高 + 6 个仿射系数，相对容差 1e-9」，并且**完全不比较 CRS、
        也不做重采样**——CRS 不同会静默产出位置错误的结果。所以这里除了网格，
        还要显式比对 CRS。
        """
        base = layers[0]
        for index, layer in enumerate(layers[1:], start=2):
            if layer.width() != base.width() or layer.height() != base.height():
                return "第 %d 期尺寸不一致：%d×%d ≠ %d×%d。" % (
                    index,
                    layer.width(),
                    layer.height(),
                    base.width(),
                    base.height(),
                )
            if not layer.crs() == base.crs():
                return (
                    "第 %d 期坐标系与第 1 期不一致。\n"
                    "引擎不会自动重投影，请先统一坐标系再运行。" % index
                )
            if not self._extent_close(layer.extent(), base.extent(), base):
                return (
                    "第 %d 期的范围与第 1 期不一致（同一网格应完全重合）。\n"
                    "请先对齐网格再运行。" % index
                )
        return ""

    @staticmethod
    def _extent_close(a, b, base_layer):
        """按千分之一像元的容差比较两个范围。"""
        tol = max(abs(base_layer.rasterUnitsPerPixelX()), abs(base_layer.rasterUnitsPerPixelY()))
        tol = max(tol * 1e-3, 1e-9)
        return (
            abs(a.xMinimum() - b.xMinimum()) <= tol
            and abs(a.xMaximum() - b.xMaximum()) <= tol
            and abs(a.yMinimum() - b.yMinimum()) <= tol
            and abs(a.yMaximum() - b.yMaximum()) <= tol
        )

    # ------------------------------------------------------------------ 执行

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802  (QGIS 约定)
        """组装 job、跑引擎、读回 metrics。"""
        feedback.setProgress(0)
        feedback.pushInfo("准备 CA-Markov 运行环境…")

        python_env = find_python(
            qgis_prefix=self._qgis_prefix(),
            saved=QgsSettings().value("camarkov/python", "", type=str) or None,
        )
        if not python_env.usable:
            raise QgsProcessingException(
                "找不到可用的 Python 解释器，或缺少依赖：\n\n%s\n\n"
                "可以在「设置 → 选项 → 处理」之外手动指定；也可以直接执行上面的 pip 命令安装。"
                % python_env.describe()
            )
        feedback.pushInfo("解释器：%s" % python_env.describe())

        if not os.path.isfile(ENGINE_SCRIPT):
            raise QgsProcessingException("找不到引擎脚本：%s" % ENGINE_SCRIPT)

        job = self._build_job(parameters, context)
        work_dir = tempfile.mkdtemp(prefix="camarkov_")
        job_path = os.path.join(work_dir, "job.json")
        # 引擎用 json.load 读，BOM 会让它报错；ensure_ascii=False 保持中文可读
        with open(job_path, "w", encoding="utf-8") as handle:
            json.dump(job, handle, ensure_ascii=False)

        result = runner.run_engine(
            python_env.exe_path,
            ENGINE_SCRIPT,
            job_path,
            on_progress=lambda percent, text: self._on_progress(feedback, percent, text),
            on_info=feedback.pushInfo,
            on_warn=feedback.pushWarning,
            is_cancelled=feedback.isCanceled,
        )

        try:
            metrics_path = job.get("outputs", {}).get("metrics")
            if result.cancelled:
                raise QgsProcessingException("已取消。")
            if not result.ok:
                raise QgsProcessingException(result.error_message())
            if not metrics_path or not os.path.isfile(metrics_path):
                raise QgsProcessingException(
                    "引擎没有生成指标文件，可能被提前中断：\n%s" % metrics_path
                )
            data = metrics_mod.load(metrics_path)
        finally:
            self._cleanup(work_dir, job, result)

        self._last_metrics_path = metrics_path
        self._last_summary = metrics_mod.summary(data)
        self._last_warnings = list(data.get("warnings") or [])

        feedback.setProgress(100)
        return self._results(parameters, context, metrics_path)

    def _build_job(self, parameters, context):
        """把 QGIS 参数翻译成引擎的 job 字典。"""
        layers = self.parameterAsLayerList(parameters, "PERIODS", context)
        band = self.parameterAsInt(parameters, "PERIOD_BAND", context)
        periods = [
            {"path": self._local_path(layer), "band": band}
            for layer in layers
        ]

        class_count = self.parameterAsInt(parameters, "CLASS_COUNT", context)
        nodata = self.parameterAsInt(parameters, "NODATA", context)
        names = self._class_names(parameters, context, class_count, nodata)

        mode = self._suitability_mode(parameters, context)
        factors = []
        if mode == "factor":
            factors = job_schema.parse_factor_matrix(
                self.parameterAsMatrix(parameters, "FACTORS", context)
            )

        drivers = []
        if mode == "rf":
            drivers = [
                {"path": self._local_path(layer), "band": 1}
                for layer in self.parameterAsLayerList(parameters, "TRAIN_DRIVERS", context)
            ]

        model_path = self.parameterAsFile(parameters, "RF_MODEL", context) or None
        external = self.parameterAsRasterLayer(parameters, "EXTERNAL_SUITABILITY", context)
        constraint = self.parameterAsRasterLayer(parameters, "CONSTRAINT", context)

        outputs = {
            "metrics": self.parameterAsFileOutput(parameters, "OUTPUT_METRICS", context),
            "fig_dir": self._figure_dir(parameters, context),
        }
        if self.SUPPORTS_REPORT:
            outputs["report"] = self.parameterAsFileOutput(parameters, "OUTPUT_REPORT", context)
        if self.NEEDS_RASTER_OUTPUT:
            outputs["raster"] = self.parameterAsOutputLayer(parameters, "OUTPUT_RASTER", context)
        if self.NEEDS_MODEL_OUTPUT:
            outputs["model"] = self.parameterAsFileOutput(parameters, "OUTPUT_MODEL", context)

        return job_schema.build_job(
            mode=self.MODE,
            periods=periods,
            nodata=nodata,
            class_count=class_count,
            class_names=names,
            transition_source=job_schema.TRANSITION_SOURCES[
                self.parameterAsEnum(parameters, "TRANSITION_SOURCE", context)
            ],
            steps=self.parameterAsInt(parameters, "STEPS", context),
            neighborhood_size=self.parameterAsInt(parameters, "NEIGHBORHOOD_SIZE", context),
            recompute_neighborhood=self.parameterAsBool(
                parameters, "RECOMPUTE_NEIGHBORHOOD", context
            ),
            suitability_mode=mode,
            normalize_method=job_schema.NORMALIZE_METHODS[
                self.parameterAsEnum(parameters, "NORMALIZE_METHOD", context)
            ],
            factors=factors,
            weights={
                "suitability": self.parameterAsDouble(parameters, "WEIGHT_SUITABILITY", context),
                "neighborhood": self.parameterAsDouble(
                    parameters, "WEIGHT_NEIGHBORHOOD", context
                ),
            },
            modulate_by_probability=self.parameterAsBool(
                parameters, "MODULATE_BY_PROBABILITY", context
            ),
            validation_enabled=self.parameterAsBool(parameters, "VALIDATION_ENABLED", context),
            validation_same_period=self.parameterAsBool(
                parameters, "VALIDATION_SAME_PERIOD", context
            ),
            outputs=outputs,
            chunk=self.parameterAsInt(parameters, "CHUNK", context),
            lang="en" if self.parameterAsEnum(parameters, "LANG", context) == 1 else "zh",
            rf_model=model_path,
            rf_force_train=self.parameterAsBool(parameters, "RF_FORCE_TRAIN", context),
            train_drivers=drivers,
            # 引擎读 rf.predict_drivers；预测阶段没有单独的因子输入，先沿用训练驱动
            predict_drivers=None,
            n_estimators=self.parameterAsInt(parameters, "TRAIN_TREES", context),
            max_depth=self.parameterAsInt(parameters, "TRAIN_DEPTH", context),
            imbalance=self.parameterAsDouble(parameters, "TRAIN_IMBALANCE", context),
            seed=self.parameterAsInt(parameters, "TRAIN_SEED", context),
            constraint_path=self._local_path(constraint) if constraint else None,
            external_path=self._local_path(external) if external else None,
            external_band_mode=job_schema.BAND_MODES[
                self.parameterAsEnum(parameters, "EXTERNAL_BAND_MODE", context)
            ],
            save_model=outputs.get("model"),
        )

    def _class_names(self, parameters, context, class_count, nodata):
        """取类别名：优先用「高级」里的名称表，否则按类别数生成。"""
        values = self.parameterAsMatrix(parameters, "CLASS_NAMES", context)
        if values:
            pairs = [values[i:i + 2] for i in range(0, len(values) - 1, 2)]
            names = list(job_schema.default_class_names(class_count, nodata))
            for pair in pairs:
                try:
                    index = int(float(pair[0]))
                except (TypeError, ValueError):
                    continue
                if 0 <= index < len(names):
                    names[index] = str(pair[1])
            if names:
                return names
        return job_schema.default_class_names(class_count, nodata)

    # ------------------------------------------------------------------ 收尾

    def postProcessAlgorithm(self, context, feedback):  # noqa: N802  (QGIS 约定)
        """写设置 + 打一行摘要。**不弹窗**：批处理与模型器也会走到这里。"""
        path = getattr(self, "_last_metrics_path", "")
        if path and os.path.isfile(path):
            QgsSettings().setValue("camarkov/last_metrics", path)
            feedback.pushInfo("CA-Markov 完成：%s" % getattr(self, "_last_summary", ""))
            feedback.pushInfo("指标文件：%s" % path)
            for warning in getattr(self, "_last_warnings", []):
                feedback.pushWarning(warning)
        return {}

    def _results(self, parameters, context, metrics_path):
        """构造返回值：QGIS 靠这些键加载图层。"""
        results = {"OUTPUT_METRICS": metrics_path}
        if self.SUPPORTS_REPORT:
            report = self.parameterAsFileOutput(parameters, "OUTPUT_REPORT", context)
            if report:
                results["OUTPUT_REPORT"] = report
        if self.NEEDS_RASTER_OUTPUT:
            results["OUTPUT_RASTER"] = self.parameterAsOutputLayer(
                parameters, "OUTPUT_RASTER", context
            )
        if self.NEEDS_MODEL_OUTPUT:
            results["OUTPUT_MODEL"] = self.parameterAsFileOutput(
                parameters, "OUTPUT_MODEL", context
            )
        return results

    def _cleanup(self, work_dir, job, result):
        """删除临时 job 目录；取消或失败时顺带删掉本次写出的半成品。

        只删除**本次运行创建**的文件：先记录运行前是否已存在，
        避免误删用户已有的同名输出。
        """
        try:
            import shutil

            if os.path.isdir(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:  # nosec B110
            pass

        if result is not None and (result.cancelled or not result.ok):
            outputs = job.get("outputs") or {}
            for key in ("raster", "model"):
                path = outputs.get(key)
                if path and os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    # ------------------------------------------------------------------ 工具

    @staticmethod
    def _on_progress(feedback, percent, text):
        """把进度与阶段名送到 QGIS。空文本表示阶段没变，不刷日志。"""
        feedback.setProgress(percent)
        if text:
            feedback.setProgressText(text)

    def _suitability_mode(self, parameters, context):
        """把「适宜性来源」的下拉项翻译成引擎的枚举字符串。"""
        index = self.parameterAsEnum(parameters, "SUITABILITY_MODE", context)
        return job_schema.SUITABILITY_MODES[min(index, 3)]

    def _figure_dir(self, parameters, context):
        """图表目录；用户留空时给一个临时目录，否则引擎一张图都不出。

        不能用 ``QgsProcessingUtils.generateTempFilename``：它返回的是**文件**路径，
        拿它当目录 ``makedirs`` 会留下一个"名字像文件的目录"，QGIS 退出清理时
        会以 0xC0000409 崩溃（没有 traceback，只有退出码）。
        """
        folder = self.parameterAsFileOutput(parameters, "OUTPUT_FIG_DIR", context)
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                pass
            return folder
        return tempfile.mkdtemp(prefix="camarkov_figs_")

    @staticmethod
    def _local_path(layer):
        """取图层的本地文件路径；``|`` 之后是图层内的子数据集记号。"""
        return os.path.abspath((layer.source() or "").split("|")[0])

    @staticmethod
    def _qgis_prefix():
        """QGIS 安装前缀，用于定位自带的 Python。"""
        from qgis.core import QgsApplication

        return QgsApplication.prefixPath()
