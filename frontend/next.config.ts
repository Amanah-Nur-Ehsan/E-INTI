import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Pins the workspace root explicitly -- otherwise Turbopack scans upward
  // and can pick up an unrelated lockfile from the home directory.
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        // Same-origin from the browser's perspective, so no CORS/cookie
        // headaches in dev even though the real API runs on a different
        // port. Production deployments can point API_ORIGIN elsewhere or
        // drop the rewrite in favour of a reverse proxy.
        source: "/api/:path*",
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
