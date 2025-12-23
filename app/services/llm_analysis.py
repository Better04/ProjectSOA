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

    def __init__(self):
        self.api_key = os.environ.get('MOONSHOT_API_KEY')
        self.base_url = os.environ.get('MOONSHOT_BASE_URL', "https://api.moonshot.cn/v1")

    def analyze_github_user(self, username: str, profile_data: dict, detailed_repos_data: list,
                            simple_repos_data: list) -> dict:
        """
        调用 LLM 对用户进行全方位分析。
        """

        if not self.api_key:
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
            "Authorization": f"Bearer {self.api_key}",
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
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=180)
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

        if not self.api_key:
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
                "functionality": 80,
                "code_quality": 90,
                "documentation": 70,
                "influence": 60, 
                "innovation": 85
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
            "Authorization": f"Bearer {self.api_key}",
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
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60)
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
        核心对战解说生成方法

        Args:
            player1_data: 红方选手数据（包含 GitHub 和平台数据）
            player2_data: 蓝方选手数据（包含 GitHub 和平台数据）

        Returns:
            str: AI 生成的解说文本
        """

        # 1. 检查 API 配置
        if not self.api_key:
            return self._generate_fallback_commentary(player1_data, player2_data)

        # 2. 智能判定对战场景
        battle_scene = self._identify_battle_scene(player1_data, player2_data)

        # 3. 构建精心设计的提示词
        system_prompt = self._build_system_prompt(battle_scene)
        user_prompt = self._build_user_prompt(player1_data, player2_data, battle_scene)

        # 4. 调用 AI API
        try:
            commentary = self._call_moonshot_api(system_prompt, user_prompt)
            return commentary
        except Exception as e:
            print(f"[AI Error] {e}")
            return self._generate_fallback_commentary(player1_data, player2_data)

    def _identify_battle_scene(self, p1: dict, p2: dict) -> str:
        """
        智能识别对战场景类型
        返回: 'internal_war' | 'external_war' | 'mixed_battle'
        """
        p1_member = p1.get('internal_data', {}).get('is_member', False)
        p2_member = p2.get('internal_data', {}).get('is_member', False)

        if p1_member and p2_member:
            return 'internal_war'  # 平台内战
        elif not p1_member and not p2_member:
            return 'external_war'  # 野生大神对决
        else:
            return 'mixed_battle'  # 踢馆赛

    def _build_system_prompt(self, battle_scene: str) -> str:
        """
        根据对战场景构建系统提示词
        """

        # 基础人设
        base_persona = """你是《代码竞技场》的金牌解说员，风格幽默风趣、充满激情。
你精通各种编程语言和技术栈，能够从 GitHub 数据中洞察程序员的真实实力。
你的解说要像电竞解说员一样热血沸腾，但也要保持专业和客观。"""

        # 根据场景调整解说策略
        scene_strategies = {
            'internal_war': """
【场景】：这是一场平台内部的"巅峰内战"！
【解说重点】：
- 对比双方的 GitHub 技术实力（仓库、Star、活跃度）
- 强调平台数据的差异（心愿数、积分）
- 分析谁更有"梦想驱动力"vs"技术硬实力"
- 营造势均力敌、精彩纷呈的氛围
""",
            'external_war': """
【场景】：这是一场"野生大神遭遇战"！
【解说重点】：
- 完全聚焦于 GitHub 数据的硬核技术对比
- 不要提及"没有心愿"这件事（避免负面）
- 强调双方都是技术高手，在开源社区叱咤风云
- 用技术指标（仓库质量、Star数、提交频率）判断胜负
- 语气要尊重这些"隐世高人"
""",
            'mixed_battle': """
【场景】：这是一场"踢馆赛"（会员 VS 路人）！
【解说重点】：
- 幽默调侃路人选手"虽强但缺乏梦想"
- 突出会员的主场优势（有心愿、有积分、有归属感）
- 同时尊重路人的技术实力
- 制造戏剧冲突：技术 vs 梦想，哪个更重要？
- 鼓励路人加入平台，一起追逐梦想
"""
        }

        scene_strategy = scene_strategies.get(battle_scene, scene_strategies['internal_war'])

        # 输出规范
        output_rules = """
【输出规范】
1. **格式**：纯文本，不使用 Markdown 或特殊符号
2. **字数**：严格控制在 180-220 字之间
3. **结构**：
   - 开场白（20字）：点燃激情
   - 数据对比（80字）：分析双方实力
   - 胜负判定（60字）：给出明确结论或趋势分析
   - 结语（20字）：鼓励和展望
4. **语气**：热血、幽默、专业，适当使用 Emoji
5. **必须包含**：至少 2 个具体的数据对比
6. **禁止**：
   - 过度贬低任何一方
   - 使用刻板印象或歧视性语言
   - 冗长废话和重复表述
   - 超过 220 字
