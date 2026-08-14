"""LocalFilesystemBackend：落盘实现。

读写 ``MEDIA_STORAGE_ROOT`` 下的 ``storage_key`` 相对路径，
两级分片目录格式为 ``{id[:2]}/{id[2:4]}/{id}``。
"""

from pathlib import Path


class LocalFilesystemBackend:
    """落盘存储后端。

    Args:
        root: 存储根目录（Path 或 str），如 ``.data/media`` 或 pytest ``tmp_path``。
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    async def save(self, key: str, data: bytes) -> None:
        """将字节写入 ``root / key``，自动创建父目录。"""
        target = self._root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(data)

    async def open(self, key: str) -> bytes:
        """读取 ``root / key``。文件不存在时抛出 FileNotFoundError。"""
        target = self._root / key
        if not target.is_file():
            raise FileNotFoundError(key)
        return target.read_bytes()

    async def delete(self, key: str) -> None:
        """删除 ``root / key``。文件不存在时静默跳过（幂等）。"""
        target = self._root / key
        target.unlink(missing_ok=True)
