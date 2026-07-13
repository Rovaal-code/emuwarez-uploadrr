// Cross-component "unsaved changes" guard. A form (e.g. the Settings tabs)
// registers a getter reporting whether it has unsaved changes; navigation
// (sidebar pages, Settings tabs, browser unload) checks it before leaving.
//
// The in-app confirmation is a styled card modal: the modal host registers a
// `prompt` opener, and callers use `guardedLeave(proceed)` which runs `proceed`
// immediately when clean or opens the modal (and runs `proceed` on confirm).

let dirtyCheck: (() => boolean) | null = null
let opener: ((proceed: () => void) => void) | null = null

export function setUnsavedGuard(fn: (() => boolean) | null): void {
  dirtyCheck = fn
}

export function hasUnsavedChanges(): boolean {
  return dirtyCheck ? dirtyCheck() : false
}

// Registered by the modal host (AppShell) so guardedLeave can show a styled
// confirmation instead of window.confirm.
export function setLeavePrompt(fn: ((proceed: () => void) => void) | null): void {
  opener = fn
}

// Run `proceed` if there are no unsaved changes; otherwise ask the user first.
export function guardedLeave(proceed: () => void): void {
  if (!hasUnsavedChanges()) {
    proceed()
    return
  }
  if (opener) {
    opener(proceed)
  } else if (window.confirm('Tienes cambios sin guardar. ¿Salir y descartarlos?')) {
    proceed()
  }
}
