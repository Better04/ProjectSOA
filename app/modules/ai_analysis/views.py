from flask import jsonify, request, send_file, make_response, current_app
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
# [核心修复] 字体全局注册 (移花接木：覆盖默认字体)
# ---------------------------------------------------------
# 1. 构造字体文件的绝对路径
FONT_FILENAME = "simhei.ttf"
# 假设 views.py 位于 app/modules/ai_analysis/
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'fonts')
FONT_PATH = os.path.join(FONT_DIR, FONT_FILENAME)

print("\n" + "=" * 50)
print("           [START FONT REGISTRATION]           ")
print("=" * 50)

if os.path.exists(FONT_PATH):
    try:
        # 【关键步骤】
        # xhtml2pdf 默认使用 'Helvetica' 作为 sans-serif 字体。
        # 我们将 SimHei 注册为 'Helvetica'，这样 xhtml2pdf 就会自动使用中文字体，
        # 而不需要在 CSS 中使用 @font-face (从而避开 Windows 路径权限 BUG)。

        # 1. 覆盖标准字体 'Helvetica'
        pdfmetrics.registerFont(TTFont('Helvetica', FONT_PATH))

        # 2. 覆盖其他常用别名，防止回退
        pdfmetrics.registerFont(TTFont('Arial', FONT_PATH))
        pdfmetrics.registerFont(TTFont('sans-serif', FONT_PATH))

        # 3. 注册映射：告诉 ReportLab，Helvetica 的粗体、斜体其实都用这个文件
        # (因为 SimHei 通常只有一个文件，没有专门的粗体文件)
        addMapping('Helvetica', 0, 0, 'Helvetica')  # Normal
        addMapping('Helvetica', 1, 0, 'Helvetica')  # Bold
        addMapping('Helvetica', 0, 1, 'Helvetica')  # Italic
        addMapping('Helvetica', 1, 1, 'Helvetica')  # Bold & Italic

        print(f"--- [GLOBAL FONT] Successfully hijacked 'Helvetica' using {FONT_FILENAME}.")
    except Exception as e:
        print(f"❌ [GLOBAL FONT ERROR] Failed to register font: {e}")
else:
    print(f"❌ [GLOBAL FONT ERROR] Font file not found at: {FONT_PATH}")
print("=" * 50 + "\n")


