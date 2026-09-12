/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // JSL GreenSteel design tokens - industrial control-room palette.
        // Deliberately NOT the generic cream/terracotta or SaaS-card look.
        base: {
          900: "#12161A", // primary background - graphite/near-black
          800: "#181D22", // panel background
          700: "#222931", // raised panel / card
          600: "#2C3540", // borders, dividers
          500: "#465364", // muted borders on light content
        },
        steel: {
          400: "#7FA8C9",
          500: "#4C82AA", // primary accent - cold-rolled steel blue
          600: "#3A6688",
        },
        ember: {
          400: "#F0A445",
          500: "#DB8A2C", // secondary accent - furnace amber, used sparingly (heat/energy)
          600: "#B96F1D",
        },
        carbon: {
          400: "#8A97A3",
          500: "#5C6975", // carbon/emissions neutral grey
        },
        good: {
          500: "#4C9A6A", // lower emissions / favorable
        },
        warn: {
          500: "#C4502A", // higher emissions / unfavorable
        },
        ink: {
          100: "#F2F4F6",
          200: "#DCE1E6",
          300: "#B7C0C9",
          400: "#8B96A1",
        },
      },
      fontFamily: {
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};
