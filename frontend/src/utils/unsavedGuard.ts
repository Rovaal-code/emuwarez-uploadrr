// Cross-component "unsaved changes" guard. A form (e.g. the Settings tabs)
// registers a getter that reports whether it currently has unsaved changes;
// navigation (sidebar pages, Settings tabs, browser unload) checks it before
// leaving so the user can't silently lose edits.

let dirtyCheck: (() => boolean) | null = null

export function setUnsavedGuard(fn: (() => boolean) | null): void {
  dirtyCheck = fn
}

export function hasUnsavedChanges(): boolean {
  return dirtyCheck ? dirtyCheck() : false
}

// Returns true if it's safe to proceed (no changes, or the user confirmed
// discarding them).
export function confirmDiscardIfDirty(
  message = 'Tienes cambios sin guardar en Configuración. ¿Seguro que quieres salir y descartarlos?',
): boolean {
  return hasUnsavedChanges() ? window.confirm(message) : true
}
