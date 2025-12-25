/** @type {import('next').NextConfig} */
const nextConfig = {
  // 移除 output: "export" 以支持动态路由
  distDir: "out",
};

module.exports = nextConfig;


