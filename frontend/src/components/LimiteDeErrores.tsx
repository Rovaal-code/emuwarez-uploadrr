import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorState } from './ErrorState'

interface Props {
  children: ReactNode
  // Qué se rompió, para el mensaje: «la página», «la aplicación»…
  donde?: string
}

interface Estado {
  error: Error | null
}

/**
 * Atrapa un error de render de lo que lleva dentro. Sin esto, React desmonta
 * toda la aplicación al primer error y deja la pantalla en negro hasta
 * recargar. Con él se ve un mensaje, el resto de la aplicación sigue en pie y
 * «Reintentar» vuelve a pintar lo que falló.
 */
export class LimiteDeErrores extends Component<Props, Estado> {
  state: Estado = { error: null }

  static getDerivedStateFromError(error: Error): Estado {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Error de render:', error, info.componentStack)
  }

  private reintentar = () => this.setState({ error: null })

  render() {
    if (!this.state.error) return this.props.children
    return (
      <ErrorState
        title={`Algo ha fallado en ${this.props.donde ?? 'esta página'}`}
        message="Se ha producido un error al mostrarla. El resto de la aplicación sigue funcionando. Si se repite, recarga la página (F5) y avisa de lo que estabas haciendo."
        onRetry={this.reintentar}
      />
    )
  }
}
