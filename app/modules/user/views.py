from flask import request, jsonify, session
from app.modules.user import user_bp
from app.services.user_service import UserService
from functools import wraps # <--- 新增导入

# 导入 models 中的 User 类，虽然我们主要通过 Service 操作，但可以用于类型提示

# --------------------
# 辅助函数：权限验证装饰器
# --------------------
# 我们使用 Flask 的 session 来存储用户登录状态
def login_required(f):
    """一个简单的装饰器，检查用户是否登录"""

    # 关键修改：移除 @user_bp.route('/', methods=['GET'])
    @wraps(f) # <--- 新增：使用 @wraps(f) 确保保留原函数 f 的元数据（例如：端点名称）
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # 返回 401 Unauthorized
            return jsonify({'message': '未授权，请先登录'}), 401
        # 权限检查通过后，调用并返回原视图函数的结果
        return f(*args, **kwargs)

    return decorated_function

# --------------------
# 注册路由
# --------------------
@user_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'message': '缺少必要的注册信息'}), 400

    new_user = UserService.register_user(username, email, password)

    if new_user:
        return jsonify({
            'message': '注册成功',
            'user_id': new_user.id,
            'username': new_user.username
        }), 201
    else:
        return jsonify({'message': '用户名或邮箱已被使用'}), 409  # Conflict


# --------------------
# 登录路由
# --------------------
@user_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = UserService.authenticate_user(username, password)

    if user:
        # 登录成功，设置 Session
        session['user_id'] = user.id
        session['username'] = user.username
        session.permanent = True  # 设置 Session 永久有效（或一定时长）
        return jsonify({
            'message': '登录成功',
            'username': user.username
        }), 200
    else:
        return jsonify({'message': '用户名或密码错误'}), 401


# --------------------
# 登出路由
# --------------------
@user_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return jsonify({'message': '已登出'}), 200


# --------------------
# 获取当前用户信息 (用于前端判断是否已登录)
# --------------------
@user_bp.route('/info', methods=['GET'])
@login_required  # 使用我们定义的装饰器来保护此路由
def get_user_info():
    # 因为有 @login_required 检查，所以 session['user_id'] 一定存在
    return jsonify({
        'user_id': session.get('user_id'),
        'username': session.get('username')
    }), 200