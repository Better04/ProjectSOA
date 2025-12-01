from .database import db
from datetime import datetime


class User(db.Model):
    """用户模型：存放登录信息"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))  # 存储密码的哈希值
    email = db.Column(db.String(120), unique=True)

    # 关联心愿单：一个用户有多个心愿 (backref='user' 可以在 Wish 中通过 .user 访问用户)
    wishes = db.relationship('Wish', backref='user', lazy='dynamic')


class Item(db.Model):
    """商品模型：存放商品的通用信息"""
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)

    # 商品的唯一识别码，例如京东 SKU 或 Steam AppID
    platform_item_id = db.Column(db.String(128), index=True, nullable=False)

    # 原始链接，用于回溯
    original_url = db.Column(db.String(512), unique=True, nullable=False)

    # 商品名称和图片（由平台服务抓取）
    title = db.Column(db.String(256), nullable=False)
    image_url = db.Column(db.String(512))

    # 平台名称：'jd', 'steam', 'taobao'
    platform = db.Column(db.String(50), index=True, nullable=False)

    # 关联价格历史记录
    prices = db.relationship('PriceHistory', backref='item', lazy='dynamic')
    wishes = db.relationship('Wish', backref='item', lazy='dynamic')


class Wish(db.Model):
    """心愿单模型：连接用户和商品，并记录用户的期望价格"""
    __tablename__ = 'wishes'
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'))

    # 用户的期望价格
    target_price = db.Column(db.Float, nullable=False)

    # 激活状态
    is_active = db.Column(db.Boolean, default=True)


class PriceHistory(db.Model):
    """价格历史模型：记录每次抓取到的价格"""
    __tablename__ = 'price_history'
    id = db.Column(db.Integer, primary_key=True)

    item_id = db.Column(db.Integer, db.ForeignKey('items.id'))
    price = db.Column(db.Float, nullable=False)

    # 记录抓取时间
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)