# ---------------------------------------------------------
# 核心路由 1：执行 AI 分析 (保持不变)
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
    for r in sorted_repos: simple_repos_data.append(
        {'name': r.get('name'), 'description': r.get('description'), 'updated_at': r.get('updated_at'),
         'language': r.get('language'), 'stars': r.get('stars')})
    top_repos = sorted_repos[:5]
    detailed_repos = []
    print(f"--- [Backend] 正在抓取 {username} 的 Top {len(top_repos)} 仓库详情 ---")
    for repo in top_repos:
        repo_name = repo['name']
        langs = github_service.fetch_repo_languages(username, repo_name)
        readme_content = github_service.fetch_repo_readme(username, repo_name)
        if readme_content and len(readme_content) > 3000: readme_content = readme_content[:3000] + "...(truncated)"
        detailed_repos.append({
            'name': repo_name, 'description': repo['description'], 'stars': repo['stars'],
            'updated_at': repo['updated_at'], 'language': repo['language'], 'languages_stats': langs,
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
# 核心路由 2：生成 PDF 简历 (中文版)
# ---------------------------------------------------------
@ai_bp.route('/resume/<string:username>', methods=['GET'])
def generate_resume_pdf(username):
    # 0. 获取 URL 参数 mode
    display_mode = request.args.get('mode', 'attachment')

    # 1. 获取数据
    record = GitHubAnalysis.query.filter_by(github_username=username).order_by(GitHubAnalysis.timestamp.desc()).first()
    if not record:
        return jsonify({'message': '未找到分析记录，请先生成报告'}), 404

    data = json.loads(record.analysis_json)

    # 2. 准备渲染数据
    resume_content = {
        'username': username,
        'avatar_url': record.avatar_url,
        'score': data.get('overall_score', 0),
        'tech_stack': data.get('tech_stack', []),
        'summary_html': markdown.markdown(data.get('summary', '暂无总结')),
        'repos': data.get('repositories', [])[:5]
    }

    # ---------------------------------------------------------
    # [字体配置]
    # ---------------------------------------------------------
    # 因为我们已经把 SimHei 注册为了 'Helvetica'，所以这里不需要任何 CSS @font-face。
    # xhtml2pdf 默认使用 Helvetica，所以它会自动用到我们的 SimHei。
    font_face_css = ""

    # 我们依然可以在 CSS 中指定 Helvetica 以防万一
    font_family_val = "'Helvetica', 'Arial', sans-serif"

    # 3. 构建 HTML 模板
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            {font_face_css}

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

            /* 强制所有元素使用 Helvetica (实际上是 SimHei) */
            * {{
                font-family: {font_family_val};
            }}

            body {{
                font-family: {font_family_val}; 
                line-height: 1.6;
                color: #333;
            }}

            .header {{
                text-align: center;
                border-bottom: 2px solid #1976D2;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .header h1 {{ font-size: 24px; color: #1976D2; margin: 0; font-weight: bold; }}
            .header p {{ color: #666; margin: 5px 0; }}

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
                padding: 2px 8px;
                margin: 2px;
                border-radius: 4px;
                font-size: 12px;
            }}

            .repo-item {{
                margin-bottom: 15px;
                border-bottom: 1px dashed #eee;
                padding-bottom: 10px;
            }}
            .repo-name {{ font-weight: bold; font-size: 14px; }}
            .repo-desc {{ font-size: 12px; color: #555; }}
            .score-badge {{
                font-size: 20px; font-weight: bold; color: #e65100;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{resume_content['username']} 的技术分析报告</h1>
            <p>GitHub 深度评估简历 · 由 AI 生成</p>
        </div>

        <div>
            <span class="section-title">综合评分</span>
            <span class="score-badge">{resume_content['score']} 分</span>
        </div>

        <div style="margin-top: 15px;">
            <div class="section-title">技术栈指纹</div>
            <div>
                {''.join([f'<span class="tech-tag">{t}</span>' for t in resume_content['tech_stack']])}
            </div>
        </div>

        <div>
            <div class="section-title">深度能力评估</div>
            <div style="font-size: 12px;">
                {resume_content['summary_html']}
            </div>
        </div>

        <div>
            <div class="section-title">精选开源贡献</div>
            {''.join([f'''
            <div class="repo-item">
                <div class="repo-name">{r.get('name')} <span style="font-size:10px;color:#999">({r.get('status')})</span></div>
                <div class="repo-desc">{r.get('ai_summary')}</div>
            </div>
            ''' for r in resume_content['repos']])}
        </div>

        <div style="text-align: center; color: green; font-size: 10px; margin-top: 20px;">
           [DEBUG] 字体测试：你好世界 (Hello World)
        </div>

        <div id="footerContent" style="text-align: center; color: #999; font-size: 10px;">
            此报告由 DevLife Aggregator 生成
        </div>
    </body>
    </html>
    """

    # 4. 生成 PDF
    pdf_file = BytesIO()

    # 不传入 link_callback，也无需 font_config
    pisa_status = pisa.CreatePDF(
        html_template,
        dest=pdf_file,
        encoding='utf-8'
    )

    if pisa_status.err:
        return jsonify({'message': 'PDF 生成失败'}), 500

    pdf_file.seek(0)
    response = make_response(pdf_file.read())
    response.headers['Content-Type'] = 'application/pdf'

    filename = f"{username}_AI_Resume.pdf"
    content_disposition = f'{display_mode}; filename="{filename}"'

    response.headers['Content-Disposition'] = content_disposition
    return response