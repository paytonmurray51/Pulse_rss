/** @type {import('tailwindcss').Config} */

// Monochrome theme. All interface chrome is greyscale so the score rings —
// the only saturated colour in the UI — carry the ranking signal.
// Swapping themes means changing `accent` and the `bg` ramp; nothing else
// in the components references a colour directly.
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0a0a0a',
          surface: '#141414',
          elevated: '#1e1e1e',
          border: '#2a2a2a',
        },
        accent: {
          DEFAULT: '#e5e5e5',
          hover: '#ffffff',
          press: '#a3a3a3',
          dim: '#8a8a8a',
        },
        // Semantic, deliberately kept saturated in every theme.
        score: {
          high: '#10b981',
          mid: '#f59e0b',
          low: '#ef4444',
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Plus Jakarta Sans', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s cubic-bezier(0.16,1,0.3,1)',
        'pulse-dot': 'pulseDot 1.5s ease-in-out infinite',
        spin: 'spin 1s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseDot: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
    },
  },
  plugins: [],
}
