import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="container mx-auto flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <h1 className="text-4xl font-bold tracking-tight">ValueChain AI</h1>
      <p className="max-w-2xl text-center text-lg text-foreground/70">
        공급망 기반 기업 재무 추정 및 예측 에이전트.
        <br />
        네트워크 정합성 · 미래 충돌 · 자가 최적화
      </p>
      <Link
        href="/dashboard"
        className="rounded-lg bg-[var(--color-brand-primary)] px-6 py-3 text-white transition-opacity hover:opacity-90"
      >
        Dashboard 들어가기 →
      </Link>
    </main>
  );
}
