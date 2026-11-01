import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/globals.css'
import './styles/layout.css'
import './styles/components.css'
import './styles/dashboard.css'
import './styles/hud-theme.css'
import './styles/tour.css'
import './styles/asistente.css'
import './styles/ajustes.css'
import './styles/peticiones.css'
import './styles/detalle-subida.css'
import './styles/guia.css'
import './styles/setup.css'
import { App } from './App'
import { LimiteDeErrores } from './components/LimiteDeErrores'
import { iniciarEscaladoUi } from './utils/uiScale'

// Antes del primer render: así el primer pintado ya sale al tamaño bueno, sin
// el salto de ver la interfaz a escala 1 y encogerse un instante después.
iniciarEscaladoUi()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LimiteDeErrores donde="la aplicación">
      <App />
    </LimiteDeErrores>
  </StrictMode>,
)
