import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ValueChain AI',
  description: '공급망 기반 기업 재무 추정 및 예측 에이전트',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
