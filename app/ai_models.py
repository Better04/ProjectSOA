from app.database import db
from datetime import datetime


class GitHubAnalysis(db.Model):
    """
    [新增] 存储 AI 对 GitHub 用户的深度分析报告及五维评分
    """
    __tablename__ = 'github_analysis'

    id = db.Column(db.Integer, primary_key=True)

    # 被分析的 GitHub 用户名
    github_username = db.Column(db.String(128), index=True, nullable=False)

    # 用户头像 URL (冗余存储，便于前端快速渲染列表)
    avatar_url = db.Column(db.String(512))

    # 存储结构化的 JSON 字符串
    # 必须包含:
    # 1. radar_scores (五维评分)
    # 2. analysis_result (文本报告 - summary)
    # 3. tech_stack (技术栈)
    # 4. repositories (新增：仓库列表分析，包含 ai_summary 和 status)
    analysis_json = db.Column(db.Text, nullable=False)

    # 分析时间
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'github_username': self.github_username,
            'avatar_url': self.avatar_url,
            'timestamp': self.timestamp.isoformat()
        }