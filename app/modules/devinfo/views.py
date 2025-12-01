# app/modules/devinfo/views.py

from flask import jsonify
from app.modules.devinfo import devinfo_bp
from app.services.github_service import github_service


# --------------------
# 路由 1：获取指定用户的 GitHub 仓库列表 (包含描述)
# GET /api/devinfo/repos/<username>
# --------------------
@devinfo_bp.route('/repos/<string:username>', methods=['GET'])
def get_user_github_repos(username):
    """
    根据用户名查询 GitHub 仓库列表，并返回创建日期、更新日期和描述。
    """
    if not username:
        return jsonify({'message': '缺少 GitHub 用户名'}), 400

    repos_data = github_service.fetch_user_repos(username)

    if not repos_data:
        return jsonify({
            'message': f'未找到用户 {username} 的公开仓库数据，或 API 请求失败。',
            'data': []
        }), 200

    return jsonify({
        'message': f'成功获取用户 {username} 的 GitHub 仓库数据',
        'data': repos_data
    }), 200


# --------------------
# 路由 2：获取单个仓库的详细信息 (贡献者和活动)
# GET /api/devinfo/details/<owner>/<repo_name>
# --------------------
@devinfo_bp.route('/details/<string:owner>/<string:repo_name>', methods=['GET'])
def get_repo_details(owner, repo_name):
    """
    获取单个仓库的详细信息，包括描述、贡献者、最近活动等。
    URL 格式：/api/devinfo/details/flask/flask
    """
    if not all([owner, repo_name]):
        return jsonify({'message': '缺少仓库所有者或仓库名称'}), 400

    try:
        details = github_service.fetch_repo_details(owner, repo_name)
    except ValueError as e:
        # 捕获服务层抛出的错误，通常是 404 Not Found
        return jsonify({'message': f"查询失败: {str(e)}"}), 404

    # 检查是否因为 API 错误导致数据不完整
    if not details or not details.get('name'):
        return jsonify({'message': f"无法找到或获取 {owner}/{repo_name} 的详细信息"}), 404

    return jsonify({
        'message': f'成功获取 {owner}/{repo_name} 的详细数据',
        'data': details
    }), 200


# --------------------
# 路由 3：获取用户基本资料 (新增)
# GET /api/devinfo/profile/<username>
# --------------------
@devinfo_bp.route('/profile/<string:username>', methods=['GET'])
def get_user_profile(username):
    """
    获取用户基本资料（头像、Bio、粉丝数等）
    """
    profile = github_service.fetch_user_profile(username)

    if not profile:
        return jsonify({'message': '未找到用户或获取失败'}), 404

    return jsonify({
        'message': '获取成功',
        'data': profile
    }), 200


# --------------------
# 路由 4：获取仓库 README 内容 (新增)
# GET /api/devinfo/readme/<owner>/<repo_name>
# --------------------
@devinfo_bp.route('/readme/<string:owner>/<string:repo_name>', methods=['GET'])
def get_repo_readme(owner, repo_name):
    """
    获取仓库 README 内容
    """
    content = github_service.fetch_repo_readme(owner, repo_name)

    return jsonify({
        'message': '获取成功',
        'data': content  # 直接返回字符串内容
    }), 200


# --------------------
# 路由 5：获取仓库语言分布 (新增)
# GET /api/devinfo/languages/<owner>/<repo_name>
# --------------------
@devinfo_bp.route('/languages/<string:owner>/<string:repo_name>', methods=['GET'])
def get_repo_languages(owner, repo_name):
    """
    获取仓库语言构成
    """
    languages = github_service.fetch_repo_languages(owner, repo_name)

    return jsonify({
        'message': '获取成功',
        'data': languages
    }), 200