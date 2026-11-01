#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SharpGIS · 土地利用变化预测引擎（CA-Markov + 随机森林转移潜力）

命令行：
    python camarkov_engine.py --job job.json     # 按 C# 下发的参数执行
    python camarkov_engine.py --selftest         # 纯函数自检（不读写栅格）

三种模式（job.json 的 mode 字段）：
    analyze  只算转移矩阵与面积统计，用于界面上的"先分析"预览
    train    训练 81 类转移潜力随机森林并保存模型
    predict  完整链路：转移矩阵 → 转移预算 → 适宜性 → 邻域 → CA 分配 → 精度评价 → 出图

标准输出行协议（C# 侧解析）：
    @@PROGRESS <0..1> <阶段>   @@INFO <文本>   @@WARN <文本>   @@DONE
退出码：0 成功 / 1 参数与数据错误 / 2 运行时异常 / 3 用户取消（由 C# 侧杀进程）
"""

from __future__ import print_function

import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

# ---------------------------------------------------------------- 行协议

def _emit(tag, text):
    sys.stdout.write("@@" + tag + " " + str(text) + "\n")
    sys.stdout.flush()


def progress(frac, msg=""):
    frac = max(0.0, min(1.0, float(frac)))
    _emit("PROGRESS", "%.4f %s" % (frac, msg))


def info(msg):
    _emit("INFO", msg)


def warn(msg):
    _emit("WARN", msg)


class JobError(Exception):
    """参数或数据错误，对应退出码 1。"""


# ---------------------------------------------------------------- 语言

_LANG = "zh"

_EN = {}


def _load_translations():
    """从同目录的 lang_en.py 载入英文译文表。

    译文表独立成文件，便于维护；找不到时退化为「全部中文」，功能不受影响。
    """
    global _EN
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "lang_en.py")
    if not os.path.exists(path):
        return
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("camarkov_lang_en", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        table = getattr(module, "EN", None)
        if isinstance(table, dict):
            _EN = table
    except Exception:
        pass


_load_translations()


def L(text, *args):
    """按当前语言取文案。

    用法一：L("保存模型：")                 —— 直接取一条固定文案。
    用法二：L("第 %d 期", k + 1)           —— 先按模板取译文，再套参数；
               译文表里的占位符必须与原文数量、顺序一致。

    没有译文时原样返回中文，保证缺词条不会变成空串。
    """
    if _LANG != "en":
        template = text
    else:
        template = _EN.get(text, text)
    if args:
        try:
            return template % args
        except (TypeError, ValueError):
            return template
    return template


# ---------------------------------------------------------------- 常量

# 与参考实现 run_validation*.py 完全一致的 CLCD 调色板
CLCD_COLORS = [
    (128, 128, 128), (57, 114, 177), (44, 160, 44), (148, 103, 189),
    (158, 218, 229), (25, 100, 180), (200, 200, 200), (188, 189, 34),
    (214, 39, 40),
]
# CLCD 兜底类别名。模块级常量会在导入时就求值（那时语言还没定），
# 因此这里用函数延迟到真正使用时再取。
def clcd_names():
    """CLCD 兜底类别名，随界面语言切换。"""
    return [L("无效值"), L("耕地"), L("森林"), L("草地"), L("灌木"),
            L("水体"), L("冰雪"), L("裸地"), L("不透水面")]


# 报告里显示的枚举值 → 可读名称
_SOURCE_NAMES = {
    "last_interval": "最近一期",
    "last_two_average": "最近两期平均",
    "all_periods": "全部时期累计",
}
_SUIT_NAMES = {
    "rf": "随机森林",
    "factor": "因子加权",
    "external": "外部适宜性图集",
    "none": "不使用适宜性",
}


def source_name(code):
    """转移矩阵来源代码 → 可读名称。"""
    key = str(code)
    return L(_SOURCE_NAMES[key]) if key in _SOURCE_NAMES else key


def suit_name(code):
    """适宜性模式代码 → 可读名称。"""
    key = str(code)
    return L(_SUIT_NAMES[key]) if key in _SUIT_NAMES else key

# DEM 类无效大值：参考实现用 3e4 作为硬阈值，这里保留并叠加 NoData 元数据判定
DEM_INVALID_THRESHOLD = 3.0e4


# ---------------------------------------------------------------- 栅格 IO

def _rasterio():
    try:
        import rasterio
    except ImportError:
        raise JobError(L("缺少 Python 依赖 rasterio。请执行：\n  pip install rasterio"))
    return rasterio


def _open(path):
    if not path or not os.path.exists(path):
        raise JobError(L("文件不存在：") + str(path))
    rio = _rasterio()
    return rio.open(path)


def read_meta(path):
    """读取栅格元数据（不载入像素）。"""
    with _open(path) as ds:
        tr = ds.transform
        crs = ds.crs
        return {
            "path": os.path.abspath(path),
            "width": int(ds.width),
            "height": int(ds.height),
            "count": int(ds.count),
            "dtype": ds.dtypes[0],
            "nodata": None if ds.nodata is None else float(ds.nodata),
            "transform": [float(tr.a), float(tr.b), float(tr.c),
                          float(tr.d), float(tr.e), float(tr.f)],
            "crs": "" if crs is None else crs.to_string(),
            "geographic": bool(crs.is_geographic) if crs is not None else False,
            "res": [float(abs(tr.a)), float(abs(tr.e))],
        }


def read_band(path, band=1):
    with _open(path) as ds:
        if band < 1 or band > ds.count:
            raise JobError(L("波段号 %d 越界：%s 只有 %d 个波段") % (band, path, ds.count))
        return ds.read(int(band))


def _same_grid(a, b):
    """网格一致性：宽高 + 6 个仿射系数（相对容差 1e-9，与 C# 侧 RasterGrid.Same 对齐）。"""
    if a["width"] != b["width"] or a["height"] != b["height"]:
        return False, L("尺寸不同（%d×%d ≠ %d×%d）") % (
            a["width"], a["height"], b["width"], b["height"])
    for i in range(6):
        x, y = a["transform"][i], b["transform"][i]
        if abs(x - y) > 1e-9 * max(1.0, abs(x), abs(y)):
            return False, L("仿射系数 %d 不一致（%.10g ≠ %.10g）") % (i, x, y)
    return True, ""


def load_lulc(path, band, nodata, n_classes, label):
    """载入一期 LULC，返回 (int32 数组, 有效掩膜)。非整数值直接报错。"""
    arr = read_band(path, band)
    if not np.issubdtype(arr.dtype, np.integer):
        f = arr.astype(np.float64)
        finite = np.isfinite(f)
        r = np.rint(np.where(finite, f, nodata))
        if finite.any() and np.any(np.abs(f[finite] - r[finite]) > 1e-6):
            raise JobError(L("%s 含有非整数值，不适合作为土地利用分类栅格：%s") % (label, path))
        arr = r
    a = arr.astype(np.int32)
    out_of_range = (a < 0) | (a >= n_classes)
    if out_of_range.any():
        bad = np.unique(a[out_of_range])
        warn(L("%s 有 %d 个像元取值超出类别范围 0..%d（例如 %s），已按无效值处理")
             % (label, int(out_of_range.sum()), n_classes - 1,
                ",".join(str(int(v)) for v in bad[:5])))
        a[out_of_range] = nodata
    valid = a != nodata
    return a, valid


# ---------------------------------------------------------------- 类别与面积

def class_counts(arr, valid, n_classes):
    if not valid.any():
        return np.zeros(n_classes, np.int64)
    return np.bincount(arr[valid].astype(np.int64), minlength=n_classes)[:n_classes].astype(np.int64)


def pixel_area_km2(meta):
    """像元面积（km²）；地理坐标系下无法直接换算，返回 None。

    transform 的 6 个系数是 (a, b, c, d, e, f)：x = a*col + b*row + c，y = d*col + e*row + f，
    像元面积取仿射矩阵行列式 |a*e - b*d|（平方米），再换算成平方千米。
    """
    if meta.get("geographic"):
        return None
    t = meta["transform"]
    a, b, d, e = t[0], t[1], t[3], t[4]
    det = abs(a * e - b * d)
    return det / 1.0e6


# ---------------------------------------------------------------- Markov

def transition_counts(a, va, b, vb, n_classes):
    """两期转移计数矩阵 C[i,j]（仅统计两期都有效的像元）。"""
    m = va & vb
    if not m.any():
        return np.zeros((n_classes, n_classes), np.int64)
    ai = a[m].astype(np.int64)
    bi = b[m].astype(np.int64)
    flat = np.bincount(ai * n_classes + bi, minlength=n_classes * n_classes)
    return flat.reshape(n_classes, n_classes).astype(np.int64)


def select_intervals(n_periods, source):
    """按来源选择参与统计的区间（相邻两期为一区间）。"""
    pairs = [(k, k + 1) for k in range(n_periods - 1)]
    if not pairs:
        raise JobError(L("至少需要两期数据才能统计转移矩阵"))
    if source == "last_interval":
        return pairs[-1:]
    if source == "all_periods":
        return pairs
    return pairs[-2:]   # last_two_average


def probability_matrix(counts):
    """按行归一化；空行保持全 0（不制造虚假概率）。"""
    p = counts.astype(np.float64)
    row = p.sum(axis=1, keepdims=True)
    row[row == 0] = 1.0
    return p / row


