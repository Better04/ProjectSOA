from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from sqlalchemy import create_engine
from flask import Flask

# Global scheduler instance
scheduler = BackgroundScheduler()

# 全局存储 JobStore 实例，用于在 CLI 命令中手动创建表
_job_store_instance = None


def init_scheduler(app: Flask):
    """
    初始化并配置 APScheduler。
    """
    global _job_store_instance

    # ----------------------------------------------------
    # 1. 配置 JobStore
    # ----------------------------------------------------
    jobstores = {
        # 使用数据库连接字符串作为 JobStore，将任务信息存入 MySQL
        'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
    }
    _job_store_instance = jobstores['default']

    # ----------------------------------------------------
    # 2. 配置 Executor
    # ----------------------------------------------------
    executors = {
        'default': ThreadPoolExecutor(20)
    }

    scheduler.configure(jobstores=jobstores, executors=executors, timezone='Asia/Shanghai')

    # ----------------------------------------------------
    # 3. 注册核心任务 (关键修正部分)
    # ----------------------------------------------------

    from app.services.monitoring_service import run_price_monitoring

    config_name = 'default'

    scheduler.add_job(
        func=run_price_monitoring,
        trigger='interval',
        minutes=1,
        id='global_price_monitor',
        max_instances=1,
        kwargs={'config_name': config_name},

        # 🚨 核心修正：如果任务 ID 存在，则直接替换它，解决冲突问题
        replace_existing=True
    )


def create_scheduler_tables(app: Flask):
    """
    手动创建 APScheduler 自身的表 (apscheduler_jobs, etc.)。
    """
    global _job_store_instance

    if not _job_store_instance:
        init_scheduler(app)

    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])

    try:
        # 手动调用 JobStore 的 start() 方法创建表
        conn = engine.connect()
        _job_store_instance.start(scheduler, conn)
        _job_store_instance.shutdown()
        conn.close()
        print("✅ APScheduler 表创建成功!")

    except Exception as e:
        print(f"❌ 警告：尝试创建 APScheduler 表时遇到错误: {e}")


def start_scheduler():
    """启动调度器"""
    try:
        scheduler.start()
        print("✅ APScheduler 启动成功，价格监控任务已安排！")
    except Exception as e:
        print(f"❌ APScheduler 启动失败: {e}")