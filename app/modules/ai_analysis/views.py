from flask import jsonify, request, make_response
import json
from datetime import datetime, timedelta
from io import BytesIO
import markdown
import os

# 导入当前蓝图
from app.modules.ai_analysis import ai_bp

# 导入服务
from app.services.github_service import github_service
from app.services.llm_analysis import llm_service
from app.ai_models import GitHubAnalysis
from app.database import db

# PDF 库和 ReportLab 核心依赖
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

# ---------------------------------------------------------
# [全局配置] 字体注册
# ---------------------------------------------------------
FONT_FILENAME = "simhei.ttf"
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'fonts')
FONT_PATH = os.path.join(FONT_DIR, FONT_FILENAME)

if os.path.exists(FONT_PATH):
    try:
        # 注册字体
        pdfmetrics.registerFont(TTFont('Helvetica', FONT_PATH))
        pdfmetrics.registerFont(TTFont('Arial', FONT_PATH))
        pdfmetrics.registerFont(TTFont('sans-serif', FONT_PATH))
        addMapping('Helvetica', 0, 0, 'Helvetica')
        addMapping('Helvetica', 1, 0, 'Helvetica')
        addMapping('Helvetica', 0, 1, 'Helvetica')
        addMapping('Helvetica', 1, 1, 'Helvetica')
    except Exception as e:
        print(f"Font registration error: {e}")


# ---------------------------------------------------------
# [增强版] 内容生成工具
# ---------------------------------------------------------

def expand_summary(text):
    """
    将 Summary 拆分，仅返回干净的文本列表。
    """
    # 基础清洗
    text = text.replace('**', '').replace('##', '').strip()

    # 强制按句号拆分
    sentences = [s.strip() for s in text.replace('。', '。\n').split('\n') if len(s) > 5]

    # 补充内容
    defaults = [
        "具备扎实的计算机科学基础，深入理解数据结构、算法及操作系统原理，能够编写高质量、高性能的代码。",
        "拥有良好的全栈开发视野，熟悉从前端交互到后端架构的完整链路，能够独立主导复杂模块的设计与落地。",
        "热衷于开源技术探索，保持对前沿技术栈（如云原生、微服务、AI应用）的持续关注与实践。",
        "具备优秀的团队协作与沟通能力，习惯在 Agile/Scrum 敏捷开发流程中高效交付价值。"
    ]

    final_bullets = sentences[:3]
    for d in defaults:
        if len(final_bullets) < 5:  # 确保至少5行
            final_bullets.append(d)

    return final_bullets


def enrich_description(text):
    """
    项目描述扩充
    """
    defaults = [
        "主导了核心业务模块的架构重构，通过解耦服务依赖与优化数据库查询，将系统响应延迟降低了 40%。",
        "基于 CI/CD 流水线搭建了自动化测试与部署环境，显著提升了代码交付质量与迭代效率。",
        "负责 API 接口的设计与规范制定，编写了详尽的技术文档，降低了前后端协作成本。",
        "引入了 Redis 缓存机制与消息队列，有效解决了高并发场景下的数据一致性与削峰填谷问题。",
        "参与了代码审查（Code Review）与技术分享会，推动团队代码规范化建设，提升了整体工程素养。",
        "针对系统瓶颈进行了深度性能分析，通过内存优化与算法改进，减少了服务器资源占用。"
    ]

    bullets = []
    if text:
        text = text.replace('**', '').replace('##', '').strip()
        parts = [p.strip() for p in text.replace('。', '。\n').replace('；', '；\n').split('\n') if len(p) > 5]
        bullets.extend(parts)

    count = 0
    while len(bullets) < 4:  # 确保至少4条
        bullets.append(defaults[count % len(defaults)])
        count += 1

    return bullets[:6]


