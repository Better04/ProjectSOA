# app/services/platform_router.py

# 从上一步我们实现的平台服务中导入
from .steam_service import steam_service
from .github_service import github_service # <-- 新增导入
# from .jd_service import jd_service # 假设我们未来会添加京东服务
# from .taobao_service import taobao_service # 假设我们未来会添加淘宝服务

# -------------------
# 平台服务映射表
# -------------------
# 映射 URL 中的关键词到对应的服务实例
PLATFORM_SERVICES = {
    'steampowered.com': steam_service,
    'github.com': github_service, # <-- 新增映射
    # 'jd.com': jd_service,
    # 'taobao.com': taobao_service,
}

def get_service_by_url(url: str):
    """根据 URL 查找对应的平台服务实例"""
    for keyword, service in PLATFORM_SERVICES.items():
        if keyword in url:
            return service
    return None # 如果找不到匹配的服务

def get_supported_platforms() -> list:
    """返回支持的平台列表（用于前端展示）"""
    return list(PLATFORM_SERVICES.keys())