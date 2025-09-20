#!/bin/bash

# TODO: version properly
docker build --platform linux/amd64 -t ophintor/papishares:latest . --push

helm upgrade --install \
  papishares ./chart \
  --namespace papishares \
  --create-namespace \
  --set env.api_key=$(cat .env | grep API_KEY | cut -f2 -d'=') \
  --set env.api_base=$(cat .env | grep API_BASE | cut -f2 -d'=') \
  --set env.bot_token=$(cat .env | grep BOT_TOKEN | cut -f2 -d'=') \
  --set env.chat_id=$(cat .env | grep CHAT_ID | cut -f2 -d'=')
