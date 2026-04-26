"""에러 핸들러 분류 + FastAPI 통합 검증 (T4.2).

검증 범위:
1. classify_exception - 모든 도메인 예외 → 정확한 카테고리/retriable
2. classify_exception - httpx 401/429/5xx 분기
3. ErrorClassification.to_payload - SSE 페이로드 형식
4. FastAPI 핸들러 - HTTPException 외 도메인 예외도 JSON 응답으로 변환
5. SSE 스트림에서 도메인 예외 발생 시 분류된 페이로드 송출
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.middleware.error_handler import (
    ErrorCategory,
    classify_exception,
    register_exception_handlers,
)
from app.schemas.grounded import CitationRecord
from app.services.validation import GroundingError, TimeIsolationError
from app.sources.dart import DartClientError
from app.sources.edgar import EdgarClientError
from app.sources.fx import EcosClientError


# ============================================================
# classify_exception - 도메인 예외
# ============================================================


def test_classify_grounding_error_is_hallucination_not_retriable() -> None:
    err = GroundingError(missing_ids=[uuid4(), uuid4()])
    result = classify_exception(err)
    assert result.category is ErrorCategory.HALLUCINATION
    assert result.retriable is False
    assert result.error_code == "LLM_HALLUCINATION_BLOCKED"
    assert result.http_status == 422
    # 사용자 메시지에 민감 정보(uuid) 노출 X
    assert "출처가 없는" in result.user_message
    assert str(err.missing_ids[0]) not in result.user_message
    # details 에는 노출
    assert "missing_ids" in result.details


def test_classify_time_isolation_error_breach() -> None:
    leak = CitationRecord(
        id=uuid4(),
        publish_date=date(2025, 1, 1),
        source_type="DART",
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250101",
    )
    err = TimeIsolationError(offending=[leak], as_of_date=date(2024, 12, 31))
    result = classify_exception(err)
    assert result.category is ErrorCategory.TIME_ISOLATION
    assert result.retriable is False
    assert result.http_status == 422
    assert result.error_code == "TIME_ISOLATION_BREACH"
    assert "백테스트" in result.user_message
    assert result.details["as_of_date"] == "2024-12-31"
    assert result.details["offending_count"] == 1


def test_classify_dart_client_error_is_external_retriable() -> None:
    err = DartClientError("DART error 010: 조회된 데이터가 없습니다.")
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True
    assert result.error_code == "DART_API_ERROR"
    assert result.http_status == 502
    assert "DART" in result.user_message


def test_classify_edgar_client_error_is_external_retriable() -> None:
    err = EdgarClientError("EDGAR 503 timeout")
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True
    assert result.error_code == "EDGAR_API_ERROR"


def test_classify_ecos_client_error_is_external_retriable() -> None:
    err = EcosClientError("ECOS 환율 데이터 없음")
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True
    assert result.error_code == "ECOS_API_ERROR"


# ============================================================
# classify_exception - httpx 분기
# ============================================================


def _mk_httpx_status_error(status: int, retry_after: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://opendart.fss.or.kr/api/test")
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status, request=request, headers=headers)
    return httpx.HTTPStatusError(
        f"{status} error", request=request, response=response
    )


def test_classify_httpx_401_is_auth_not_retriable() -> None:
    err = _mk_httpx_status_error(401)
    result = classify_exception(err)
    assert result.category is ErrorCategory.AUTH
    assert result.retriable is False
    assert result.error_code == "EXTERNAL_AUTH_FAILED"
    assert result.http_status == 502
    assert "API 키" in result.user_message


def test_classify_httpx_403_is_auth_not_retriable() -> None:
    err = _mk_httpx_status_error(403)
    result = classify_exception(err)
    assert result.category is ErrorCategory.AUTH
    assert result.retriable is False


def test_classify_httpx_429_is_rate_limit_retriable() -> None:
    err = _mk_httpx_status_error(429, retry_after="30")
    result = classify_exception(err)
    assert result.category is ErrorCategory.RATE_LIMIT
    assert result.retriable is True
    assert result.error_code == "EXTERNAL_RATE_LIMIT"
    assert result.details["retry_after"] == "30"
    assert "한도" in result.user_message


def test_classify_httpx_500_is_external_retriable() -> None:
    err = _mk_httpx_status_error(500)
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True
    assert result.error_code == "EXTERNAL_API_ERROR"


def test_classify_httpx_503_is_external_retriable() -> None:
    err = _mk_httpx_status_error(503)
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True


def test_classify_httpx_timeout_is_external_retriable() -> None:
    err = httpx.TimeoutException("read timeout", request=MagicMock())
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True
    assert result.error_code == "EXTERNAL_NETWORK_ERROR"
    assert result.http_status == 504


def test_classify_httpx_connect_error_is_external_retriable() -> None:
    err = httpx.ConnectError("connection refused")
    result = classify_exception(err)
    assert result.category is ErrorCategory.EXTERNAL_API
    assert result.retriable is True


# ============================================================
# classify_exception - 폴백
# ============================================================


def test_classify_value_error_is_validation_not_retriable() -> None:
    err = ValueError("invalid quarter format")
    result = classify_exception(err)
    assert result.category is ErrorCategory.VALIDATION
    assert result.retriable is False
    assert result.http_status == 400
    assert result.error_code == "VALUE_ERROR"


def test_classify_unknown_exception_is_internal_not_retriable() -> None:
    err = RuntimeError("unexpected boom")
    result = classify_exception(err)
    assert result.category is ErrorCategory.INTERNAL
    assert result.retriable is False
    assert result.http_status == 500
    assert result.error_code == "INTERNAL_ERROR"


def test_to_payload_excludes_internal_details() -> None:
    """to_payload 는 details (운영 로그용) 를 노출하지 않음."""
    err = GroundingError(missing_ids=[uuid4()])
    result = classify_exception(err)
    payload = result.to_payload()
    assert set(payload.keys()) == {"category", "error_code", "message", "retriable"}
    assert "details" not in payload
    assert "missing_ids" not in payload


# ============================================================
# FastAPI 통합 - register_exception_handlers
# ============================================================


def _build_test_app() -> FastAPI:
    """register_exception_handlers 단독 검증용 미니 앱."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-grounding")
    def _ground() -> dict[str, str]:
        raise GroundingError(missing_ids=[uuid4()])

    @app.get("/raise-time-iso")
    def _time() -> dict[str, str]:
        raise TimeIsolationError(offending=[], as_of_date=date(2024, 1, 1))

    @app.get("/raise-dart")
    def _dart() -> dict[str, str]:
        raise DartClientError("DART 503")

    @app.get("/raise-edgar")
    def _edgar() -> dict[str, str]:
        raise EdgarClientError("EDGAR 500")

    @app.get("/raise-httpx-401")
    def _h401() -> dict[str, str]:
        raise _mk_httpx_status_error(401)

    @app.get("/raise-httpx-429")
    def _h429() -> dict[str, str]:
        raise _mk_httpx_status_error(429, retry_after="60")

    @app.get("/raise-runtime")
    def _runtime() -> dict[str, str]:
        raise RuntimeError("boom")

    @app.get("/raise-http-exception")
    def _http_exc() -> dict[str, str]:
        # FastAPI 기본 처리되어야 - 우리 핸들러가 가로채지 않음
        raise HTTPException(status_code=404, detail="not found")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_test_app(), raise_server_exceptions=False)


