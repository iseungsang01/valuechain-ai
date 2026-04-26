"""에러 분류 + 사용자 친화 메시지 변환 + FastAPI 전역 핸들러 (T4.2).

목표:
1. 도메인별 예외(DartClientError, GroundingError 등)를 카테고리로 통합 분류.
2. SSE 스트림 / HTTP 응답 양쪽에서 같은 분류 결과를 사용 → 일관된 UX.
3. retriable 여부를 명시 → 프론트가 자동 재연결/재시도 결정 가능.
4. 민감 정보(API key, 스택트레이스) 차단 + 운영 로그에는 상세 기록.

설계 원칙 (ADR-005, ADR-008 정합):
- "환각(GroundingError)"은 retriable=False - 같은 입력으로 재시도해도 같은 결과.
- "외부 API 401 (인증)"은 retriable=False - 키 갱신 필요.
- "외부 API 429 (Rate limit)"은 retriable=True - backoff 후 재시도 가능.
- 알 수 없는 예외는 retriable=False - 기본 안전.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.validation import GroundingError, TimeIsolationError
from app.sources.dart import DartClientError
from app.sources.edgar import EdgarClientError
from app.sources.fx import EcosClientError

logger = logging.getLogger(__name__)

# 422 - "Unprocessable Content" (RFC 9110 갱신, 구 명칭: "Unprocessable Entity").
# starlette 가 두 상수를 모두 노출하지만 ENTITY 는 deprecated. 의존성 변동에 안전하게
# 숫자 리터럴 사용.
_HTTP_422: int = 422


# ============================================================
# 카테고리 + 분류 결과
# ============================================================


class ErrorCategory(str, Enum):
    """프런트가 분기하는 카테고리. SSE error 페이로드 + HTTP 응답 둘 다 동일."""

    AUTH = "auth"  # 401, API key 누락/무효
    RATE_LIMIT = "rate_limit"  # 429
    EXTERNAL_API = "external_api"  # 5xx, network
    HALLUCINATION = "hallucination"  # citation_id 가공 → 차단
    TIME_ISOLATION = "time_isolation"  # 백테스트 시점 위반
    VALIDATION = "validation"  # 입력 검증 실패 (Pydantic)
    INTERNAL = "internal"  # 그 외 (5xx)


@dataclass(frozen=True)
class ErrorClassification:
    """예외 → 사용자 메시지 변환 결과.

    Attributes:
        category: 6 카테고리 중 하나.
        http_status: REST 응답 시 사용할 status code.
        user_message: 한국어 사용자 친화 메시지 (스택트레이스/키 미포함).
        error_code: 프런트에서 분기 가능한 안정 코드 (예: 'DART_AUTH_FAILED').
        retriable: 같은 요청으로 자동 재시도 가능한가?
        details: 운영 로그용 추가 정보 (사용자 노출 X).
    """

    category: ErrorCategory
    http_status: int
    user_message: str
    error_code: str
    retriable: bool
    details: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """SSE error event payload (shared/agents.ts ErrorEvent 와 호환).

        details 는 노출되지 않음 - 별도 logger.exception 으로 기록.
        """
        return {
            "category": self.category.value,
            "error_code": self.error_code,
            "message": self.user_message,
            "retriable": self.retriable,
        }


# ============================================================
# httpx 응답 코드 → 카테고리 매핑
# ============================================================


def _http_status_to_category(http_status: int) -> ErrorCategory:
    if http_status in (401, 403):
        return ErrorCategory.AUTH
    if http_status == 429:
        return ErrorCategory.RATE_LIMIT
    if 500 <= http_status < 600:
        return ErrorCategory.EXTERNAL_API
    return ErrorCategory.EXTERNAL_API


def _classify_httpx_error(exc: httpx.HTTPStatusError) -> ErrorClassification:
    """httpx.HTTPStatusError → 카테고리 추출.

    DART/EDGAR/ECOS adapter 가 raise 하기 전 raise_for_status 단계에서 발생 가능.
    """
    response = exc.response
    http_status = response.status_code
    category = _http_status_to_category(http_status)

    if category is ErrorCategory.AUTH:
        return ErrorClassification(
            category=category,
            http_status=status.HTTP_502_BAD_GATEWAY,  # 외부 API 인증 실패는 GW 5xx 로 추상화
            user_message=(
                "외부 데이터 소스 인증에 실패했습니다. "
                "관리자가 API 키 갱신 후 다시 시도해주세요."
            ),
            error_code="EXTERNAL_AUTH_FAILED",
            retriable=False,
            details={"http_status": http_status, "url": str(response.request.url)},
        )

    if category is ErrorCategory.RATE_LIMIT:
        retry_after = response.headers.get("retry-after")
        return ErrorClassification(
            category=category,
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            user_message=(
                "외부 API 호출 한도에 도달했습니다. "
                "잠시 후 자동으로 재시도됩니다."
            ),
            error_code="EXTERNAL_RATE_LIMIT",
            retriable=True,
            details={
                "http_status": http_status,
                "retry_after": retry_after,
                "url": str(response.request.url),
            },
        )

    return ErrorClassification(
        category=ErrorCategory.EXTERNAL_API,
        http_status=status.HTTP_502_BAD_GATEWAY,
        user_message=(
            "외부 데이터 소스 호출 중 오류가 발생했습니다. "
            "잠시 후 다시 시도해주세요."
        ),
        error_code="EXTERNAL_API_ERROR",
        retriable=True,
        details={"http_status": http_status, "url": str(response.request.url)},
    )


# ============================================================
# 메인 분류 함수 (도메인 예외 → ErrorClassification)
# ============================================================


def classify_exception(exc: BaseException) -> ErrorClassification:
    """모든 예외를 사용자 표시용 ErrorClassification 으로 변환.

    어댑터(DART/EDGAR/ECOS) → 도메인(Validation) → 일반 순서로 매칭.
    """
    # ---- LLM 환각 차단 (citation_id 가공) -----------------
    if isinstance(exc, GroundingError):
        return ErrorClassification(
            category=ErrorCategory.HALLUCINATION,
            http_status=_HTTP_422,
            user_message=(
                "AI가 출처가 없는 수치를 생성하려고 시도했습니다 "
                "(가공된 인용 차단됨). 신뢰성을 위해 결과를 거부했습니다."
            ),
            error_code="LLM_HALLUCINATION_BLOCKED",
            retriable=False,
            details={"missing_ids": [str(i) for i in exc.missing_ids]},
        )

    # ---- 백테스트 시점 위반 -----------------------------
    if isinstance(exc, TimeIsolationError):
        return ErrorClassification(
            category=ErrorCategory.TIME_ISOLATION,
            http_status=_HTTP_422,
            user_message=(
                "백테스트 무결성 위반: 분석 시점 이후의 데이터가 사용되었습니다. "
                "출처 시점을 확인해주세요."
            ),
            error_code="TIME_ISOLATION_BREACH",
            retriable=False,
            details={
                "as_of_date": exc.as_of_date.isoformat(),
                "offending_count": len(exc.offending),
            },
        )

    # ---- 외부 API 도메인 예외 ---------------------------
    if isinstance(exc, DartClientError):
        return ErrorClassification(
            category=ErrorCategory.EXTERNAL_API,
            http_status=status.HTTP_502_BAD_GATEWAY,
            user_message=(
                "DART 공시 데이터 조회에 실패했습니다. "
                "잠시 후 다시 시도해주세요."
            ),
            error_code="DART_API_ERROR",
            retriable=True,
            details={"source": "DART", "raw": str(exc)[:200]},
        )

    if isinstance(exc, EdgarClientError):
        return ErrorClassification(
            category=ErrorCategory.EXTERNAL_API,
            http_status=status.HTTP_502_BAD_GATEWAY,
            user_message=(
                "SEC EDGAR 공시 데이터 조회에 실패했습니다. "
                "잠시 후 다시 시도해주세요."
            ),
            error_code="EDGAR_API_ERROR",
            retriable=True,
            details={"source": "EDGAR", "raw": str(exc)[:200]},
        )

    if isinstance(exc, EcosClientError):
        return ErrorClassification(
            category=ErrorCategory.EXTERNAL_API,
            http_status=status.HTTP_502_BAD_GATEWAY,
            user_message=(
                "환율 데이터 조회에 실패했습니다. "
                "잠시 후 다시 시도해주세요."
            ),
            error_code="ECOS_API_ERROR",
            retriable=True,
            details={"source": "ECOS", "raw": str(exc)[:200]},
        )

    # ---- httpx 직접 예외 --------------------------------
    if isinstance(exc, httpx.HTTPStatusError):
        return _classify_httpx_error(exc)

    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError | httpx.NetworkError):
        return ErrorClassification(
            category=ErrorCategory.EXTERNAL_API,
            http_status=status.HTTP_504_GATEWAY_TIMEOUT,
            user_message=(
                "외부 데이터 소스에 연결할 수 없습니다. "
                "네트워크 상태를 확인하고 다시 시도해주세요."
            ),
            error_code="EXTERNAL_NETWORK_ERROR",
            retriable=True,
            details={"raw": str(exc)[:200]},
        )

    # ---- 입력 검증 (Pydantic) ---------------------------
    # 422 (FastAPI/Pydantic 표준) 유지 - 클라이언트가 status code 로 분기 가능.
    # 페이로드만 분류된 형태로 변환.
    if isinstance(exc, RequestValidationError):
        return ErrorClassification(
            category=ErrorCategory.VALIDATION,
            http_status=_HTTP_422,
            user_message="요청 형식이 올바르지 않습니다. 입력값을 확인해주세요.",
            error_code="REQUEST_VALIDATION_FAILED",
            retriable=False,
            details={"errors": exc.errors()[:5]},  # 최대 5개만 노출
        )

    if isinstance(exc, ValueError):
        return ErrorClassification(
            category=ErrorCategory.VALIDATION,
            http_status=status.HTTP_400_BAD_REQUEST,
            user_message=f"입력값 오류: {exc!s}",
            error_code="VALUE_ERROR",
            retriable=False,
            details={"raw": str(exc)[:200]},
        )

    # ---- 폴백 (알 수 없는 예외) -------------------------
    return ErrorClassification(
        category=ErrorCategory.INTERNAL,
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        user_message=(
            "예상치 못한 오류가 발생했습니다. "
            "문제가 지속되면 관리자에게 문의해주세요."
        ),
        error_code="INTERNAL_ERROR",
        retriable=False,
        details={"exc_type": type(exc).__name__, "raw": str(exc)[:200]},
    )


# ============================================================
# FastAPI 전역 핸들러 등록
# ============================================================


async def _domain_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """모든 비-HTTPException 도메인 예외를 ErrorClassification 으로 변환."""
    classification = classify_exception(exc)
    logger.exception(
        "request.error",
        extra={
            "path": request.url.path,
            "category": classification.category.value,
            "error_code": classification.error_code,
            "details": classification.details,
        },
    )
    return JSONResponse(
        status_code=classification.http_status,
        content={
            "category": classification.category.value,
            "error_code": classification.error_code,
            "message": classification.user_message,
            "retriable": classification.retriable,
        },
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic 422 → 사용자 친화 400."""
    classification = classify_exception(exc)
    logger.warning(
        "request.validation_failed",
        extra={
            "path": request.url.path,
            "errors": classification.details.get("errors"),
        },
    )
    return JSONResponse(
        status_code=classification.http_status,
        content={
            "category": classification.category.value,
            "error_code": classification.error_code,
            "message": classification.user_message,
            "retriable": classification.retriable,
            "validation_errors": classification.details.get("errors", []),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 도메인 예외 핸들러를 부착.

    main.py 의 create_app() 에서 호출. HTTPException 은 FastAPI 기본 처리 유지
    (FastAPI 가 starlette HTTPException 전용 핸들러를 사전에 등록하기 때문).

    핸들러 등록 순서:
    1. 도메인 예외 (DART/EDGAR/Grounding) - 명시적 클래스 매칭
    2. httpx 예외 - 외부 API 호출 시
    3. Exception (폴백) - Starlette MRO lookup 으로 HTTPException 보다 후순위
    4. RequestValidationError - 사용자 친화 400 변환
    """
    # 도메인 예외 - 광범위하게 catch
    app.add_exception_handler(DartClientError, _domain_exception_handler)
    app.add_exception_handler(EdgarClientError, _domain_exception_handler)
    app.add_exception_handler(EcosClientError, _domain_exception_handler)
    app.add_exception_handler(GroundingError, _domain_exception_handler)
    app.add_exception_handler(TimeIsolationError, _domain_exception_handler)
    app.add_exception_handler(httpx.HTTPStatusError, _domain_exception_handler)
    app.add_exception_handler(httpx.TimeoutException, _domain_exception_handler)
    app.add_exception_handler(httpx.NetworkError, _domain_exception_handler)

    # 폴백 - 알 수 없는 예외도 분류된 형태로 응답.
    # HTTPException 은 FastAPI 가 자체 핸들러를 우선 등록하므로
    # MRO(HTTPException → Exception) 에서 HTTPException 핸들러가 매칭됨.
    app.add_exception_handler(Exception, _domain_exception_handler)

    # Pydantic 422 → 400 (사용자 친화)
    app.add_exception_handler(
        RequestValidationError,
        _validation_exception_handler,  # type: ignore[arg-type]
    )
