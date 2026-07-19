import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dark navy - sidebar active text, headings, primary buttons.
        // Sampled from the Figma "Sign in" button (#213145).
        ink: {
          950: "#0F1826",
          900: "#16233A",
          800: "#1D2E4A",
          700: "#213145",
          600: "#2C3E5C",
        },
        // Amber/gold brand color - "New Meeting" button, active nav,
        // stat accents. Sampled from Figma (#FFB800).
        brand: {
          50: "#FFF8E6",
          100: "#FFEFC2",
          200: "#FFE293",
          300: "#FFD25E",
          400: "#FFC02E",
          500: "#FFB800",
          600: "#F5A700",
          700: "#CC8B00",
          800: "#A36F00",
          900: "#7A5300",
        },
        // Warm cream page background used behind the app shell and the
        // gold auth panel. Sampled from Figma (#F0EADC / #F3D989).
        cream: {
          50: "#FBF9F5",
          100: "#F6F3F2",
          200: "#F0EADC",
          300: "#F3D989",
          400: "#EFCE6E",
        },
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
        "3xl": "1.75rem",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(33, 49, 69, 0.06), 0 1px 2px -1px rgba(33, 49, 69, 0.06)",
      },
    },
  },
  plugins: [],
} satisfies Config;
