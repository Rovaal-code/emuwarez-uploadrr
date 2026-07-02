// Region (ISO 3166-1) and language (BCP-47-ish, matching TMDb's convention)
// option lists for Settings/setup — a broad practical set, not exhaustive.

export interface SelectOption {
  value: string
  label: string
}

export const REGION_OPTIONS: SelectOption[] = [
  { value: 'ES', label: 'España' },
  { value: 'MX', label: 'México' },
  { value: 'AR', label: 'Argentina' },
  { value: 'CO', label: 'Colombia' },
  { value: 'CL', label: 'Chile' },
  { value: 'PE', label: 'Perú' },
  { value: 'VE', label: 'Venezuela' },
  { value: 'UY', label: 'Uruguay' },
  { value: 'US', label: 'Estados Unidos' },
  { value: 'GB', label: 'Reino Unido' },
  { value: 'FR', label: 'Francia' },
  { value: 'DE', label: 'Alemania' },
  { value: 'IT', label: 'Italia' },
  { value: 'PT', label: 'Portugal' },
  { value: 'BR', label: 'Brasil' },
  { value: 'NL', label: 'Países Bajos' },
  { value: 'CA', label: 'Canadá' },
  { value: 'AU', label: 'Australia' },
  { value: 'JP', label: 'Japón' },
  { value: 'KR', label: 'Corea del Sur' },
]

export const LANGUAGE_OPTIONS: SelectOption[] = [
  { value: 'es-ES', label: 'Español (España)' },
  { value: 'es-MX', label: 'Español (México)' },
  { value: 'es-AR', label: 'Español (Argentina)' },
  { value: 'en-US', label: 'Inglés (EE.UU.)' },
  { value: 'en-GB', label: 'Inglés (Reino Unido)' },
  { value: 'fr-FR', label: 'Francés' },
  { value: 'de-DE', label: 'Alemán' },
  { value: 'it-IT', label: 'Italiano' },
  { value: 'pt-PT', label: 'Portugués (Portugal)' },
  { value: 'pt-BR', label: 'Portugués (Brasil)' },
  { value: 'nl-NL', label: 'Neerlandés' },
  { value: 'ja-JP', label: 'Japonés' },
  { value: 'ko-KR', label: 'Coreano' },
  { value: 'zh-CN', label: 'Chino (simplificado)' },
  { value: 'ru-RU', label: 'Ruso' },
  { value: 'ca-ES', label: 'Catalán' },
]

export function findRegionLabel(value: string): string {
  return REGION_OPTIONS.find(o => o.value === value)?.label ?? value
}

export function findLanguageLabel(value: string): string {
  return LANGUAGE_OPTIONS.find(o => o.value === value)?.label ?? value
}
