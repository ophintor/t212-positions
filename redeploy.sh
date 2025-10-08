#!/bin/bash
# set -x

# TODO: version properly
docker build --platform linux/amd64 -t ophintor/papishares:latest . --push

helm upgrade --install \
  papishares ./chart \
  --namespace papishares \
  --create-namespace \
  --set env.t212_api_key=$(cat .env | grep T212_API_KEY | cut -f2 -d'=') \
  --set env.t212_secret_key=$(cat .env | grep T212_SECRET_KEY | cut -f2 -d'=') \
  --set env.t212_api_base=$(cat .env | grep T212_API_BASE | cut -f2 -d'=') \
  --set env.telegram_bot_token=$(cat .env | grep TELEGRAM_BOT_TOKEN | cut -f2 -d'=') \
  --set env.telegram_chat_id=$(cat .env | grep TELEGRAM_CHAT_ID | cut -f2 -d'=')
