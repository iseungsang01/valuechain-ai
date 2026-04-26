"""데모 시드 + cold-cache 워밍 스크립트 (T4.3).

목표:
1. 데모 fixture (DART/EDGAR 2024Q3 mock) 로드 검증
2. LangGraph 컴파일 + InMemoryRepository 초기화 워밍 → 첫 요청 cold-start 회피
3. 토폴로지 노드/엣지 / FX rate 일관성 점검
4. 벤치마크 / 데모 시연 직전에 한번 실행

실행:
    cd apps/api
    .\.venv\Scripts\python.exe scripts\seed_demo.py
    # 또는 module 형태
    python -m scripts.seed_demo

종료 코드:
    0: 정상 워밍 완료
    1: 데모 fixture 로 파이프라인 실행 실패
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

# scripts/ 가 apps/api 기준 sibling - import path 보정
APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


# fmt: off
from app.agents import build_graph                          # noqa: E402
from app.agents.demo_fixtures import (                      # noqa: E402
    DART_FIXTURES_2024Q3,
    DEMO_FX_RATES,
    EDGAR_COGS_2024Q3,
    EDGAR_REVENUE_2024Q3,
    build_demo_deps,
)
from app.agents.state import PipelineState                  # noqa: E402
# fmt: on


def _print_section(title: str) -> None:
    print(f"\n=== {title} ===")  # noqa: T201


def _verify_fixtures() -> None:
    """fixture 정합성: DART 2개 회사, EDGAR 5개 회사, FX 1개 페어."""
    _print_section("Fixture Sanity Check")
    dart_count = len(DART_FIXTURES_2024Q3)
    edgar_rev = len(EDGAR_REVENUE_2024Q3)
    edgar_cogs = len(EDGAR_COGS_2024Q3)
    fx_count = len(DEMO_FX_RATES)

    assert dart_count == 2, f"DART fixture 회사 수 mismatch: {dart_count}"
    assert edgar_rev == 5, f"EDGAR revenue 회사 수 mismatch: {edgar_rev}"
    assert edgar_cogs == 5, f"EDGAR COGS 회사 수 mismatch: {edgar_cogs}"
    assert fx_count >= 1, f"FX rate 누락: {fx_count}"

    print(f"  DART 회사: {dart_count} (SK Hynix, Samsung)")  # noqa: T201
    print(f"  EDGAR revenue: {edgar_rev}, COGS: {edgar_cogs} (MU, NVDA, AMD, INTC, TSM)")  # noqa: T201
    print(f"  FX rates: {fx_count} (KRW/USD)")  # noqa: T201


async def _warm_pipeline() -> dict[str, Any]:
    """LangGraph 빌드 + 데모 deps 로 1회 실행 → 결과 요약 반환.

    Returns:
        {
            'topology': {nodes, edges},
            'edge_metrics': N,
            'reconciliation_errors': N,
            'duration_s': float,
        }
    """
    _print_section("LangGraph Warm Run")

    deps = build_demo_deps()
    graph = build_graph()

    initial_state = PipelineState(
        sector="memory_semiconductor",
        target_quarter="2024Q3",
        as_of_date=datetime.now(UTC),
        is_backtest=False,
        run_id="seed-demo",
        topology=None,
        raw_data=None,
        quantified=None,
        reconciliation_errors=[],
        confidence_map={},
        trace_events=[],
    )
    config: dict[str, Any] = {
        "configurable": {"thread_id": "seed-demo", "deps": deps},
    }

    started = time.perf_counter()
    final_state: dict[str, Any] = {}
    async for chunk in graph.astream(
        cast(Any, initial_state), config=cast(Any, config), stream_mode="values"
    ):
        final_state = cast(dict[str, Any], chunk)
    duration = time.perf_counter() - started

    topology = final_state.get("topology") or {}
    nodes = topology.get("nodes", [])
    edges = topology.get("edges", [])
    quantified = final_state.get("quantified") or {}
    edge_metrics = quantified.get("edge_metrics", [])
    recon_errors = final_state.get("reconciliation_errors", []) or []

    print(f"  Topology nodes: {len(nodes)}")  # noqa: T201
    print(f"  Topology edges: {len(edges)}")  # noqa: T201
    print(f"  Edge metrics: {len(edge_metrics)}")  # noqa: T201
    print(f"  Reconciliation errors: {len(recon_errors)}")  # noqa: T201
    print(f"  Duration: {duration:.2f}s")  # noqa: T201

    # 합격 가드
    assert len(nodes) >= 5, f"토폴로지 노드 부족: {len(nodes)} < 5"
    assert len(edges) >= 3, f"토폴로지 엣지 부족: {len(edges)} < 3"
    assert len(edge_metrics) >= 1, "edge_metrics 비어있음 - QuantEstimator 미실행 의심"

    return {
        "topology": {"nodes": len(nodes), "edges": len(edges)},
        "edge_metrics": len(edge_metrics),
        "reconciliation_errors": len(recon_errors),
        "duration_s": round(duration, 3),
    }


async def main() -> int:
    print("ValueChain AI - Demo Seed & Cache Warm")  # noqa: T201
    print(f"Started: {datetime.now(UTC).isoformat()}")  # noqa: T201

    _verify_fixtures()

    try:
        summary = await _warm_pipeline()
    except (AssertionError, Exception) as exc:
        print(f"\n[FAIL] Pipeline warm failed: {exc!r}")  # noqa: T201
        return 1

    _print_section("Summary")
    for k, v in summary.items():
        print(f"  {k}: {v}")  # noqa: T201

    print("\n[OK] Demo cache warmed - cold-start avoided.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
