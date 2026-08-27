/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        nexus: {
          dark: "#0a0d14",
          surface: "#121824",
          border: "#1e293b",
          primary: "#38bdf8",
          accent: "#818cf8"
        }
      }
    },
  },
  plugins: [],
}
