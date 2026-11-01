# -*- coding: utf-8 -*-
"""让测试能 import qgis_camarkov，无需安装成包。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
