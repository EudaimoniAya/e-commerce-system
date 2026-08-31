"""黄金测试集 schema 校验测试（TDD 红阶段）。

覆盖 spec ai-ragas-eval「Golden eval dataset schema」：
- ``evals/golden/<snapshot_id>/samples.jsonl`` 必须存在于仓库；
- 条数 20–40（含）；每条可解析为含 ``id`` / ``question`` / ``shop_id`` 的对象；
- ``product_id`` 允许 JSON ``null``（缺省或 null = 整店检索），且至少一条为非空 UUID 字符串；
- 样本 SHALL NOT 要求会话消息 / HTTP 字段（键集 ⊆ 黄金集 schema）；
- 含 ``reference_context_ids`` 的样本，每项匹配 ``{document_id}:{chunk_index}``
  且 ``chunk_index`` 为非负整数；每条至少有 ``reference`` 或非空 ``reference_context_ids`` 之一；
- ``evals/golden/<snapshot_id>/manifest.yaml`` 声明 ``snapshot_id``、Eval 店标识，
  与 pytest 临时店数据分离（不得指向 ``clean_ai_chunks`` 类 fixture 店）。

红门禁：本测不创建 jsonl / 不编写 manifest；§4.2 落地黄金测试集前应红。
"""

import json
import uuid
from pathlib import Path

import allure
import pytest
import yaml

# 黄金测试集 schema 允许的顶层键（其余视为会话消息 / HTTP 残留）
_ALLOWED_KEYS = frozenset(
    {
        "id",
        "question",
        "shop_id",
        "product_id",
        "reference",
        "reference_context_ids",
    }
)

_GOLDEN_ROOT = Path("evals/golden")


def _current_snapshot_dir() -> Path:
    """返回当前快照目录（目录名字典序最大者 = 最新快照）。

    无快照目录时 ``pytest.fail``（红）：黄金测试集须与语料快照同版本（design 决策 2）。
    """
    snapshots = sorted(p for p in _GOLDEN_ROOT.glob("*") if p.is_dir())
    if not snapshots:
        pytest.fail(
            f"仓库缺少黄金测试集快照目录（{_GOLDEN_ROOT}/<snapshot_id>/）；"
            "§4.2 落地 samples.jsonl 前本测应红"
        )
    return snapshots[-1]


