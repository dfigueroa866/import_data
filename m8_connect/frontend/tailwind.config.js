/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0036b9',
          hover: '#0a3d61',
        },
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        surface: {
          light: '#ffffff',
          dark: '#1f2937',
        },
        login: {
          bg: '#f3f4f6',
          'bg-dark': '#111827',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Hanken Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'display-sm': ['24px', { lineHeight: '32px', fontWeight: '600', letterSpacing: '-0.02em' }],
        'headline-md': ['18px', { lineHeight: '24px', fontWeight: '600' }],
        'body-md': ['14px', { lineHeight: '20px', fontWeight: '400' }],
        'body-sm': ['12px', { lineHeight: '16px', fontWeight: '400' }],
        'label-xs': ['11px', { lineHeight: '12px', fontWeight: '600' }],
        'data-mono': ['12px', { lineHeight: '16px', fontWeight: '500', letterSpacing: '-0.01em' }],
      },
      borderRadius: {
        widget: '6px',
      },
      boxShadow: {
        widget: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
      },
    },
  },
  plugins: [],
};
