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
        # 将 SimHei 注册为 Helvetica (xhtml2pdf 的默认字体)
        # 这样无需在每个 CSS 中指定字体，自动生效
        pdfmetrics.registerFont(TTFont('Helvetica', FONT_PATH))
        pdfmetrics.registerFont(TTFont('Arial', FONT_PATH))
        pdfmetrics.registerFont(TTFont('sans-serif', FONT_PATH))

        # 映射粗体/斜体到同一个字体文件，防止报错
        addMapping('Helvetica', 0, 0, 'Helvetica')
        addMapping('Helvetica', 1, 0, 'Helvetica')
        addMapping('Helvetica', 0, 1, 'Helvetica')
        addMapping('Helvetica', 1, 1, 'Helvetica')
    except Exception as e:
        print(f"❌ Font registration error: {e}")
else:
    print(f"❌ Font file missing at {FONT_PATH}")


# ---------------------------------------------------------
# [核心修复] 强制换行工具函数
# ---------------------------------------------------------
def split_text_by_length(text, limit=55):
    """
    核心修复逻辑：
    将长文本按指定长度 limit (默认55字符) 强制切分，
    并插入 <br/> 标签实现换行。
    这比依赖 CSS word-break 在 xhtml2pdf 中更可靠。
    """
    if not text:
        return ""

    # 移除可能存在的非法字符或多余空白，避免干扰
    text = text.strip()

    # 简单切片法：每 limit 个字符切一刀
    chunks = [text[i:i + limit] for i in range(0, len(text), limit)]
    return "<br/>".join(chunks)


def process_markdown_text(text, limit=55):
    """
    专门处理 Markdown 文本。
    为了防止把 Markdown 的标题标记（如 # 标题）切坏，
    我们按行处理，只对长行进行切分。
    """
    if not text:
        return ""

    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        if len(line) > limit:
            # 如果这一行超过了限制，就进行强制切分
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
# 路由：生成 PDF 简历 (物理切分 + 技术栈空格修复版)
# ---------------------------------------------------------
@ai_bp.route('/resume/<string:username>', methods=['GET'])
def generate_resume_pdf(username):
    display_mode = request.args.get('mode', 'attachment')

    # 字符限制配置
    LINE_CHAR_LIMIT = 55

    record = GitHubAnalysis.query.filter_by(github_username=username).order_by(GitHubAnalysis.timestamp.desc()).first()
    if not record:
        return jsonify({'message': '未找到分析记录，请先生成报告'}), 404

    data = json.loads(record.analysis_json)

    # [修复步骤 1] 处理 Summary (深度评估)
    raw_summary = data.get('summary', '暂无总结')
    safe_summary_md = process_markdown_text(raw_summary, LINE_CHAR_LIMIT)
    summary_html = markdown.markdown(safe_summary_md)

    # [修复步骤 2] 处理 Repos (项目经历)
    processed_repos = []
    for repo in data.get('repositories', [])[:5]:
        repo_copy = repo.copy()
        raw_ai_summary = repo_copy.get('ai_summary', '')
        repo_copy['ai_summary_safe'] = split_text_by_length(raw_ai_summary, LINE_CHAR_LIMIT)
        processed_repos.append(repo_copy)

    # 3. 准备渲染数据
    resume_content = {
        'username': username,
        'avatar_url': record.avatar_url,
        'score': data.get('overall_score', 0),
        'tech_stack': data.get('tech_stack', []),
        'summary_html': summary_html,
        'repos': processed_repos
    }

    # 4. 构建 HTML 模板
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 2cm;
                @frame footer_frame {{
                    -pdf-frame-content: footerContent;
                    bottom: 1cm;
                    margin-left: 2cm;
                    margin-right: 2cm;
                    height: 1cm;
                }}
            }}

            /* 字体设置 */
            * {{ font-family: 'Helvetica', 'Arial', sans-serif; }}

            body {{
                font-family: 'Helvetica', 'Arial', sans-serif; 
                line-height: 1.5;
                color: #333;
                font-size: 12px;
            }}

            .header {{
                text-align: center;
                border-bottom: 2px solid #1976D2;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .header h1 {{ font-size: 24px; color: #1976D2; margin: 0; }}

            .section-title {{
                font-size: 16px;
                font-weight: bold;
                color: #1976D2;
                border-left: 4px solid #1976D2;
                padding-left: 10px;
                margin-top: 20px;
                margin-bottom: 10px;
                background-color: #f0f7ff;
            }}

            .tech-tag {{
                display: inline-block;
                background-color: #e3f2fd;
                color: #1565c0;
                padding: 4px 8px; /* 增加一点内边距 */
                margin: 2px 5px 2px 0; /* 右侧增加 5px 边距 */
                border-radius: 4px;
                font-size: 10px;
            }}

            .content-box {{
                width: 100%;
                margin-bottom: 10px;
            }}

            .repo-item {{
                margin-bottom: 15px;
                border-bottom: 1px dashed #eee;
                padding-bottom: 10px;
            }}

            .repo-name {{ 
                font-weight: bold; 
                font-size: 14px; 
                color: #000;
            }}

            .repo-desc {{ 
                font-size: 12px; 
                color: #555;
                margin-top: 5px;
            }}

            .score-badge {{ font-size: 20px; font-weight: bold; color: #e65100; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{resume_content['username']} 技术分析报告</h1>
            <p>GitHub 深度评估 · AI 生成</p>
        </div>

        <div>
            <div class="section-title">综合评分</div>
            <div class="score-badge">{resume_content['score']} / 100</div>
        </div>

        <div>
            <div class="section-title">技术栈</div>
            <div class="content-box">
                {''.join([f'<span class="tech-tag">{t}</span>&nbsp;&nbsp;' for t in resume_content['tech_stack']])}
            </div>
        </div>

        <div>
            <div class="section-title">深度能力评估</div>
            <div class="content-box">
                {resume_content['summary_html']}
            </div>
        </div>

        <div>
            <div class="section-title">精选开源贡献</div>
            {''.join([f'''
            <div class="repo-item">
                <div class="repo-name">{r.get('name')} 
                    <span style="font-size:10px;color:#999;font-weight:normal">({r.get('status', 'Active')})</span>
                </div>
                <div class="repo-desc">{r.get('ai_summary_safe')}</div>
            </div>
            ''' for r in resume_content['repos']])}
        </div>

        <div id="footerContent" style="text-align: center; color: #999; font-size: 10px;">
            此报告由 DevLife Aggregator 生成 · {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </body>
    </html>
    """

    # 4. 生成 PDF
    pdf_file = BytesIO()
    pisa_status = pisa.CreatePDF(html_template, dest=pdf_file, encoding='utf-8')

    if pisa_status.err:
        return jsonify({'message': 'PDF 生成失败'}), 500

    pdf_file.seek(0)
    response = make_response(pdf_file.read())
    response.headers['Content-Type'] = 'application/pdf'

    filename = f"{username}_Resume.pdf"
    response.headers['Content-Disposition'] = f'{display_mode}; filename="{filename}"'

    return response