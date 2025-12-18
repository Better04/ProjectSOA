# app/modules/battle/views.py

from flask import Blueprint, request, jsonify
# 引入之前写好的 Service
from app.services.battle_service import battle_service
from app.services.llm_analysis import llm_service

# 定义蓝图
battle_bp = Blueprint('battle', __name__, url_prefix='/api/battle')

@battle_bp.route('/analyze', methods=['POST'])
def analyze_battle():
    """
    对战分析接口
    前端发送 JSON: { "player1": "github_id_1", "player2": "github_id_2" }
    """
    try:
        data = request.json
        # 获取前端传来的两个 GitHub 用户名
        p1_username = data.get('player1')
        p2_username = data.get('player2')

        # 1. 校验必填项
        if not p1_username or not p2_username:
            return jsonify({
                "success": False, 
                "message": "错误：必须输入两名选手的 GitHub 用户名"
            }), 400

        # 2. 获取两名选手的战斗数据 (GitHub + 本地心愿)
        # 调用 battle_service 获取聚合数据
        p1_data = battle_service.get_player_data(p1_username)
        p2_data = battle_service.get_player_data(p2_username)

        # 3. 检查 GitHub 是否有效 (如果连 GitHub 都查不到，视为无效用户)
        if not p1_data['found']:
            return jsonify({"success": False, "message": f"找不到用户 {p1_username} (GitHub)"}), 404
        if not p2_data['found']:
            return jsonify({"success": False, "message": f"找不到用户 {p2_username} (GitHub)"}), 404

        # 4. 调用 AI 生成解说词
        # 调用 llm_analysis 生成文本
        ai_commentary = llm_service.analyze_battle(p1_data, p2_data)

        # 5. 返回最终结果给前端
        return jsonify({
            "success": True,
            "players": {
                "player1": p1_data,
                "player2": p2_data
            },
            "commentary": ai_commentary
        })

    except Exception as e:
        print(f"Battle View Error: {e}")
        return jsonify({"success": False, "message": "服务器内部错误，对战分析失败"}), 500