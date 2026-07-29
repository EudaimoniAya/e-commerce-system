"""ordering 域 checkout_batch 仓储层。"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.models import CheckoutBatch


class CheckoutBatchRepository:
    """结算批次仓储（checkout_batches 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, batch: CheckoutBatch) -> None:
        """持久化新 checkout_batch。"""
        self._session.add(batch)

    async def get_by_id(self, batch_id: uuid.UUID) -> CheckoutBatch | None:
        """按主键查询。"""
        return await self._session.get(CheckoutBatch, batch_id)
