"""StorageBackend LocalFilesystemBackend 单元测试（TDD 红阶段）。

测试 save/open/delete 与分片路径，使用 pytest tmp_path 隔离磁盘。
"""

import uuid
from pathlib import Path

import allure
import pytest

from app.media.storage.local import LocalFilesystemBackend


def _rand_key() -> str:
    """生成一个与 MediaAsset.storage_key 格式一致的随机 key。"""
    id_ = uuid.uuid4().hex
    return f"{id_[:2]}/{id_[2:4]}/{id_}"


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("storage_local")
@allure.title("save 后 open 返回相同字节（round-trip）")
async def test_save_open_roundtrip(tmp_path: Path) -> None:
    """save 后 open 应返回完全相同的字节。"""
    backend = LocalFilesystemBackend(root=tmp_path)
    key = _rand_key()
    data = b"hello media storage"

    await backend.save(key, data)
    result = await backend.open(key)

    assert result == data


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("storage_local")
@allure.title("open 不存在的 key 抛出 FileNotFoundError")
async def test_open_nonexistent_raises(tmp_path: Path) -> None:
    """open 从未 save 过的 key 应抛出 FileNotFoundError。"""
    backend = LocalFilesystemBackend(root=tmp_path)
    key = _rand_key()

    with pytest.raises(FileNotFoundError):
        await backend.open(key)


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("storage_local")
@allure.title("delete 后 open 抛出 FileNotFoundError")
async def test_delete_then_open_raises(tmp_path: Path) -> None:
    """delete 已保存的 key 后 open 应抛出 FileNotFoundError。"""
    backend = LocalFilesystemBackend(root=tmp_path)
    key = _rand_key()
    data = b"temporary content"

    await backend.save(key, data)
    await backend.delete(key)

    with pytest.raises(FileNotFoundError):
        await backend.open(key)


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("storage_local")
@allure.title("delete 不存在的 key 静默成功（幂等）")
async def test_delete_nonexistent_noop(tmp_path: Path) -> None:
    """delete 不存在的 key 应静默成功，不抛异常。"""
    backend = LocalFilesystemBackend(root=tmp_path)
    key = _rand_key()

    # 不应抛异常
    await backend.delete(key)


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("storage_local")
@allure.title("storage_key 两级分片路径正确（{hex[:2]}/{hex[2:4]}/{id}）")
async def test_shard_path_structure(tmp_path: Path) -> None:
    """save 后文件应位于预期的分片路径下。"""
    backend = LocalFilesystemBackend(root=tmp_path)
    id_ = uuid.uuid4().hex
    key = f"{id_[:2]}/{id_[2:4]}/{id_}"
    data = b"shard test"

    await backend.save(key, data)

    expected_path = tmp_path / key
    assert expected_path.exists()
    assert expected_path.read_bytes() == data


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("storage_local")
@allure.title("同一 key 重复 save 覆盖旧内容")
async def test_save_overwrites_existing(tmp_path: Path) -> None:
    """同一 key save 两次，后一次覆盖前一次内容。"""
    backend = LocalFilesystemBackend(root=tmp_path)
    key = _rand_key()

    await backend.save(key, b"v1")
    await backend.save(key, b"v2")

    result = await backend.open(key)
    assert result == b"v2"
