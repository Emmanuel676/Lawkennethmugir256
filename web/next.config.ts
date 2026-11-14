import type { NextConfig } from "next";

// FairLend Watch web interface. Every number comes from the API in ../api.
// The browser calls /api/* on this web app's own origin and Next.js forwards it to the API (FAIRLEND_API_URL,
// default http://127.0.0.1:8000). Same origin is what lets the API's SameSite=Strict session cookie work.
const API_URL = (process.env.FAIRLEND_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
