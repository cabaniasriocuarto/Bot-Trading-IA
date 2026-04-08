FROM freqtradeorg/freqtrade:stable

WORKDIR /app

USER root

COPY pyproject.toml README.md /app/
COPY config /app/config
COPY rtlab_core /app/rtlab_core
COPY user_data /app/user_data
COPY scripts /app/scripts
COPY rtlab_config.yaml.example /app/rtlab_config.yaml.example

RUN python -m pip install --no-cache-dir .
RUN python -c "import yaml; print(yaml.__file__)"

USER ftuser

ENTRYPOINT ["python", "-m", "rtlab_core.web.main"]
