FROM freqtradeorg/freqtrade:stable

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY rtlab_core /app/rtlab_core
COPY user_data /app/user_data
COPY scripts /app/scripts
COPY rtlab_config.yaml.example /app/rtlab_config.yaml.example

RUN pip install --no-cache-dir .

ENTRYPOINT ["rtbot"]
CMD ["status"]
