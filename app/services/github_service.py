# app/services/github_service.py

import requests
import os;
import base64
from .base_platform_service import BasePlatformService

# GitHub API 的基础 URL
GITHUB_API_BASE = "https://api.github.com"

# 🚨🚨🚨 请在这里填入你申请的 GitHub Personal Access Token 🚨🚨🚨
# 格式通常是 "ghp_" 开头的一长串字符
# 如果留空，每小时只能请求 60 次；填入后可请求 5000 次。
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')


class GitHubService(BasePlatformService):
    """GitHub 开发者信息获取服务"""

    def get_platform_name(self) -> str:
        return 'github'

    def extract_item_id(self, url: str) -> str:
        raise NotImplementedError("此服务不使用 extract_item_id 方法进行用户仓库查询。")

    def fetch_item_details(self, item_id: str, url: str) -> dict:
        raise NotImplementedError("此服务不使用 fetch_item_details 方法进行用户仓库查询。")

    # 🟢 核心辅助方法：统一生成带 Token 的请求头
    def _get_headers(self):
        headers = {
            'Accept': 'application/vnd.github.v3+json',
        }
        if GITHUB_TOKEN:
            headers['Authorization'] = f'token {GITHUB_TOKEN}'
        return headers

    def fetch_user_repos(self, username: str) -> list:
        """
        获取指定用户的所有仓库的基础列表（包含描述和更新日期）。
        """
        url = f"{GITHUB_API_BASE}/users/{username}/repos"

        # 使用带 Token 的 headers
        headers = self._get_headers()

        params = {
            'type': 'owner',
            'sort': 'updated',
            'direction': 'desc'
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            repo_list = response.json()

            formatted_data = []
            for repo in repo_list:
                formatted_data.append({
                    'name': repo.get('name'),
                    'full_name': repo.get('full_name'),
                    'html_url': repo.get('html_url'),
                    'description': repo.get('description') or '暂无描述',
                    'created_at': repo.get('created_at'),
                    'updated_at': repo.get('updated_at'),
                    'stars': repo.get('stargazers_count'),
                    'language': repo.get('language')
                })

            return formatted_data

        except requests.RequestException as e:
            print(f"Error fetching GitHub data for user {username}: {e}")
            return []

    def fetch_repo_details(self, owner: str, repo_name: str) -> dict:
        """
        获取单个仓库的详细信息，包括贡献者和最新提交活动。
        """
        repo_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}"
        contributors_url = f"{repo_url}/contributors"
        commit_activity_url = f"{repo_url}/stats/commit_activity"  # 周提交统计

        # 使用带 Token 的 headers
        headers = self._get_headers()

        details = {}

        # 1. 获取基本信息（用于验证仓库存在性）
        try:
            repo_resp = requests.get(repo_url, headers=headers, timeout=5)
            repo_resp.raise_for_status()
            repo_data = repo_resp.json()

            details.update({
                'name': repo_data.get('name'),
                'description': repo_data.get('description') or '暂无描述',
                'updated_at': repo_data.get('updated_at'),
                'language': repo_data.get('language'),
                'forks_count': repo_data.get('forks_count'),
                'open_issues_count': repo_data.get('open_issues_count')
            })
        except requests.RequestException as e:
            raise ValueError(f"无法获取仓库基本信息: {e}")

        # 2. 获取贡献者信息（成员情况和贡献情况）
        try:
            # 默认 GitHub API 响应是按贡献次数降序排列的
            contr_resp = requests.get(contributors_url, headers=headers, timeout=5)
            contr_resp.raise_for_status()
            contr_data = contr_resp.json()

            contributors = []
            for contributor in contr_data[:5]:  # 只返回前5名贡献者作为代表
                contributors.append({
                    'login': contributor.get('login'),
                    'avatar_url': contributor.get('avatar_url'),  # 获取头像
                    'contributions': contributor.get('contributions'),
                    'html_url': contributor.get('html_url')
                })
            details['contributors'] = contributors

        except requests.RequestException:
            details['contributors'] = []

        # 3. 获取最近提交活动（仓库更新情况 - 深度）
        try:
            activity_resp = requests.get(commit_activity_url, headers=headers, timeout=5)

            if activity_resp.status_code == 202:
                # 202 表示 GitHub 正在计算统计数据
                details['commit_activity'] = "提交活动统计正在 GitHub 后台计算中，请稍后重试。"
                details['recent_commit_count_4weeks'] = 0
            else:
                activity_resp.raise_for_status()
                activity_data = activity_resp.json()
                # 提取最近四周的提交总数
                recent_commits = sum(week.get('total', 0) for week in activity_data[-4:])
                details['recent_commit_count_4weeks'] = recent_commits
                details['weekly_activity'] = activity_data  # 包含过去一年每周的提交数据

        except requests.RequestException:
            details['commit_activity'] = '无法获取提交活动数据。'
            details['recent_commit_count_4weeks'] = -1

        return details

    def fetch_user_profile(self, username: str) -> dict:
        """
        获取 GitHub 用户的基本个人资料（头像、Bio、粉丝数等）
        """
        url = f"{GITHUB_API_BASE}/users/{username}"
        # 使用带 Token 的 headers
        headers = self._get_headers()

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 404:
                return None  # 用户不存在
            response.raise_for_status()

            data = response.json()
            return {
                'username': data.get('login'),
                'name': data.get('name'),  # 用户的昵称/真名
                'avatar_url': data.get('avatar_url'),
                'bio': data.get('bio'),  # 个人简介
                'public_repos': data.get('public_repos'),
                'followers': data.get('followers'),
                'following': data.get('following'),
                'html_url': data.get('html_url'),
                'created_at': data.get('created_at')
            }
        except requests.RequestException as e:
            print(f"获取用户 {username} 资料失败: {e}")
            return None

    def fetch_repo_readme(self, owner: str, repo_name: str) -> str:
        """
        获取仓库的 README.md 内容。
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/readme"
        # 使用带 Token 的 headers
        headers = self._get_headers()

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 404:
                return "该仓库没有 README 文档。"

            response.raise_for_status()
            data = response.json()

            # GitHub API 返回的 content 是 Base64 编码的，需要解码
            content_encoded = data.get('content', '')
            encoding = data.get('encoding', 'utf-8')

            if encoding == 'base64':
                # 解码成字符串
                return base64.b64decode(content_encoded).decode('utf-8', errors='ignore')
            else:
                return content_encoded

        except Exception as e:
            print(f"获取 README 失败: {e}")
            return "无法读取文档内容。"

    def fetch_repo_languages(self, owner: str, repo_name: str) -> dict:
        """
        获取仓库的语言分布数据 (例如: {'Python': 1200, 'HTML': 300})
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/languages"
        headers = self._get_headers()

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            # 返回的数据格式: {"TypeScript": 4096, "Vue": 2048, ...} (单位是字节)
            return response.json()

        except requests.RequestException as e:
            print(f"获取语言数据失败: {e}")
            return {}

# 实例化服务，供其他模块调用
github_service = GitHubService()