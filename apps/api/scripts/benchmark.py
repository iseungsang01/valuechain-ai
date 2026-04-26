"""성능 벤치마크 - TTFGraph + 첫 SSE 청크 SLA 측정 (T4.3).

측정 지표:
1. **first_chunk_s** - POST /api/runs 응답부터 첫 SSE 청크까지의 시간
2. **ttf_graph_s** - 첫 SSE 청크부터 partial_graph(nodes 포함) 가 도착할 때까지의 시간
3. **total_s** - 스트림 전체 종료까지의 시간
4. **events_count** - 송출된 SSE 이벤트 총 개수

SLA (architecture.md §10 T4.3):
- TTFGraph p50 < 30s, p95 < 60s
- 첫 SSE 청크 < 3s

실행:
    cd apps/api
    .\.venv\Scripts\python.exe scripts\benchmark.py --runs 5
    .\.venv\Scripts\python.exe scripts\benchmark.py --runs 5 --remote http://localhost:8000
    .\.venv\Scripts\python.exe scripts\benchmark.py --runs 5 --no-assert  # SLA 위반해도 0 종료

종료 코드:
    0: 모든 SLA 충족 (또는 --no-assert)
    1: SLA 위반 (적어도 하나의 지표가 한도 초과)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# scripts/ 가 apps/api 기준 sibling - import path 보정
APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

# ---- SLA 한도 (architecture.md §10 T4.3) ----
SLA_FIRST_CHUNK_MAX_S = 3.0
SLA_TTFG_P50_MAX_S = 30.0
SLA_TTFG_P95_MAX_S = 60.0


@dataclass
class BenchmarkResult:
    first_chunk_s: float
    ttf_graph_s: float
    total_s: float
    events_count: int

    def as_row(self, idx: int) -> str:
        return (
            f"  Run {idx + 1:>2}: first_chunk={self.first_chunk_s:6.3f}s | "
            f"ttf_graph={self.ttf_graph_s:6.3f}s | "
            f"total={self.total_s:6.3f}s | events={self.events_count:>3}"
        )


# ============================================================
# 측정 - in-process (TestClient)
# ============================================================


def _run_inprocess(payload: dict[str, str]) -> BenchmarkResult:
    """단일 측정 - FastAPI TestClient + 데모 deps.

    한 프로세스 안에서 실행되므로 네트워크 latency 0. 파이프라인 자체 성능 측정용.
    """
    client = TestClient(app)
    started = time.perf_counter()

    # 1. POST /api/runs → run_id
    create_resp = client.post("/api/runs", json=payload)
    create_resp.raise_for_status()
    run_id = create_resp.json()["run_id"]
    post_done = time.perf_counter()

    # 2. GET stream
    first_chunk_at: float | None = None
    ttfg_at: float | None = None
    events_count = 0

    with client.stream("GET", f"/api/runs/{run_id}/stream") as resp:
        resp.raise_for_status()

        current: dict[str, str] = {}
        for line in resp.iter_lines():
            now = time.perf_counter()
            if first_chunk_at is None:
                first_chunk_at = now
            if not line.strip():
                if current:
                    events_count += 1
                    if ttfg_at is None and current.get("event") == "graph_update":
                        try:
                            data = json.loads(current.get("data", "{}"))
                        except json.JSONDecodeError:
                            data = {}
                        partial = (data.get("payload") or {}).get(
                            "partial_graph"
                        )
                        if (
                            isinstance(partial, dict)
                            and isinstance(partial.get("nodes"), list)
                            and len(partial["nodes"]) > 0
                        ):
                            ttfg_at = now
                    current = {}
                continue
            if line.startswith(":"):
                continue
            if ":" not in line:
                continue
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
            current[field.strip()] = value

    finished = time.perf_counter()

    # 첫 청크 미수신 → POST 응답 직후로 fallback (방어적)
    first_chunk = (first_chunk_at or post_done) - post_done
    # ttf_graph 미수신 → total 로 폴백 (실패 신호)
    ttf_graph = (ttfg_at or finished) - (first_chunk_at or post_done)
    total = finished - started

    return BenchmarkResult(
        first_chunk_s=round(first_chunk, 4),
        ttf_graph_s=round(ttf_graph, 4),
        total_s=round(total, 4),
        events_count=events_count,
    )


# ============================================================
# 측정 - remote (실 운영 서버)
# ============================================================


async def _run_remote(
    base_url: str, payload: dict[str, str]
) -> BenchmarkResult:
    """단일 측정 - 실 운영 서버에 httpx 로 요청.

    네트워크 latency 포함, 운영 환경 SLA 검증용.
    """
    timeout = httpx.Timeout(120.0, connect=10.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        started = time.perf_counter()
        create_resp = await client.post("/api/runs", json=payload)
        create_resp.raise_for_status()
        run_id = create_resp.json()["run_id"]
        post_done = time.perf_counter()

        first_chunk_at: float | None = None
        ttfg_at: float | None = None
        events_count = 0

        async with client.stream(
            "GET",
            f"/api/runs/{run_id}/stream",
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()

            current: dict[str, str] = {}
            async for line in resp.aiter_lines():
                now = time.perf_counter()
                if first_chunk_at is None:
                    first_chunk_at = now
                if not line.strip():
                    if current:
                        events_count += 1
                        if (
                            ttfg_at is None
                            and current.get("event") == "graph_update"
                        ):
                            try:
                                data = json.loads(current.get("data", "{}"))
                            except json.JSONDecodeError:
                                data = {}
                            partial = (data.get("payload") or {}).get(
                                "partial_graph"
                            )
                            if (
                                isinstance(partial, dict)
                                and isinstance(partial.get("nodes"), list)
                                and len(partial["nodes"]) > 0
                            ):
                                ttfg_at = now
                        current = {}
                    continue
                if line.startswith(":"):
                    continue
                if ":" not in line:
                    continue
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
                current[field.strip()] = value

        finished = time.perf_counter()

        first_chunk = (first_chunk_at or post_done) - post_done
        ttf_graph = (ttfg_at or finished) - (first_chunk_at or post_done)
        total = finished - started

        return BenchmarkResult(
            first_chunk_s=round(first_chunk, 4),
            ttf_graph_s=round(ttf_graph, 4),
            total_s=round(total, 4),
            events_count=events_count,
        )


# ============================================================
# 통계 집계
# ============================================================


def _percentile(values: list[float], p: float) -> float:
    """간이 percentile - 정렬 후 인덱스 보간 (numpy 의존성 회피)."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_v) - 1)
    frac = k - lo
    return sorted_v[lo] * (1 - frac) + sorted_v[hi] * frac


