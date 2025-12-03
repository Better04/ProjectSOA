from app.database import db
from app.models import Item, Wish, PriceHistory, User
from app.services.platform_router import get_service_by_url
from sqlalchemy.exc import IntegrityError # 用于处理数据库唯一性约束错误

from app.services.notification_service import send_unlock_notification
from app.services.achievement_service import achievement_service

class WishlistService:

    @staticmethod
    def add_wish(user_id: int, url: str, target_price: float, condition_type: str = None, target_value: int = 0):
        """
        添加一个新的心愿商品。
        如果商品已存在（相同的URL），则只创建新的 Wish 记录。
        """
        service = get_service_by_url(url)
        if not service:
            return None, "不支持该平台或URL格式错误"

        try:
            # 1. 解析出商品 ID
            item_id = service.extract_item_id(url)

            # 2. 尝试查找 Item 是否已存在于数据库
            item = Item.query.filter_by(original_url=url).first()

            if not item:
                # 3. 如果 Item 不存在，调用外部服务获取详细信息
                item_data = service.get_standard_item_data(item_id, url)

                # 4. 创建新的 Item 记录
                item = Item(
                    platform_item_id=item_data['platform_item_id'],
                    original_url=item_data['original_url'],
                    title=item_data['title'],
                    image_url=item_data['image_url'],
                    platform=item_data['platform']
                )
                db.session.add(item)
                db.session.flush()  # 临时提交，以便获取 item.id

                # 5. 记录首次价格历史
                history = PriceHistory(
                    item_id=item.id,
                    price=item_data['current_price']
                )
                db.session.add(history)

            # 6. 创建 Wish 记录（无论 Item 是否新建）
            # 检查用户是否已经添加过该商品
            existing_wish = Wish.query.filter_by(user_id=user_id, item_id=item.id).first()
            if existing_wish:
                return existing_wish, "该商品已存在于您的心愿单中"

            # 如果没有设置条件(None)，默认为解锁(True)；否则为锁定(False)
            is_unlocked_status = (condition_type is None)

            new_wish = Wish(
                user_id=user_id,
                item_id=item.id,
                target_price=target_price,
                is_unlocked=is_unlocked_status,
                unlock_condition_type=condition_type,
                unlock_target_value=target_value
            )
            db.session.add(new_wish)
            db.session.commit()
            return new_wish, "心愿添加成功"

        except IntegrityError:
            # 处理并发或唯一性约束失败的情况
            db.session.rollback()
            return None, "数据库完整性错误，请稍后再试"
        except ValueError as e:
            db.session.rollback()
            return None, str(e)
        except Exception as e:
            db.session.rollback()
            print(f"添加心愿时发生未知错误: {e}")
            return None, "服务处理失败"

    @staticmethod
    def get_wishes_by_user(user_id: int):
        """查询用户所有心愿单项目及最新价格"""
        # 使用 SQLAlchemy 的 join 语句查询
        wishes = db.session.query(Wish, Item).join(Item).filter(Wish.user_id == user_id).all()

        result = []
        for wish, item in wishes:
            # 获取最新价格：通过 PriceHistory 表按照时间倒序查询第一个记录
            latest_price_record = PriceHistory.query.filter_by(item_id=item.id).order_by(
                PriceHistory.timestamp.desc()
            ).first()

            latest_price = latest_price_record.price if latest_price_record else None

            # 🚨 核心修正：当 latest_price 不为 None 时才进行价格比较。
            if latest_price is not None and latest_price <= wish.target_price:
                status = '低于目标'
            else:
                status = '高于目标'

            result.append({
                'wish_id': wish.id,
                'target_price': wish.target_price,
                'item_id': item.id,
                'title': item.title,
                'platform': item.platform,
                'original_url': item.original_url,
                'image_url': item.image_url,
                'latest_price': latest_price,
                'status': status,
                'is_unlocked': wish.is_unlocked,
                'unlock_condition_type': wish.unlock_condition_type,
                'unlock_target_value': wish.unlock_target_value
            })
        return result

    @staticmethod
    def delete_wish(user_id: int, wish_id: int):
        """删除一个心愿单项目"""
        wish = Wish.query.filter_by(id=wish_id, user_id=user_id).first()
        if wish:
            db.session.delete(wish)
            db.session.commit()
            # 注意：这里我们不删除 Item 和 PriceHistory，因为其他用户可能也收藏了该 Item
            return True
        return False

   
    @staticmethod
    def check_and_unlock_wishes(user_id: int):
        """
        核心功能：检查该用户的所有锁定心愿，如果达成 GitHub 目标则解锁
        此方法供 API /refresh 路由调用
        """
        try:
            # 1. 获取用户信息 (我们需要 GitHub 用户名)
            user = User.query.get(user_id)
            if not user or not user.username:
                # 这里假设 user.username 存的是 GitHub 用户名
                return False, "找不到用户或用户未绑定 GitHub"

            github_username = user.username 

            # 2. 查找该用户所有【未解锁】且【有条件】的心愿
            # 注意：这里使用了 Wish 模型里新加的字段
            locked_wishes = Wish.query.filter_by(
                user_id=user_id, 
                is_unlocked=False
            ).filter(Wish.unlock_condition_type.isnot(None)).all()

            if not locked_wishes:
                return False, "当前没有需要解锁的心愿"

            unlocked_count = 0
            
            # 3. 遍历检查
            for wish in locked_wishes:
                # 问裁判：达标了吗？
                achieved = achievement_service.check_achievement(
                    github_username,
                    wish.unlock_condition_type,
                    wish.unlock_target_value
                )

                if achieved:
                    wish.is_unlocked = True
                    unlocked_count += 1
                    try:
                        # 准备数据
                        title = wish.item.title if wish.item else "神秘商品"
                        url = wish.item.original_url if wish.item else ""
                        condition_msg = f"{wish.unlock_condition_type} >= {wish.unlock_target_value}"
                        
                        # 发送解锁通知
                        send_unlock_notification(user_id, title, url, condition_msg)
                        
                    except Exception as e:
                        # 捕获错误，防止因为发邮件失败导致数据库回滚
                        print(f"邮件发送非致命错误: {e}")

            # 4. 提交更改
            if unlocked_count > 0:
                db.session.commit()
                return True, f"恭喜！成功解锁了 {unlocked_count} 个心愿！"
            
            return False, "条件尚未达成，继续加油！"

        except Exception as e:
            db.session.rollback()
            print(f"解锁检查失败: {e}")
            return False, f"检查出错: {str(e)}"