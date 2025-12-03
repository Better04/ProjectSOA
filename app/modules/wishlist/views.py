from flask import request, jsonify, session
from app.modules.wishlist import wishlist_bp
from app.services.wishlist_service import WishlistService
from app.modules.user.views import login_required  # 导入我们之前写的登录验证装饰器


# --------------------
# 路由：获取当前用户的所有心愿单
# --------------------
@wishlist_bp.route('/', methods=['GET'])
@login_required
def get_all_wishes():
    user_id = session.get('user_id')
    wishes = WishlistService.get_wishes_by_user(user_id)
    return jsonify({
        'message': '心愿单列表获取成功',
        'data': wishes
    }), 200


# --------------------
# 路由：添加新的心愿单项目
# --------------------
@wishlist_bp.route('/', methods=['POST'])
@login_required
def add_wish():
    data = request.get_json()
    url = data.get('url')
    target_price = data.get('target_price')

    condition_type = data.get('condition_type')  # e.g. 'weekly_commits'
    target_value = data.get('target_value')      # e.g. 5

    if not url or target_price is None:
        return jsonify({'message': '缺少 URL 或期望价格'}), 400

    try:
        target_price = float(target_price)
    except ValueError:
        return jsonify({'message': '期望价格格式不正确'}), 400

    user_id = session.get('user_id')

    new_wish, msg = WishlistService.add_wish(
        user_id, 
        url, 
        target_price,
        condition_type=condition_type, 
        target_value=target_value)

    if new_wish:
        return jsonify({'message': msg, 'wish_id': new_wish.id}), 201
    else:
        # msg 包含了失败原因
        return jsonify({'message': msg}), 400

    # --------------------


# 路由：删除心愿单项目
# --------------------
@wishlist_bp.route('/<int:wish_id>', methods=['DELETE'])
@login_required
def delete_wish(wish_id):
    user_id = session.get('user_id')

    if WishlistService.delete_wish(user_id, wish_id):
        return jsonify({'message': '心愿单项目删除成功'}), 200
    else:
        return jsonify({'message': '心愿单项目不存在或不属于该用户'}), 404
    

# 路由：检查成就并尝试解锁心愿
# --------------------
@wishlist_bp.route('/check-status', methods=['POST'])
@login_required
def check_unlock_status():
    """
    手动触发：检查当前用户的所有心愿解锁条件是否达成
    """
    user_id = session.get('user_id')
    
    success, msg = WishlistService.check_and_unlock_wishes(user_id)
    
    return jsonify({
        'message': msg,
        'unlocked': success
    }), 200