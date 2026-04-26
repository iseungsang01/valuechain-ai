# Supabase Setup (ValueChain AI)

> Phase 1 MVP의 데이터 레이어. 실제 적용은 사용자가 Supabase 프로젝트를 생성한 후 수행.

## 사전 요구사항

- Node.js 20+ (`npx supabase` 사용)
- Supabase 무료 프로젝트 (https://app.supabase.com)
- (선택) Docker Desktop - 로컬 개발 시 필요. 없으면 클라우드 직접 push 가능.

## 디렉토리 구조

```
supabase/
├── config.toml              # 프로젝트 설정 (supabase init이 생성)
├── migrations/
│   └── 20260426053252_initial_schema.sql  # 8개 테이블 + RLS
├── seed.sql                 # 메모리 반도체 7개 기업 + 11개 엣지 시드
└── README.md                # 본 문서
```

## 적용 방법

### Option A: 클라우드 Supabase에 직접 push (권장 - Docker 불필요)

```powershell
# 1. Supabase 프로젝트 생성 (https://app.supabase.com)
#    - 새 프로젝트 → Project Ref와 DB password 메모

# 2. 프로젝트 ref와 연동
npx supabase login        # 처음 1회 (브라우저 OAuth)
npx supabase link --project-ref <YOUR_PROJECT_REF>

# 3. 마이그레이션 push
npx supabase db push      # migrations/*.sql 모두 적용

# 4. 시드 데이터 적용
npx supabase db execute --file supabase/seed.sql
# 또는 (CLI 버전에 따라):
psql $env:DATABASE_URL -f supabase/seed.sql

# 5. 검증
psql $env:DATABASE_URL -c "select count(*) from public.companies;"
# → 7
psql $env:DATABASE_URL -c "select count(*) from public.edges;"
# → 11
```

### Option B: 로컬 개발 (Docker 필요)

```powershell
# 1. Docker Desktop 설치 후 실행
# 2. 로컬 stack 기동
npx supabase start

# 3. 마이그레이션 + seed 자동 적용
npx supabase db reset

# 4. Studio 확인
# http://localhost:54323 접속 → Tables 확인
```

## 환경 변수

`.env` 파일에 다음 키들을 채워야 백엔드/프론트가 동작합니다:

```bash
# Project Settings > API에서 복사
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...    # 백엔드 전용, 절대 노출 X
DATABASE_URL=postgresql://postgres:PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres

# 프론트엔드용 (NEXT_PUBLIC_ prefix는 브라우저 노출됨)
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

## 보안 정책 요약

- **RLS by default**: public schema 모든 테이블에 RLS 활성화
- **Phase 1 정책**: 정책 없음 = deny-all. backend service_role만 접근 (RLS bypass)
- **권한 회수**: anon/authenticated 역할의 모든 권한 명시적 revoke (이중 차단)
- **V2에서 추가**: 사용자 인증 도입 시 workspace_id 기반 정책 추가

## 스키마 변경 절차

1. SQL을 직접 실행하지 말고 `npx supabase migration new <descriptive_name>` 으로 새 파일 생성
2. 새 파일에 SQL 작성
3. `npx supabase db push`로 적용
4. `npx supabase db advisors` (CLI 2.81.3+) 또는 MCP로 보안 검사
