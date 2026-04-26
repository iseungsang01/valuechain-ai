"""LangGraph 노드 의존성 주입 (Pipeline Deps).

각 노드(DataCollector, QuantEstimator, Evaluator)가 필요로 하는 외부 자원을
한 곳에 모아서 RunnableConfig.configurable 로 전달.

테스트: in-memory repo + mock 어댑터 주입
프로덕션: 실 Supabase repo + 실 어댑터 주입
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any

from app.db.repository import CompanyRepository, InMemoryRepository
from app.sources.dart import DartClient
from app.sources.edgar import EdgarClient
from app.sources.fx import EcosClient

# 어댑터 팩토리 - 매 호출마다 새 컨텍스트 매니저 생성 (async with 안전)
DartFactory = Callable[[], AbstractAsyncContextManager[DartClient]]
EdgarFactory = Callable[[], AbstractAsyncContextManager[EdgarClient]]
EcosFactory = Callable[[], AbstractAsyncContextManager[EcosClient]]


@dataclass
class PipelineDeps:
    """파이프라인 노드의 모든 외부 의존성 컨테이너.

    Phase 1: repo 는 InMemoryRepository, 어댑터 팩토리는 mock 또는 실 클라이언트.
    """

    repo: CompanyRepository = field(default_factory=InMemoryRepository)
    dart_factory: DartFactory | None = None
    edgar_factory: EdgarFactory | None = None
    ecos_factory: EcosFactory | None = None
    # 정적 시드 - FX 등 사전 로딩 데이터를 노드에 주입
    fx_rates: dict[tuple[str, str], float] = field(default_factory=dict)
    # 추가 메타: run_id 추적 등
    extra: dict[str, Any] = field(default_factory=dict)


def deps_from_config(config: dict[str, Any] | None) -> PipelineDeps:
    """LangGraph 가 노드에 주입하는 RunnableConfig 에서 PipelineDeps 추출.

    config['configurable']['deps'] 에 PipelineDeps 가 들어있어야 함.
    없으면 기본값(in-memory) 으로 생성 - 단 어댑터 팩토리가 없어 실 호출은 실패.
    """
    if not config:
        return PipelineDeps()
    configurable = config.get("configurable") or {}
    deps = configurable.get("deps")
    if isinstance(deps, PipelineDeps):
        return deps
    return PipelineDeps()
