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
# [全局配置] 字体注册 (确保中文显示)
# ---------------------------------------------------------
FONT_FILENAME = "simhei.ttf"
# 定位字体文件路径
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'fonts')
FONT_PATH = os.path.join(FONT_DIR, FONT_FILENAME)

print(f"--- [PDF Init] Font path: {FONT_PATH}")

if os.path.exists(FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont('Helvetica', FONT_PATH))
        pdfmetrics.registerFont(TTFont('Arial', FONT_PATH))
        pdfmetrics.registerFont(TTFont('sans-serif', FONT_PATH))
        addMapping('Helvetica', 0, 0, 'Helvetica')
        addMapping('Helvetica', 1, 0, 'Helvetica')
        addMapping('Helvetica', 0, 1, 'Helvetica')
        addMapping('Helvetica', 1, 1, 'Helvetica')
    except Exception as e:
        print(f"❌ Font registration error: {e}")
else:
    print(f"❌ Font file missing at {FONT_PATH}")


# ---------------------------------------------------------
# [工具函数] 文本处理
# ---------------------------------------------------------
def split_text_by_length(text, limit=65):
    """
    核心修复逻辑：强制切分长文本
    """
    if not text:
        return ""
    text = text.strip()
    chunks = [text[i:i + limit] for i in range(0, len(text), limit)]
    return "<br/>".join(chunks)