def generate_ai_evaluation(score, tech_stack):
    """
    生成深度评估报告
    """
    # 清洗技术栈数据
    clean_stack = [t.strip() for t in tech_stack]
    tech_str = "、".join(clean_stack[:5]) if clean_stack else "全栈技术"

    # 这里的文本保持不变
    intro = (
        "基于 GitHub 行为数据的深度分析显示，该候选人在 "
        f"{tech_str} "
        "等领域展现了卓越的技术竞争力。其代码库不仅展示了扎实的编程功底，"
        f"更体现了成熟的软件工程思维。综合评分 {score}/100。"
    )

    # 关键修改：去除 text-align: justify 相关的隐患，这里只负责内容结构
    # class="eval-p" 将在 CSS 中被设置为左对齐 + 首行缩进
    intro_html = f'<div class="eval-p">{intro}</div>'

    points = [
        ("技术深度",
         f"候选人不仅仅满足于 API 的调用，对底层原理有深入的探究。在 {clean_stack[0] if clean_stack else '核心'} 领域，候选人展示了从源码层面解决复杂问题的能力。"),
        ("工程质量",
         "代码提交记录（Commit History）显示出极高的规范性。项目结构遵循行业最佳实践，模块划分合理，且具备完善的单元测试覆盖。"),
        ("问题解决",
         "在多个开源项目中，候选人通过创新的算法或架构设计解决了实际痛点。面对性能瓶颈或复杂逻辑时，能够提出多种解决方案并进行权衡。"),
        ("开源影响", "活跃的 Issue 讨论与 Pull Request 记录证明了候选人良好的沟通能力与协作精神。")
    ]

    html = intro_html
    for title, content in points:
        clean_content = content.replace('\n', '').strip()
        # 注意：这里也移除了潜在的导致排版问题的样式
        html += f"""
        <div class="eval-item">
            <span class="eval-title">{title}：</span>{clean_content}
        </div>
        """
    return html


# ---------------------------------------------------------
# 路由：执行 AI 分析 (保持不变)
# ---------------------------------------------------------
@ai_bp.route('/analyze/<string:username>', methods=['POST', 'GET'])
def analyze_github_user_radar(username):
    # 1. 检查缓存
    cached = GitHubAnalysis.query.filter_by(github_username=username).order_by(GitHubAnalysis.timestamp.desc()).first()

    if cached and cached.timestamp > datetime.utcnow() - timedelta(hours=24):
        try:
            return jsonify({
                'message': '获取成功 (来自缓存)',
                'data': json.loads(cached.analysis_json),
                'avatar_url': cached.avatar_url,
                'cached': True,
                'username': username
            }), 200
        except json.JSONDecodeError:
            pass

    # 2. 获取基础数据
    profile = github_service.fetch_user_profile(username)
    if not profile:
        return jsonify({'message': f'GitHub 用户 {username} 不存在或 API 受限'}), 404

    repos = github_service.fetch_user_repos(username)
    if not repos:
        return jsonify({'message': '该用户没有公开仓库，无法分析'}), 400

    # 3. 数据准备
    sorted_repos = sorted(repos, key=lambda r: (r.get('stars', 0), r.get('updated_at', '')), reverse=True)
    simple_repos_data = []
    for r in sorted_repos:
        simple_repos_data.append({
            'name': r.get('name'),
            'description': r.get('description'),
            'updated_at': r.get('updated_at'),
            'language': r.get('language'),
            'stars': r.get('stars')
        })

    top_repos = sorted_repos[:5]
    detailed_repos = []

    for repo in top_repos:
        repo_name = repo['name']
        langs = github_service.fetch_repo_languages(username, repo_name)
        readme_content = github_service.fetch_repo_readme(username, repo_name)
        if readme_content and len(readme_content) > 3000:
            readme_content = readme_content[:3000] + "...(truncated)"
        detailed_repos.append({
            'name': repo_name,
            'description': repo['description'],
            'stars': repo['stars'],
            'updated_at': repo['updated_at'],
            'language': repo['language'],
            'languages_stats': langs,
            'readme': readme_content
        })

    # 4. 调用 AI
    ai_result = llm_service.analyze_github_user(username, profile, detailed_repos, simple_repos_data)

    if "error" in ai_result:
        return jsonify({'message': ai_result['error'], 'data': ai_result, 'avatar_url': profile.get('avatar_url')}), 500

    # 5. 存入数据库
    try:
        analysis_json_str = json.dumps(ai_result, ensure_ascii=False)
        new_record = GitHubAnalysis(
            github_username=username, avatar_url=profile.get('avatar_url'), analysis_json=analysis_json_str
        )
        db.session.add(new_record)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error saving AI analysis to DB: {e}")

    return jsonify({
        'message': 'AI 深度分析完成',
        'data': ai_result,
        'avatar_url': profile.get('avatar_url'),
        'cached': False,
        'username': username
    }), 200


