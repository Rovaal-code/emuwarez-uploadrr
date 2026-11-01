// El aviso de Source cuando MediaInfo (Internal Source Tool) apunta a otro
// source que el nombre o Radarr/Sonarr. Lo redacta el servidor
// (source_assistant.aviso_source_discrepante); aquí solo se decide si se
// enseña: en cuanto el usuario elige en Source lo que dice MediaInfo, ya no
// hay nada que avisar.
export function avisoSourceVisible(
  aviso: string | null | undefined,
  deMediainfo: string | null | undefined,
  sourceActual: string | null | undefined,
): string | null {
  if (!aviso) return null
  if (deMediainfo && sourceActual === deMediainfo) return null
  return aviso
}
