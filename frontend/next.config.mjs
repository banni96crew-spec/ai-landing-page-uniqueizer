/** @type {import('next').NextConfig} */
const backendOrigin =
  process.env.API_PROXY_ORIGIN?.replace(/\/$/, "") ||
  process.env.BACKEND_ORIGIN?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