def build_budget(counts, P, n_classes, nodata):
    """转移预算 B[i,j] = floor(n_i · P(i→j))，逐行最大余数法补齐到 n_i。

    不变量：Σ_j B[i,j] == n_i（每行）；Σ_i B[i,j] ≈ Markov 预测目标面积（每列）。
    对角线 B[i,i] 表示"保持原类"的像元，不参与 CA 分配。
    绝不按列强制填充——否则会把超额面积一次性灌进某个转移对，造成空间分布失真。
    """
    B = np.zeros((n_classes, n_classes), np.int64)
    for i in range(n_classes):
        if i == nodata or counts[i] == 0:
            continue
        row = P[i] * counts[i]
        B[i] = np.floor(row).astype(np.int64)
        diff = int(counts[i]) - int(B[i].sum())        # 取整残差（0 ≤ diff < 类别数）
        if diff > 0:
            frac = row - np.floor(row)
            order = np.argsort(-frac, kind="stable")
            taken = 0
            for idx in order:
                if taken >= diff:
                    break
                if P[i, idx] <= 0.0:
                    continue
                B[i, idx] += 1
                taken += 1
            if taken < diff:                            # 极端情况（概率全为 0）：残差留作不变
                B[i, i] += diff - taken
        elif diff < 0:
            frac = np.where(row > 0, np.ceil(row) - row, 0.0)
            back = 0
            for idx in np.argsort(-frac, kind="stable"):
                if back >= -diff:
                    break
                if B[i, idx] > 0:
                    B[i, idx] -= 1
                    back += 1
    return B


def markov_target_counts(counts, P, n_classes, nodata):
    """Markov 预测的下期各类像元数（用于报告与校验，取整误差补给最大类）。"""
    dist = counts.astype(np.float64)
    total = dist.sum()
    if total <= 0:
        return counts.copy()
    future = (dist / total) @ P
    target = np.floor(future * total).astype(np.int64)
    gap = int(total) - int(target.sum())
    if gap != 0:
        target[int(np.argmax(target))] += gap
    return target


# ---------------------------------------------------------------- 邻域

def neighborhood_map(cur, cls, size):
    """目标类 cls 在 size×size 窗口内的占比（边界补 0），与 scipy convolve2d fill 等价。"""
    from scipy.ndimage import uniform_filter
    pad = size // 2
    binary = (cur == cls).astype(np.float32)
    padded = np.pad(binary, pad, mode="constant", constant_values=0.0)
    blurred = uniform_filter(padded, size=size, mode="constant", cval=0.0)
    return blurred[pad:pad + cur.shape[0], pad:pad + cur.shape[1]]


# ---------------------------------------------------------------- CA 分配

def allocate_step(cur, valid, B, suit, weights, phat, size, constraint,
                  n_classes, nodata, recompute_neighborhood=True):
    """单步 CA 分配。

    suit      : list[n] 或 None，每个目标类一张 0~1 适宜性图
    phat      : (n,n) 转移概率调制系数（共享单图模式下区分目标类）
    constraint: 可转变掩膜（False 处禁止转变），或 None
    返回 (新图, 预算缺额)
    """
    w_s, w_n = weights
    h, w = cur.shape
    result = cur.ravel().copy()
    assigned = np.zeros(result.size, dtype=bool)
    idx_by_class = [np.flatnonzero(cur.ravel() == c) for c in range(n_classes)]

    tasks = [(int(B[i, j]), i, j)
             for i in range(n_classes) for j in range(n_classes)
             if i != j and B[i, j] > 0]
    tasks.sort(key=lambda t: (-t[0], t[1], t[2]))

    neigh_cache = {}
    deficit = 0
    for budget, i, j in tasks:
        cand = idx_by_class[i]
        if cand.size == 0:
            continue
        cand = cand[~assigned[cand]]
        if constraint is not None:
            cand = cand[constraint.ravel()[cand]]
        if cand.size == 0:
            deficit += budget
            continue

        score = np.zeros(cand.size, dtype=np.float32)
        if w_n > 0:
            if recompute_neighborhood or j not in neigh_cache:
                neigh_cache[j] = neighborhood_map(cur, j, size)
            score += np.float32(w_n) * neigh_cache[j].ravel()[cand]
        if suit is not None and w_s > 0:
            score += np.float32(w_s * phat[i, j]) * suit[j].ravel()[cand]

        if cand.size <= budget:
            pick = cand
        else:
            keep = cand.size - budget
            sel = np.argpartition(score, keep)[keep:]
            pick = cand[sel]
        result[pick] = j
        assigned[pick] = True
        deficit += budget - int(pick.size)

    out = result.reshape(h, w).astype(np.int32)
    out[~valid] = nodata
    return out, deficit


# ---------------------------------------------------------------- 随机森林

def _balanced_indices(a, b, va, vb, imbalance, min_samples, seed):
    """平衡采样：保留全部变化像元 + 从不变像元里抽 imbalance 倍。

    参考实现用 np.random.choice 且未设种子 → 不可复现；这里固定种子保证可复现。
    """
    m = va & vb
    idx = np.flatnonzero(m.ravel())
    ai = a.ravel()[idx]
    bi = b.ravel()[idx]
    change = ai != bi
    ic = idx[change]
    isame = idx[~change]
    if imbalance is None or ic.size < min_samples or isame.size == 0:
        return idx
    rng = np.random.RandomState(seed)
    take = min(int(round(ic.size * float(imbalance))), isame.size)
    same = rng.choice(isame, size=take, replace=False)
    return np.concatenate([ic, same])


def _feature_matrix(drivers, idx):
    """按像元下标抽取特征矩阵（float32，列顺序即模型特征顺序）。"""
    return np.column_stack([d.ravel()[idx] for _, d in drivers]).astype(np.float32)


def train_rf(drivers, X, y, cfg):
    """训练 81 类转移潜力随机森林。drivers 为 [(名称, float32 二维数组)]。"""
    try:
        from sklearn.ensemble import RandomForestClassifier
        import sklearn
    except ImportError:
        raise JobError(L("缺少 Python 依赖 scikit-learn。请执行：\n  pip install scikit-learn"))

    if y.size < 50:
        raise JobError(L("训练样本不足（只有 %d 个），请检查两期数据的有效像元") % y.size)

    n_estimators = int(cfg.get("n_estimators", 200))
    max_depth = cfg.get("max_depth", 20)
    max_depth = None if max_depth in (None, 0) else int(max_depth)
    info(L("训练随机森林：%d 棵树 · 深度 %s · %d 个特征 · %d 个样本 · sklearn %s")
         % (n_estimators, L("无限制") if max_depth is None else max_depth,
            X.shape[1], y.size, sklearn.__version__))

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_split=8,
        random_state=int(cfg.get("seed", 42)),
        n_jobs=-1,
    )
    model.fit(X, y)
    return model


def export_trees(model, n_classes):
    """把 sklearn 森林导出为“全局模式”的紧凑树集合。

    每个节点只保留 9 维聚合概率：agg[leaf, j] = Σ_{i≠j} value[node, i*n+j] / total。
    这与参考实现 global 模式（跳过对角后按目标类求和）逐式等价，
    但推理时每个像元只需 9 维而不是 81 维。

    注意：sklearn 的 classes_ 只包含实际出现过的转移标签，必须映射回 n×n 全表，
    否则类别缺失时列会错位。
    """
    trees = []
    span = n_classes * n_classes
    for est in model.estimators_:
        t = est.tree_
        value = np.asarray(t.value, dtype=np.float64).reshape(t.node_count, -1)
        full = np.zeros((t.node_count, span), dtype=np.float64)
        classes = np.asarray(model.classes_).astype(np.int64)
        if classes.size != value.shape[1]:
            raise JobError(L("模型内部类别数与概率列数不一致（%d vs %d）")
                           % (classes.size, value.shape[1]))
        full[:, classes] = value
        v = full.reshape(t.node_count, n_classes, n_classes)
        agg = v.sum(axis=1)
        for j in range(n_classes):
            agg[:, j] -= v[:, j, j]      # 对角（保持不变）不计入适宜性
        # 注意：分母必须用“全部 81 类的计数和”，即 sklearn predict_proba 用的 node 总数。
        # 若改用变化部分的和归一化，会让“几乎不变的像元”的适宜性被放大到 1，
        # 从而在评分里与真正高变化的像元等价，直接拉低精度。
        total = full.sum(axis=1)
        total[total <= 0] = 1.0
        prob = (agg / total[:, None]).astype(np.float32)
        trees.append({
            "left": np.asarray(t.children_left, dtype=np.int32),
            "right": np.asarray(t.children_right, dtype=np.int32),
            "feature": np.asarray(t.feature, dtype=np.int32),
            "threshold": np.asarray(t.threshold, dtype=np.float64),
            "prob": prob,
        })
    return trees


def save_trees(path, trees, feature_names, n_classes, meta):
    """保存为 npz（逐树分键），便于增量加载与体积控制。"""
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    arrays = {
        "meta": np.array(json.dumps({
            "n_classes": n_classes,
            "feature_names": feature_names,
            "trees": len(trees),
        }, ensure_ascii=False)),
    }
    for k, t in enumerate(trees):
        arrays["t%d_left" % k] = t["left"]
        arrays["t%d_right" % k] = t["right"]
        arrays["t%d_feature" % k] = t["feature"]
        arrays["t%d_threshold" % k] = t["threshold"]
        arrays["t%d_prob" % k] = t["prob"]
    np.savez_compressed(path, **arrays)


def load_trees(path):
    if not os.path.exists(path):
        raise JobError(L("模型文件不存在：") + path)
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    trees = []
    for k in range(int(meta["trees"])):
        trees.append({
            "left": z["t%d_left" % k], "right": z["t%d_right" % k],
            "feature": z["t%d_feature" % k], "threshold": z["t%d_threshold" % k],
            "prob": z["t%d_prob" % k],
        })
    return trees, meta


def _leaves(x, tree):
    left, right = tree["left"], tree["right"]
    n = x.shape[0]
    node = np.zeros(n, dtype=np.int32)
    if left.size == 0 or left[0] < 0:
        return node
    active = np.ones(n, dtype=bool)
    feat, thr = tree["feature"], tree["threshold"]
    while True:
        idx = np.flatnonzero(active)
        if idx.size == 0:
            break
        nd = node[idx]
        go_left = x[idx, feat[nd]] <= thr[nd]
        node[idx] = np.where(go_left, left[nd], right[nd])
        active[idx] = left[node[idx]] >= 0
    return node


