# ValueChain AI

> 공급망 기반 기업 재무 추정 및 예측 에이전트 (SaaS)

투자자, 애널리스트, 기관 리서처를 위한 AI 기반 공급망 정합성 검증 + 미래 수급 충돌 탐지 플랫폼.


두 가지의 측면에서 알파를 낼 수 있는 구조임.

1. 양쪽에 가이던스(상호 매출 추정치)가 맞지 않을 경우, 낮게 매출이 잡힌 기업에는 롱, 덜 매출이 잡힌 기업에는 숏 포지션을 구축할 경우, 이러한 괴리를 기반으로 수익을 낼 수 있는 구조임.  
(가이던스의 경우, dart api, edgar api 대신 bloomberg나 Fnguide 등 유료 api를 수집하거나 직접 레포트를 읽게 하고 애널리스트 별 추정치의 range나 평균치 정도를 가져오면 될 것임) 
2. 그래프 사이즈 확장하여, 작은 기업 단으로 들어가면 괴리가 기하급수적으로 커질 것이며, 어닝 서프나 어닝 쇼크 예측에 효과적일 것임.

https://valuechain-ai.vercel.app/

## 핵심 가치

- **Network Consistency**: 공급망 전체에서 A의 매출 ≈ B의 매입 정합성 자동 검증
- **Forward Conflict Detection**: 전·후방 가이던스 모순으로 미래 수급 불균형(알파) 포착
- **Self-Optimization**: 백테스트로 추론 로직을 스스로 개선하는 자가 진화 시스템

## 아키텍처

```
[Next.js 16 Web] ←─SSE─→ [FastAPI Gateway] ←──→ [LangGraph 4 Agents]
                                  │                       │
                                  │              ┌────────┼────────┐
                                  │              ↓        ↓        ↓
                                  │         [DART API][EDGAR][FX/ECOS]
                                  ↓
                          [Supabase Postgres + pgvector]
```

자세한 설계: [.sisyphus/plans/valuechain-ai-architecture.md](./.sisyphus/plans/valuechain-ai-architecture.md)

## 모노레포 구조

```
.
├── apps/
│   ├── web/          # Next.js 16 + React 19 + Tailwind v4 + React Flow
│   └── api/          # FastAPI + LangGraph + Google Gemini (Python 3.11)
├── packages/
│   └── shared/       # 공통 TypeScript 타입 정의
├── .sisyphus/
│   └── plans/        # 설계 문서 (Momus 승인 v1.1)
└── package.json      # npm workspaces (root)
```

## 개발 환경 셋업

### 사전 요구사항

- Node.js 20+ (확인: `node --version`)
- npm 10+ (Node와 함께 설치됨)
- Python 3.11+ (확인: `python --version`)
- Git 2.x

### 설치

```bash
# 1. Repo 클론
git clone <this-repo>
cd contest2

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 실제 키 값 입력

# 3. 의존성 설치 (frontend)
npm install

# 4. Python 의존성은 apps/api에서 별도 (T1.3에서 셋업)
```

### 개발 서버 실행

```bash
# 프론트엔드 개발 서버
npm run dev:web

# 백엔드 (apps/api 셋업 후)
# T1.3 완료 시 추가 예정
```

## 이전 버전 (초기 아이디어)
Feedback loop를 기반으로 한 부품사 - 동사 - 고객사 구조의 매출, 비용 추정 (but, P, Q를 구하는 과정이 생각보다 정확하지 않아서 포기)
<img width="1200" height="720" alt="image" src="https://github.com/user-attachments/assets/cae7078a-f96a-48ad-8a49-a7f9890f648f" />


Frontend : https://contest-v44h.vercel.app/  
Backend : http://localhost:8000/ (직접 구동 필요)
