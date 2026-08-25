"""support 域对外端口：AI 回合 handler。

由 ``main.py``（组合根）经 ``app.support.deps.register_buyer_turn_handler_factory``
注册工厂注入；support 模块 **不 import** ``app.ai``。Port 只返回助手正文，落库 /
preview / 事务仍在 ``SupportService``。
"""

from typing import Protocol


class BuyerTurnAiHandler(Protocol):
    """AI 回合处理器：``handler_mode=ai`` 时买家 POST 同步调用，返回助手正文。"""

    async def handle_buyer_turn(
        self,
        *,
        shop_id: str,
        body: str | None,
        product_ref_ids: list[str],
    ) -> str:
        """消费一轮买家输入（shop_id / body / 本条消息 product refs），返回回复正文。"""