@dataclass
class Stats:
    p50: float
    p95: float
    avg: float
    min_v: float
    max_v: float

    def __str__(self) -> str:
        return (
            f"p50={self.p50:.3f}s | p95={self.p95:.3f}s | "
            f"avg={self.avg:.3f}s | min={self.min_v:.3f}s | max={self.max_v:.3f}s"
        )


def _compute_stats(values: list[float]) -> Stats:
    return Stats(
        p50=round(_percentile(values, 0.50), 4),
        p95=round(_percentile(values, 0.95), 4),
        avg=round(statistics.mean(values), 4) if values else 0.0,
        min_v=round(min(values), 4) if values else 0.0,
        max_v=round(max(values), 4) if values else 0.0,
    )


# ============================================================
# SLA 평가
# ============================================================


def _evaluate_sla(
    first_chunk_stats: Stats, ttfg_stats: Stats
) -> tuple[bool, list[str]]:
    """모든 SLA 충족 여부 + 위반 목록."""
    violations: list[str] = []

    if first_chunk_stats.max_v > SLA_FIRST_CHUNK_MAX_S:
        violations.append(
            f"first_chunk max {first_chunk_stats.max_v:.3f}s > "
            f"SLA {SLA_FIRST_CHUNK_MAX_S}s"
        )

    if ttfg_stats.p50 > SLA_TTFG_P50_MAX_S:
        violations.append(
            f"ttf_graph p50 {ttfg_stats.p50:.3f}s > SLA {SLA_TTFG_P50_MAX_S}s"
        )

    if ttfg_stats.p95 > SLA_TTFG_P95_MAX_S:
        violations.append(
            f"ttf_graph p95 {ttfg_stats.p95:.3f}s > SLA {SLA_TTFG_P95_MAX_S}s"
        )

    return (len(violations) == 0, violations)


