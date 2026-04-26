/**
 * Citation types - Mandatory Grounding (모든 수치는 출처 첨부)
 * 백엔드 Pydantic Citation, GroundedNumber와 정확히 동기화 유지
 */

export type SourceType =
  | 'DART' // 한국 전자공시 (https://opendart.fss.or.kr)
  | 'EDGAR' // 미국 SEC 공시
  | 'CUSTOMS' // 한국 관세청 (HS code)
  | 'IR_PDF' // 기업 IR 페이지 직접 공개 PDF
  | 'NEWS' // 뉴스 기사
  | 'EARNINGS_CALL'; // 어닝 콜 트랜스크립트 (자체 STT 포함)

export type SourceTier = 1 | 2 | 3;

export interface Citation {
  id: string; // UUID
  source_url: string;
  source_type: SourceType;
  source_tier: SourceTier;
  publish_date: string; // ISO date 'YYYY-MM-DD'
  disclosure_id: string | null; // DART rcept_no, EDGAR accession number 등
  snippet: string | null; // 인용 발췌문 (UI 표시용)
  created_at: string; // ISO datetime
}

export type Currency = 'USD' | 'KRW' | 'JPY' | 'TWD' | 'CNY';

/**
 * 모든 수치는 GroundedNumber로 표현되어야 함 (출처 ≥ 1)
 */
export interface GroundedNumber {
  value: number;
  currency: Currency;
  citation_ids: string[]; // 최소 1개 이상
  is_hypothesis: boolean;
  confidence: number; // 1~100
}