"""

        return f"{base_persona}\n\n{scene_strategy}\n\n{output_rules}"

    def _build_user_prompt(self, p1: dict, p2: dict, scene: str) -> str:
        """
        构建用户提示词，格式化选手数据
        """

        def format_player(p: dict, side: str) -> str:
            """格式化单个选手信息"""
            gh = p.get('github_data', {})
            internal = p.get('internal_data', {})

            # 基础信息
            info = f"【{side}】{p.get('username', 'Unknown')} ({p.get('rank', '战士')} {p.get('rank_emoji', '')})\n"

            # GitHub 数据
            info += f"GitHub实力：\n"
            info += f"  - 仓库数: {gh.get('repos', 0)} 个\n"
            info += f"  - 粉丝数: {gh.get('followers', 0)} 人\n"
            info += f"  - 获赞数: {gh.get('stars', 0)} Stars\n"
            info += f"  - 周活跃: {gh.get('commits_weekly', 0)} 次提交\n"

            # 平台数据
            if internal.get('is_member'):
                info += f"平台数据：\n"
                info += f"  - 身份: 🏅 认证会员\n"
                info += f"  - 心愿数: {internal.get('wishes_count', 0)} 个\n"
                info += f"  - 积分: {internal.get('score', 0)} 点\n"
            else:
                info += f"平台数据：\n"
                info += f"  - 身份: 👻 野生路人（未注册）\n"

            # 特长标签
            if p.get('strengths'):
                info += f"特长: {', '.join(p.get('strengths', []))}\n"

            # 综合战力
            info += f"综合战力: {p.get('power_score', 0)} 点\n"

            return info

        # 格式化双方数据
        p1_info = format_player(p1, "红方选手")
        p2_info = format_player(p2, "蓝方选手")

        # 添加对战场景说明
        scene_hints = {
            'internal_war': "这是平台内部的会员对决，请重点对比他们的梦想（心愿）和技术（GitHub）数据。",
            'external_war': "双方都是野生高手，请完全基于 GitHub 技术数据进行对比，不要提及心愿。",
            'mixed_battle': "会员 vs 路人的踢馆赛，请对比技术实力与平台归属感的差异。"
        }

        hint = scene_hints.get(scene, "")

        return f"""
{p1_info}

VS

{p2_info}

【对战提示】
{hint}

请生成一段精彩的解说词（180-220字，纯文本）：
"""

    def _call_moonshot_api(self, system_prompt: str, user_prompt: str) -> str:
        """
        调用 Moonshot AI API
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.8,  # 提高创造力
            "max_tokens": 1000,
            "top_p": 0.9
        }

        try:
            print(f"[AI] 正在生成对战解说...")
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()

            result = response.json()
            content = result['choices'][0]['message']['content'].strip()

            # 清理可能的 Markdown 格式
            content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
            content = re.sub(r'[#*_`]', '', content)

            print(f"[AI] 解说生成成功，长度: {len(content)} 字")
            return content

        except requests.exceptions.Timeout:
            print("[AI] 请求超时")
            raise Exception("AI 响应超时")
        except requests.exceptions.RequestException as e:
            print(f"[AI] 网络请求失败: {e}")
            raise Exception(f"网络错误: {str(e)}")
        except KeyError:
            print("[AI] API 返回格式错误")
            raise Exception("API 返回格式异常")

    def _generate_fallback_commentary(self, p1: dict, p2: dict) -> str:
        """
        AI 不可用时的备用解说生成
        使用规则引擎生成基础解说
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
        repo_diff = abs(p1_gh.get('repos', 0) - p2_gh.get('repos', 0))
        star_diff = abs(p1_gh.get('stars', 0) - p2_gh.get('stars', 0))
        commit_diff = abs(p1_gh.get('commits_weekly', 0) - p2_gh.get('commits_weekly', 0))

        # 生成解说
        intro = f"🎮 各位观众，欢迎来到代码竞技场！红方{p1_name}（{p1_rank}）VS 蓝方{p2_name}（{p2_rank}）！"

        # 数据对比
        if star_diff > 50:
            comparison = f"从 GitHub 数据来看，双方在Star数上差距明显（相差{star_diff}）！"
        elif repo_diff > 20:
            comparison = f"项目数量对比悬殊，一方拥有{repo_diff}个仓库的优势！"
        elif commit_diff > 10:
            comparison = f"活跃度天差地别，周提交数相差{commit_diff}次！"
        else:
            comparison = f"双方实力接近，数据胶着，这将是一场精彩对决！"

        # 胜负分析
        if gap_percent > 50:
            conclusion = f"{leader}展现出碾压级的实力，领先{gap_percent}%！但我们期待{follower}能够奋起直追，创造奇迹！✨"
        elif gap_percent > 20:
            conclusion = f"{leader}暂时领先，但{follower}仍有逆转机会！代码世界，一切皆有可能！🚀"
        else:
            conclusion = f"势均力敌！{leader}仅以微弱优势领先，这场战斗充满悬念！让我们拭目以待！💪"

        return f"{intro}\n\n{comparison}\n\n{conclusion}"


llm_service = LLMAnalysisService()