def test_handler_grounding_returns_422_with_payload(client: TestClient) -> None:
    resp = client.get("/raise-grounding")
    assert resp.status_code == 422
    body = resp.json()
    assert body["category"] == "hallucination"
    assert body["retriable"] is False
    assert body["error_code"] == "LLM_HALLUCINATION_BLOCKED"
    assert "출처" in body["message"]


def test_handler_time_isolation_returns_422(client: TestClient) -> None:
    resp = client.get("/raise-time-iso")
    assert resp.status_code == 422
    body = resp.json()
    assert body["category"] == "time_isolation"
    assert body["retriable"] is False


def test_handler_dart_returns_502(client: TestClient) -> None:
    resp = client.get("/raise-dart")
    assert resp.status_code == 502
    body = resp.json()
    assert body["category"] == "external_api"
    assert body["error_code"] == "DART_API_ERROR"
    assert body["retriable"] is True


def test_handler_edgar_returns_502(client: TestClient) -> None:
    resp = client.get("/raise-edgar")
    assert resp.status_code == 502
    body = resp.json()
    assert body["error_code"] == "EDGAR_API_ERROR"


def test_handler_httpx_401_returns_502(client: TestClient) -> None:
    resp = client.get("/raise-httpx-401")
    assert resp.status_code == 502
    body = resp.json()
    assert body["category"] == "auth"
    assert body["retriable"] is False


