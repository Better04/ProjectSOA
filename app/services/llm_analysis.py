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
        :param username: 用户名
        :param profile_data: 用户基本资料
        :param detailed_repos_data: 包含 README 的核心仓库数据 (用于深度点评)
        :param simple_repos_data: 所有仓库的基础元数据 (用于生成列表和状态判断)
        """
        # 直接从环境变量读取
        api_key = os.environ.get('MOONSHOT_API_KEY')
        base_url = os.environ.get('MOONSHOT_BASE_URL', "https://api.moonshot.cn/v1")

        if not api_key:
            return {"error": "后端未配置 MOONSHOT_API_KEY"}

        current_date = datetime.now().strftime("%Y-%m-%d")

        # 1. 构造 System Prompt
        system_prompt = f"""
        你是一个资深技术专家。你的任务是分析 GitHub 用户的技术能力，并整理其仓库清单。
        当前日期是: {current_date}

        【输出格式要求】
        必须输出严格的 JSON 格式，包含以下字段：
        1. "radar_scores": {{ "code_quality": 0-100, "activity": 0-100, "documentation": 0-100, "influence": 0-100, "tech_breadth": 0-100 }}
        2. "overall_score": 综合评分 (0-100)
        3. "tech_stack": [技术栈列表]
        4. "summary": (Markdown格式) 深度分析报告。
        5. "repositories": [
            {{
                "name": "仓库名",
                "status": "Active" | "Maintenance" | "Deprecated",
                "ai_summary": "一句话中文简介"
            }}
        ]

        注意：必须处理我提供的【所有】仓库，不要遗漏，也不要中途截断 JSON。
        """

        # 2. 构造 User Prompt
        # 为了防止 Prompt 过长导致 context window 不够，我们依然限制输入给 AI 的列表长度
        # 但 max_tokens 增大后，这里可以适当放宽，比如传前 30-50 个
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

        # ---------------------------------------------------------------------
        # [关键修复] 添加 max_tokens 并降低 temperature
        # ---------------------------------------------------------------------
        payload = {
            "model": "moonshot-v1-32k",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,  # 使用低温 (0.1) 确保格式稳定
            "max_tokens": 16000,  # [核心修复] 强制要求长输出，防止 JSON 被截断
            "response_format": {"type": "json_object"}
        }

        try:
            print(f"--- [AI] 正在请求 Kimi 深度分析 {username} (max_tokens=16000)... ---")

            # 增加 timeout 到 180秒，因为生成长文本需要更多时间
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload,
                                     timeout=180)
            response.raise_for_status()

            result = response.json()
            raw_content = result['choices'][0]['message']['content']

            # ----------------- [DEBUG] -----------------
            # 如果还是出错，可以看这里的日志
            # print("\n" + "="*20 + " DEBUG: Kimi 返回内容 " + "="*20)
            # print(raw_content[-200:]) # 打印最后200个字符检查结尾
            # print("="*60 + "\n")
            # -------------------------------------------

            content = raw_content

            # 数据清洗：移除 Markdown 标记
            if content.strip().startswith("```"):
                content = re.sub(r'^```json\s*|\s*```$', '', content.strip(), flags=re.MULTILINE)

            # 数据清洗：移除非法控制字符
            illegal_json_chars = re.compile(r'[\x00-\x1f]')
            content = illegal_json_chars.sub(r'', content)

            # 解析 JSON
            parsed_result = json.loads(content)

            # 兜底补全
            if 'repositories' not in parsed_result:
                parsed_result['repositories'] = []

            if 'radar_scores' not in parsed_result:
                parsed_result['radar_scores'] = {
                    "code_quality": 60, "activity": 60, "documentation": 60,
                    "influence": 60, "tech_breadth": 60
                }

            return parsed_result

        except json.JSONDecodeError as e:
            print(f"\n❌ [CRITICAL ERROR] JSON 解析失败: {e}")
            # 打印出错位置的片段
            print(f"Error context: {content[max(0, e.pos - 50):min(len(content), e.pos + 50)]}")
            return {
                "error": f"JSON解析失败: {str(e)}",
                "radar_scores": {"code_quality": 0, "activity": 0, "documentation": 0, "influence": 0,
                                 "tech_breadth": 0},
                "summary": "AI 返回数据截断或格式错误，请重试。",
                "repositories": [],
                "overall_score": 0,
                "tech_stack": []
            }

        except Exception as e:
            print(f"AI Service Error: {e}")
            return {
                "error": str(e),
                "radar_scores": {"code_quality": 0, "activity": 0, "documentation": 0, "influence": 0,
                                 "tech_breadth": 0},
                "summary": "AI 服务暂时不可用。",
                "repositories": [],
                "overall_score": 0,
                "tech_stack": []
            }


# 单例导出
llm_service = LLMAnalysisService()