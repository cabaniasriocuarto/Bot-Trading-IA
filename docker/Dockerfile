FROM freqtradeorg/freqtrade:stable

WORKDIR /app

COPY rtlab_autotrader/pyproject.toml rtlab_autotrader/README.md /app/
COPY config /app/config
COPY rtlab_autotrader/rtlab_core /app/rtlab_core
COPY rtlab_autotrader/user_data /app/user_data
COPY rtlab_autotrader/scripts /app/scripts
COPY rtlab_autotrader/rtlab_config.yaml.example /app/rtlab_config.yaml.example

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "rtlab_core.web.main"]
