"""StorageBackend 协议定义。"""

from typing import Protocol


class StorageBackend(Protocol):
    """存储后端协议：字节的 save / open / delete。

    实现类：
    - ``LocalFilesystemBackend``：落盘（dev / backend 单测）
    - ``InMemoryBackend``：进程内 dict（integration 测试）
    """

    async def save(self, key: str, data: bytes) -> None:
        """持久化字节到指定 key。"""
        ...

    async def open(self, key: str) -> bytes:
        """读取 key 对应的字节。key 不存在时抛出 FileNotFoundError。"""
        ...

    async def delete(self, key: str) -> None:
        """删除 key 对应的字节。key 不存在时静默成功（幂等）。"""
        ...
