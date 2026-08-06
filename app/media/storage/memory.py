"""InMemoryBackend：进程内 dict 实现（integration 测试专用）。

SAVEPOINT 回滚不覆盖文件 IO，因此 integration 测试必须注入此 backend
以避免磁盘残留。数据随进程销毁自动丢弃。
"""


class InMemoryBackend:
    """进程内存储后端。

    内部使用 ``dict[str, bytes]``，不产生任何文件 IO。
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def save(self, key: str, data: bytes) -> None:
        """将字节存入进程内字典。"""
        self._store[key] = data

    async def open(self, key: str) -> bytes:
        """从进程内字典读取字节。key 不存在时抛出 FileNotFoundError。"""
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]

    async def delete(self, key: str) -> None:
        """从进程内字典删除 key。key 不存在时静默跳过（幂等）。"""
        self._store.pop(key, None)
