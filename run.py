import os
from app import create_app
from app.database import db
from app import models
# 导入 init_scheduler
from app.scheduler import start_scheduler, create_scheduler_tables, init_scheduler
from flask.cli import load_dotenv

# 默认使用开发配置
app = create_app('default')  # <-- app 实例被创建


# ----------------- 数据库初始化（CLI 命令） -----------------
@app.cli.command("init_db")
def init_db_command():
    with app.app_context():
        # 1. 创建应用程序模型表
        db.create_all()
        print('✅ 应用程序模型表创建成功!')

        # 2. 必须先配置调度器，才能创建它的表
        init_scheduler(app)  # <-- 在这里调用 init_scheduler
        create_scheduler_tables(app)

    print('✅ 数据库初始化完成!')


# ---------------------------------------------------------------


if __name__ == '__main__':
    # 🚨 关键修正：在启动前配置调度器
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduler(app)  # <-- 在这里调用 init_scheduler
        start_scheduler()

        # Flask 自带的开发服务器启动
    app.run(host='0.0.0.0', port=5000)