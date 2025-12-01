from flask import Blueprint

# 创建一个名为 'user' 的蓝图
# url_prefix='/api/user' 意味着这个蓝图下的所有路由都以 /api/user 开头
user_bp = Blueprint('user', __name__, url_prefix='/api/user')

# 导入 views 文件，将路由注册到蓝图上
from . import views