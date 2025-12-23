# app/modules/battle/views.py (优化版)

from flask import Blueprint, request, jsonify
from functools import wraps
import time
import re
from app.services.battle_service import battle_service
from app.services.llm_analysis import llm_service

battle_bp = Blueprint('battle', __name__, url_prefix='/api/battle')


# ============ 装饰器：请求验证 ============
def validate_battle_request(f):
    """验证对战请求的装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.json

        if not data:
            return jsonify({
                "success": False,
                "message": "请求体不能为空"
            }), 400

        player1 = data.get('player1', '').strip()
        player2 = data.get('player2', '').strip()

        # 验证必填项
        if not player1 or not player2:
            return jsonify({
                "success": False,
                "message": "必须输入两名选手的 GitHub 用户名"
            }), 400

        # 验证用户名格式（GitHub 用户名规则）
        if not _is_valid_github_username(player1):
            return jsonify({
                "success": False,
                "message": f"无效的 GitHub 用户名格式: {player1}"
            }), 400

        if not _is_valid_github_username(player2):
            return jsonify({
                "success": False,
                "message": f"无效的 GitHub 用户名格式: {player2}"
            }), 400

        # 验证不能自己和自己对战
        if player1.lower() == player2.lower():
            return jsonify({
                "success": False,
                "message": "不能选择相同的选手进行对战！"
            }), 400

        return f(*args, **kwargs)

    return decorated_function


def _is_valid_github_username(username):
    """
    验证 GitHub 用户名格式
    规则：只能包含字母、数字、连字符，不能以连字符开头或结尾，长度1-39
    """
    if not username or len(username) > 39:
        return False
    if username.startswith('-') or username.endswith('-'):
        return False
    return all(c.isalnum() or c == '-' for c in username)


# ============ 主要路由 ============
@battle_bp.route('/analyze', methods=['POST'])
@validate_battle_request
def analyze_battle():
    """
    对战分析接口
    前端发送 JSON: { "player1": "github_id_1", "player2": "github_id_2" }
    返回: {
        "success": true,
        "players": {
            "player1": {
                "username", "avatar", "rank", "rank_emoji",
                "power_score", "strengths",
                "github_data", "internal_data"
            },
            "player2": {...}
        },
        "commentary": "AI解说文本",
        "analysis_time": 1.23  # 分析耗时（秒）
    }
    """
    start_time = time.time()

    try:
        data = request.json
        p1_username = data.get('player1').strip()
        p2_username = data.get('player2').strip()

        print(f"\n{'=' * 60}")
        print(f"[Battle Request] {p1_username} VS {p2_username}")
        print(f"{'=' * 60}")

        # 1. 获取两名选手数据
        print("[Step 1/3] 获取选手数据...")
        try:
            p1_data = battle_service.get_player_data(p1_username)
        except Exception as e:
            print(f"[Error] Failed to fetch player1 data: {e}")
            return jsonify({
                "success": False,
                "message": f"获取选手 {p1_username} 数据失败，请检查用户名是否正确"
            }), 404

        try:
            p2_data = battle_service.get_player_data(p2_username)
        except Exception as e:
            print(f"[Error] Failed to fetch player2 data: {e}")
            return jsonify({
                "success": False,
                "message": f"获取选手 {p2_username} 数据失败，请检查用户名是否正确"
            }), 404

        # 2. 验证数据有效性
        if not p1_data.get('found'):
            return jsonify({
                "success": False,
                "message": f"GitHub 用户不存在: {p1_username}"
            }), 404

        if not p2_data.get('found'):
            return jsonify({
                "success": False,
                "message": f"GitHub 用户不存在: {p2_username}"
            }), 404

        print(f"  ✓ 红方: {p1_data.get('username')} (战力: {p1_data.get('power_score', 0)})")
        print(f"  ✓ 蓝方: {p2_data.get('username')} (战力: {p2_data.get('power_score', 0)})")

        # 3. 数据预处理和增强
        print("[Step 2/3] 数据增强...")
        p1_enhanced = _enhance_player_data(p1_data)
        p2_enhanced = _enhance_player_data(p2_data)
        print(f"  ✓ 数据增强完成")

        # 4. 调用 AI 生成深度解说
        print("[Step 3/3] AI 生成解说...")
        try:
            ai_commentary = llm_service.analyze_battle(p1_enhanced, p2_enhanced)
            print(f"  ✓ AI 解说生成成功 (长度: {len(ai_commentary)} 字)")
        except Exception as e:
            print(f"[Warning] AI analysis failed: {e}")
            # AI 失败时返回默认解说
            ai_commentary = _generate_fallback_commentary(p1_enhanced, p2_enhanced)
            print(f"  ⚠ 使用备用解说")

        # 5. 计算分析耗时
        analysis_time = round(time.time() - start_time, 2)
        print(f"\n[Battle Complete] 分析耗时: {analysis_time}s")
        print(f"{'=' * 60}\n")

        # 6. 返回完整结果
        return jsonify({
            "success": True,
            "players": {
                "player1": p1_enhanced,
                "player2": p2_enhanced
            },
            "commentary": ai_commentary,
            "analysis_time": analysis_time,
            "timestamp": int(time.time())
        }), 200

    except Exception as e:
        print(f"\n[Fatal Error] Battle analysis failed: {e}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": "服务器内部错误，对战分析失败，请稍后重试"
        }), 500


# ============ 辅助函数 ============
def _enhance_player_data(player_data):
    """
    增强选手数据，添加计算字段和战力评分
    """
    github = player_data.get('github_data', {})
    internal = player_data.get('internal_data', {})

    # 计算综合战力值（加权算法）
    # 权重设计：活跃度 > 质量 > 数量
    power_score = (
            github.get('repos', 0) * 5 +  # 仓库数
            github.get('followers', 0) * 3 +  # 粉丝数
            github.get('stars', 0) * 2 +  # 获赞数
            github.get('commits_weekly', 0) * 10 +  # 周提交（最重要）
            internal.get('wishes_count', 0) * 8 +  # 心愿数
            internal.get('score', 0) * 1  # 积分
    )

    # 判定等级和徽章
    rank, rank_emoji = _calculate_rank(power_score)

    player_data['power_score'] = power_score
    player_data['rank'] = rank
    player_data['rank_emoji'] = rank_emoji

    # 添加特长标签
    player_data['strengths'] = _identify_strengths(github, internal)

    return player_data


def _calculate_rank(power_score):
    """
    根据战力值计算等级
    返回: (等级名称, Emoji)
    """
    if power_score < 100:
        return "新手村民", "🌱"
    elif power_score < 500:
        return "见习战士", "⚔️"
    elif power_score < 1500:
        return "精英骑士", "🛡️"
    elif power_score < 5000:
        return "传奇勇者", "👑"
    else:
        return "神话英雄", "⚡"


def _identify_strengths(github, internal):
    """
    识别选手的特长领域
    """
    strengths = []

    # GitHub 维度
    if github.get('repos', 0) > 50:
        strengths.append("项目大户")
    if github.get('followers', 0) > 100:
        strengths.append("人气王者")
    if github.get('stars', 0) > 500:
        strengths.append("Star收割机")
    if github.get('commits_weekly', 0) > 20:
        strengths.append("提交狂魔")

    # 平台维度
    if internal.get('is_member'):
        strengths.append("平台VIP")
    if internal.get('wishes_count', 0) > 10:
        strengths.append("许愿专家")
    if internal.get('score', 0) > 500:
        strengths.append("积分达人")

    return strengths if strengths else ["潜力新星"]


def _generate_fallback_commentary(p1, p2):
    """
    AI 失败时的后备解说生成（规则引擎）
    """
    p1_name = p1.get('username', 'Player1')
    p2_name = p2.get('username', 'Player2')
    p1_score = p1.get('power_score', 0)
    p2_score = p2.get('power_score', 0)
    p1_rank = p1.get('rank', '战士')
    p2_rank = p2.get('rank', '战士')

    p1_gh = p1.get('github_data', {})
    p2_gh = p2.get('github_data', {})

    # 判断优势方
    if p1_score > p2_score:
        leader = p1_name
        leader_rank = p1_rank
        follower = p2_name
        gap = p1_score - p2_score
        gap_percent = round((gap / p2_score * 100)) if p2_score > 0 else 100
    else:
        leader = p2_name
        leader_rank = p2_rank
        follower = p1_name
        gap = p2_score - p1_score
        gap_percent = round((gap / p1_score * 100)) if p1_score > 0 else 100

    # 找出关键差距
    star_diff = abs(p1_gh.get('stars', 0) - p2_gh.get('stars', 0))
    repo_diff = abs(p1_gh.get('repos', 0) - p2_gh.get('repos', 0))

    # 生成解说
    intro = f"🎮 各位观众，欢迎来到代码竞技场！红方{p1_name}（{p1_rank}）VS 蓝方{p2_name}（{p2_rank}）！"

    # 数据对比
    if star_diff > 100:
        comparison = f"从 GitHub 数据来看，双方在Star数上差距明显，相差 {star_diff} 个赞！"
    elif repo_diff > 20:
        comparison = f"项目数量对比悬殊，一方拥有 {repo_diff} 个仓库的优势！"
    else:
        comparison = f"双方实力接近，数据胶着，这将是一场精彩对决！"

    # 胜负分析
    if gap_percent > 50:
        conclusion = f"{leader}（{leader_rank}）展现出碾压级的实力，领先 {gap_percent}%！但我们期待{follower}能够奋起直追，创造奇迹！✨"
    elif gap_percent > 20:
        conclusion = f"{leader}暂时领先，但{follower}仍有逆转机会！代码世界，一切皆有可能！🚀"
    else:
        conclusion = f"势均力敌！{leader}仅以微弱优势领先，这场战斗充满悬念！让我们拭目以待！💪"

    return f"{intro}\n\n{comparison}\n\n{conclusion}"


# ============ 健康检查路由 ============
@battle_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        "status": "healthy",
        "service": "battle_arena",
        "version": "2.0",
        "timestamp": int(time.time())
    }), 200


# ============ 统计接口 ============
@battle_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    获取对战统计数据（可选功能）
    """
    # TODO: 实现统计逻辑，如总对战次数、热门选手等
    return jsonify({
        "success": True,
        "message": "统计功能开发中..."
    }), 200