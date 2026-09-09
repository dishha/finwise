#!/usr/bin/env bash
# Builds an arm64 ZIP for AgentCore Runtime direct code deployment.
set -euo pipefail
rm -rf deployment_package deployment_package.zip
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.13 \
  --target=deployment_package \
  --only-binary=:all: \
  -r pyproject.toml
(cd deployment_package && zip -qr ../deployment_package.zip .)
zip -q deployment_package.zip main.py agents.py tools.py -r data
echo "Built deployment_package.zip ($(du -h deployment_package.zip | cut -f1))"