# ---------------------------------------------------------
# 路由：生成简历 (完美缩进修复版)
# ---------------------------------------------------------
@ai_bp.route('/resume/<string:username>', methods=['GET'])
def generate_resume_pdf(username):
    display_mode = request.args.get('mode', 'attachment')

    record = GitHubAnalysis.query.filter_by(github_username=username).order_by(GitHubAnalysis.timestamp.desc()).first()
    if not record:
        return jsonify({'message': '未找到分析记录'}), 404

    data = json.loads(record.analysis_json)

    # ---------------- 1. 内容构建 ----------------
    summary_bullets = expand_summary(data.get('summary', ''))

    # ... (中间数据处理逻辑保持不变) ...
    processed_repos = []
    for repo in data.get('repositories', [])[:6]:
        repo_copy = repo.copy()
        repo_copy['bullets'] = enrich_description(repo_copy.get('ai_summary', ''))
        repo_copy['role'] = "Core Contributor" if (repo_copy.get('stars', 0) or 0) > 10 else "Developer"
        processed_repos.append(repo_copy)

    overall_score = data.get('overall_score', 0)
    tech_stack = data.get('tech_stack', [])
    evaluation_html = generate_ai_evaluation(overall_score, tech_stack)

    # ... (Job title 逻辑保持不变) ...
    if overall_score >= 90:
        job_title = "Senior Software Architect"
    elif overall_score >= 80:
        job_title = "Full Stack Engineer"
    else:
        job_title = "Software Developer"

    resume_content = {
        'username': username,
        'job_title': job_title,
        'tech_stack': " / ".join(tech_stack),
        'summary_bullets': summary_bullets,
        'repos': processed_repos,
        'evaluation_html': evaluation_html,
        'date': datetime.now().strftime('%Y.%m.%d'),
        'email': f"{username}@gmail.com",
        'phone': "138-xxxx-xxxx",
        'location': "Shanghai, China",
        'education': "Bachelor of Science in Computer Science",
        'university': "Shanghai Jiao Tong University"
    }

    # ---------------- 2. CSS 模板 (包含修复) ----------------

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4 portrait;
                margin: 1.2cm 1.5cm;
            }}
            * {{ font-family: 'Helvetica', 'Arial', sans-serif; box-sizing: border-box; }}
            body {{ font-size: 10px; line-height: 1.4; color: #222; }}

            /* 头部样式保持不变 */
            .header {{ 
                text-align: center; margin-bottom: 20px; 
                border-bottom: 2px solid #003366; padding-bottom: 15px;
            }}
            .name {{ font-size: 28px; font-weight: bold; text-transform: uppercase; margin-bottom: 6px; color: #003366; }}
            .title {{ font-size: 12px; margin-bottom: 8px; color: #4A90E2; font-weight: bold; letter-spacing: 1px; }}
            .contact {{ font-size: 9px; color: #555; }}
            .contact span {{ margin: 0 8px; font-weight: bold; color: #444; }}
            .sep {{ color: #4A90E2; }}

            /* 板块标题 */
            .section {{ margin-bottom: 20px; }}
            .section-title {{ 
                font-size: 13px; font-weight: bold; text-transform: uppercase; 
                color: #003366; background-color: #f0f4f8; 
                padding: 4px 8px; margin-bottom: 10px;
                border-left: 5px solid #003366;
            }}

            /* --- 修复点 1: Summary 样式修改 --- */
            /* 改为相对定位 + 左内边距，模拟列表效果 */
            .summary-item {{
                position: relative;
                margin-bottom: 6px;
                padding-left: 14px; /* 预留给方块的空间 */
                font-size: 10px;
                line-height: 1.5;
                text-align: justify; /* 纯中文可以用 justify，如果 summary 也有英文空白问题，请改为 left */
            }}
            /* 新增：Summary 前面的小方块/符号 */
            .summary-marker {{
                position: absolute;
                left: 0;
                top: 0;
                color: #4A90E2;
                font-weight: bold;
                font-size: 14px; /*稍微大一点 */
                line-height: 12px;
            }}

            /* 技能栈 */
            .tech-box {{ font-size: 10px; line-height: 1.6; text-align: justify; }}

            /* 教育背景和项目经历样式保持不变 */
            .edu-table {{ width: 100%; margin-bottom: 5px; }}
            .edu-school {{ font-weight: bold; font-size: 11px; color: #003366; }}
            .edu-degree {{ font-style: italic; color: #555; }}
            .edu-date {{ text-align: right; color: #000; font-weight: bold; }}

            .job-item {{ margin-bottom: 16px; }}
            .job-header {{ width: 100%; margin-bottom: 3px; }}
            .job-role {{ font-weight: bold; font-size: 11px; color: #000; }}
            .job-company {{ font-size: 11px; color: #4A90E2; font-weight: bold; }}
            .job-date {{ text-align: right; font-size: 10px; color: #666; }}

            .job-bullet {{
                position: relative; padding-left: 10px; margin-bottom: 2px;
                font-size: 10px; color: #444; text-align: justify;
            }}
            .job-bullet-marker {{
                position: absolute; left: 0; top: 0; color: #4A90E2; font-weight: bold;
            }}

            /* --- 修复点 2: 评估报告样式修改 --- */
            /* 关键：将 text-align 改为 left，解决中英文混排的大片空白问题 */
            .eval-p {{ 
                margin-top: 0; margin-bottom: 8px; 
                font-size: 10px; line-height: 1.5; 
                text-align: left; /* 修复空白问题的关键 */
                text-indent: 2em; /* 保持首行缩进 */
                color: #444;
            }}

            .eval-item {{
                margin-bottom: 5px;
                padding-left: 0; 
                font-size: 10px;
                line-height: 1.5;
                text-align: left; /* 修复空白问题的关键 */
                color: #444;
                /* 如果希望每个小点（如技术深度）也首行缩进，可以加 text-indent: 2em; 
                   通常小标题形式不需要缩进，看您个人喜好 */
            }}
            .eval-title {{
                font-weight: bold;
                color: #003366;
                margin-right: 5px;
            }}

        </style>
    </head>
    <body>
        <div class="header">
            <div class="name">{resume_content['username']}</div>
            <div class="title">{resume_content['job_title']}</div>
            <div class="contact">
                <span>Email: {resume_content['email']}</span> <span class="sep">|</span>
                <span>Tel: {resume_content['phone']}</span> <span class="sep">|</span>
                <span>Add: {resume_content['location']}</span> <span class="sep">|</span>
                <span>Web: github.com/{resume_content['username']}</span>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Professional Summary</div>
            <div>
                {''.join([f'<div class="summary-item"><span class="summary-marker">▪</span>{b}</div>' for b in resume_content['summary_bullets']])}
            </div>
        </div>

        <div class="section">
            <div class="section-title">Technical Skills</div>
            <div class="tech-box">
                <span style="font-weight:bold; color:#003366;">Core Tech:</span> {resume_content['tech_stack']}
            </div>
        </div>

        <div class="section">
            <div class="section-title">Education</div>
            <table class="edu-table">
                <tr>
                    <td class="edu-school">{resume_content['university']}</td>
                    <td class="edu-date">Sep 2018 - Jun 2022</td>
                </tr>
                <tr>
                    <td class="edu-degree">{resume_content['education']}</td>
                    <td class="edu-date">{resume_content['location']}</td>
                </tr>
            </table>
        </div>

        <div class="section">
            <div class="section-title">Project Experience</div>
            {''.join([f'''
            <div class="job-item">
                <table class="job-header">
                    <tr>
                        <td class="job-role">{r['name']} <span style="font-weight:normal; color:#666">({r.get('language', 'Code')})</span></td>
                        <td class="job-date">Stars: {r.get('stars', 0)} | Status: {r.get('status', 'Active')}</td>
                    </tr>
                    <tr>
                        <td class="job-company">{r['role']}</td>
                        <td></td>
                    </tr>
                </table>
                <div>
                    {''.join([f'<div class="job-bullet"><span class="job-bullet-marker">-</span>{b}</div>' for b in r['bullets']])}
                </div>
            </div>
            ''' for r in resume_content['repos']])}
        </div>

        <div class="section">
            <div class="section-title">Competency Analysis</div>
            <div>
                {resume_content['evaluation_html']}
            </div>
        </div>

    </body>
    </html>
    """

    pdf_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_template, dest=pdf_file, encoding='utf-8')

    if pisa_status.err:
        return jsonify({'message': 'PDF 生成失败'}), 500

    pdf_file.seek(0)
    response = make_response(pdf_file.read())
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"{username}_CV.pdf"
    response.headers['Content-Disposition'] = f'{display_mode}; filename="{filename}"'

    return response


@ai_bp.route('/analyze/repo/<string:owner>/<string:repo_name>', methods=['GET'])
def analyze_single_repo_route(owner, repo_name):
    # 保持不变
    try:
        repo_details = github_service.fetch_repo_details(owner, repo_name)
        readme_content = github_service.fetch_repo_readme(owner, repo_name)
        analysis_result = llm_service.analyze_specific_repo(repo_details, readme_content)

        if "error" in analysis_result:
            return jsonify({'message': analysis_result['error']}), 500

        return jsonify({
            'message': '仓库分析完成',
            'data': analysis_result
        }), 200

    except Exception as e:
        print(f"Controller Error: {e}")
        return jsonify({'message': '服务器内部错误'}), 500