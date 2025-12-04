# app/__init__.py

from flask import Flask
from config import config
from .database import db
from flask_cors import CORS


# from .scheduler import init_scheduler # 移除这个导入

def create_app(config_name='default'):
    """
    Flask 应用工厂函数。
    """
    app = Flask(__name__)

    # 1. 加载配置
    app.config.from_object(config[config_name])

    # 2. 注册数据库扩展
    db.init_app(app)

    # 3. 注册蓝图 (Blueprint)
    from app.modules.user import user_bp
    from app.modules.wishlist import wishlist_bp
    from app.modules.devinfo import devinfo_bp # <-- 新增导入

    # 在 app/__init__.py 中找到注册蓝图的位置，添加：
    from app.modules.chat.views import chat_bp
    app.register_blueprint(chat_bp, url_prefix='/api/chat')

    app.register_blueprint(user_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(devinfo_bp) # <-- 新增注册

    # 4. 注册 CORS 扩展
    CORS(app, supports_credentials=True)

    from app.modules.ai_analysis import ai_bp
    app.register_blueprint(ai_bp)

    # 简单的测试路由
    @app.route('/')
    def index():
        return 'Welcome to Heart\'s Desire Aggregator Backend!'

    return app