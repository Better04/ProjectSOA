# 导入创建 App 的工厂函数
from app import create_app
from app.database import db
from app.models import Item, Wish, PriceHistory
from app.services.platform_router import get_service_by_url
from app.services.notification_service import send_price_alert
# 导入 Flask，但仅用于类型提示，不用于创建实例
from flask import Flask


# 🚨 修正：接收 config_name，而不是 app 实例
def run_price_monitoring(config_name: str):
    """
    全局价格监控任务。由 APScheduler 每小时调用一次。
    """
    # ----------------------------------------------------
    # 1. 重建 App 实例并创建上下文 (解决 Cannot pickle local object)
    # ----------------------------------------------------
    # 在后台线程中创建一个新的、精简的应用实例
    app = create_app(config_name)

    # 必须在 app_context 中运行，才能访问数据库和配置
    with app.app_context():
        print("--- ⚙️ 价格监控任务开始执行 ---")

        # 2. 查询所有活跃的心愿商品
        # 这里我们只查询有活跃心愿的 Item，避免重复监控
        all_monitored_items = Item.query.join(Wish).filter(Wish.is_active == True).distinct().all()

        checked_item_ids = set()

        for item in all_monitored_items:
            if item.id in checked_item_ids:
                continue

            print(f"   -> 正在监控商品：{item.title} ({item.platform})")

            # 3. 查找对应的平台服务
            service = get_service_by_url(item.original_url)
            if not service:
                print(f"   -> WARNING: 未找到 {item.platform} 的服务，跳过。")
                continue

            try:
                # 4. 调用外部平台服务获取最新数据 (这是 SOA 的核心调用)
                # 注意：这里的 item_id 应该使用 item.platform_item_id
                item_data = service.get_standard_item_data(item.platform_item_id, item.original_url)
                new_price = item_data['current_price']

                # 🚨 核心修正：只在价格获取失败（返回 -1）时跳过，价格为 0.00 视为免费，允许记录
                if new_price < 0:
                    print(f"   -> ERROR: 价格获取失败，跳过记录和通知。")
                    continue

                # 5. 记录最新价格
                latest_history = PriceHistory(
                    item_id=item.id,
                    price=new_price
                )
                db.session.add(latest_history)
                db.session.commit()
                print(f"   -> 最新价格已记录: ¥{new_price:.2f}")

                # 6. 检查并触发通知
                wishes_for_item = Wish.query.filter_by(item_id=item.id, is_active=True).all()
                for wish in wishes_for_item:
                    # 价格达到期望，发送通知 (即使价格是 0.00 且目标价高于 0.00 也会触发)
                    if new_price <= wish.target_price:
                        send_price_alert(
                            user_id=wish.user_id,
                            item_title=item.title,
                            current_price=new_price,
                            target_price=wish.target_price
                        )

            except Exception as e:
                # 在事务失败时进行回滚
                db.session.rollback()
                print(f"   -> CRITICAL ERROR: 监控 {item.title} 时发生错误: {e}")

            checked_item_ids.add(item.id)

        print("--- ✅ 价格监控任务执行完毕 ---")