def _load_samples() -> list[dict]:
    """读取当前快照的 samples.jsonl，逐行解析为 JSON 对象（setup fail-fast）。"""
    samples_file = _current_snapshot_dir() / "samples.jsonl"
    if not samples_file.is_file():
        pytest.fail(f"黄金测试集缺失：{samples_file}")

    samples: list[dict] = []
    for lineno, raw in enumerate(
        samples_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{samples_file}:{lineno} 不是合法 JSON：{exc}")
        if not isinstance(parsed, dict):
            pytest.fail(
                f"{samples_file}:{lineno} 应为 JSON 对象，got {type(parsed).__name__}"
            )
        samples.append(parsed)
    return samples


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("当前快照目录存在 samples.jsonl。")
def test_samples_jsonl_exists_in_current_snapshot() -> None:
    """黄金测试集 SHALL 以 ``evals/golden/<snapshot_id>/samples.jsonl`` 存在。"""
    snapshot = _current_snapshot_dir()
    assert (snapshot / "samples.jsonl").is_file()


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("样本条数在 20–40（含）之间。")
def test_sample_count_between_20_and_40() -> None:
    """条数 SHALL 在 20 至 40（含）之间。"""
    samples = _load_samples()
    assert 20 <= len(samples) <= 40, f"样本条数 {len(samples)} 超出 20–40"


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("每条样本含非空 id/question/shop_id。")
def test_every_sample_has_retrieval_keys() -> None:
    """每一行 SHALL 解析为含 ``id`` / ``question`` / ``shop_id`` 的对象（非空字符串）。"""
    for idx, sample in enumerate(_load_samples()):
        for key in ("id", "question", "shop_id"):
            value = sample.get(key)
            assert isinstance(value, str) and value, (
                f"样本[{idx}] 缺少非空 {key}: {sample!r}"
            )


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("product_id 允许 null，且至少一条为非空 UUID 字符串。")
def test_product_id_null_or_uuid_and_at_least_one_non_null() -> None:
    """product_id 缺省/null = 整店检索；至少一条样本为非空 UUID 字符串。"""
    samples = _load_samples()
    product_ids: list[str] = []
    for idx, sample in enumerate(samples):
        pid = sample.get("product_id")
        if pid is None:
            continue
        assert isinstance(pid, str) and pid, (
            f"样本[{idx}] product_id 应为 null 或非空字符串: {sample!r}"
        )
        try:
            uuid.UUID(pid)
        except ValueError as exc:
            pytest.fail(f"样本[{idx}] product_id 不是合法 UUID: {pid!r} ({exc})")
        product_ids.append(pid)
    assert product_ids, "黄金测试集至少需要一条带非空 product_id 的样本"


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("样本只携带黄金集 schema 字段，不含会话消息 / HTTP 字段。")
def test_samples_carry_no_session_or_http_fields() -> None:
    """样本 SHALL NOT 要求会话消息 / HTTP 字段：键集 ⊆ 黄金集 schema 白名单。"""
    for idx, sample in enumerate(_load_samples()):
        extra = set(sample) - _ALLOWED_KEYS
        assert not extra, (
            f"样本[{idx}] 出现 schema 外字段（可能为会话/HTTP 残留）: {sorted(extra)}"
        )


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("含 reference_context_ids 的样本每项匹配 document_id:chunk_index。")
def test_reference_context_ids_format() -> None:
    """应召回 id SHALL 匹配 ``{document_id}:{chunk_index}`` 且 ``chunk_index`` 为非负整数。"""
    for idx, sample in enumerate(_load_samples()):
        ids = sample.get("reference_context_ids")
        if not ids:
            continue
        assert isinstance(ids, list), (
            f"样本[{idx}] reference_context_ids 应为列表: {sample!r}"
        )
        for item in ids:
            assert isinstance(item, str) and ":" in item, (
                f"样本[{idx}] 应召回 id 应形如 document_id:chunk_index: {item!r}"
            )
            doc_id, chunk_part = item.rsplit(":", 1)
            assert doc_id, f"样本[{idx}] 应召回 id 缺 document_id: {item!r}"
            assert chunk_part.isdigit(), (
                f"样本[{idx}] chunk_index 应为非负整数: {item!r}"
            )


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("每条样本至少有 reference 或非空 reference_context_ids 之一。")
def test_every_sample_has_reference_or_context_ids() -> None:
    """Context recall 需应召回信息：reference 与非空 reference_context_ids 至少其一。"""
    for idx, sample in enumerate(_load_samples()):
        reference = sample.get("reference")
        has_reference = isinstance(reference, str) and bool(reference.strip())
        ids = sample.get("reference_context_ids")
        has_ids = isinstance(ids, list) and any(isinstance(i, str) and i for i in ids)
        assert has_reference or has_ids, (
            f"样本[{idx}] 缺 reference 且 reference_context_ids 为空: {sample!r}"
        )


def _manifest() -> dict:
    """读取当前快照的 manifest.yaml 并解析为映射（setup fail-fast）。"""
    manifest_file = _current_snapshot_dir() / "manifest.yaml"
    if not manifest_file.is_file():
        pytest.fail(f"黄金测试集 manifest 缺失：{manifest_file}")
    data = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "manifest.yaml 应为映射"
    return data


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("manifest.yaml 存在且 snapshot_id 与目录名一致。")
def test_manifest_snapshot_id_matches_dir_name() -> None:
    """快照须版本化：manifest 的 ``snapshot_id`` SHALL 与目录名一致。"""
    snapshot = _current_snapshot_dir()
    assert (snapshot / "manifest.yaml").is_file()
    manifest = _manifest()
    assert manifest.get("snapshot_id") == snapshot.name


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("manifest 记录 Eval 店 shop_id 或可重建种子标识。")
def test_manifest_records_eval_shop_or_seed() -> None:
    """Eval 店标识 SHALL 可复现：shop_id 或种子标识至少其一。"""
    manifest = _manifest()
    shop_id = manifest.get("shop_id")
    seed_keys = [k for k in manifest if "seed" in k.lower()]
    has_seed = bool(
        seed_keys
        and any(isinstance(manifest[k], str) and manifest[k] for k in seed_keys)
    )
    if isinstance(shop_id, str) and shop_id:
        uuid.UUID(shop_id)  # Eval 店应为稳定 UUID（与 pytest 随建随清店分离）
    else:
        assert has_seed, "manifest 须含 Eval 店 shop_id（UUID）或可重建种子标识"


@allure.epic("ai")
@allure.feature("golden_dataset")
@allure.title("manifest 不指向 clean_ai_chunks 类 pytest fixture 店。")
def test_manifest_shop_not_a_test_fixture_shop() -> None:
    """Eval 店 SHALL 与 pytest 临时店数据分离（design 决策 2）。

    ``clean_ai_chunks`` 类 fixture 店随测随清，chunks 会被清空导致 recall 假摔；
    manifest 若引用 fixture 店即违反快照隔离。shop_id 须为稳定 UUID。
    """
    snapshot = _current_snapshot_dir()
    manifest_text = (snapshot / "manifest.yaml").read_text(encoding="utf-8")
    assert "clean_ai_chunks" not in manifest_text, "manifest 不得引用 pytest fixture 店"
    manifest = _manifest()
    shop_id = manifest.get("shop_id")
    if isinstance(shop_id, str) and shop_id:
        uuid.UUID(shop_id)
