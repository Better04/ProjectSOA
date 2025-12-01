from flask_sqlalchemy import SQLAlchemy

# 初始化 SQLAlchemy 实例
db = SQLAlchemy()

# ⚠️ 注意：这个文件只负责创建 db 实例，不会立即连接数据库。
# 实际的连接和配置将在 app/__init__.py 中完成。