import logging
# 导入你刚刚修改过的 github_service 实例
from app.services.github_service import github_service

logger = logging.getLogger(__name__)

class AchievementService:
    """
    成就裁判服务：连接 GitHub 数据与奖励机制
    """

    @staticmethod
    def check_achievement(user_github_username: str, condition_type: str, target_value: int) -> bool:
        
        if not user_github_username:
            return False

        try:
            
            if condition_type == 'weekly_commits':
                
                current_commits = github_service.get_user_weekly_commit_count(user_github_username)
                
                logger.info(f"用户 {user_github_username} 本周提交: {current_commits}, 目标: {target_value}")
                return current_commits >= target_value

            
            elif condition_type == 'total_stars':
               
                current_stars = github_service.get_total_stars(user_github_username)
                
                logger.info(f"用户 {user_github_username} Star总数: {current_stars}, 目标: {target_value}")
                return current_stars >= target_value

            else:
                logger.warning(f"未定义的成就类型: {condition_type}")
                return False

        except Exception as e:
            logger.error(f"成就检查出错: {str(e)}")
            return False

# 实例化供外部调用
achievement_service = AchievementService()