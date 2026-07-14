/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#1d4ed8',
          600: '#1565c0',
          700: '#0d47a1',
          800: '#1e3a5f',
          900: '#0f2a4a',
          950: '#060f1e',
        },
        civic: {
          teal:   '#00897b',
          amber:  '#f59e0b',
          slate:  '#1e293b',
          muted:  '#64748b',
          border: '#e2e8f0',
        },
        severity: {
          low:      '#16a34a',
          medium:   '#d97706',
          high:     '#ea580c',
          critical: '#dc2626',
        },
        status: {
          submitted:    '#6b7280',
          processing:   '#3b82f6',
          assigned:     '#8b5cf6',
          in_progress:  '#f59e0b',
          resolved:     '#10b981',
          verified:     '#06b6d4',
          closed:       '#64748b',
          rejected:     '#ef4444',
        },
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ['Inter', 'system-ui', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        'card':     '0 1px 3px 0 rgba(0,0,0,.06), 0 1px 2px -1px rgba(0,0,0,.06)',
        'card-md':  '0 4px 6px -1px rgba(0,0,0,.07), 0 2px 4px -2px rgba(0,0,0,.07)',
        'card-lg':  '0 10px 15px -3px rgba(0,0,0,.08), 0 4px 6px -4px rgba(0,0,0,.08)',
        'glow-blue':'0 0 0 3px rgba(29,78,216,.25)',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      animation: {
        'fade-in':    'fadeIn .25s ease-out',
        'slide-up':   'slideUp .3s cubic-bezier(.16,1,.3,1)',
        'pulse-dot':  'pulseDot 2s ease-in-out infinite',
        'count-up':   'countUp .6s ease-out',
      },
      keyframes: {
        fadeIn:    { from: { opacity: 0 },                    to: { opacity: 1 } },
        slideUp:   { from: { transform: 'translateY(12px)', opacity: 0 }, to: { transform: 'translateY(0)', opacity: 1 } },
        pulseDot:  { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.4 } },
        countUp:   { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
      },
    },
  },
  plugins: [],
};
