import requests
import json
import re
import os
from datetime import datetime
from flask import current_app


class LLMAnalysisService:
    """
    AI 分析服务：负责调用 Kimi 大模型并清洗数据
    """

    def analyze_github_user(self, username: str, profile_data: dict, detailed_repos_data: list,
                            simple_repos_data: list) -> dict:
        """
        调用 LLM 对用户进行全方位分析。
        """
        # 直接从环境变量读取
        api_key = os.environ.get('MOONSHOT_API_KEY')
        base_url = os.environ.get('MOONSHOT_BASE_URL', "https://api.moonshot.cn/v1")

        if not api_key:
            return {"error": "后端未配置 MOONSHOT_API_KEY"}

        current_date = datetime.now().strftime("%Y-%m-%d")

        # ---------------------------------------------------------------------
        # [修改] System Prompt: 恢复为中文输出要求
        # ---------------------------------------------------------------------
        system_prompt = f"""
        你是一个资深技术专家。你的任务是分析 GitHub 用户的技术能力，并整理其仓库清单。请注意你的评分标准应当**适度宽松**，侧重于发现潜力，而非仅仅挑剔不足,分数尽量满足70的正态分布。
        当前日期是: {current_date}

        【输出格式要求】
        必须输出严格的 JSON 格式，包含以下字段：
        1. "radar_scores": {{ "code_quality": 0-100, "activity": 0-100, "documentation": 0-100, "influence": 0-100, "tech_breadth": 0-100 }}
        2. "overall_score": 综合评分 (0-100)
        3. "tech_stack": [技术栈列表]
        4. "summary": (Markdown格式) 深度分析报告（**中文**）。
        5. "repositories": [
            {{
                "name": "仓库名",
                "status": "Active" | "Maintenance" | "Deprecated",
                "ai_summary": "一句话**中文**简介"
            }}
        ]

        注意：必须处理我提供的【所有】仓库，不要遗漏，也不要中途截断 JSON。
        """

        # 2. 构造 User Prompt
        limited_simple_repos = simple_repos_data[:30]

        user_prompt = f"""
        请分析开发者 '{username}'。

        【个人资料】:
        {json.dumps(profile_data, ensure_ascii=False)}

        【待分析仓库列表】:
        {json.dumps(limited_simple_repos, ensure_ascii=False)}

        【核心仓库深度数据】(用于点评):
        {json.dumps(detailed_repos_data, ensure_ascii=False)}

        请生成 JSON 报告。
        """

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 参数设置
        payload = {
            "model": "moonshot-v1-32k",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 16000,
            "response_format": {"type": "json_object"}
        }

        try:
            print(f"--- [AI] 正在请求 Kimi 深度分析 {username}... ---")
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=180)
            response.raise_for_status()

            result = response.json()
            content = result['choices'][0]['message']['content']

            # 数据清洗
            if content.strip().startswith("```"):
                content = re.sub(r'^```json\s*|\s*```$', '', content.strip(), flags=re.MULTILINE)

            illegal_json_chars = re.compile(r'[\x00-\x1f]')
            content = illegal_json_chars.sub(r'', content)

            parsed_result = json.loads(content)

            # 兜底补全
            if 'repositories' not in parsed_result: parsed_result['repositories'] = []
            if 'radar_scores' not in parsed_result:
                parsed_result['radar_scores'] = {k: 60 for k in
                                                 ["code_quality", "activity", "documentation", "influence",
                                                  "tech_breadth"]}
            if 'overall_score' not in parsed_result: parsed_result['overall_score'] = 60

            return parsed_result

        except json.JSONDecodeError as e:
            print(f"\n❌ [CRITICAL ERROR] JSON 解析失败: {e}")
            print(f"Error context: {content[max(0, e.pos - 50):min(len(content), e.pos + 50)]}")
            return {"error": f"JSON解析失败: {str(e)}"}
        except Exception as e:
            print(f"AI Service Error: {e}")
            return {"error": str(e)}

    def analyze_specific_repo(self, repo_details: dict, readme_content: str) -> dict:
        """
        [任务 4 - 升级版] 针对单个仓库进行可视化数据分析。
        要求 AI 输出数值型数据，用于前端渲染图表。
        """
        api_key = os.environ.get('MOONSHOT_API_KEY')
        base_url = os.environ.get('MOONSHOT_BASE_URL', "https://api.moonshot.cn/v1")

        if not api_key:
            return {"error": "未配置 API KEY"}

        safe_readme = readme_content[:8000] + "..." if len(readme_content) > 8000 else readme_content

        # --- 修改点：Prompt 改为请求 JSON 数据，而非 Markdown 文本 ---
        system_prompt = """
        你是一个代码仓库可视化分析专家。你的任务是将 GitHub 仓库的价值转化为【可视化数据】。
        请**不要**输出长篇大论的文字，而是输出**数值**和**短语**，以便前端渲染图表。

        【分析维度】
        1. **综合评分**: 0-100 分。
        2. **五维能力 (Dimensions)**: 请从 [功能完备性, 代码规范度, 文档质量, 社区影响力, 技术创新性] 5个维度打分 (0-100)。
        3. **适用场景 (Scenarios)**: 列出 3-5 个最适合使用该仓库的场景，并给出推荐指数 (0-100)。
        4. **核心关键词**: 提取 5-8 个核心技术或功能关键词。

        【输出格式】
        请输出严格的 JSON 格式：
        {
            "summary": "一句话超简短总结 (30字以内)",
            "overall_score": 85,
            "radar_data": {
                "functionality": 80,  // 功能完备性
                "code_quality": 90,   // 代码规范度
                "documentation": 70,  // 文档质量
                "influence": 60,      // 社区影响力
                "innovation": 85      // 技术创新性
            },
            "scenarios": [
                {"name": "微服务架构", "score": 95},
                {"name": "个人学习", "score": 80},
                {"name": "生产环境", "score": 60}
            ],
            "keywords": ["Web框架", "Python", "轻量级", "WSGI", "路由系统"]
        }
        """

        user_prompt = f"""
        【仓库元数据】:
        {json.dumps(repo_details, ensure_ascii=False)}

        【README 文档片段】:
        {safe_readme}

        请生成可视化分析数据。
        """

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "moonshot-v1-32k",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            content = response.json()['choices'][0]['message']['content']
            if content.strip().startswith("```"):
                content = re.sub(r'^```json\s*|\s*```$', '', content.strip(), flags=re.MULTILINE)

            return json.loads(content)

        except Exception as e:
            print(f"Repo Analysis Error: {e}")
            return {"error": str(e)}

llm_service = LLMAnalysisService()