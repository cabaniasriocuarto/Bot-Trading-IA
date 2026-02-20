# RTLab AutoTrader

Bot de trading automatico con arquitectura modular, orientado a robustez operativa y control de riesgo estricto.

No existe rentabilidad garantizada; el sistema aplica validaciones y stress tests para reducir riesgo de overfitting.

## 1) Requisitos

- Python 3.11+
- `uv` o `poetry` (se muestran comandos con `uv`)
- Docker + Docker Compose (para runtime empaquetado)

## 2) Instalacion local

```bash
uv venv
uv pip install -e .[dev]
```

Opcional (motor Freqtrade local):

```bash
uv pip install -e .[trading]
```

## 3) Setup de entorno

```bash
cp .env.example .env
cp rtlab_config.yaml.example rtlab_config.yaml
```

Variables minimas en `.env`:

- `RTLAB_CONFIG_PATH=rtlab_config.yaml`
- `TELEGRAM_ENABLED=true|false`
- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_CHAT_ID=...`

Variables recomendadas para API/BFF en Railway:

- `AUTH_SECRET=<32+ chars>`
- `ADMIN_USERNAME=Wadmin`
- `ADMIN_PASSWORD=moroco123`
- `VIEWER_USERNAME=viewer`
- `VIEWER_PASSWORD=<tu-pass>`
- `MODE=paper|testnet|live`
- `EXCHANGE_NAME=binance|bybit`
- `RTLAB_USER_DATA_DIR=/tmp/rtlab_user_data` (recomendado en Railway)
- `PORT` (Railway lo inyecta automaticamente)

## API Web (Railway)

El backend HTTP de consola expone:

- REST: `/api/v1/*`
- Stream SSE: `/api/v1/stream`

Ejecutar local:

```bash
python -m rtlab_core.web.main
```

Debe escuchar en `0.0.0.0:$PORT`.

## 4) Setup de `user_data/` (Freqtrade userdir)

```bash
bash scripts/bootstrap_userdir.sh
```

## 5) Descargar data historica

```bash
bash scripts/download_data.sh rtlab_config.yaml
```

## 6) Backtest + reporte (estrategia base)

```bash
bash scripts/run_backtest.sh rtlab_config.yaml MicrostructureTrendPullbackStrategy 20240101- "BTC/USDT ETH/USDT"
bash scripts/report_backtest.sh
```

## 7) Importar strategy pack TXT

```bash
bash scripts/strategy_pack_import.sh user_data/strategy_packs/packs/trend_pullback_v1.txt
rtbot pack list
rtbot pack validate --name trend_pullback
```

## 8) Backtest de pack + ranking

```bash
rtbot pack backtest --name trend_pullback --timerange 20240101-20241231 --pairs "BTC/USDT,ETH/USDT"
rtbot pack rank --timerange 20240101-20241231
```

## 9) Promover estrategia a principal

```bash
rtbot pack promote --name trend_pullback --mode paper
rtbot status
```

## 10) Correr dry-run / paper / testnet

```bash
bash scripts/run_dryrun.sh rtlab_config.yaml
bash scripts/run_paper.sh rtlab_config.yaml
bash scripts/run_testnet.sh rtlab_config.yaml
```

Live (solo cuando se habilite):

```bash
bash scripts/run_live.sh rtlab_config.yaml
```

## 11) Docker (PC local -> VPS)

Levantar:

```bash
cd docker
docker compose up --build
```

Unidad `systemd` de ejemplo para VPS (`/etc/systemd/system/rtlab-autotrader.service`):

```ini
[Unit]
Description=RTLab AutoTrader
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/rtlab_autotrader/docker
ExecStart=/usr/bin/docker compose up --build
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rtlab-autotrader
sudo systemctl start rtlab-autotrader
```

## 12) Backup de SQLite

```bash
mkdir -p backups
sqlite3 user_data/strategy_packs/registry.sqlite3 ".backup 'backups/registry_$(date +%F_%H%M%S).sqlite3'"
```

## 13) Checklist de seguridad

- Secretos solo en `.env` (nunca commitear claves reales)
- Permisos minimos para API keys (sin retiros)
- Firewall VPS (permitir solo SSH + trafico necesario)
- Usuario sin privilegios de root para correr servicios
- Rotacion de logs y backups periodicos
- Monitorear alertas Telegram: SAFE/KILL/errores
- Revisar `daily_loss` y `max_drawdown` antes de live

## 14) CLI principal (`rtbot`)

- `rtbot pack import --file <path> [--notes ...]`
- `rtbot pack validate --name <name>`
- `rtbot pack list`
- `rtbot pack backtest --name <name> --timerange <...> --pairs <...>`
- `rtbot pack rank --timerange <...>`
- `rtbot pack promote --name <name> --mode paper|testnet|live`
- `rtbot run --mode paper|testnet|live`
- `rtbot status`

## 15) CI

GitHub Actions ejecuta `pytest` en Python 3.11/3.12 sobre cada push/PR.
