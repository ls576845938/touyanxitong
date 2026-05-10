import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172026",
        panel: "#ffffff",
        line: "#d9e2e0",
        mint: "#2e7d6f",
        amber: "#b66a20",
        rose: "#a7434b"
      }
    }
  },
  plugins: []
};

export default config;
