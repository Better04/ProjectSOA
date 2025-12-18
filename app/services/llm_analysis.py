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
        # [修改] System Prompt: 区分网页端深度评语(summary)和简历摘要(resume_summary)
        # ---------------------------------------------------------------------
        system_prompt = f"""
        你是一个资深技术专家和CTO。你的任务是基于 GitHub 数据对候选人进行深度技术评估。
        当前日期: {current_date}

        【任务目标】
        请生成两份不同用途的分析文案：
        1. **网页深度报告 (summary)**：字数 500 字左右，Markdown 格式，分维度深度解析。
        2. **简历摘要 (resume_summary)**：字数 150 字左右，精炼概括，用于简历头部。

        【输出格式要求】
        必须输出严格的 JSON 格式，包含以下字段：
        1. "radar_scores": {{ "code_quality": 0-100, "activity": 0-100, "documentation": 0-100, "influence": 0-100, "tech_breadth": 0-100 }}
        2. "overall_score": 综合评分 (0-100)
        3. "tech_stack": [技术栈列表]

        4. "summary": (Markdown格式) **网页端深度评语**。
           - **字数要求**：500字左右。
           - **内容结构**：请使用 Markdown 二级标题 (##) 分隔以下四个章节：
             - ## 核心竞争力摘要：宏观评价技术段位、主攻领域及最大亮点。
             - ## 技术深度与架构：深挖最具挑战性的技术实现，必须引用具体仓库名说明。
             - ## 工程素养与规范：评价代码可读性、设计模式、测试覆盖率及文档质量。
             - ## 业务价值与潜能：分析其解决实际问题的能力及产品思维。
           - **语气**：专业、犀利、客观，拒绝空泛的套话。

        5. "resume_summary": (纯文本) **简历专用摘要**。
           - **字数要求**：120-150字。
           - **内容要求**：高度概括，适合放在简历 Header 部分的自我介绍。不要使用 Markdown 标题。

        6. "repositories": [
            {{
                "name": "仓库名",
                "status": "Active" | "Maintenance" | "Deprecated",
                "ai_summary": "一句话中文简介"
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
            # 稍微调高温度以生成更丰富的长文本
            "temperature": 0.4,
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

            # [新增] 确保 resume_summary 存在，如果 AI 未生成则截取 summary
            if 'resume_summary' not in parsed_result:
                raw_summary = parsed_result.get('summary', '')
                clean_text = raw_summary.replace('#', '').replace('*', '')
                parsed_result['resume_summary'] = clean_text[:150] + "..."

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
        base_url = os.environ.get('MOONSHOT_BASE_URL', "[https://api.moonshot.cn/v1](https://api.moonshot.cn/v1)")

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
    
    def analyze_battle(self, player1_data: dict, player2_data: dict) -> str:
        """
        对战解说功能
        接收两名选手的完整数据，调用 AI 生成激情解说词。
        """
        # 0. 检查 API Key
        api_key = os.environ.get('MOONSHOT_API_KEY')
        base_url = os.environ.get('MOONSHOT_BASE_URL', "https://api.moonshot.cn/v1")
        
        if not api_key:
            return "解说员正在休息（后端未配置 API Key），请自行根据雷达图判断胜负！"

        # 1. 智能判定对战类型，用于指导 AI 的解说侧重点
        # 即使两边都没注册 (is_member=False)，这里也能处理
        p1_is_member = player1_data['internal_data'].get('is_member', False)
        p2_is_member = player2_data['internal_data'].get('is_member', False)

        battle_context = ""
        if p1_is_member and p2_is_member:
            battle_context = "【场景】：这是一场平台内部的‘巅峰内战’。请重点对比两人的心愿完成度（梦想）和 GitHub 技术实力（现实）。"
        elif not p1_is_member and not p2_is_member:
            battle_context = "【场景】：这是一场‘野生大神遭遇战’。两位选手均未入驻本平台（心愿数据均为0）。请完全忽略心愿数据，**专注于 GitHub 数据的硬核技术对比**（仓库、粉丝、活跃度、Star数）。不要嘲讽他们没有心愿，要赞叹他们的技术。"
        else:
            battle_context = "【场景】：这是一场‘踢馆赛’（会员 VS 路人）。请幽默地调侃路人选手虽然技术可能很强，但因为没有许愿单而显得‘缺乏生活情趣’或‘没有梦想’，突显会员的主场优势。"

        # 2. 构造 System Prompt (人设与规则)
        system_prompt = f"""
        你是一名《代码竞技场》的金牌解说员，风格幽默、犀利、充满激情（类似电竞解说）。
        你的任务是根据两名程序员的【GitHub数据】和【本平台许愿数据】进行 1v1 对比分析。
        
        {battle_context}
        
        【输出要求】
        - 不需要输出 JSON，直接输出一段**纯文本**解说词。
        - 字数严格控制在 **150字 - 200字** 之间。
        - 必须包含一个明确的**“胜负判定”**或**“风格评价”**。
        - 适当使用 Emoji 🎤 ⚔️ 🏆 🔥。
        """

        # 3. 构造 User Prompt (格式化数据喂给 AI)
        def format_player_info(p_data):
            gh = p_data['github_data']
            internal = p_data['internal_data']
            
            # 基础信息
            info = f"选手: {p_data['username']}\n"
            info += f"   - GitHub: {gh.get('repos', 0)} 仓库, {gh.get('followers', 0)} 粉丝, {gh.get('stars', 0)} Stars, 本周提交 {gh.get('commits_weekly', 0)} 次\n"
            
            # 平台信息
            if internal.get('is_member'):
                info += f"   - 平台战力: 认证会员 (心愿数: {internal.get('wishes_count')}, 积分: {internal.get('score')})\n"
            else:
                info += f"   - 平台战力: 路人 (无本平台记录)\n"
            
            return info

        user_prompt = f"""
        【红方选手】
        {format_player_info(player1_data)}

        【蓝方选手】
        {format_player_info(player2_data)}

        请开始你的解说！
        """

        # 4. 调用大模型
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
            "temperature": 0.7, # 稍微调高温度，让解说更生动
        }

        try:
            # 这里的 timeout 设置为 60 秒，防止 AI 思考过久
            response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            return content

        except Exception as e:
            print(f"Battle Analysis AI Error: {e}")
            return "🎤 滋...滋... 现场信号受到太阳黑子干扰，解说员暂时失联！请观众朋友们直接看大屏幕上的数据对比！"


llm_service = LLMAnalysisService()