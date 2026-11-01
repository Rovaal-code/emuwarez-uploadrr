// A tab exposes its save action so the page-header (top-right) can render the
// button, like the sync buttons in Biblioteca/Peticiones.
export interface SaveExpose {
  dirty: boolean
  saving: boolean
  onSave: () => void
  label: string
}
