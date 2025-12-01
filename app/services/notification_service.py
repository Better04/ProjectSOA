import smtplib
from email.mime.text import MIMEText
from app.models import User
from flask import current_app


def send_price_alert(user_id: int, item_title: str, current_price: float, target_price: float):
    # 使用 current_app.config 动态获取配置
    config = current_app.config

    SMTP_SERVER = config.get('SMTP_SERVER')
    SMTP_PORT = config.get('SMTP_PORT')
    SMTP_USER = config.get('SMTP_USER')
    SMTP_PASSWORD = config.get('SMTP_PASSWORD')
    """
    发送价格提醒邮件。

    """
    user = User.query.get(user_id)
    if not user or not user.email:
        print(f"Warning: User ID {user_id} not found or no email configured.")
        return

    recipient = user.email
    subject = f"心愿价格提醒：{item_title} 已降价！"
    body = f"""
    亲爱的 {user.username}:

    您心愿单中的商品 **《{item_title}》** 价格已达到或低于您的期望价格！

    - 您的期望价格: ¥{target_price:.2f}
    - 当前最新价格: ¥{current_price:.2f}

    快去查看吧: [查看链接] (这里应该放商品的原始链接)

    ---
    心愿单聚合器
    """

    # ------------------- 邮件发送核心逻辑 -------------------
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = recipient

    try:
        # 🚨 核心修正：对于端口 465，必须使用 smtplib.SMTP_SSL
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)

        # 移除 server.starttls()，因为 SMTP_SSL 已经处理了 SSL/TLS 握手

        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [recipient], msg.as_string())
        server.quit()
        print(f"✅ 价格提醒邮件已发送给 {user.email}")
    except Exception as e:
        print(f"❌ 邮件发送失败给 {user.email}: {e}")
        # 在实际项目中，这里需要记录日志或使用更健壮的队列服务