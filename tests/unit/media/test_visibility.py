"""visibility 读权限规则单元测试：owner_only / public（TDD 红阶段）。

使用 InMemoryBackend 注入，测试 can_read 规则。
"""

import uuid

import allure
import pytest

from app.media.service import MediaService
from app.media.storage.memory import InMemoryBackend
from tests.support.helper.media import MINI_PNG_BYTES


async def _upload_and_get_id(
    service: MediaService, owner_user_id: str, visibility: str = "owner_only"
) -> str:
    """通过 service 上传文件并返回 media id。"""
    result = await service.upload(
        file_bytes=MINI_PNG_BYTES,
        original_filename="test.png",
        owner_user_id=owner_user_id,
        content_type="image/png",
        visibility=visibility,
    )
    return result.id


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("visibility")
@allure.title("owner_only 文件：owner 可读（can_read → True）")
async def test_owner_only_owner_can_read() -> None:
    """owner_only 文件的拥有者应可读。"""
    storage = InMemoryBackend()
    service = MediaService(storage=storage)  # type: ignore[arg-type]
    owner_id = str(uuid.uuid4())

    media_id = await _upload_and_get_id(service, owner_id, visibility="owner_only")

    can_read = await service.can_read(media_id=media_id, user_id=owner_id)
    assert can_read is True


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("visibility")
@allure.title("owner_only 文件：非 owner 不可读（can_read → False）")
async def test_owner_only_non_owner_cannot_read() -> None:
    """owner_only 文件的非拥有者不可读。"""
    storage = InMemoryBackend()
    service = MediaService(storage=storage)  # type: ignore[arg-type]
    owner_id = str(uuid.uuid4())
    other_user_id = str(uuid.uuid4())

    media_id = await _upload_and_get_id(service, owner_id, visibility="owner_only")

    can_read = await service.can_read(media_id=media_id, user_id=other_user_id)
    assert can_read is False


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("visibility")
@allure.title("owner_only 文件：匿名（user_id=None）不可读")
async def test_owner_only_anonymous_cannot_read() -> None:
    """owner_only 文件对匿名用户（user_id=None）不可读。"""
    storage = InMemoryBackend()
    service = MediaService(storage=storage)  # type: ignore[arg-type]
    owner_id = str(uuid.uuid4())

    media_id = await _upload_and_get_id(service, owner_id, visibility="owner_only")

    can_read = await service.can_read(media_id=media_id, user_id=None)
    assert can_read is False


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("visibility")
@allure.title("public 文件：匿名可读（can_read → True）")
async def test_public_anonymous_can_read() -> None:
    """public 文件对匿名用户可读。"""
    storage = InMemoryBackend()
    service = MediaService(storage=storage)  # type: ignore[arg-type]
    owner_id = str(uuid.uuid4())

    media_id = await _upload_and_get_id(service, owner_id, visibility="public")

    can_read = await service.can_read(media_id=media_id, user_id=None)
    assert can_read is True


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("visibility")
@allure.title("public 文件：owner 可读")
async def test_public_owner_can_read() -> None:
    """public 文件的拥有者也应可读。"""
    storage = InMemoryBackend()
    service = MediaService(storage=storage)  # type: ignore[arg-type]
    owner_id = str(uuid.uuid4())

    media_id = await _upload_and_get_id(service, owner_id, visibility="public")

    can_read = await service.can_read(media_id=media_id, user_id=owner_id)
    assert can_read is True


@pytest.mark.asyncio
@allure.epic("media")
@allure.feature("visibility")
@allure.title("public 文件：非 owner 登录用户也可读")
async def test_public_other_user_can_read() -> None:
    """public 文件对非拥有者的登录用户也可读。"""
    storage = InMemoryBackend()
    service = MediaService(storage=storage)  # type: ignore[arg-type]
    owner_id = str(uuid.uuid4())
    other_user_id = str(uuid.uuid4())

    media_id = await _upload_and_get_id(service, owner_id, visibility="public")

    can_read = await service.can_read(media_id=media_id, user_id=other_user_id)
    assert can_read is True
