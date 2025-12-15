import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.models import User
from flask import current_app


def send_price_alert(user_id: int, item_title: str, current_price: float, target_price: float, image_url: str = None,
                     item_url: str = None):
    """
    发送价格提醒邮件 (修复图片防盗链问题)
    """
    config = current_app.config
    SMTP_SERVER = config.get('SMTP_SERVER')
    SMTP_PORT = config.get('SMTP_PORT')
    SMTP_USER = config.get('SMTP_USER')
    SMTP_PASSWORD = config.get('SMTP_PASSWORD')

    user = User.query.get(user_id)
    if not user or not user.email:
        return

    recipient = user.email
    subject = f"📉 降价提醒：{item_title} 现仅售 ¥{current_price:.2f}"

    # 1. 构造图片 HTML
    img_html = ""
    if image_url:
        img_html = f"""
        <tr>
            <td align="center" style="padding: 20px 0;">
                <img src="{image_url}" alt="商品封面" width="260" referrerpolicy="no-referrer" style="display: block; border-radius: 8px; border: 1px solid #eee; max-width: 100%; height: auto;" />
            </td>
        </tr>
        """

    action_link = item_url if item_url else "#"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 0; background-color: #f6f6f6; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed;">
            <tr>
                <td align="center" style="padding: 20px;">
                    <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                        <tr>
                            <td align="center" style="background-color: #2c3e50; padding: 25px; color: #ffffff;">
                                <h2 style="margin: 0; font-size: 22px; font-weight: bold;">心愿达成通知</h2>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px; color: #333333;">
                                <p style="margin-bottom: 20px; font-size: 16px;">亲爱的 <strong>{user.username}</strong>：</p>
                                <p style="margin-bottom: 25px; line-height: 1.6;">好消息！您的心愿商品价格已降至预期范围内。</p>

                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8f9fa; border-radius: 8px; border: 1px solid #eeeeee;">
                                    <tr>
                                        <td align="center" style="padding: 15px 15px 0 15px;">
                                            <h3 style="margin: 0; color: #2c3e50; font-size: 16px; line-height: 1.4;">{item_title}</h3>
                                        </td>
                                    </tr>
                                    {img_html}
                                    <tr>
                                        <td align="center" style="padding-bottom: 20px;">
                                            <div style="font-size: 28px; color: #e74c3c; font-weight: bold; margin-bottom: 5px;">¥{current_price:.2f}</div>
                                            <div style="color: #999; text-decoration: line-through; font-size: 13px;">期望价格: ¥{target_price:.2f}</div>
                                        </td>
                                    </tr>
                                </table>

                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top: 30px;">
                                    <tr>
                                        <td align="center">
                                            <a href="{action_link}" style="background-color: #3498db; color: #ffffff; padding: 14px 35px; text-decoration: none; border-radius: 30px; font-weight: bold; display: inline-block; font-size: 16px;">立即查看商品</a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="background-color: #f1f2f6; padding: 15px; color: #95a5a6; font-size: 12px;">
                                本邮件由 Heart's Desire Aggregator 系统自动发送
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = recipient

    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [recipient], msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ 邮件发送失败给 {user.email}: {e}")


def send_unlock_notification(user_id: int, item_title: str, item_url: str, condition_desc: str, image_url: str = None):
    """
    发送心愿解锁祝贺邮件 (支持图片显示)
    """
    config = current_app.config
    SMTP_SERVER = config.get('SMTP_SERVER')
    SMTP_PORT = config.get('SMTP_PORT')
    SMTP_USER = config.get('SMTP_USER')
    SMTP_PASSWORD = config.get('SMTP_PASSWORD')

    user = User.query.get(user_id)
    if not user or not user.email:
        return

    subject = f"🔓 成就达成：【{item_title}】已解锁！"

    # 构造图片 HTML
    img_html = ""
    if image_url:
        img_html = f"""
        <div style="text-align: center; margin: 20px 0;">
            <img src="{image_url}" alt="解锁商品" width="200" referrerpolicy="no-referrer" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);" />
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f4f4; padding: 20px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #8e44ad, #9b59b6); color: white; padding: 30px 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">🎉 恭喜！成就已达成</h1>
            </div>
            <div style="padding: 30px;">
                <p style="font-size: 16px; color: #333;">亲爱的 <strong>{user.username}</strong>:</p>
                <p style="color: #555; line-height: 1.6;">您的努力得到了回报！检测到您的 GitHub 活跃度已达标：</p>

                <div style="background: #e8f8f5; color: #27ae60; padding: 15px; border-left: 5px solid #2ecc71; margin: 20px 0; border-radius: 4px;">
                    <strong>✅ 达成条件：</strong> {condition_desc}
                </div>

                <div style="text-align: center; margin: 25px 0;">
                    <p style="font-size: 18px; color: #2c3e50; font-weight: bold; margin-bottom: 10px;">《{item_title}》</p>
                    <p style="color: #7f8c8d; font-size: 14px;">现已解锁，不再受到限制。</p>
                    {img_html}
                </div>

                <div style="text-align: center; margin-top: 35px; margin-bottom: 10px;">
                    <a href="{item_url}" style="background-color: #8e44ad; color: white; padding: 16px 40px; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(142, 68, 173, 0.4); display: inline-block;">🎁 前往奖励自己</a>
                </div>
            </div>
            <div style="background-color: #f9f9f9; padding: 15px; text-align: center; color: #999; font-size: 12px;">
                Keep Coding, Keep Playing.
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = user.email
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [user.email], msg.as_string())
        server.quit()
        print(f"✅ 解锁祝贺邮件已发送给 {user.email}")
    except Exception as e:
        print(f"❌ 邮件发送失败给 {user.email}: {e}")