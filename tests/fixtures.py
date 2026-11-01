# -*- coding: utf-8 -*-
"""生成合成土地利用栅格，供测试与手工验证使用。

三期 100×80 的 uint8 分类栅格（0=无效，1=耕地，2=森林，3=水体），
坐标系 EPSG:32650，像元 30 米。三期的变化刻意简单，便于断言面积。
"""

import os

import numpy as np
import rasterio
from rasterio.transform import from_origin

NODATA = 0
HEIGHT = 80
WIDTH = 100


def build_periods():
    """返回三期数组（按时间从旧到新）。"""
    first = np.ones((HEIGHT, WIDTH), np.uint8)
    first[:40, :] = 2

    second = first.copy()
    second[20:35, 30:60] = 3

    third = second.copy()
    third[30:45, 35:70] = 1
    return [first, second, third]


def write_raster(path, array, epsg=32650):
    """写出一幅单波段 uint8 GeoTIFF。

    :param path: 输出路径。
    :param array: 二维数组。
    :param epsg: 目标坐标系。
    :returns: 写出的路径。
    """
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="uint8",
        nodata=NODATA,
        transform=from_origin(500000, 3500000, 30, 30),
        crs="EPSG:%d" % epsg,
    ) as dataset:
        dataset.write(array, 1)
    return path


def make_fixtures(directory):
    """在指定目录生成三期栅格并返回路径列表。

    :param directory: 输出目录，不存在会自动创建。
    :returns: 三个栅格路径（旧 → 新）。
    """
    os.makedirs(directory, exist_ok=True)
    paths = []
    for index, array in enumerate(build_periods()):
        name = "lulc_%d.tif" % (2010 + index * 5)
        paths.append(write_raster(os.path.join(directory, name), array))
    return paths


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "fixtures"
    for path in make_fixtures(target):
        print(path)
