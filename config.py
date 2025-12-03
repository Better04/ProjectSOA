import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()


class Config:
    """基础配置类"""
    # 随机生成一个 SECRET_KEY，用于保护会话和CSRF
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'A_REALLY_BAD_SECRET_KEY'

    # --- 数据库配置 (MySQL) ---
    # 确保你已经安装并启动了 MySQL 服务
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or 'root'  # 🚨 替换为你自己的密码
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_PORT = os.environ.get('MYSQL_PORT') or '3306'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'wishlist_aggregator'  # 项目数据库名称
    # ------------------- SMTP 邮件配置 (新增/修改) -------------------
    # QQ 邮箱 SMTP 服务器地址
    SMTP_SERVER = os.environ.get('SMTP_SERVER') or 'smtp.qq.com'
    # QQ 邮箱 SMTP 默认端口 (使用 SSL/TLS 加密)
    SMTP_PORT = os.environ.get('SMTP_PORT') or 465

    # 你的 QQ 邮箱完整地址 (发送方)
    SMTP_USER = os.environ.get('SMTP_USER') or '1431785463@qq.com'  # 🚨 替换成你的邮箱
    # 在步骤一中获得的 16 位授权码，不是你的登录密码！
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD') or 'uhizndmuaarfbaai'  # 🚨 替换成你的授权码
    # ------------------------------------------------------------------
    # SQLAlchemy 配置
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    # 禁用修改追踪，可以节省资源
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True  # 开启调试模式


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    # 这里可以添加生产环境专有的配置


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}