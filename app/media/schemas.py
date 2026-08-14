"""media 域跨域 DTO（与 spec 对齐）。"""

from datetime import datetime

from pydantic import BaseModel, Field


class MediaSummary(BaseModel):
    """上传响应体——媒体元数据摘要。

    url 为相对路径 ``/media/{id}/file``。
    """

    id: str = Field(description="媒体 UUID")
    url: str = Field(description="下载相对路径 /media/{id}/file")
    content_type: str = Field(description="魔数检测后的 MIME")
    size_bytes: int = Field(description="实际上传字节数")
    created_at: datetime = Field(description="创建时间")


class MediaDetail(BaseModel):
    """``GET /media/{id}`` 响应体——媒体元数据详情（跨域 DTO）。

    含 ``visibility`` 与 ``original_filename``；**不暴露** storage_key / owner_user_id。
    """

    id: str = Field(description="媒体 UUID")
    url: str = Field(description="下载相对路径 /media/{id}/file")
    content_type: str = Field(description="魔数检测后的 MIME")
    size_bytes: int = Field(description="字节数")
    visibility: str = Field(description="public | owner_only")
    original_filename: str = Field(description="上传时文件名")
    created_at: datetime = Field(description="创建时间")
