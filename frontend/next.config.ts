import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  experimental: {
    optimizePackageImports: ['lucide-animated', 'lucide-react', '@ant-design/icons', 'antd', '@ant-design/x'],
  },
};

export default nextConfig;