def process_markdown_text(text, limit=65):
    """
    Markdown 清洗与格式化
    """
    if not text:
        return ""
    # 移除 MD 符号
    text = text.replace('##', '').replace('###', '').replace('**', '').replace('__', '')

    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        if len(line) > limit:
            processed_lines.append(split_text_by_length(line, limit))
        else:
            processed_lines.append(line)
    return "\n".join(processed_lines)


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

    profile = github_service.fetch_user_profile(username)
    if not profile:
        return jsonify({'message': f'GitHub 用户 {username} 不存在或 API 受限'}), 404

    repos = github_service.fetch_user_repos(username)
    if not repos:
        return jsonify({'message': '该用户没有公开仓库，无法分析'}), 400

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

    ai_result = llm_service.analyze_github_user(username, profile, detailed_repos, simple_repos_data)

    if "error" in ai_result:
        return jsonify({'message': ai_result['error'], 'data': ai_result, 'avatar_url': profile.get('avatar_url')}), 500

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
# 路由：生成专业 PDF 简历 (技术栈空格修复版)
# ---------------------------------------------------------
@ai_bp.route('/resume/<string:username>', methods=['GET'])
def generate_resume_pdf(username):
    display_mode = request.args.get('mode', 'attachment')

    # 稍微放宽字符限制
    LINE_CHAR_LIMIT = 55

    record = GitHubAnalysis.query.filter_by(github_username=username).order_by(GitHubAnalysis.timestamp.desc()).first()
    if not record:
        return jsonify({'message': '未找到分析记录，请先生成报告'}), 404

    data = json.loads(record.analysis_json)

    # ---------------- 数据清洗 ----------------

    # Summary
    raw_summary = data.get('summary', '暂无总结')
    safe_summary_md = process_markdown_text(raw_summary, LINE_CHAR_LIMIT)
    summary_html = markdown.markdown(safe_summary_md)

    # Radar
    radar = data.get('radar_scores', {})
    radar_map = {
        "code_quality": "代码规范",
        "activity": "活跃度",
        "documentation": "文档质量",
        "influence": "影响力",
        "tech_breadth": "技术广度"
    }
    radar_items = []
    for key, label in radar_map.items():
        score = radar.get(key, 60)
        radar_items.append({"name": label, "score": score})

    # Repos
    processed_repos = []
    for repo in data.get('repositories', [])[:6]:
        repo_copy = repo.copy()
        raw_ai_summary = repo_copy.get('ai_summary', '')
        repo_copy['ai_summary_safe'] = split_text_by_length(raw_ai_summary, LINE_CHAR_LIMIT)
        processed_repos.append(repo_copy)

    # 头衔计算
    score = data.get('overall_score', 0)
    if score >= 90:
        level_title = "卓越级开源架构师"
    elif score >= 80:
        level_title = "资深全栈开发者"
    elif score >= 70:
        level_title = "高级开源贡献者"
    else:
        level_title = "新锐开发者"

    # 上下文
    resume_content = {
        'username': username,
        'avatar_url': record.avatar_url,
        'overall_score': score,
        'level_title': level_title,
        'tech_stack': data.get('tech_stack', []),
        'summary_html': summary_html,
        'repos': processed_repos,
        'radar_items': radar_items,
        'date': datetime.now().strftime('%Y/%m/%d'),
        'email': f"{username}@github.com",
    }

    # ---------------- HTML 模板 ----------------

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4 portrait;
                margin: 0;
            }}

            * {{ font-family: 'Helvetica', 'Arial', sans-serif; box-sizing: border-box; }}
            body {{ font-size: 9px; line-height: 1.4; margin: 0; padding: 0; color: #333; }}

            .container-table {{
                width: 100%;
                border-collapse: collapse;
            }}

            /* --- 左侧侧边栏 --- */
            .sidebar {{
                width: 28%;
                background-color: #1a252f;
                color: #ecf0f1;
                vertical-align: top;
                padding: 30px 15px;
            }}

            /* --- 右侧内容区 --- */
            .main-content {{
                width: 72%;
                background-color: #ffffff;
                vertical-align: top;
                padding: 30px 25px;
            }}

            /* --- 左侧元素 --- */
            .avatar-box {{ text-align: center; margin-bottom: 20px; }}
            .avatar-img {{
                width: 85px; height: 85px; 
                border-radius: 50%; 
                border: 3px solid #34495e;
            }}
            .sidebar-name {{ font-size: 18px; font-weight: bold; margin-top: 10px; color: #fff; text-align: center; }}
            .sidebar-title {{ font-size: 10px; color: #95a5a6; text-align: center; margin-bottom: 25px; font-style: italic; }}

            .sidebar-header {{
                font-size: 11px; font-weight: bold; color: #3498db; 
                border-bottom: 1px solid #34495e; padding-bottom: 3px; 
                margin-top: 20px; margin-bottom: 10px; letter-spacing: 1px;
            }}

            .contact-item {{ font-size: 9px; color: #bdc3c7; margin-bottom: 6px; }}

            /* 技术栈标签修复 */
            .tech-tag {{
                display: inline-block; background-color: #2c3e50; color: #ecf0f1;
                padding: 2px 6px; margin: 0 4px 5px 0; border-radius: 3px;
                font-size: 8px; border: 1px solid #3e5871;
            }}

            .skill-item {{ margin-bottom: 8px; }}
            .skill-name {{ font-size: 8px; color: #bdc3c7; margin-bottom: 2px; }}
            .progress-bg {{ width: 100%; background-color: #2c3e50; height: 4px; border-radius: 2px; }}
            .progress-bar {{ height: 4px; background-color: #3498db; border-radius: 2px; }}

            .score-box {{ text-align: center; margin-top: 30px; border: 1px solid #34495e; padding: 10px; border-radius: 6px; }}
            .score-val {{ font-size: 28px; font-weight: bold; color: #f39c12; }}

            /* --- 右侧元素 --- */
            .main-header {{
                border-bottom: 2px solid #2c3e50; padding-bottom: 8px; margin-bottom: 15px;
            }}
            .main-title {{ font-size: 20px; color: #2c3e50; font-weight: bold; }}
            .main-subtitle {{ font-size: 10px; color: #7f8c8d; margin-top: 3px; }}

            .section-title {{
                font-size: 13px; color: #2c3e50; font-weight: bold; 
                margin-top: 15px; margin-bottom: 10px; 
                background-color: #f2f3f4; padding: 4px 8px; border-left: 4px solid #2c3e50;
            }}

            .summary-text {{
                font-size: 9px; color: #444; line-height: 1.5; text-align: justify;
                padding: 0 5px; margin-bottom: 15px;
            }}
            .summary-text p {{ margin: 0 0 5px 0; }}

            .repo-card {{
                background-color: #fbfbfb;
                border: 1px solid #eee;
                border-radius: 4px;
                padding: 8px 10px;
                margin-bottom: 8px;
            }}
            .repo-top {{ width: 100%; margin-bottom: 3px; }}
            .repo-name {{ font-size: 11px; font-weight: bold; color: #2980b9; }}
            .repo-status {{ font-size: 8px; color: #95a5a6; text-align: right; }}
            .repo-desc {{ font-size: 9px; color: #555; line-height: 1.4; }}

            .footer {{
                margin-top: 20px; text-align: center; font-size: 8px; color: #ccc; border-top: 1px solid #f0f0f0; padding-top: 5px;
            }}
        </style>
    </head>
    <body>
        <table class="container-table">
            <tr>
                <td class="sidebar">
                    <div class="avatar-box">
                        <img src="{resume_content['avatar_url']}" class="avatar-img" />
                        <div class="sidebar-name">{resume_content['username']}</div>
                        <div class="sidebar-title">{resume_content['level_title']}</div>
                    </div>

                    <div class="sidebar-header">基本信息 / INFO</div>
                    <div class="contact-item">📅 {resume_content['date']}</div>
                    <div class="contact-item">✉️ {resume_content['email']}</div>
                    <div class="contact-item">📍 Remote / Global</div>

                    <div class="sidebar-header">核心能力 / SKILLS</div>
                    {''.join([f'''
                    <div class="skill-item">
                        <div class="skill-name">{item['name']}</div>
                        <div class="progress-bg">
                            <div class="progress-bar" style="width: {item['score']}%;"></div>
                        </div>
                    </div>
                    ''' for item in resume_content['radar_items']])}

                    <div class="sidebar-header">技术栈 / TECH</div>
                    <div style="line-height: 1.8;">
                        {'  '.join([f'<span class="tech-tag">{t}</span>' for t in resume_content['tech_stack']])}
                    </div>

                    <div class="score-box">
                        <div class="score-val">{resume_content['overall_score']}</div>
                        <div style="font-size:8px; color:#bdc3c7;">综合技术评分</div>
                    </div>
                </td>

                <td class="main-content">
                    <div class="main-header">
                        <div class="main-title">{resume_content['username']}</div>
                        <div class="main-subtitle">职业目标：全栈开发工程师 / 开源贡献者</div>
                    </div>

                    <div class="section-title">个人总结 / SUMMARY</div>
                    <div class="summary-text">
                        {resume_content['summary_html']}
                    </div>

                    <div class="section-title">开源项目经历 / PROJECTS</div>
                    {''.join([f'''
                    <div class="repo-card">
                        <table class="repo-top">
                            <tr>
                                <td class="repo-name">{r.get('name')}</td>
                                <td class="repo-status">{r.get('status', 'Active')} · ⭐ {r.get('stars', 0) if r.get('stars') else '0'}</td>
                            </tr>
                        </table>
                        <div class="repo-desc">{r.get('ai_summary_safe')}</div>
                    </div>
                    ''' for r in resume_content['repos']])}

                    <div class="section-title">成就亮点 / HIGHLIGHTS</div>
                    <div style="font-size: 9px; color: #555; line-height: 1.6; padding: 5px;">
                        • <strong>代码影响力：</strong> 在 GitHub 社区保持活跃，项目 Star 总数体现了技术受认可度。<br/>
                        • <strong>技术栈覆盖：</strong> 熟练掌握 {len(resume_content['tech_stack'])} 种以上前沿技术，具备独立开发能力。<br/>
                        • <strong>持续交付：</strong> 仓库提交记录显示了稳定的编码习惯和良好的项目维护意识。
                    </div>

                    <div class="footer">
                        Generated by DevLife Aggregator · Professional Career Analysis
                    </div>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    # 生成 PDF
    pdf_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_template, dest=pdf_file, encoding='utf-8')

    if pisa_status.err:
        return jsonify({'message': 'PDF 生成失败'}), 500

    pdf_file.seek(0)
    response = make_response(pdf_file.read())
    response.headers['Content-Type'] = 'application/pdf'

    filename = f"{username}_Professional_Resume.pdf"
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