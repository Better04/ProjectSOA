from abc import ABC, abstractmethod


class BasePlatformService(ABC):
    """
    所有外部平台服务的抽象基类。
    所有具体平台服务（如 JdService, SteamService）必须实现以下方法。
    """

    @abstractmethod
    def get_platform_name(self) -> str:
        """返回平台的唯一名称（如 'jd', 'steam'）。"""
        pass

    @abstractmethod
    def extract_item_id(self, url: str) -> str:
        """从商品 URL 中解析出唯一的商品 ID（如 SKU 或 AppID）。"""
        pass

    @abstractmethod
    def fetch_item_details(self, item_id: str, url: str) -> dict:
        """
        获取商品的详细信息（名称、图片、当前价格）。
        返回标准化字典，这是服务的核心输出。
        """
        raise NotImplementedError

    def get_standard_item_data(self, item_id: str, url: str) -> dict:
        """
        调用 fetch_item_details，并返回最终标准化的数据结构。
        """
        data = self.fetch_item_details(item_id, url)

        # 统一的输出数据结构，强制要求各平台服务返回此格式
        return {
            'platform_item_id': item_id,
            'original_url': url,
            'title': data.get('title'),
            'image_url': data.get('image_url'),
            'current_price': data.get('current_price'),
            'platform': self.get_platform_name()
        }