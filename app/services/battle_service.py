# app/services/battle_service.py

from app.models import User
from app.services.github_service import github_service

class BattleService:
    """
    对战服务：负责聚合 GitHub 数据和本地数据库数据，
    为 AI 分析和前端雷达图提供标准的'战斗力'数据。
    """

    @staticmethod
    def get_player_data(username: str) -> dict:
        """
        获取单个选手的完整战斗数据 (GitHub + 本地心愿单)
        参数:
            username: 前端传入的 GitHub 用户名
        """
        
        # === 1. 获取 GitHub 维度数据 ===
        # 调用现有的 github_service 获取基础信息
        profile = github_service.fetch_user_profile(username)
        
        # 如果 GitHub 上查无此人，直接返回错误标记
        # 注意：这里我们认为如果是无效的 GitHub 用户，连对战资格都没有
        if not profile:
            return {
                "username": username,
                "found": False,
                "avatar": "", 
                "github_data": {},
                "internal_data": {}
            }

        # 获取更详细的 GitHub 战力指标
        # 获取 Star 总数
        total_stars = github_service.get_total_stars(username)
        
        # 获取最近一周的提交数 (活跃度指标)
        weekly_commits = github_service.get_user_weekly_commit_count(username)

        github_stats = {
            "repos": profile.get('public_repos', 0),
            "followers": profile.get('followers', 0),
            "stars": total_stars,
            "commits_weekly": weekly_commits,
            "bio": profile.get('bio') or '暂无介绍'
        }

        # === 2. 获取本地数据库维度数据 (心愿单/积分) ===
        # 逻辑：尝试在本地数据库查找同名用户
        internal_stats = {
            "is_member": False,
            "wishes_count": 0,
            "score": 0
        }

        try:
            # 查询本地数据库
            # 注意：前提是用户注册的 username 和 GitHub ID 一致
            local_user = User.query.filter_by(username=username).first()
            
            if local_user:
                # 获取心愿数量
                # 如果你的 wishes 是 lazy='dynamic'，用 .count()；如果是 list，用 len()
                # 根据你之前的 User 模型代码，这里假定是 dynamic
                wishes_count = local_user.wishes.count() 
                
                # 计算综合战斗力积分
                # 算法：(心愿数 * 10) + (GitHub Stars * 5) + (GitHub Repos * 2)
                # 这样既看重内部活跃度，也看重外部技术实力
                score = (wishes_count * 10) + (total_stars * 5) + (github_stats['repos'] * 2)
                
                internal_stats = {
                    "is_member": True,
                    "wishes_count": wishes_count,
                    "score": score
                }
            else:
                # 如果本地没查到，那就是“纯 GitHub 路人”
                # 积分为 0 或者仅基于 GitHub 数据计算一个基础分，这里设为 0 以突显差距
                internal_stats = {
                    "is_member": False,
                    "wishes_count": 0,
                    "score": 0
                }
                
        except Exception as e:
            print(f"数据库查询失败 (用户: {username}): {e}")
            # 发生数据库错误时，降级处理，不影响 GitHub 数据展示
            internal_stats = {"is_member": False, "wishes_count": 0, "score": 0}

        # === 3. 返回整合后的战斗力数据 ===
        return {
            "username": profile.get('login', username), 
            "name": profile.get('name', username),
            "avatar": profile.get('avatar_url'),
            "found": True,
            "github_data": github_stats,
            "internal_data": internal_stats
        }

# 实例化服务
battle_service = BattleService()