"""离线 RAGAS 评测 runner（ai-ragas-eval §5.1）。

用法（离线，需 ``uv sync --group eval`` + 裁判密钥）::

    devbox run -- uv run python -m app.ai.evals.runner

流程：读当前快照黄金测试集 → 叶子 adapter（``retrieve_chunks`` + ``rag_answer`` 生成）
→ RAGAS Faithfulness + Context recall 打分（裁判用 ``RAGAS_JUDGE_*``）→
报告写入 ``evals/reports/``（gitignored，不进库）。

**不**挂进 ``task ci``（design 决策 6）：CI 只守接线（指标清单 §1.8），真打分走离线；
缺裁判密钥 / 缺 ragas 时默认 pytest 与 CI 仍绿。ragas / langchain 均惰性 import，
本模块在无 eval 依赖环境也能导入。
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ai.deps import build_llm_client, build_prompt_loader
from app.ai.evals.adapter import build_eval_sample
from app.ai.evals.metrics import enabled_metrics
from app.ai.rag.retrieval.service import retrieve_chunks
from app.infra.config import get_settings

_GOLDEN_ROOT = Path("evals/golden")
_REPORT_DIR = Path("evals/reports")


def current_snapshot_dir() -> Path:
    """返回当前快照目录（字典序最大者 = 最新快照，与黄金测试集测试一致）。"""
    snapshots = sorted(p for p in _GOLDEN_ROOT.glob("*") if p.is_dir())
    if not snapshots:
        raise FileNotFoundError(
            f"仓库缺少黄金测试集快照（{_GOLDEN_ROOT}/<snapshot_id>/）"
        )
    return snapshots[-1]


def load_samples(snapshot_dir: Path) -> list[dict]:
    """读取 samples.jsonl 为 dict 列表（逐行解析，跳过空行）。"""
    samples_file = snapshot_dir / "samples.jsonl"
    samples: list[dict] = []
    for raw in samples_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        samples.append(json.loads(line))
    return samples


def build_judge_llm() -> Any:
    """按 Settings 构造裁判 LLM（``RAGAS_JUDGE_*``，OpenAI 兼容 GPT）。

    任一裁判配置缺失即抛错——离线真打分必须显式配置（CI 不读这些变量）。
    """
    settings = get_settings()
    if not (settings.ragas_judge_api_key and settings.ragas_judge_model):
        raise RuntimeError(
            "离线评测需配置 RAGAS_JUDGE_API_KEY / RAGAS_JUDGE_BASE_URL / RAGAS_JUDGE_MODEL"
        )
    from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]
    from pydantic import SecretStr
    from ragas.llms import LangchainLLMWrapper  # type: ignore[import-not-found]

    judge_model = ChatOpenAI(
        model=settings.ragas_judge_model,
        api_key=SecretStr(settings.ragas_judge_api_key),
        base_url=settings.ragas_judge_base_url,
        temperature=0,
    )
    return LangchainLLMWrapper(judge_model)


def _build_metric_objects(judge_llm: Any) -> list[Any]:
    """把 ``enabled_metrics()`` 的名字映射为 RAGAS 指标对象（惰性 import ragas）。

    ``evaluate(llm=judge_llm)`` 会把裁判 LLM 应用于所有指标，故此处不逐指标绑。
    """
    from ragas.metrics import (  # type: ignore[import-not-found]
        ContextRecall,
        Faithfulness,
    )

    by_name: dict[str, Any] = {
        "faithfulness": Faithfulness,
        "context_recall": ContextRecall,
    }
    return [cls() for name, cls in by_name.items() if name in enabled_metrics()]


async def prepare_ragas_samples(
    samples: list[dict],
    *,
    retrieve: Any,
    generation_llm: Any,
    prompt_loader: Any,
) -> list[Any]:
    """黄金样本 → 叶子 adapter → RAGAS ``SingleTurnSample``（惰性 import ragas）。

    ``reference`` 用黄金样本的参考答案（Context recall 需要对照）。
    """
    from ragas import SingleTurnSample  # type: ignore[import-not-found]

    ragas_samples: list[Any] = []
    for sample in samples:
        eval_sample = await build_eval_sample(
            sample,
            retrieve=retrieve,
            generation_llm=generation_llm,
            prompt_loader=prompt_loader,
        )
        ragas_samples.append(
            SingleTurnSample(
                user_input=sample["question"],
                response=eval_sample.response,
                retrieved_contexts=eval_sample.retrieved_contexts,
                reference=sample.get("reference", ""),
            )
        )
    return ragas_samples


def score_samples(ragas_samples: list[Any], *, judge_llm: Any) -> Any:
    """对已组装的 ``SingleTurnSample`` 列表跑 RAGAS Faithfulness + Context recall。"""
    from ragas.evaluation import (  # type: ignore[import-not-found]
        EvaluationDataset,
        evaluate,
    )

    dataset = EvaluationDataset(samples=ragas_samples)
    return evaluate(
        dataset,
        metrics=_build_metric_objects(judge_llm),
        llm=judge_llm,
        show_progress=True,
    )


def _clean_value(value: Any) -> Any:
    """NaN → None（JSON 序列化友好）。"""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def write_report(result: Any, *, snapshot_id: str) -> Path:
    """把 EvaluationResult 写为 JSON 报告，返回报告路径（gitignored）。"""
    settings = get_settings()
    df = result.to_pandas()
    records = [
        {key: _clean_value(value) for key, value in row.items()}
        for row in df.to_dict(orient="records")
    ]
    numeric = df.select_dtypes(include="number")
    aggregate = (
        {key: float(value) for key, value in numeric.mean().to_dict().items()}
        if not numeric.empty
        else {}
    )
    report = {
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": enabled_metrics(),
        "judge_model": settings.ragas_judge_model,
        "judge_base_url": settings.ragas_judge_base_url,
        "generation_provider": settings.llm_provider,
        "generation_model": settings.llm_model,
        "sample_count": len(records),
        "aggregate_scores": aggregate,
        "samples": records,
    }
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = _REPORT_DIR / f"{snapshot_id}-{timestamp}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report_path


async def _run() -> None:
    """组装 runner：读快照 → adapter → RAGAS 打分 → 报告 → 打印摘要。"""
    settings = get_settings()
    snapshot_dir = current_snapshot_dir()
    samples = load_samples(snapshot_dir)
    if not samples:
        raise RuntimeError(f"黄金测试集为空：{snapshot_dir / 'samples.jsonl'}")

    print(f"快照: {snapshot_dir.name}  样本数: {len(samples)}")
    print(
        f"生成: LLM_PROVIDER={settings.llm_provider}  裁判: {settings.ragas_judge_model}"
    )
    print("组装叶子样本（retrieve + generate）...")
    ragas_samples = await prepare_ragas_samples(
        samples,
        retrieve=retrieve_chunks,
        generation_llm=build_llm_client(),
        prompt_loader=build_prompt_loader(),
    )
    print("RAGAS 打分（Faithfulness / Context recall）...")
    result = score_samples(ragas_samples, judge_llm=build_judge_llm())
    report_path = write_report(result, snapshot_id=snapshot_dir.name)
    print(f"报告: {report_path}")


def main() -> None:
    """CLI 入口。"""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
