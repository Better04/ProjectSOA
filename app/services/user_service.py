import hashlib
from app.database import db
from app.models import User


# -------------------
# 辅助函数：密码哈希
# -------------------
def hash_password(password: str) -> str:
    """对密码进行 SHA-256 哈希"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def check_password(hashed_password: str, password: str) -> bool:
    """检查密码是否匹配"""
    return hashed_password == hash_password(password)


# -------------------
# 用户服务核心逻辑
# -------------------
class UserService:

    @staticmethod
    def register_user(username, email, password):
        """注册新用户，如果用户已存在则返回 None"""
        if User.query.filter_by(username=username).first() or \
                User.query.filter_by(email=email).first():
            return None  # 用户名或邮箱已存在

        # 实例化 User 模型，并哈希密码
        new_user = User(
            username=username,
            email=email,
            password_hash=hash_password(password)
        )

        db.session.add(new_user)
        db.session.commit()
        return new_user

    @staticmethod
    def authenticate_user(username, password):
        """验证用户身份，成功则返回 User 对象，否则返回 None"""
        user = User.query.filter_by(username=username).first()

        if user and check_password(user.password_hash, password):
            return user
        return None