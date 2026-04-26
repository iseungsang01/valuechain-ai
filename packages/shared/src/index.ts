/**
 * @valuechain/shared
 *
 * Shared types between frontend (Next.js) and backend (FastAPI).
 * Backend Python Pydantic models should mirror these definitions.
 *
 * Naming convention: snake_case in JSON wire format, but TypeScript
 * uses snake_case here intentionally to match backend exactly.
 */

export type * from './citations.js';
export type * from './graph.js';
export type * from './agents.js';
