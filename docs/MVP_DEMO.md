# ValueChain AI - 5분 데모 시연 가이드

> Phase 1 MVP - "공급망 정합성 검증" 의 가치를 1회 만에 이해시키는 시연 시나리오.

## 시연 목표

투자자/애널리스트/리서처가 5분 후 다음 질문에 "아하" 라고 답할 수 있게 하는 것:

> **"왜 공급망 전체를 한 번에 보고 정합성을 검증하는 게 알파를 만드는가?"**

3가지 핵심 경험으로 설계:

1. **연결의 가치** (Network Consistency) - "A의 매출 ≈ B의 매입" 정합성 자동 검증
2. **출처의 신뢰** (Mandatory Grounding) - 모든 수치에 DART/EDGAR 공시 인용
3. **반응성** (Real-time SSE) - 1초 안에 첫 청크, 60초 안에 그래프 완성

---

## 사전 준비 (시연 5분 전)

```powershell
# 1. 백엔드 데모 캐시 워밍 (cold-start 회피)
cd apps/api
.\.venv\Scripts\python.exe scripts\seed_demo.py
# 예상 출력: "[OK] Demo cache warmed - cold-start avoided."

# 2. (선택) 성능 SLA 사전 검증
.\.venv\Scripts\python.exe scripts\benchmark.py --runs 5
# 예상: TTFGraph p95 < 1초, first_chunk < 0.05초 (in-process)

# 3. 백엔드 / 프론트엔드 기동 (별도 터미널 2개)
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000

# 새 터미널
cd apps/web
npm run build && npm run start
```

브라우저: http://localhost:3000 (홈) → "Dashboard 들어가기" 클릭

---

## 5분 시나리오

### [0:00 - 0:30] 문제 정의 (30초)

> "여러분이 NVIDIA 의 H100 매출을 추정하고 싶다고 생각해봅시다."
> "공시는 GPU 제품 단위로 분리되어 있지 않습니다. NVIDIA 의 분기 매출만 알 수 있죠."
> "그런데, **HBM 공급사인 SK하이닉스 / 삼성 / 마이크론의 매출 = NVIDIA 의 HBM 매입 비용**이라는 사실은 어떻게 활용할까요?"

화면: ValueChain AI 홈 → Dashboard 진입.

---

### [0:30 - 1:00] 토폴로지 안내 (30초)

> "메모리 반도체 공급망 7개 기업을 자동 매핑했습니다."
>
> - **HBM 3사** (SK하이닉스, 삼성, 마이크론)
> - **AI GPU 2사** (NVIDIA, AMD)
> - **CPU 1사** (인텔)
> - **파운드리** (TSMC)

화면: Dashboard 진입 직후 Topology Preview 카드 (7 nodes, 11 edges).

---

### [1:00 - 1:10] Run 클릭 (10초)

> "2024 Q3 분석을 실행합니다."

조작:

- Sector dropdown: `Memory Semiconductor` (default)
- Quarter dropdown: `2024 Q3` (default)
- 우상단 **Run Analysis** 버튼 클릭

→ 즉시 SSE 연결 + 4개 에이전트 컬럼 활성화.

---

### [1:10 - 2:00] 4 에이전트 thought stream 관찰 (50초)

오른쪽 ThoughtPanel 4분할 컬럼이 차례로 채워짐:

1. **StructureMapper** (~5s)
   - "memory_semiconductor 토폴로지 로드 - 7 nodes, 11 edges"
   - 그래프(왼쪽 60%) 에 노드 + 엣지 즉시 렌더 (스켈레톤 → 회색)

2. **DataCollector** (~10s)
   - "DART: 005930.KS, 000660.KS facts 로드"
   - "EDGAR: NVDA, AMD, INTC, MU, TSM facts 로드"
   - 각 thought 카드에 출처(citation_id) 첨부

3. **QuantEstimator** (~15s)
   - "NVDA 의 HBM 분배: SK하이닉스 50%, 삼성 30%, 마이크론 20%"
   - "FX 환산: 17.6조 KRW × 1340 KRW/USD ≈ 13.1B USD"
   - 엣지에 USD 금액 라벨 표시 (예: `$8.78B`)

4. **Evaluator** (~5s)
   - "NVDA: 매입 합계 7.66B vs 우리 추정 inflow 합계 비교"
   - "정합성 오차 3건 발행"

해설:

> "보세요. 4개 에이전트가 차례로 사고하는 과정이 그대로 보입니다."
> "추측이 아닙니다. 모든 thought 에 **출처 카드**가 붙어 있습니다 - 클릭하면 DART/EDGAR 원문으로 이동합니다."

---

### [2:00 - 3:00] 그래프 시각화 + 정합성 (60초)

왼쪽 React Flow 그래프 완성. 다음을 가리키며:

