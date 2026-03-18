# Jerarquia de Autoridad Tecnica

Fecha de actualizacion: 2026-03-18

## Regla operativa

Cuando haya diferencias entre documentos, configuracion y comportamiento efectivo:

1. runtime real del backend y contratos API efectivos
2. `config/policies` canonico del monorepo
3. defaults fail-closed del backend cuando falta YAML
4. `docs/truth`
5. `docs/plan`

## Fuente unica de verdad de policies

- Raiz canonica esperada:
  - `config/policies/`
- Compatibilidad permitida solo como fallback:
  - `rtlab_autotrader/config/policies/`
- Si ambas raices existen pero divergen:
  - manda `config/policies/`
  - la raiz nested queda documentada como compatibilidad de empaquetado/deploy
  - la divergencia debe quedar visible en `GET /api/v1/config/policies`

## Taxonomia canonica de modos

- Runtime global:
  - `PAPER`
  - `TESTNET`
  - `LIVE`
- Modo operativo por bot:
  - `shadow`
  - `paper`
  - `testnet`
  - `live`
- Fuentes de evidence / learning:
  - `backtest`
  - `shadow`
  - `paper`
  - `testnet`

## Alias legacy

- `MOCK`:
  - solo alias del mock local del frontend
  - no es modo canonico del runtime real
- `demo`:
  - contexto legacy de research/promocion
  - no es modo operativo canonico
