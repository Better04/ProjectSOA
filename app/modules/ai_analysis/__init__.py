from flask import Blueprint

# 创建一个新的蓝图 'ai_analysis'
# URL 前缀为 /api/ai，避免与 /api/devinfo 冲突
ai_bp = Blueprint('ai_analysis', __name__, url_prefix='/api/ai')

from . import views