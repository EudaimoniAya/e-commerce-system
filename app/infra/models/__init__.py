"""infra 层 ORM 模型（非业务域）。"""

from app.infra.models.ai_migration_smoke import InfraAiMigrationSmoke
from app.infra.models.migration_smoke import InfraMigrationSmoke

__all__ = ["InfraAiMigrationSmoke", "InfraMigrationSmoke"]
