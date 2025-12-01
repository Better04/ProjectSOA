from flask import Blueprint

# 创建一个名为 'wishlist' 的蓝图
# url_prefix='/api/wishlist' 意味着这个蓝图下的所有路由都以 /api/wishlist 开头
wishlist_bp = Blueprint('wishlist', __name__, url_prefix='/api/wishlist')

# 导入 views 文件，将路由注册到蓝图上
from . import views