FROM freqtradeorg/freqtrade:stable

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY rtlab_core /app/rtlab_core
COPY config /app/config
COPY user_data /app/user_data
COPY scripts /app/scripts
COPY rtlab_config.yaml.example /app/rtlab_config.yaml.example

ENV RTLAB_CONFIG_POLICIES_ROOT=/app/config/policies

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "rtlab_core.web.main"]