1. **노드 색상** - 각 회사의 분기 매출 USD
2. **엣지 두께** - 추정된 공급 매출 (USD 로그 스케일)
3. **엣지 색상** - 정합성 severity:
   - 녹색 = `low` (정합)
   - 노랑 = `medium` (10%~50% 초과)
   - 빨강 = `high` (50%+ 초과 - 모순!)

엣지 hover → **EdgeTooltip** 표시:

```
SK하이닉스 → NVIDIA  (HBM)
공급사 매출: $8.78B
바이어 비용: $7.66B
괴리: -12.7%   [low]
```

해설:

> "여기 **NVIDIA 행**을 보세요. 우리가 추정한 inflow 합계가 NVIDIA 의 실제 COGS 와 다르면..."
> "이건 **정보가 부족하거나, 누군가 가이던스를 잘못 말하고 있다**는 신호입니다."
> "이 신호가 알파의 시작점입니다."

---

### [3:00 - 4:00] 출처 추적 (60초)

ThoughtPanel 의 임의 thought 카드 → CitationCard 클릭:

> "DART 공시 ID `00164779` - SK하이닉스 2024Q3 보고서"
> "원문 PDF 1쪽에서 매출 17,573,000,000,000 KRW 확인"

→ 클릭 시 새 탭으로 `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=...` 이동.

해설:

> "Mandatory Grounding 원칙입니다."
> "AI 가 출처 없이 수치를 만들어내면 **시스템이 차단**합니다 (T4.2 hallucination 방어)."
> "투자 의사결정에 쓸 수 있는 데이터만 통과시킵니다."

---

### [4:00 - 4:30] 에러 처리 시연 (30초)

DevTools → Network → SSE 연결 강제 종료.

→ AgentErrorPanel 자동 노출:

> 🟡 외부 데이터 일시 오류
> 자동 재연결 중... (1/3)
> 자동 재연결 중... (2/3)
> 자동 재연결 중... (3/3)

해설:

> "네트워크 일시 끊김은 자동 복구됩니다 (3회 backoff)."
> "DART 인증 실패, Rate limit, LLM 환각 - 모든 에러 카테고리에 친절한 메시지 + 적절한 액션."

---

### [4:30 - 5:00] V2 비전 (30초)

> "이게 Phase 1 MVP 입니다. 하지만 진짜 가치는..."
>
> 1. **Forward Conflict** (V2): 가이던스끼리 모순될 때 미래 알파 신호
>    - 예: TSMC 4Q 가이던스 +20% vs NVIDIA 4Q 가이던스 -10% → 누가 맞는가?
> 2. **Self-Optimization** (V3): 백테스트로 추론 로직 자가 개선
>    - 12분기 (3년) 실 데이터로 정합성 검증 알고리즘 자체를 진화

> "공급망을 한 줄에서 보는 사람만 보이는 알파 - 이걸 자동화한 게 ValueChain AI 입니다."

---

## 합격 기준 (시연 후 자체 평가)

5분 시연이 끝나고 시청자에게:

> "방금 본 게 어떤 가치인지 한 문장으로 설명해주실래요?"

다음 키워드 중 2개 이상 자발적으로 언급되면 ✅:

- "공급망"
- "정합성"
- "출처/citation/공시"
- "모순/충돌/conflict"
- "알파"

---

## 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| 첫 SSE 청크 > 5초 | cold start (uvicorn 부팅 + LangGraph 임포트) | `seed_demo.py` 사전 실행 |
| 그래프 비어있음 | NEXT_PUBLIC_API_BASE_URL 미설정 | `.env.local` 에 `http://localhost:8000` 명시 |
| CORS 에러 | API 가 prod 모드 (CORS_ORIGINS 좁음) | `ENVIRONMENT=development` 또는 `CORS_ORIGINS` 추가 |
| `Reconnecting 1/3` 무한 반복 | 백엔드 5xx 응답 / 무응답 | API 헬스 확인 `curl http://localhost:8000/api/health` |
| ThoughtPanel 비어있음 | SSE 연결은 됐지만 이벤트 미수신 | DevTools → Network → EventStream 탭 검사 |

---

## 시연용 화면 캡처 (선택)

`docs/screenshots/` 디렉토리에 시연 직전 캡처 권장:

1. **dashboard-initial.png** - 진입 직후 Topology Preview
2. **dashboard-streaming.png** - Run 클릭 후 첫 5초 (스트리밍 중)
3. **dashboard-complete.png** - 60초 후 완성된 그래프
4. **citation-card.png** - 출처 카드 hover 상태
5. **error-panel.png** - 에러 패널 노출 (네트워크 강제 종료)

(데모 영상 또는 GIF 도 동일 흐름으로 제작 가능)
