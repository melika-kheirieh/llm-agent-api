from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection

_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _ROOT / "alembic.ini"
_SCRIPT_LOCATION = _ROOT / "alembic"


def alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    return cfg


def upgrade_to_head(connection: Connection) -> None:
    """Apply Alembic migrations using an existing (sync) connection."""
    cfg = alembic_config()
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")
