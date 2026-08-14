"""media 域速率限制：Redis 固定窗口计数。

- 每个 authenticated user 独立计数
- 窗口时长与阈值由 ``Settings`` 注入（可 env 覆盖）
- 超限返回 429
"""

import time
import uuid

from fastapi import Depends, HTTPException, status

from app.infra.auth import get_current_user_id
from app.infra.config import Settings, get_settings
from app.infra.redis import get_redis

_KEY_PREFIX = "media_rate"


async def check_upload_rate_limit(
    user_id: uuid.UUID = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> None:
    """检查当前用户是否超过上传速率限制。

    用 Redis 固定窗口计数：key = ``media_rate:{user_id}:{window_start}``。
    窗口大小 = 60 秒，阈值 = ``media_upload_rate_limit_per_minute``。
    超限抛出 HTTP 429。
    """
    window_seconds = 60
    max_requests = settings.media_upload_rate_limit_per_minute
    window_start = int(time.time()) // window_seconds * window_seconds
    key = f"{_KEY_PREFIX}:{user_id}:{window_start}"

    r = get_redis()
    # INCR：首次创建 key 时设 TTL
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds + 1)  # +1 避免边界竞争

    if count > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="上传请求过于频繁，请稍后再试",
        )
