/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Proxy same-origin `/api/*` to the orchestrator so the browser talks to the
  // REAL backend with no CORS and no backend modification. The destination is
  // resolved from the server-side env `ORCH_API_URL` (e.g.
  // http://127.0.0.1:8090). With no env set the rewrite is inert.
  async rewrites() {
    const dest = process.env.ORCH_API_URL;
    if (!dest) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${dest.replace(/\/$/, "")}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
