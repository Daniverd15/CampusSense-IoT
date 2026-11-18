#!/usr/bin/env bash
# Crea un token de InfluxDB de SOLO LECTURA sobre el bucket "campus" para Grafana (mínimo privilegio)
# y lo guarda en .env como INFLUX_TOKEN_GRAFANA. El token de administrador queda solo en los
# contenedores internos (ingestor, API, dispositivos), que no se exponen a Internet.
# Uso (en la VM, desde ~/campus, después del primer `docker compose up -d`):
#   bash scripts/crear_token_grafana.sh && docker compose up -d grafana
set -euo pipefail
cd "$(dirname "$0")/.."
BID=$(docker compose exec -T influxdb influx bucket list --org unab --name campus --hide-headers | awk '{print $1}')
TOK=$(docker compose exec -T influxdb influx auth create --org unab --read-bucket "$BID" \
        --description "grafana-solo-lectura" --hide-headers | awk '{print $3}')
if [ "${#TOK}" -lt 40 ]; then echo "FALLO creando el token"; exit 1; fi
if grep -q '^INFLUX_TOKEN_GRAFANA=' .env; then
  sed -i "s|^INFLUX_TOKEN_GRAFANA=.*|INFLUX_TOKEN_GRAFANA=$TOK|" .env
else
  echo "INFLUX_TOKEN_GRAFANA=$TOK" >> .env
fi
echo "token de solo lectura para Grafana creado (longitud ${#TOK}, bucket $BID)"
