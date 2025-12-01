import re
import requests
from .base_platform_service import BasePlatformService

# Steam Store API 的基础 URL
# 我们使用 cc=cn (中国) 获取人民币价格, l=chinese (简体中文) 获取中文信息
STEAM_API_URL = "https://store.steampowered.com/api/appdetails"


class SteamService(BasePlatformService):
    """Steam 平台数据获取服务"""

    def get_platform_name(self) -> str:
        return 'steam'

    def extract_item_id(self, url: str) -> str:
        # Steam URL 示例: https://store.steampowered.com/app/1085660/Destiny_2/
        match = re.search(r'/app/(\d+)', url)
        if match:
            return match.group(1)  # 返回数字 AppID
        raise ValueError("无效的 Steam 商品 URL 格式")

    def fetch_item_details(self, item_id: str, url: str) -> dict:
        """
        调用 Steam Store API 获取商品详情和价格。
        App ID (item_id) 在 Steam 平台上是全球唯一的。
        """
        params = {
            'appids': item_id,
            'cc': 'cn',  # 国家/地区代码：中国 (用于获取人民币价格)
            'l': 'chinese'  # 语言：简体中文
        }

        try:
            # 注意：Steam API 对爬取速度有限制，实际使用中可能需要考虑限速或代理
            response = requests.get(STEAM_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Steam API 返回的 JSON 结构: {app_id: {success: bool, data: {...}}}
            app_data = data.get(item_id, {}).get('data')

            if not app_data:
                # 检查是否获取失败（例如：商品不存在、已下架或请求过于频繁）
                raise ValueError("未找到商品数据或请求失败")

            # ------------------- 解析逻辑 -------------------

            # 1. 价格: price_overview (包含价格信息)
            price_overview = app_data.get('price_overview')

            if app_data.get('is_free'):
                # 免费游戏，价格为 0.00
                current_price = 0.00
            elif price_overview:
                # 付费游戏，价格以“分”为单位，需要转换为“元”
                current_price = price_overview.get('final') / 100.0
            else:
                # 价格不可用 (如尚未发行、需要外部包等)
                print(f"Warning: Steam item {item_id} has no price overview and is not free.")
                current_price = -1

            # 2. 标题
            title = app_data.get('name', f"Steam Item {item_id}")

            # 3. 图片 URL (使用 header_image)
            image_url = app_data.get('header_image', f"https://steamcdn-a.akamaihd.net/steam/apps/{item_id}/header.jpg")

            price_info = {
                'title': title,
                'image_url': image_url,
                'current_price': current_price
            }
            # ---------------------------------------------

            return price_info

        except requests.RequestException as e:
            # 记录日志，但不中断程序
            print(f"Error fetching Steam data for ID {item_id} (API Request Failed): {e}")
            return {
                'title': f"Item ID {item_id} (Data Fetch Failed)",
                'image_url': None,
                'current_price': -1  # 用负值表示价格获取失败
            }
        except ValueError as e:
            # 记录日志，但不中断程序 (例如: "未找到商品数据" 或 "无效的 Steam 商品 URL 格式")
            print(f"Error processing Steam data for ID {item_id} (Data Error): {e}")
            return {
                'title': f"Item ID {item_id} (Data Process Failed)",
                'image_url': None,
                'current_price': -1
            }


# 实例化服务，在其他模块可以直接导入使用
steam_service = SteamService()