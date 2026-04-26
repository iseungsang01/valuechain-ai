import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // monorepo - shared package transpile
  transpilePackages: ['@valuechain/shared'],
  // Next.js 15+ : typedRoutes 가 experimental 에서 stable 로 승격
  typedRoutes: true,
  // SSE 엔드포인트 프록시 (개발 시 백엔드 직접 호출 우회)
  async rewrites() {
    return [
      {
        source: '/api/backend/:path*',
        destination:
          process.env.NEXT_PUBLIC_API_BASE_URL
            ? `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/:path*`
            : 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;