def test_handler_httpx_429_returns_503_retriable(client: TestClient) -> None:
    resp = client.get("/raise-httpx-429")
    assert resp.status_code == 503
    body = resp.json()
    assert body["category"] == "rate_limit"
    assert body["retriable"] is True


def test_handler_runtime_returns_500_internal(client: TestClient) -> None:
    resp = client.get("/raise-runtime")
    assert resp.status_code == 500
    body = resp.json()
    assert body["category"] == "internal"
    assert body["retriable"] is False


def test_handler_does_not_intercept_http_exception(client: TestClient) -> None:
    """FastAPI HTTPException 은 우리 핸들러 통과 → FastAPI 기본 응답 형식 유지."""
    resp = client.get("/raise-http-exception")
    assert resp.status_code == 404
    body = resp.json()
    assert body == {"detail": "not found"}


# ============================================================
# Pydantic Validation 통합
# ============================================================


def test_handler_pydantic_validation_returns_422_with_friendly_payload() -> None:
    """RequestValidationError → 422 (표준 status) + 친절한 페이로드 포맷."""
    from main import app

    client = TestClient(app, raise_server_exceptions=False)
    # POST /api/runs 에 필수 필드 누락 → FastAPI 표준 422 유지하되 페이로드는 분류된 형태
    resp = client.post("/api/runs", json={})
    assert resp.status_code == 422
    body = resp.json()
    # 우리의 분류된 페이로드 형식
    assert body["category"] == "validation"
    assert body["error_code"] == "REQUEST_VALIDATION_FAILED"
    assert body["retriable"] is False
    assert "validation_errors" in body
    # 운영자가 디버깅 가능한 errors 정보 포함
    assert isinstance(body["validation_errors"], list)
    assert len(body["validation_errors"]) > 0


# ============================================================
# Stream 통합 - 파이프라인 예외 발생 시
# ============================================================


def test_stream_propagates_classified_error_payload() -> None:
    """SSE 파이프라인 안에서 GroundingError 가 발생하면 분류된 페이로드 전송."""
    import json

    from app.services.runs import InMemoryRunStore, get_run_store
    from main import app

    store = InMemoryRunStore()

    # 의도적으로 GroundingError 를 raise 하는 deps 주입은 복잡 - 대신
    # graph.astream 자체를 monkey-patch.
    from app.services import stream as stream_module

    async def boom(*_: Any, **__: Any) -> Any:
        # async generator 처럼 동작 → 첫 chunk 에서 예외
        raise GroundingError(missing_ids=[uuid4()])
        yield  # type: ignore[unreachable]

    class _BoomGraph:
        def astream(self, *_: Any, **__: Any) -> Any:
            return boom()

    original_build = stream_module.build_graph
    stream_module.build_graph = lambda: _BoomGraph()  # type: ignore[assignment]
    app.dependency_overrides[get_run_store] = lambda: store

    try:
        client = TestClient(app)
        create_resp = client.post(
            "/api/runs",
            json={"sector": "memory_semiconductor", "target_quarter": "2024Q3"},
        )
        run_id = create_resp.json()["run_id"]

        with client.stream("GET", f"/api/runs/{run_id}/stream") as resp:
            assert resp.status_code == 200
            error_events: list[dict[str, Any]] = []
            current: dict[str, str] = {}
            for line in resp.iter_lines():
                if not line.strip():
                    if current.get("event") == "error":
                        error_events.append(json.loads(current.get("data", "{}")))
                    current = {}
                    continue
                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
                current[field.strip()] = value

            assert len(error_events) >= 1, "분류된 error event 미송출"
            err = error_events[0]
            assert err["type"] == "error"
            assert err["payload"]["category"] == "hallucination"
            assert err["payload"]["error_code"] == "LLM_HALLUCINATION_BLOCKED"
            assert err["payload"]["retriable"] is False
            # 민감 정보 노출 X
            assert "uuid" not in err["payload"].get("message", "").lower()

        # Run 상태가 'failed' + 친절한 메시지로 갱신
        record = store.get(run_id)
        assert record is not None
        assert record.status == "failed"
        assert record.error_message is not None
        assert "출처" in record.error_message

    finally:
        stream_module.build_graph = original_build
        app.dependency_overrides.clear()
