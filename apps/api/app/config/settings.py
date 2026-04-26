"""Pydantic Settings - 환경변수 검증 + 타입 안전성."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """모든 환경변수는 여기에서 단일 진입점으로 관리.

    .env 파일에서 자동 로드. 실패 시 명확한 에러 메시지.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),  # apps/api 또는 monorepo root
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 알 수 없는 env 무시
    )

    # ---------- 환경 ----------
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="배포 환경 구분",
    )

    # ---------- Supabase ----------
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_service_role_key: str = Field(
        default="",
        description="Service role key (백엔드 전용, NEVER expose to frontend)",
    )
    database_url: str = Field(
        default="",
        description="Postgres direct connection URL",
    )

    # ---------- LLM ----------
    gemini_api_key: str = Field(default="", description="Google Gemini API key")

    # ---------- Data Sources ----------
    dart_api_key: str = Field(default="", description="DART OpenAPI key (한국 전자공시)")
    sec_user_agent: str = Field(
        default="ValueChain AI Research contact@example.com",
        description="SEC EDGAR 등록 User-Agent (이메일 포함 필수)",
    )
    ecos_api_key: str = Field(default="", description="한국은행 ECOS API key (환율)")

    # ---------- CORS ----------
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="CORS 허용 오리진 (콤마 구분)",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """싱글톤 Settings 객체. lru_cache로 한 번만 로드."""
    return Settings()