def suit_from_trees(trees, X, n_classes, chunk, progress_from, progress_to, label):
    """逐块推理，得到每个目标类的适宜性图（一维 float32）。"""
    n = X.shape[0]
    suit = [np.zeros(n, dtype=np.float32) for _ in range(n_classes)]
    if n == 0:
        return suit
    n_chunk = (n + chunk - 1) // chunk
    for c in range(n_chunk):
        s = c * chunk
        e = min(s + chunk, n)
        x = X[s:e]
        for t in trees:
            leaf = _leaves(x, t)
            # 一次取出该叶子的 9 维概率，再按列累加：比逐列花式索引少 8 次下标换算
            prob = t["prob"][leaf]
            for j in range(n_classes):
                suit[j][s:e] += prob[:, j]
        frac = progress_from + (progress_to - progress_from) * (c + 1) / n_chunk
        progress(frac, "%s %d/%d" % (label, c + 1, n_chunk))
    inv = np.float32(1.0 / max(1, len(trees)))
    for j in range(n_classes):
        suit[j] *= inv
    return suit


# ---------------------------------------------------------------- 适宜性

def normalize_factor(arr, method, low, high):
    """因子标准化到 0~1；非有限值用中位数填充。"""
    x = arr.astype(np.float32)
    finite = np.isfinite(x)
    if not finite.any():
        return np.full(x.shape, 0.5, dtype=np.float32)
    vals = x[finite]
    if method == "minmax":
        lo, hi = float(vals.min()), float(vals.max())
    else:
        lo, hi = [float(v) for v in np.percentile(vals, [low, high])]
    if hi - lo < 1e-12:
        y = np.full(x.shape, 0.5, dtype=np.float32)
    else:
        y = np.clip((x - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)
    if not finite.all():
        y[~finite] = float(np.median(y[finite]))
    return y


def load_driver(path, band, nodata_override=None):
    """载入驱动因子并做 NoData 修补。

    无效判定：非有限值、≥3e4 的“超级大值”、以及明显是哨兵的元数据 NoData。
    注意不能无条件相信元数据 NoData——距离类因子常把 0 写成 NoData，
    而 0 距离本身是有意义的，一旦被当成无效值就会把道路/水系上的像元抹掉。
    """
    meta = read_meta(path)
    arr = read_band(path, band).astype(np.float32)
    bad = ~np.isfinite(arr)
    nd = meta["nodata"] if nodata_override is None else nodata_override
    if nd is not None and (not np.isfinite(nd) or abs(float(nd)) >= 1.0e4):
        bad |= arr == np.float32(nd)
    bad |= arr >= np.float32(DEM_INVALID_THRESHOLD)
    if bad.any():
        good = arr[~bad]
        fill = float(np.median(good)) if good.size else 0.0
        arr = np.where(bad, np.float32(fill), arr)
    return arr, meta


def build_factor_suitability(factors, shape, normalize_cfg):
    acc = np.zeros(shape, dtype=np.float32)
    wsum = 0.0
    for f in factors:
        arr, _ = load_driver(f["path"], int(f.get("band", 1)))
        y = normalize_factor(arr, normalize_cfg.get("method", "quantile"),
                             float(normalize_cfg.get("low", 2)),
                             float(normalize_cfg.get("high", 98)))
        if str(f.get("direction", "+")).startswith("-"):
            y = 1.0 - y
        w = float(f.get("weight", 1.0))
        if w <= 0:
            continue
        acc += np.float32(w) * y
        wsum += w
    if wsum <= 0:
        raise JobError(L("因子权重之和为 0，请至少给一个正权重"))
    return acc / np.float32(wsum)


def build_external_suitability(path, band_mode, valid_classes, n_classes, shape):
    suit = [None] * n_classes
    with _open(path) as ds:
        count = ds.count
        order = list(valid_classes)
        if band_mode == "class_value":
            mapping = [(c, int(c)) for c in order if 1 <= int(c) <= count]
            missing = [c for c in order if not (1 <= int(c) <= count)]
            if missing:
                raise JobError(L("适宜性图集波段号需等于类别值，缺少类别 %s 对应波段")
                               % ",".join(str(m) for m in missing))
        else:
            mapping = [(c, k + 1) for k, c in enumerate(order) if k + 1 <= count]
            if len(mapping) < len(order):
                raise JobError(L("适宜性图集只有 %d 个波段，但有 %d 个有效类别")
                               % (count, len(order)))
        for cls, band in mapping:
            arr = ds.read(band).astype(np.float32)
            suit[cls] = normalize_factor(arr, "minmax", 2, 98)
    if any(s is None for s in suit[1:]):
        filled = [i for i in range(n_classes) if suit[i] is None]
        raise JobError(L("适宜性图集未覆盖类别：%s") % ",".join(map(str, filled)))
    for i in range(n_classes):
        if suit[i] is None:
            suit[i] = np.zeros(shape, dtype=np.float32)
    return suit


# ---------------------------------------------------------------- 精度

def confusion_metrics(obs, pred, valid, n_classes, nodata):
    m = valid & (obs != nodata) & (pred != nodata)
    total = int(m.sum())
    conf = np.zeros((n_classes, n_classes), np.int64)
    if total == 0:
        return {"oa": 0.0, "kappa": 0.0, "pa": [], "ua": [], "f1": [],
                "confusion": conf.tolist(), "total": 0}
    o = obs[m].astype(np.int64)
    p = pred[m].astype(np.int64)
    conf = np.bincount(o * n_classes + p, minlength=n_classes * n_classes) \
        .reshape(n_classes, n_classes).astype(np.int64)
    diag = np.diag(conf).astype(np.float64)
    oa = float(diag.sum() / total)
    row = conf.sum(axis=1).astype(np.float64)
    col = conf.sum(axis=0).astype(np.float64)
    pe = float((row * col).sum() / (float(total) * total))
    kappa = 0.0 if abs(1.0 - pe) < 1e-12 else (oa - pe) / (1.0 - pe)
    pa = np.where(row > 0, diag / np.maximum(row, 1), 0.0)
    ua = np.where(col > 0, diag / np.maximum(col, 1), 0.0)
    f1 = np.where(pa + ua > 0, 2 * pa * ua / np.maximum(pa + ua, 1e-10), 0.0)
    return {"oa": oa, "kappa": float(kappa), "pa": pa.tolist(), "ua": ua.tolist(),
            "f1": f1.tolist(), "confusion": conf.tolist(), "total": total}


# ---------------------------------------------------------------- 出图

def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _save(fig, path, plt):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    fig.savefig(path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_transition(path, P, names, counts, nodata):
    plt = _mpl()
    n = P.shape[0]
    fig, ax = plt.subplots(figsize=(max(5.2, n * 0.62), max(4.4, n * 0.56)))
    im = ax.imshow(P, cmap="YlOrRd", vmin=0, vmax=max(1e-6, float(P.max())))
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel(L("目标类别")); ax.set_ylabel(L("源类别"))
    ax.set_title(L("Markov 转移概率矩阵（行归一化）"), fontsize=10)
    if n <= 12:
        for i in range(n):
            for j in range(n):
                v = P[i, j]
                if v >= 0.005:
                    ax.text(j, i, "%.2f" % v, ha="center", va="center", fontsize=6.2,
                            color="black" if v < 0.55 * P.max() else "white")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    _save(fig, path, plt)


def draw_area_change(path, names, base, end, pred, area):
    plt = _mpl()
    n = len(names)
    idx = [i for i in range(n) if (base[i] + end[i] + pred[i]) > 0]
    x = np.arange(len(idx))
    w = 0.27
    fig, ax = plt.subplots(figsize=(max(6.4, len(idx) * 0.85), 3.9))
    ax.bar(x - w, [base[i] for i in idx], w, label=L("基期"), color="#7f8c9b")
    ax.bar(x, [end[i] for i in idx], w, label=L("末期实测"), color="#2c8bd6")
    ax.bar(x + w, [pred[i] for i in idx], w, label=L("预测"), color="#e2734e")
    ax.set_xticks(x)
    ax.set_xticklabels([names[i] for i in idx], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(L("面积（km²）") if area else L("像元数"))
    ax.set_title(L("各类面积变化"), fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    _save(fig, path, plt)


def draw_confusion(path, conf, names):
    plt = _mpl()
    n = len(names)
    c = np.asarray(conf, dtype=np.float64)
    fig, ax = plt.subplots(figsize=(max(5.2, n * 0.62), max(4.4, n * 0.56)))
    im = ax.imshow(c, cmap="Blues")
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel(L("预测类别")); ax.set_ylabel(L("实测类别"))
    ax.set_title(L("混淆矩阵（像元数）"), fontsize=10)
    if n <= 12:
        top = c.max() if c.size else 0
        for i in range(n):
            for j in range(n):
                v = int(c[i, j])
                if v > 0:
                    ax.text(j, i, "%.3g" % v if v >= 10000 else str(v),
                            ha="center", va="center", fontsize=5.6,
                            color="white" if v > 0.55 * top else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    _save(fig, path, plt)


def draw_importance(path, items):
    plt = _mpl()
    names = [it["name"] for it in items][::-1]
    vals = [it["importance"] for it in items][::-1]
    fig, ax = plt.subplots(figsize=(5.6, max(2.4, 0.42 * len(items) + 1.2)))
    ax.barh(names, vals, color="#2c8bd6")
    for k, v in enumerate(vals):
        ax.text(v, k, " %.3f" % v, va="center", fontsize=7.5)
    ax.set_xlabel(L("重要性")); ax.set_title(L("随机森林特征重要性"), fontsize=10)
    ax.grid(axis="x", alpha=0.25)
    _save(fig, path, plt)


def _color_map(names):
    from matplotlib.colors import ListedColormap
    cols = []
    for i in range(len(names)):
        r, g, b = CLCD_COLORS[i % len(CLCD_COLORS)]
        cols.append((r / 255.0, g / 255.0, b / 255.0, 1.0))
    return ListedColormap(cols)


def _downsample(arr, max_side=900):
    step = max(1, int(np.ceil(max(arr.shape) / float(max_side))))
    return arr[::step, ::step], step


def draw_compare(path, obs, pred, valid, nodata, names):
    from matplotlib.colors import ListedColormap
    plt = _mpl()
    cmap = _color_map(names)
    vmax = len(names) - 1
    a, step = _downsample(obs)
    b, _ = _downsample(pred)
    diff = np.where(a == b, 0, 1)
    mask = _downsample(valid.astype(np.uint8))[0]
    diff = np.where(mask > 0, diff, 0)

    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.6))
    for ax, data, title in ((axes[0], a, L("末期实测")),
                            (axes[1], b, L("预测"))):
        im = ax.imshow(data, cmap=cmap, vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_title(L("%s（1/%d 抽样）") % (title, step), fontsize=10)
        ax.axis("off")
    axes[2].imshow(diff, cmap=ListedColormap([(0.92, 0.92, 0.92), (0.85, 0.16, 0.15)]),
                   vmin=0, vmax=1, interpolation="nearest")
    axes[2].set_title(L("差异（红色=分类不一致）"), fontsize=10)
    axes[2].axis("off")
    cb = fig.colorbar(im, ax=list(axes), orientation="horizontal",
                      fraction=0.035, pad=0.03, ticks=range(len(names)))
    # 英文类名较长，色标标签容易挤在一起：超长时换成两行显示
    cb.ax.set_xticklabels([n.replace(" ", "\n") if len(n) > 10 else n for n in names],
                          fontsize=7)
    cb.set_label(L("土地利用类别"), fontsize=8)
    _save(fig, path, plt)


def draw_hotspot(path, base, pred, valid, names):
    """变化热点：按最主要的若干“转移类型”（源类→目标类）着色，其余变化置灰。"""
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    plt = _mpl()
    a, step = _downsample(base)
    b, _ = _downsample(pred)
    v = _downsample(valid.astype(np.uint8))[0]
    n = len(names)
    changed = (a != b) & (v > 0)

    pair = a.astype(np.int64) * n + b.astype(np.int64)
    kinds = np.zeros(a.shape, dtype=np.int16)
    kinds[changed] = 5                                   # 5 = 其他变化
    top = []
    if changed.any():
        uniq, cnt = np.unique(pair[changed], return_counts=True)
        order = np.argsort(-cnt)[:4]
        for rank, k in enumerate(order):
            code = int(uniq[k])
            top.append((code // n, code % n, int(cnt[k])))
            kinds[changed & (pair == code)] = rank + 1

    palette = [(0.93, 0.93, 0.93), (0.84, 0.15, 0.13), (0.13, 0.44, 0.80),
               (0.95, 0.58, 0.10), (0.48, 0.25, 0.65), (0.60, 0.60, 0.60)]
    fig, ax = plt.subplots(figsize=(6.8, 5.2))
    ax.imshow(kinds, cmap=ListedColormap(palette), vmin=0, vmax=5, interpolation="nearest")
    ax.set_title(L("变化热点（1/%d 抽样，按转移类型着色）") % step, fontsize=10)
    ax.axis("off")
    handles = [Patch(color=palette[0], label=L("未变化"))]
    for rank, (i, j, c) in enumerate(top):
        handles.append(Patch(color=palette[rank + 1],
                             label="%s→%s（%s）" % (names[i], names[j], format(c, ","))))
    if not top:
        handles.append(Patch(color=palette[5], label=L("无变化")))
    elif int((kinds == 5).sum()) > 0:
        handles.append(Patch(color=palette[5], label=L("其他变化")))
    ax.legend(handles=handles, loc="lower right", fontsize=7.2, framealpha=0.92)
    _save(fig, path, plt)


# ---------------------------------------------------------------- 写出

def write_raster(path, arr, meta, nodata, names):
    rio = _rasterio()
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    maxv = int(arr.max()) if arr.size else 0
    dtype = "uint8" if maxv <= 255 else "uint16"
    profile = {
        "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1],
        "count": 1, "dtype": dtype, "nodata": nodata,
        "compress": "lzw",
    }
    if meta["transform"]:
        from rasterio.transform import Affine
        t = meta["transform"]
        profile["transform"] = Affine(t[0], t[1], t[2], t[3], t[4], t[5])
    if meta["crs"]:
        profile["crs"] = meta["crs"]
    if arr.shape[0] > 256 and arr.shape[1] > 256:
        profile.update({"tiled": True, "blockxsize": 256, "blockysize": 256})
    with rio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)
        if dtype == "uint8":
            cmap = {}
            for i in range(256):
                if i < len(names):
                    r, g, b = CLCD_COLORS[i % len(CLCD_COLORS)]
                else:
                    r = g = b = 0
                cmap[i] = (r, g, b, 0 if i == int(nodata) else 255)
            dst.write_colormap(1, cmap)


def fmt_matrix(m, names, title, lines, as_int=False):
    if title:
        lines.append(title)
    head = "        " + "".join("%10s" % n[:8] for n in names)
    lines.append(head)
    for i, row in enumerate(m):
        cells = "".join(("%10d" % int(v)) if as_int else ("%10.4f" % float(v)) for v in row)
        lines.append("%8s%s" % (names[i][:8], cells))
    lines.append("")


def write_report(path, cfg, ctx):
    """生成纯文本报告。ctx 汇总所有中间结果。"""
    names = ctx["names"]
    lines = []
    lines.append(L("SharpGIS · 土地利用变化预测报告"))
    lines.append("=" * 78)
    lines.append(L("生成时间：") + time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")

    lines.append(L("一、输入数据"))
    for k, p in enumerate(cfg["periods"]):
        lines.append(L("  第 %d 期：%s（波段 %d）") % (k + 1, p["path"], int(p.get("band", 1))))
    lines.append(L("  无效值：%s") % cfg.get("nodata", 0))
    lines.append(L("  类别数：%d") % ctx["n_classes"])
    area = ctx["pixel_area_km2"]
    lines.append(L("  像元尺寸：%s（每像元 %s）") % (
        "×".join("%.4f" % v for v in ctx["meta"]["res"]),
        ("%.8f km²" % area) if area else L("未知（地理坐标系）")))
    lines.append(L("  坐标系：%s") % (ctx["meta"]["crs"] or L("无")))
    lines.append(L("  网格：%d × %d") % (ctx["meta"]["width"], ctx["meta"]["height"]))
    lines.append("")

    lines.append(L("二、建模参数"))
    lines.append(L("  转移矩阵来源：%s（区间 %s）") % (
        source_name(cfg.get("transition_source", "last_two_average")), ctx["interval_text"]))
    lines.append(L("  预测步数：%d") % ctx["steps"])
    lines.append(L("  适宜性模式：%s") % suit_name(cfg.get("suitability_mode", "rf")))
    if ctx.get("rf_summary"):
        lines.append(L("  随机森林：%s") % ctx["rf_summary"])
    w = ctx["weights"]
    lines.append(L("  评分权重：适宜性 %.3f / 邻域 %.3f（归一化后 %.3f / %.3f）")
                 % (w[0], w[1], ctx["weights_norm"][0], ctx["weights_norm"][1]))
    lines.append(L("  邻域窗口：%d × %d") % (ctx["neighborhood_size"], ctx["neighborhood_size"]))
    lines.append(L("  转移概率调制：%s") % (L("开") if ctx["modulate"] else L("关")))
    lines.append("")

    lines.append(L("三、转移矩阵（像元计数）"))
    fmt_matrix(ctx["counts"], names, None, lines, as_int=True)
    lines.append(L("四、转移概率矩阵（行归一化）"))
    fmt_matrix(ctx["P"], names, None, lines)
    lines.append(L("五、转移预算矩阵（行和 = 当期像元数）"))
    fmt_matrix(ctx["budget"], names, None, lines, as_int=True)

    lines.append(L("六、面积统计"))
    header = "  %-10s %14s %14s %14s %10s" % (L("类别"), L("基期"), L("末期"), L("预测"), L("变化率"))
    lines.append(header)
    unit = "km²" if area else L("像元")
    for row in ctx["areas"]:
        lines.append("  %-10s %14.4f %14.4f %14.4f %9.2f%%" % (
            row["name"][:10], row["base"], row["end"], row["pred"], row["change_pct"]))
    lines.append(L("  （单位：%s）") % unit)
    lines.append("")

    acc = ctx.get("accuracy")
    if acc:
        lines.append(L("七、精度评价"))
        lines.append(L("  方案：%s") % ctx["validation_note"])
        lines.append(L("  总体精度 OA：%.4f") % acc["oa"])
        lines.append(L("  Kappa 系数：%.4f") % acc["kappa"])
        if ctx.get("baseline_oa") is not None:
            lines.append(L("  未变化基线 OA：%.4f") % ctx["baseline_oa"])
        lines.append(L("  有效验证像元：%d") % acc["total"])
        lines.append("  %-10s %10s %10s %10s" % (L("类别"), "PA", "UA", "F1"))
        for i, row in enumerate(ctx["areas"]):
            if row["pred"] <= 0 and row["end"] <= 0:
                continue
            lines.append("  %-10s %10.4f %10.4f %10.4f"
                         % (names[i][:10], acc["pa"][i], acc["ua"][i], acc["f1"][i]))
        lines.append("")

    if ctx["warnings"]:
        lines.append(L("八、警告"))
        for wmsg in ctx["warnings"]:
            lines.append("  ! " + wmsg)
        lines.append("")

    lines.append(L("九、输出"))
    for label, p in ctx["outputs"].items():
        if p:
            lines.append(("  %s：%s" if _LANG == "zh" else "  %s: %s") % (label, p))
    lines.append(L("  耗时：%.1f 秒") % ctx["elapsed"])
    lines.append("")

    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ---------------------------------------------------------------- 主流程

def build_metrics(cfg, ctx):
    return {
        "mode": cfg.get("mode", "predict"),
        "classes": ctx["areas"],
        "matrix_counts": ctx["counts"].tolist(),
        "matrix_probability": ctx["P"].tolist(),
        "matrix_budget": ctx["budget"].tolist(),
        "accuracy": ctx.get("accuracy"),
        "baseline_oa": ctx.get("baseline_oa"),
        "validation_note": ctx.get("validation_note"),
        "feature_importance": ctx.get("importance", []),
        "rf_summary": ctx.get("rf_summary"),
        "warnings": ctx["warnings"],
        "weights": {"raw": ctx["weights"], "normalized": ctx["weights_norm"]},
        "neighborhood_size": ctx["neighborhood_size"],
        "steps": ctx["steps"],
        "pixel_area_km2": ctx["pixel_area_km2"],
        "timing": {"total_s": ctx["elapsed"]},
        "outputs": ctx["outputs"],
        "figures": ctx["figures"],
        "skipped_steps": ctx.get("skipped", []),
    }


def _driver_cached(ctx, spec):
    """按路径缓存驱动因子，避免验证与预测阶段重复读盘。"""
    cache = ctx.setdefault("driver_cache", {})
    key = (os.path.abspath(spec["path"]), int(spec.get("band", 1)))
    if key not in cache:
        cache[key] = load_driver(spec["path"], int(spec.get("band", 1)))
    return cache[key]


def resolve_suitability(cfg, ctx, periods, drivers, valid, n_classes, shape):
    """按模式构建适宜性图集；返回 (suit list 或 None, 是否为共享单图)。"""
    mode = cfg.get("suitability_mode", "rf")
    if mode == "none":
        return None, False

    if mode == "rf":
        rf_cfg = cfg.get("rf") or {}
        model_path = rf_cfg.get("model")
        use_saved = bool(model_path) and os.path.exists(model_path) and not rf_cfg.get("force_train")
        if use_saved:
            info(L("载入随机森林模型：") + model_path)
            trees, meta = load_trees(model_path)
            if int(meta["n_classes"]) != n_classes:
                raise JobError(L("模型类别数 %d 与当前 %d 不一致") % (int(meta["n_classes"]), n_classes))
            ctx["rf_summary"] = L("载入模型（%d 棵树）") % len(trees)
        else:
            trees, meta = ctx["train_inline"]()

        driver_specs = (rf_cfg.get("predict_drivers")
                        or (rf_cfg.get("train") or {}).get("drivers") or [])
        names = list(meta["feature_names"])
        if len(driver_specs) != len(names):
            raise JobError(L("预测用驱动因子有 %d 个，但模型需要 %d 个（%s）")
                           % (len(driver_specs), len(names), "、".join(names)))
        drivers_pred = []
        for k, spec in enumerate(driver_specs):
            arr, dmeta = _driver_cached(ctx, spec)
            ok, reason = _same_grid(ctx["meta"], dmeta)
            if not ok:
                raise JobError(L("驱动因子 %s 与基期网格不一致：%s") % (names[k], reason))
            drivers_pred.append((names[k], arr))

        idx = np.flatnonzero(valid.ravel())
        X = _feature_matrix(drivers_pred, idx)
        flat_suit = suit_from_trees(trees, X, n_classes, int(cfg.get("chunk", 200000)),
                                    0.20, 0.58, L("随机森林适宜性"))
        suit = []
        for j in range(n_classes):
            m = np.zeros(valid.size, dtype=np.float32)
            m[idx] = flat_suit[j]
            suit.append(m.reshape(shape))
        return suit, False

    if mode == "factor":
        factors = cfg.get("factors") or []
        if not factors:
            raise JobError(L("因子加权模式至少需要一个驱动因子"))
        for f in factors:
            dmeta = read_meta(f["path"])
            ok, reason = _same_grid(ctx["meta"], dmeta)
            if not ok:
                raise JobError(L("驱动因子 %s 与基期网格不一致：%s") % (
                    os.path.basename(f["path"]), reason))
        info(L("合成 %d 个因子的加权适宜性图") % len(factors))
        single = build_factor_suitability(factors, shape, cfg.get("normalize") or {})
        # 所有目标类共用同一张图：直接复用同一个对象，避免 9 份拷贝
        return [single] * n_classes, True

    if mode == "external":
        ext = cfg.get("external") or {}
        if not ext.get("path"):
            raise JobError(L("外部适宜性图集模式需要指定图集文件"))
        dmeta = read_meta(ext["path"])
        ok, reason = _same_grid(ctx["meta"], dmeta)
        if not ok:
            raise JobError(L("适宜性图集与基期网格不一致：%s") % reason)
        valid_classes = [int(c) for c in ctx["valid_classes"]]
        info(L("载入外部适宜性图集：") + ext["path"])
        return build_external_suitability(ext["path"], ext.get("band_mode", "order"),
                                          valid_classes, n_classes, shape), False

    raise JobError(L("未知的适宜性模式：") + str(mode))


def run_pipeline(cfg, ctx, base_index, intervals, steps, progress_from, progress_to):
    """从 periods[base_index] 出发做 steps 步预测，返回 (预测图, 预算, 缺额, P)。"""
    periods = ctx["periods"]
    n_classes = ctx["n_classes"]
    nodata = cfg.get("nodata", 0)

    P = ctx["build_P"](intervals)
    base = periods[base_index]["arr"]
    valid = periods[base_index]["valid"]

    # ---- 适宜性
    suit, shared = resolve_suitability(cfg, ctx, periods, ctx["drivers"],
                                       valid, n_classes, base.shape)
    w_norm = ctx["weights_norm"]
    phat = np.ones((n_classes, n_classes), dtype=np.float32)
    if ctx["modulate"] and suit is not None:
        for i in range(n_classes):
            off = P[i].copy()
            off[i] = 0.0
            mx = float(off.max()) if off.size else 0.0
            if mx > 0:
                phat[i] = (off / mx).astype(np.float32)

    constraint = ctx["constraint"]
    if constraint is not None and suit is not None:
        # 硬掩膜 + 适宜性置 0：只乘 0 不够，邻域项仍会把候选顶上来
        if shared:
            suit = [np.where(constraint, suit[0], np.float32(0.0))] * n_classes
        else:
            suit = [np.where(constraint, s, np.float32(0.0)) for s in suit]

    size = ctx["neighborhood_size"]
    cur = base
    budget = None
    total_deficit = 0
    for s in range(steps):
        counts = class_counts(cur, valid, n_classes)
        budget = build_budget(counts, P, n_classes, nodata)
        recompute = bool(cfg.get("recompute_neighborhood", True)) or s == 0
        cur, deficit = allocate_step(cur, valid, budget, suit, w_norm, phat, size,
                                     constraint, n_classes, nodata, recompute)
        total_deficit += deficit
        progress(progress_from + (progress_to - progress_from) * (s + 1) / steps,
                 L("CA 分配 第 %d/%d 步") % (s + 1, steps))
        if deficit:
            ctx["warnings"].append(L("第 %d 步有 %d 个转移预算无法落实（受限或候选不足）")
                                   % (s + 1, deficit))
    return cur, budget, total_deficit, P


def run_analyze(cfg):
    """只做转移矩阵与面积统计。"""
    ctx = prepare_common(cfg)
    progress(0.15, L("统计转移矩阵"))
    counts = np.zeros((ctx["n_classes"], ctx["n_classes"]), np.int64)
    for k1, k2 in ctx["intervals"]:
        counts += transition_counts(ctx["periods"][k1]["arr"], ctx["periods"][k1]["valid"],
                                    ctx["periods"][k2]["arr"], ctx["periods"][k2]["valid"],
                                    ctx["n_classes"])
    P = probability_matrix(counts)
    last = len(ctx["periods"]) - 1
    last_counts = class_counts(ctx["periods"][last]["arr"], ctx["periods"][last]["valid"],
                               ctx["n_classes"])
    budget = build_budget(last_counts, P, ctx["n_classes"], cfg.get("nodata", 0))
    ctx["counts"], ctx["P"], ctx["budget"] = counts, P, budget
    ctx["areas"] = build_area_rows(ctx, None)
    ctx["steps"] = 1
    ctx["weights"] = (0.6, 0.4)
    ctx["weights_norm"] = normalize_weights(0.6, 0.4)
    ctx["neighborhood_size"] = int(cfg.get("neighborhood_size", 5))
    ctx["modulate"] = bool(cfg.get("modulate_by_probability", True))
    ctx["figures"] = {}
    ctx["outputs"] = {}

    figures = ctx["figures"]
    fig_dir = (cfg.get("outputs") or {}).get("fig_dir")
    if fig_dir:
        try:
            figures["transition"] = os.path.join(fig_dir, "transition_matrix.png")
            draw_transition(figures["transition"], P, ctx["names"], counts, cfg.get("nodata", 0))
        except Exception as ex:            # 出图失败不影响主结果
            ctx["warnings"].append(L("转移矩阵图生成失败：%s") % ex)
            figures.pop("transition", None)

    progress(0.9, L("统计完成"))
    ctx["elapsed"] = time.time() - ctx["start"]
    return build_metrics(cfg, ctx)


def normalize_weights(w_s, w_n):
    total = float(w_s) + float(w_n)
    if total <= 0:
        return (0.5, 0.5)
    return (float(w_s) / total, float(w_n) / total)


def build_area_rows(ctx, pred):
    area = ctx["pixel_area_km2"]
    base = ctx["base_counts"]
    end = ctx["end_counts"]
    rows = []
    for i in range(ctx["n_classes"]):
        b = float(base[i]) * area if area else float(base[i])
        e = float(end[i]) * area if area else float(end[i])
        p = (float(pred[i]) * area if area else float(pred[i])) if pred is not None else 0.0
        pct = ((p - b) / b * 100.0) if (pred is not None and b > 0) else 0.0
        rows.append({"value": i, "name": ctx["names"][i], "base": b, "end": e,
                     "pred": p, "change_pct": pct,
                     "base_px": int(base[i]), "end_px": int(end[i]),
                     "pred_px": int(pred[i]) if pred is not None else 0})
    return rows


def prepare_common(cfg):
    """载入各期数据、校验网格、准备上下文。"""
    rio = _rasterio()
    periods_cfg = cfg.get("periods") or []
    if len(periods_cfg) < 2:
        raise JobError(L("至少需要两期土地利用数据（当前 %d 期）") % len(periods_cfg))

    nodata = cfg.get("nodata", 0)
    metas = [read_meta(p["path"]) for p in periods_cfg]
    base_meta = metas[0]
    for k, m in enumerate(metas[1:], start=1):
        ok, reason = _same_grid(base_meta, m)
        if not ok:
            raise JobError(L("第 %d 期 %s 与第 1 期网格不一致：%s")
                           % (k + 1, os.path.basename(m["path"]), reason))

    n_classes = int(cfg.get("class_count") or 0)
    periods = []
    valid_classes = set()
    for k, (spec, meta) in enumerate(zip(periods_cfg, metas)):
        band = int(spec.get("band", 1))
        arr, valid = load_lulc(spec["path"], band, int(nodata), 256 if not n_classes else n_classes,
                               L("第 %d 期") % (k + 1))
        periods.append({"arr": arr, "valid": valid, "meta": meta, "spec": spec})
        valid_classes.update(np.unique(arr[valid]).tolist())
        progress(0.05 + 0.06 * (k + 1), L("读取第 %d 期") % (k + 1))

    if not n_classes:
        n_classes = max(valid_classes) + 1 if valid_classes else 2
    if n_classes < 2:
        raise JobError(L("类别数必须 ≥ 2"))
    for p in periods:
        p["arr"][(p["arr"] < 0) | (p["arr"] >= n_classes)] = int(nodata)
        p["valid"] = p["arr"] != int(nodata)

    names = list(cfg.get("class_names") or [])
    while len(names) < n_classes:
        cn = clcd_names()
        names.append(cn[len(names)] if len(names) < len(cn) else L("类别 %d") % len(names))
    names = names[:n_classes]

    intervals = select_intervals(len(periods), cfg.get("transition_source", "last_two_average"))
    if cfg.get("transition_source") == "last_two_average" and len(periods) - 1 < 2:
        warn(L("只有 %d 个区间，'最近两期平均'退化为最近一个区间") % (len(periods) - 1))

    interval_text = (L("；") if _LANG == "zh" else "; ").join(
        "%d→%d" % (k1 + 1, k2 + 1) for k1, k2 in intervals)
    start = time.time()
    ctx = {
        "periods": periods, "metas": metas, "meta": base_meta,
        "n_classes": n_classes, "names": names,
        "nodata": int(nodata),
        "valid_classes": sorted(valid_classes),
        "intervals": intervals, "interval_text": interval_text,
        "warnings": [], "start": start,
        "pixel_area_km2": pixel_area_km2(base_meta),
        "base_counts": class_counts(periods[0]["arr"], periods[0]["valid"], n_classes),
        "end_counts": class_counts(periods[-1]["arr"], periods[-1]["valid"], n_classes),
        "drivers": [],
        "constraint": load_constraint(cfg, base_meta),
        "figures": {}, "outputs": {},
        "weights": (float(cfg.get("weights", {}).get("suitability", 0.6)),
                    float(cfg.get("weights", {}).get("neighborhood", 0.4))),
        "neighborhood_size": int(cfg.get("neighborhood_size", 5)),
        "modulate": bool(cfg.get("modulate_by_probability", True)),
        "steps": int(cfg.get("steps", 1)),
    }
    ctx["weights_norm"] = normalize_weights(*ctx["weights"])
    if any(not p["valid"].any() for p in periods):
        raise JobError(L("存在没有任何有效像元的一期，请检查无效值设置"))
    return ctx


def load_constraint(cfg, base_meta):
    spec = cfg.get("constraint") or {}
    path = spec.get("path")
    if not path:
        return None
    meta = read_meta(path)
    ok, reason = _same_grid(base_meta, meta)
    if not ok:
        raise JobError(L("限制性条件图与基期网格不一致：%s") % reason)
    arr = read_band(path, int(spec.get("band", 1))).astype(np.float32)
    nd = spec.get("nodata", meta["nodata"])
    mask = arr > 0.5
    if nd is not None and np.isfinite(nd):
        mask &= arr != np.float32(nd)
    info(L("限制性条件图：%d 个像元禁止转变") % int((~mask).sum()))
    return mask


def run_predict(cfg):
    ctx = prepare_common(cfg)
    n_classes = ctx["n_classes"]
    nodata = ctx["nodata"]
    steps = max(1, int(cfg.get("steps", 1)))
    ctx["steps"] = steps

    # ---------- 随机森林训练（延迟到需要时，结果缓存一份供精度评价复用）
    train_cache = {}

    def train_inline():
        if "trees" in train_cache:
            # 命中缓存时也要恢复摘要，否则报告与「特征重要性」页会缺这一行
            if train_cache.get("summary"):
                ctx["rf_summary"] = train_cache["summary"]
            return train_cache["trees"], train_cache["meta"]
        rf_cfg = cfg.get("rf") or {}
        tcfg = rf_cfg.get("train") or {}
        driver_specs = tcfg.get("drivers") or []
        if not driver_specs:
            raise JobError(L("随机森林模式需要提供训练用驱动因子"))
        progress(0.18, L("载入驱动因子"))
        drivers = []
        for spec in driver_specs:
            arr, dmeta = load_driver(spec["path"], int(spec.get("band", 1)))
            ok, reason = _same_grid(ctx["meta"], dmeta)
            if not ok:
                raise JobError(L("驱动因子 %s 与基期网格不一致：%s") % (
                    spec.get("name") or os.path.basename(spec["path"]), reason))
            drivers.append((spec.get("name") or os.path.basename(spec["path"]), arr))
        ctx["drivers"] = drivers

        train_pairs = tcfg.get("intervals") or ctx["intervals"]
        idx_parts = []
        label_parts = []
        for k1, k2 in train_pairs:
            a, va = ctx["periods"][k1]["arr"], ctx["periods"][k1]["valid"]
            b, vb = ctx["periods"][k2]["arr"], ctx["periods"][k2]["valid"]
            idx = _balanced_indices(a, b, va, vb,
                                    tcfg.get("imbalance", 2.0),
                                    int(tcfg.get("min_samples", 200)),
                                    int(tcfg.get("seed", 42)))
            idx_parts.append(idx)
            label_parts.append(a.ravel()[idx].astype(np.int64) * n_classes
                               + b.ravel()[idx].astype(np.int64))
        idx = np.concatenate(idx_parts)
        y = np.concatenate(label_parts)
        progress(0.20, L("抽取训练样本 %d 个") % idx.size)
        X = _feature_matrix(drivers, idx)
        model = train_rf(drivers, X, y, tcfg)
        importance = list(model.feature_importances_)
        ctx["importance"] = [
            {"name": drivers[k][0], "importance": float(importance[k])}
            for k in np.argsort(-np.asarray(importance))
        ]
        ctx["rf_summary"] = L("%d 棵树 · 深度 %s · 样本 %d") % (
            int(tcfg.get("n_estimators", 200)), tcfg.get("max_depth", 20), idx.size)
        summary = ctx["rf_summary"]
        if tcfg.get("save_model"):
            info(L("保存模型：") + tcfg["save_model"])
            try:
                trees = export_trees(model, n_classes)
                save_trees(tcfg["save_model"], trees, [d[0] for d in drivers],
                           n_classes, {})
                ctx["outputs"]["model"] = tcfg["save_model"]
                info(L("模型已保存（%d 棵树）") % len(trees))
            except Exception as ex:
                ctx["warnings"].append(L("模型保存失败：%s") % ex)
        progress(0.24, L("训练完成：") + summary)
        trees = export_trees(model, n_classes)
        meta = {"feature_names": [d[0] for d in drivers], "n_classes": n_classes,
                "trees": len(trees)}
        if not rf_cfg.get("force_train"):
            train_cache["trees"] = trees
            train_cache["meta"] = meta
            train_cache["summary"] = summary
        ctx["rf_summary"] = summary
        return trees, meta

    ctx["train_inline"] = train_inline

    progress(0.10, L("统计转移矩阵"))
    counts = np.zeros((n_classes, n_classes), np.int64)
    for k1, k2 in ctx["intervals"]:
        counts += transition_counts(ctx["periods"][k1]["arr"], ctx["periods"][k1]["valid"],
                                    ctx["periods"][k2]["arr"], ctx["periods"][k2]["valid"],
                                    n_classes)
    P = probability_matrix(counts)
    ctx["build_P"] = lambda intervals: probability_matrix(accumulate_counts(ctx, intervals))
    ctx["counts"], ctx["P"] = counts, P

    # ---------- 精度评价（默认拿最后一期当未知）
    vcfg = cfg.get("validation") or {}
    if vcfg.get("enabled", True):
        run_validation(cfg, ctx)
    else:
        ctx["validation_note"] = L("未做精度评价")

    # ---------- 正式预测
    base_index = len(ctx["periods"]) - 1
    pred, budget, deficit, P_used = run_pipeline(
        cfg, ctx, base_index, ctx["intervals"], steps, 0.62, 0.86)
    ctx["budget"] = budget
    ctx["P"] = P_used
    pred_counts = class_counts(pred, ctx["periods"][-1]["valid"], n_classes)
    ctx["areas"] = build_area_rows(ctx, pred_counts)

    # ---------- 写出
    outputs = cfg.get("outputs") or {}
    raster = outputs.get("raster") or "prediction.tif"
    progress(0.88, L("写出预测栅格"))
    write_raster(raster, np.where(ctx["periods"][-1]["valid"], pred, nodata),
                 ctx["meta"], nodata, ctx["names"])
    ctx["outputs"]["raster"] = raster

    progress(0.94, L("生成图表"))
    fig_dir = outputs.get("fig_dir")
    if fig_dir:
        figs = ctx["figures"]
        try:
            figs["transition"] = os.path.join(fig_dir, "transition_matrix.png")
            draw_transition(figs["transition"], ctx["P"], ctx["names"], counts, nodata)
        except Exception as ex:
            ctx["warnings"].append(L("转移矩阵图生成失败：%s") % ex)
        try:
            pth = os.path.join(fig_dir, "area_change.png")
            draw_area_change(pth, ctx["names"],
                             [r["base"] for r in ctx["areas"]],
                             [r["end"] for r in ctx["areas"]],
                             [r["pred"] for r in ctx["areas"]],
                             ctx["pixel_area_km2"] is not None)
            figs["area"] = pth
        except Exception as ex:
            ctx["warnings"].append(L("面积变化图生成失败：%s") % ex)
        try:
            if ctx.get("accuracy"):
                pth = os.path.join(fig_dir, "confusion.png")
                draw_confusion(pth, ctx["accuracy"]["confusion"], ctx["names"])
                figs["confusion"] = pth
        except Exception as ex:
            ctx["warnings"].append(L("混淆矩阵图生成失败：%s") % ex)
        try:
            if ctx.get("importance"):
                pth = os.path.join(fig_dir, "feature_importance.png")
                draw_importance(pth, ctx["importance"])
                figs["importance"] = pth
        except Exception as ex:
            ctx["warnings"].append(L("特征重要性图生成失败：%s") % ex)
        if cfg.get("write_compare_image", True):
            try:
                pth = outputs.get("compare_png") or os.path.join(fig_dir, "compare.png")
                obs = ctx["periods"][-1]["arr"]
                draw_compare(pth, obs, pred, ctx["periods"][-1]["valid"], nodata, ctx["names"])
                figs["compare"] = pth
            except Exception as ex:
                ctx["warnings"].append(L("对比图生成失败：%s") % ex)
        if cfg.get("write_hotspot_image", True):
            try:
                pth = os.path.join(fig_dir, "hotspot.png")
                draw_hotspot(pth, ctx["periods"][-1]["arr"], pred,
                             ctx["periods"][-1]["valid"], ctx["names"])
                figs["hotspot"] = pth
            except Exception as ex:
                ctx["warnings"].append(L("变化热点图生成失败：%s") % ex)

    if outputs.get("report"):
        progress(0.97, L("生成报告"))
        ctx["outputs"]["report"] = outputs["report"]

    ctx["elapsed"] = time.time() - ctx["start"]
    if outputs.get("report"):
        write_report(outputs["report"], cfg, ctx)
    return build_metrics(cfg, ctx)


def accumulate_counts(ctx, intervals):
    n = ctx["n_classes"]
    total = np.zeros((n, n), np.int64)
    for k1, k2 in intervals:
        total += transition_counts(ctx["periods"][k1]["arr"], ctx["periods"][k1]["valid"],
                                   ctx["periods"][k2]["arr"], ctx["periods"][k2]["valid"], n)
    return total


def run_validation(cfg, ctx):
    """时间外推检验：用倒数第二期预测最后一期，与实测比较。"""
    periods = ctx["periods"]
    if len(periods) < 2:
        return
    vcfg = cfg.get("validation") or {}
    same_period = bool(vcfg.get("same_period", False))
    pairs = [(k, k + 1) for k in range(len(periods) - 1)]
    hist = pairs[:-1] if (len(pairs) >= 2 and not same_period) else [pairs[-1]]
    if len(pairs) < 2 and not same_period:
        ctx["validation_note"] = (L("同期 in-sample 检验（只有两期数据，无法做时间外推；"
                                  "指标会偏乐观）"))
        ctx["warnings"].append(L("精度评价使用同期 in-sample 方案，OA/Kappa 偏乐观"))
    elif same_period:
        ctx["validation_note"] = L("同期 in-sample 检验（用户显式指定，指标偏乐观）")
        ctx["warnings"].append(L("精度评价被显式设为同期 in-sample，OA/Kappa 偏乐观"))
    else:
        ctx["validation_note"] = L("时间外推检验：用 %d→%d 区间建模，预测第 %d 期并与实测比较") % (
            hist[0][0] + 1, hist[-1][1] + 1, len(periods))

    info(L("精度评价：") + ctx["validation_note"])
    obs = periods[-1]
    base = periods[-2]
    P = probability_matrix(accumulate_counts(ctx, hist))
    ctx["build_P"] = lambda intervals: probability_matrix(accumulate_counts(ctx, intervals))
    ctx["P"] = P

    # 验证时若需要随机森林，必须只用历史区间训练，避免信息泄漏
    saved = ctx.get("rf_summary")
    saved_trainer = ctx.get("train_inline")
    run_cfg = cfg
    if cfg.get("suitability_mode", "rf") == "rf" and hist != list(ctx["intervals"]):
        run_cfg = json.loads(json.dumps(cfg))
        rf_cfg = run_cfg.setdefault("rf", {})
        tcfg = dict(rf_cfg.get("train") or {})
        tcfg["intervals"] = hist
        tcfg.pop("save_model", None)
        rf_cfg["train"] = tcfg
        rf_cfg["force_train"] = True
        rf_cfg["model"] = None
        ctx["train_inline"] = _make_trainer(run_cfg, ctx, tcfg)

    try:
        pred, budget, deficit, _ = run_pipeline(run_cfg, ctx, len(periods) - 2, hist, 1,
                                                0.42, 0.60)
    finally:
        # 正式预测必须用回原来的训练闭包（验证的模型只在历史区间上训练过）
        ctx["train_inline"] = saved_trainer
    acc = confusion_metrics(obs["arr"], pred, obs["valid"], ctx["n_classes"], ctx["nodata"])
    unchanged = confusion_metrics(obs["arr"], base["arr"], obs["valid"],
                                  ctx["n_classes"], ctx["nodata"])
    changed = int((pred != base["arr"]).sum())
    err_pred = acc["total"] - int(np.trace(np.array(acc["confusion"], dtype=np.int64)))
    err_base = unchanged["total"] - int(np.trace(np.array(unchanged["confusion"], dtype=np.int64)))
    info(L("精度评价：预测改动 %d 个像元；错误 %d 个（未变化基线 %d 个）")
         % (changed, err_pred, err_base))
    ctx["accuracy"] = acc
    ctx["baseline_oa"] = unchanged["oa"]
    if deficit:
        ctx["warnings"].append(L("精度评价阶段的 CA 分配有 %d 个预算未落实") % deficit)
    ctx["rf_summary"] = saved
    info(L("精度：OA=%.4f  Kappa=%.4f（未变化基线 OA=%.4f）")
         % (acc["oa"], acc["kappa"], ctx["baseline_oa"]))


def _make_trainer(cfg, ctx, tcfg):
    """构造一个只用指定区间训练的闭包（供精度评价复用）。"""
    def train():
        n_classes = ctx["n_classes"]
        driver_specs = tcfg.get("drivers") or []
        drivers = ctx["drivers"]
        if not drivers:
            for spec in driver_specs:
                arr, _ = load_driver(spec["path"], int(spec.get("band", 1)))
                drivers.append((spec.get("name") or os.path.basename(spec["path"]), arr))
            ctx["drivers"] = drivers
        parts_idx, parts_y = [], []
        for k1, k2 in tcfg.get("intervals", ctx["intervals"]):
            a, va = ctx["periods"][k1]["arr"], ctx["periods"][k1]["valid"]
            b, vb = ctx["periods"][k2]["arr"], ctx["periods"][k2]["valid"]
            idx = _balanced_indices(a, b, va, vb, tcfg.get("imbalance", 2.0),
                                    int(tcfg.get("min_samples", 200)),
                                    int(tcfg.get("seed", 42)))
            parts_idx.append(idx)
            parts_y.append(a.ravel()[idx].astype(np.int64) * n_classes
                           + b.ravel()[idx].astype(np.int64))
        idx = np.concatenate(parts_idx)
        y = np.concatenate(parts_y)
        X = _feature_matrix(drivers, idx)
        model = train_rf(drivers, X, y, tcfg)
        return export_trees(model, n_classes), {
            "feature_names": [d[0] for d in drivers],
            "n_classes": n_classes, "trees": int(tcfg.get("n_estimators", 200))}
    return train


def run_train(cfg):
    """单独训练并保存模型。"""
    ctx = prepare_common(cfg)
    ctx["weights_norm"] = normalize_weights(*ctx["weights"])
    ctx["figures"] = {}
    ctx["outputs"] = {}
    rf_cfg = cfg.get("rf") or {}
    tcfg = rf_cfg.get("train") or {}
    if not tcfg.get("drivers"):
        raise JobError(L("训练需要至少一个驱动因子"))

    n_classes = ctx["n_classes"]
    drivers = []
    for spec in tcfg["drivers"]:
        arr, dmeta = load_driver(spec["path"], int(spec.get("band", 1)))
        ok, reason = _same_grid(ctx["meta"], dmeta)
        if not ok:
            raise JobError(L("驱动因子 %s 与基期网格不一致：%s") % (
                spec.get("name") or os.path.basename(spec["path"]), reason))
        drivers.append((spec.get("name") or os.path.basename(spec["path"]), arr))
    ctx["drivers"] = drivers

    pairs = tcfg.get("intervals") or ctx["intervals"]
    idx_parts, y_parts = [], []
    for k1, k2 in pairs:
        a, va = ctx["periods"][k1]["arr"], ctx["periods"][k1]["valid"]
        b, vb = ctx["periods"][k2]["arr"], ctx["periods"][k2]["valid"]
        idx = _balanced_indices(a, b, va, vb, tcfg.get("imbalance", 2.0),
                                int(tcfg.get("min_samples", 200)), int(tcfg.get("seed", 42)))
        idx_parts.append(idx)
        y_parts.append(a.ravel()[idx].astype(np.int64) * n_classes
                       + b.ravel()[idx].astype(np.int64))
    idx = np.concatenate(idx_parts)
    y = np.concatenate(y_parts)
    info(L("训练样本 %d 个，变化像元占比 %.2f%%")
         % (idx.size, 100.0 * np.mean(y % n_classes != y // n_classes)))
    X = _feature_matrix(drivers, idx)
    progress(0.35, L("训练随机森林"))
    model = train_rf(drivers, X, y, tcfg)
    imp = list(model.feature_importances_)
    ctx["importance"] = [{"name": drivers[k][0], "importance": float(imp[k])}
                         for k in np.argsort(-np.asarray(imp))]

    out = (cfg.get("outputs") or {}).get("model") or tcfg.get("save_model")
    if not out:
        raise JobError(L("训练模式需要指定模型输出路径"))
    progress(0.8, L("导出模型"))
    trees = export_trees(model, n_classes)
    save_trees(out, trees, [d[0] for d in drivers], n_classes, {})
    size_mb = os.path.getsize(out) / 1e6
    ctx["outputs"]["model"] = out
    info(L("模型已保存：%s（%.1f MB，%d 棵树）") % (out, size_mb, len(trees)))

    ctx["rf_summary"] = L("%d 棵树 · 深度 %s · 样本 %d · %.1f MB") % (
        int(tcfg.get("n_estimators", 200)), tcfg.get("max_depth", 20), idx.size, size_mb)
    ctx["counts"] = accumulate_counts(ctx, ctx["intervals"])
    ctx["P"] = probability_matrix(ctx["counts"])
    ctx["budget"] = np.zeros((n_classes, n_classes), np.int64)
    ctx["areas"] = build_area_rows(ctx, None)
    ctx["steps"] = 1
    ctx["neighborhood_size"] = int(cfg.get("neighborhood_size", 5))
    ctx["modulate"] = bool(cfg.get("modulate_by_probability", True))
    ctx["validation_note"] = L("未做精度评价（训练模式）")
    if (cfg.get("outputs") or {}).get("fig_dir"):
        try:
            pth = os.path.join(cfg["outputs"]["fig_dir"], "feature_importance.png")
            draw_importance(pth, ctx["importance"])
            ctx["figures"]["importance"] = pth
        except Exception as ex:
            ctx["warnings"].append(L("特征重要性图生成失败：%s") % ex)
    ctx["elapsed"] = time.time() - ctx["start"]
    return build_metrics(cfg, ctx)


# ---------------------------------------------------------------- 自检

def selftest():
    """纯函数自检（不读写任何栅格）。"""
    ok = 0
    failed = []

    def check(cond, name, detail=""):
        nonlocal ok
        if cond:
            ok += 1
            print(L("  [通过] %s %s") % (name, detail))
        else:
            failed.append(name)
            print(L("  [失败] %s %s") % (name, detail))

    print(L("== 转移矩阵 =="))
    a = np.array([[1, 1, 2], [2, 3, 0]], dtype=np.int32)
    va = a != 0
    b = np.array([[1, 2, 2], [3, 3, 0]], dtype=np.int32)
    vb = b != 0
    c = transition_counts(a, va, b, vb, 4)
    check(c[1, 1] == 1 and c[1, 2] == 1 and c[2, 3] == 1 and c[3, 3] == 1,
          L("计数矩阵"), str(c.tolist()))
    check(int(c[0].sum()) == 0, L("NoData 行恒为 0"))
    P = probability_matrix(c)
    rows = P.sum(axis=1)
    check(np.allclose(rows[[1, 2, 3]], 1.0), L("概率行和=1"), str(np.round(rows, 4).tolist()))
    check(np.allclose(rows[0], 0.0), L("空行保持全 0"))

    print(L("== 转移预算 =="))
    counts = np.array([0, 10, 10, 0], np.int64)
    P2 = np.zeros((4, 4))
    P2[1, 1], P2[1, 2] = 0.6, 0.4
    P2[2, 2], P2[2, 3] = 0.5, 0.5
    B = build_budget(counts, P2, 4, 0)
    check([int(B[i].sum()) for i in range(4)] == [0, 10, 10, 0],
          L("每行和=当期像元数"), str([int(B[i].sum()) for i in range(4)]))
    check(B[1, 1] == 6 and B[1, 2] == 4 and B[2, 2] == 5 and B[2, 3] == 5,
          L("预算数值"), B.tolist())
    col = B.sum(axis=0)
    target = markov_target_counts(counts, P2, 4, 0)
    check(abs(int(col.sum()) - int(target.sum())) <= 2, L("预算总量≈Markov 目标"),
          "%d vs %d" % (int(col.sum()), int(target.sum())))

    print(L("== 最大余数 =="))
    counts3 = np.array([0, 5, 0], np.int64)
    P3 = np.array([[0, 0, 0], [0, 0.0, 1.0], [0, 0, 0]])
    B3 = build_budget(counts3, P3, 3, 0)
    check(B3[1, 2] == 5 and B3[1, 1] == 0, L("全概率行整体搬移"), B3.tolist())
    P4 = np.array([[0, 0, 0], [0.4, 0.0, 0.6], [0, 0, 0]])
    B4 = build_budget(np.array([0, 5, 0], np.int64), P4, 3, 0)
    check(B4[1].sum() == 5 and B4[1, 0] == 2 and B4[1, 2] == 3, L("按余数分配"), B4.tolist())

    print(L("== 邻域 =="))
    cur = np.zeros((5, 5), np.int32)
    cur[2, 2] = 1
    nb = neighborhood_map(cur, 1, 5)
    check(abs(float(nb[2, 2]) - 1.0 / 25) < 1e-6, L("中心 5×5 占比"), "%.4f" % nb[2, 2])
    nb3 = neighborhood_map(cur, 1, 3)
    check(abs(float(nb3[2, 2]) - 1.0 / 9) < 1e-6, L("中心 3×3 占比"), "%.4f" % nb3[2, 2])
    check(abs(float(nb[0, 0]) - 1.0 / 25) < 1e-6, L("边界补 0"), "%.4f" % nb[0, 0])

    print(L("== 精度指标 =="))
    obs = np.array([[1, 1], [2, 2]], np.int32)
    pred = np.array([[1, 2], [2, 2]], np.int32)
    valid = np.ones((2, 2), bool)
    m = confusion_metrics(obs, pred, valid, 4, 0)
    check(abs(m["oa"] - 0.75) < 1e-12, "OA", "%.4f" % m["oa"])
    row = np.array([0.0, 2.0, 2.0, 0.0])
    col = np.array([0.0, 1.0, 3.0, 0.0])
    pe = float((row * col).sum() / 16.0)
    kappa = (0.75 - pe) / (1 - pe)
    check(abs(m["kappa"] - kappa) < 1e-12, "Kappa", "%.4f" % m["kappa"])
    check(abs(m["pa"][1] - 0.5) < 1e-12 and abs(m["ua"][1] - 1.0) < 1e-12,
          "PA/UA", "%s / %s" % (m["pa"][1], m["ua"][1]))

    print(L("== 预算守恒（随机） =="))
    rng = np.random.RandomState(7)
    n = 5
    counts5 = np.array([0, 400, 300, 200, 100], np.int64)
    P5 = rng.dirichlet(np.ones(n), size=n)
    P5[:, 0] = 0
    P5 /= P5.sum(axis=1, keepdims=True)
    B5 = build_budget(counts5, P5, n, 0)
    check(all(int(B5[i].sum()) == int(counts5[i]) for i in range(n)),
          L("随机概率下行和精确"), str([int(B5[i].sum()) for i in range(n)]))

    print("")
    print(L("自检：%d 项通过，%d 项失败") % (ok, len(failed)))
    if failed:
        print(L("失败项：") + "、".join(failed))
        return 1
    return 0


# ---------------------------------------------------------------- 入口

def _force_utf8():
    """把标准输出/错误切到 UTF-8。

    C# 侧用管道读取 stdout，Windows 下 Python 默认按 GBK 写，中文阶段名会变成乱码；
    这里主动 reconfigure 而不是依赖 PYTHONIOENCODING（子进程环境块由宿主继承，不额外设置）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None):
    _force_utf8()
    ap = argparse.ArgumentParser(description=L("SharpGIS CA-Markov 引擎"))
    ap.add_argument("--job", help=L("参数 JSON 路径"))
    ap.add_argument("--selftest", action="store_true", help=L("运行纯函数自检"))
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.job:
        print(L("用法：camarkov_engine.py --job job.json 或 --selftest"))
        return 1

    try:
        with open(args.job, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as ex:
        print(L("无法读取参数文件：%s") % ex, file=sys.stderr)
        return 1

    rio = _rasterio()
    try:
        with rio.Env(GDAL_PAM_ENABLED="NO"):
            global _LANG
            _LANG = "en" if str(cfg.get("lang", "zh")).lower().startswith("en") else "zh"
            mode = cfg.get("mode", "predict")
            t0 = time.time()
            if mode == "analyze":
                metrics = run_analyze(cfg)
            elif mode == "train":
                metrics = run_train(cfg)
            elif mode == "predict":
                metrics = run_predict(cfg)
            else:
                raise JobError(L("未知模式：") + str(mode))
            out = (cfg.get("outputs") or {}).get("metrics")
            if out:
                d = os.path.dirname(os.path.abspath(out))
                if d and not os.path.isdir(d):
                    os.makedirs(d)
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(metrics, f, ensure_ascii=False)
            _emit("DONE", "%.1f" % (time.time() - t0))
            return 0
    except JobError as ex:
        print(L("参数或数据错误：%s") % ex, file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
