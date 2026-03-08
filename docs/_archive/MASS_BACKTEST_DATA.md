# Mass Backtest Data (Datos reales y reproducibles)

## Respuesta corta
- **No hace falta conectar APIs privadas** para correr Mass Backtest.
- Modo recomendado: **DATASET MODE** (datasets históricos reproducibles).
- **Sí** hace falta internet para descargar datasets públicos (ej. Binance Public Data para crypto).
- **API keys** se reservan para trading (`paper/testnet/live`) o API mode opcional.

## 1) Modo recomendado: DATASET MODE (sin API keys)
El motor de Mass Backtests usa `DATASET MODE` por defecto.

### Flujo
1. Descargar datasets históricos públicos (ej. Binance Public Data)
2. Guardarlos en `user_data/data/...` (compat actual) y/o `user_data/datasets/...` (estándar research)
3. Resolver dataset + `dataset_hash` + manifest
4. Ejecutar mass backtest con evidencia reproducible

## 2) Carpetas soportadas
### Compatibilidad actual (ya usada por el bot)
- `user_data/data/{market}/processed/`
- `user_data/data/{market}/manifests/`

### Estándar research (nuevo, recomendado)
- `user_data/datasets/{provider}/{market}/{symbol}/{timeframe}/`
  - `manifest.json`
  - archivos parquet/csv (chunks o procesado)

Ejemplo:
```text
user_data/datasets/binance_public/crypto/BTCUSDT/1m/manifest.json
```

## 3) Binance Public Data (crypto, sin API keys)
Ya existe downloader:
- `rtlab_autotrader/scripts/download_crypto_binance_public.py`

Descarga:
- `data.binance.vision` (archivos daily/monthly)
- klines `1m`
- genera dataset procesado + manifest + `dataset_hash`

Ejemplo:
```bash
python rtlab_autotrader/scripts/download_crypto_binance_public.py \
  --start-month 2024-01 \
  --end-month 2024-06 \
  --symbols BTCUSDT ETHUSDT
```

## 4) Dataset hash y provenance
El sistema registra/usa:
- `dataset_source`
- `dataset_hash`
- rango temporal
- timeframe
- universo/símbolos
- costos usados
- `commit_hash`

Esto permite comparar “manzanas con manzanas”.

## 5) Validación de datos (roadmap inmediato)
Research stack incluye `pandera[pandas]` para validar:
- columnas OHLCV
- timestamps monotónicos
- duplicados/nulos
- gaps

El motor actual ya usa manifests/hashes y hace fallback seguro; la validación estricta con `pandera` puede activarse en el pipeline de datasets sin tocar runtime.

## 6) Forex / Stocks (placeholders por ahora)
No se obliga al usuario a conectar APIs ahora.

### Forex
- Placeholder: Dukascopy (dataset mode)
- Alternativa actual: CSV/Parquet manual en `user_data/data/forex`

### Stocks
- Placeholder: Alpaca Market Data (dataset mode o API mode opcional)
- Alternativa actual: CSV/Parquet manual en `user_data/data/equities`

## 7) API MODE (opcional)
Existe interfaz `API MODE` como placeholder en research.
- No recomendado para reproducibilidad
- Puede sufrir rate limits/cambios de proveedor
- No está implementado como camino principal del motor masivo

## 8) Recomendación práctica
Para empezar:
1. Descargar `BTCUSDT` y `ETHUSDT` (Binance Public Data)
2. Correr Mass Backtest en `DATASET MODE`
3. Revisar ranking robusto y KPIs por régimen
4. Marcar candidato (Opción B) y pasar por gates/canary/approve