# ============================================================
# 메인
# ============================================================


async def _amain(args: argparse.Namespace) -> int:
    payload: dict[str, str] = {
        "sector": args.sector,
        "target_quarter": args.quarter,
    }

    print(f"\nValueChain AI - Performance Benchmark")  # noqa: T201
    print(f"  mode: {'remote ' + args.remote if args.remote else 'in-process'}")  # noqa: T201
    print(f"  runs: {args.runs}")  # noqa: T201
    print(f"  payload: {payload}")  # noqa: T201

    # Warm 1회 - cold start 효과 제거
    print("\n[warmup]")  # noqa: T201
    if args.remote:
        warm = await _run_remote(args.remote, payload)
    else:
        warm = _run_inprocess(payload)
    print(f"  {warm.as_row(-1).strip()}")  # noqa: T201

    # 본 측정
    print(f"\n[measurement runs={args.runs}]")  # noqa: T201
    results: list[BenchmarkResult] = []
    for i in range(args.runs):
        if args.remote:
            r = await _run_remote(args.remote, payload)
        else:
            r = _run_inprocess(payload)
        results.append(r)
        print(r.as_row(i))  # noqa: T201

    # 통계
    first_chunks = [r.first_chunk_s for r in results]
    ttfgs = [r.ttf_graph_s for r in results]
    totals = [r.total_s for r in results]

    fc_stats = _compute_stats(first_chunks)
    ttfg_stats = _compute_stats(ttfgs)
    total_stats = _compute_stats(totals)

    print("\n[stats]")  # noqa: T201
    print(f"  first_chunk: {fc_stats}")  # noqa: T201
    print(f"  ttf_graph  : {ttfg_stats}")  # noqa: T201
    print(f"  total      : {total_stats}")  # noqa: T201

    # SLA 검증
    print("\n[sla]")  # noqa: T201
    print(f"  first_chunk max ≤ {SLA_FIRST_CHUNK_MAX_S}s")  # noqa: T201
    print(f"  ttf_graph p50  ≤ {SLA_TTFG_P50_MAX_S}s")  # noqa: T201
    print(f"  ttf_graph p95  ≤ {SLA_TTFG_P95_MAX_S}s")  # noqa: T201

    ok, violations = _evaluate_sla(fc_stats, ttfg_stats)
    if ok:
        print("  [PASS] all SLAs met")  # noqa: T201
    else:
        print("  [FAIL] SLA violations:")  # noqa: T201
        for v in violations:
            print(f"    - {v}")  # noqa: T201

    # JSON 출력 (CI 친화)
    if args.json:
        report = {
            "mode": "remote" if args.remote else "in-process",
            "runs": args.runs,
            "first_chunk": fc_stats.__dict__,
            "ttf_graph": ttfg_stats.__dict__,
            "total": total_stats.__dict__,
            "sla_pass": ok,
            "violations": violations,
            "raw_results": [
                {
                    "first_chunk_s": r.first_chunk_s,
                    "ttf_graph_s": r.ttf_graph_s,
                    "total_s": r.total_s,
                    "events_count": r.events_count,
                }
                for r in results
            ],
        }
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\n  JSON report: {args.json}")  # noqa: T201

    if not ok and not args.no_assert:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ValueChain AI benchmark (T4.3)")
    p.add_argument("--runs", type=int, default=5, help="측정 반복 수 (default: 5)")
    p.add_argument(
        "--sector",
        type=str,
        default="memory_semiconductor",
        help="섹터 (default: memory_semiconductor)",
    )
    p.add_argument(
        "--quarter",
        type=str,
        default="2024Q3",
        help="분기 (default: 2024Q3)",
    )
    p.add_argument(
        "--remote",
        type=str,
        default=None,
        help="원격 서버 URL. 미지정 시 in-process TestClient",
    )
    p.add_argument(
        "--no-assert",
        action="store_true",
        help="SLA 위반해도 종료 코드 0 (CI 검증 회피용)",
    )
    p.add_argument(
        "--json", type=str, default=None, help="JSON report 출력 경로"
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
