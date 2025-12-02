from flask import jsonify, request
import json
from datetime import datetime, timedelta

# 导入当前蓝图
from app.modules.ai_analysis import ai_bp

# 导入服务
from app.services.github_service import github_service
from app.services.llm_analysis import llm_service
from app.ai_models import GitHubAnalysis
from app.database import db


@ai_bp.route('/analyze/<string:username>', methods=['POST', 'GET'])
def analyze_github_user_radar(username):
    """
    [POST/GET] /api/ai/analyze/<username>
    功能：聚合 GitHub 数据 -> AI 分析 (含仓库列表状态) -> 存库 -> 返回
    """
    # 1. 检查缓存
    cached = GitHubAnalysis.query.filter_by(github_username=username).order_by(GitHubAnalysis.timestamp.desc()).first()

    if cached and cached.timestamp > datetime.utcnow() - timedelta(hours=24):
        try:
            return jsonify({
                'message': '获取成功 (来自缓存)',
                'data': json.loads(cached.analysis_json),
                'avatar_url': cached.avatar_url,
                'cached': True,
                'username': username
            }), 200
        except json.JSONDecodeError:
            pass

    # 2. 获取基础数据
    profile = github_service.fetch_user_profile(username)
    if not profile:
        return jsonify({'message': f'GitHub 用户 {username} 不存在或 API 受限'}), 404

    repos = github_service.fetch_user_repos(username)
    if not repos:
        return jsonify({'message': '该用户没有公开仓库，无法分析'}), 400

    # 3. 数据准备
    # 排序：Stars 优先, Updated 其次
    sorted_repos = sorted(repos, key=lambda r: (r.get('stars', 0), r.get('updated_at', '')), reverse=True)

    # A. 准备简单列表数据 (传给 AI 用于生成列表和判断状态)
    # 包含：name, description, updated_at, language, stars
    simple_repos_data = []
    for r in sorted_repos:
        simple_repos_data.append({
            'name': r.get('name'),
            'description': r.get('description'),
            'updated_at': r.get('updated_at'),
            'language': r.get('language'),
            'stars': r.get('stars')
        })

    # B. 准备深度数据 (Top 5 仓库，包含 README)
    top_repos = sorted_repos[:5]
    detailed_repos = []
    print(f"--- [Backend] 正在抓取 {username} 的 Top {len(top_repos)} 仓库详情 (含 README) ---")

    for repo in top_repos:
        repo_name = repo['name']
        langs = github_service.fetch_repo_languages(username, repo_name)
        readme_content = github_service.fetch_repo_readme(username, repo_name)

        if readme_content and len(readme_content) > 2000:
            readme_content = readme_content[:2000] + "...(truncated)"

        detailed_repos.append({
            'name': repo_name,
            'description': repo['description'],
            'stars': repo['stars'],
            'updated_at': repo['updated_at'],
            'language': repo['language'],
            'languages_stats': langs,
            'readme': readme_content
        })

    # 4. 调用 AI (传入 detailed 用于 summary，simple 用于列表生成)
    ai_result = llm_service.analyze_github_user(username, profile, detailed_repos, simple_repos_data)

    if "error" in ai_result:
        return jsonify({'message': 'AI 分析服务出错', 'error': ai_result['error']}), 500

    # 5. 存入数据库
    try:
        analysis_json_str = json.dumps(ai_result, ensure_ascii=False)
        new_record = GitHubAnalysis(
            github_username=username,
            avatar_url=profile.get('avatar_url'),
            analysis_json=analysis_json_str
        )
        db.session.add(new_record)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error saving AI analysis to DB: {e}")

    # 6. 返回结果
    return jsonify({
        'message': 'AI 深度分析完成',
        'data': ai_result,
        'avatar_url': profile.get('avatar_url'),
        'cached': False,
        'username': username
    }), 200