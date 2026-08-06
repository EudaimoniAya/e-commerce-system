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
