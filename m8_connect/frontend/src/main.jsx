import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

const applySystemTheme = () => {
  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}

applySystemTheme()
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applySystemTheme)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
