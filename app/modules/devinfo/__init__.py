# app/modules/devinfo/__init__.py

from flask import Blueprint

# 创建一个名为 'devinfo' 的蓝图，URL 前缀为 /api/devinfo
devinfo_bp = Blueprint('devinfo', __name__, url_prefix='/api/devinfo')

# 导入 views 文件，将路由注册到蓝图上
from . import views