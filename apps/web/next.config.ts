import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the Next.js dev-tools badge; it only exists in `next dev` and clutters the UI.
  devIndicators: false,
  // The public deployment builds into its own folder so it never clashes with `next dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
