import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorState } from './ErrorState'

interface Props {
  children: ReactNode
  // Qué se rompió, para el mensaje: «la página», «la aplicación»…
  donde?: string
}

interface Estado {
  // Aparte del error: lo lanzado puede ser null o undefined, y entonces el
  // error por sí solo no diría que hubo fallo.
  fallo: boolean
  error: unknown
}

/**
 * Atrapa un error de render de lo que lleva dentro. Sin esto, React desmonta
 * toda la aplicación al primer error y deja la pantalla en negro hasta
 * recargar. Con él se ve un mensaje, el resto de la aplicación sigue en pie y
 * «Reintentar» vuelve a pintar lo que falló.
 */
export class LimiteDeErrores extends Component<Props, Estado> {
  state: Estado = { fallo: false, error: null }

  static getDerivedStateFromError(error: unknown): Estado {
    return { fallo: true, error }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('Error de render:', error, info.componentStack)
  }

  private reintentar = () => this.setState({ fallo: false, error: null })

  render() {
    if (!this.state.fallo) return this.props.children
    return (
      <ErrorState
        title={`Algo ha fallado en ${this.props.donde ?? 'esta página'}`}
        message="Se ha producido un error al mostrarla. El resto de la aplicación sigue funcionando. Si se repite, recarga la página (F5) y avisa de lo que estabas haciendo."
        onRetry={this.reintentar}
      />
    )
  }
}
