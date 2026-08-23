"""devbox 三库本地运维契约测试（ops）。

纯文件读取、无进程 I/O：断言 §2 之后才成立的本地运维契约
（`db-data/` 数据根、`PGHOST` 为目录而非 IP）。
当前 §1 红阶段应全部失败，§2 落地后转绿。
"""

import ipaddress
import json
from pathlib import Path

import allure

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVBOX_JSON = REPO_ROOT / "devbox.json"
MYSQL_CONF = REPO_ROOT / "devbox.d" / "mysql80" / "my.cnf"
REDIS_CONF = REPO_ROOT / "devbox.d" / "redis" / "redis.conf"


def _is_ip(value: str) -> bool:
    """判断字符串是否为合法 IP（IPv4/IPv6）。"""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


@allure.epic("ops")
@allure.feature("devbox_compose_contract")
@allure.title("devbox.json 的 PGHOST 不是 IP")
def test_pghost_is_not_ip() -> None:
    """devbox.json 的 PGHOST SHALL 为 unix socket 目录，不是 127.0.0.1。"""
    env = json.loads(DEVBOX_JSON.read_text(encoding="utf-8"))["env"]
    assert _is_ip(env["PGHOST"]) is False


@allure.epic("ops")
@allure.feature("devbox_compose_contract")
@allure.title("devbox.json 数据路径含 db-data")
def test_devbox_json_data_paths_contain_db_data() -> None:
    """devbox.json 的 MYSQL_DATADIR 与 PGDATA SHALL 落在 db-data/ 下。"""
    env = json.loads(DEVBOX_JSON.read_text(encoding="utf-8"))["env"]
    assert "db-data" in env["MYSQL_DATADIR"]
    assert "db-data" in env["PGDATA"]


@allure.epic("ops")
@allure.feature("devbox_compose_contract")
@allure.title("MySQL 本地配置 datadir 含 db-data")
def test_mysql_conf_datadir_contains_db_data() -> None:
    """devbox.d/mysql80/my.cnf 的 datadir SHALL 指向 db-data/mysql/。"""
    text = MYSQL_CONF.read_text(encoding="utf-8")
    datadir = next(line for line in text.splitlines() if line.startswith("datadir"))
    assert "db-data" in datadir


@allure.epic("ops")
@allure.feature("devbox_compose_contract")
@allure.title("Redis 本地配置 dir 含 db-data")
def test_redis_conf_dir_contains_db_data() -> None:
    """devbox.d/redis/redis.conf 的 dir SHALL 指向 db-data/redis/。"""
    text = REDIS_CONF.read_text(encoding="utf-8")
    dir_line = next(line for line in text.splitlines() if line.startswith("dir "))
    assert "db-data" in dir_line
