#!/usr/bin/env bash

set -e

echo "Building Docker image for cross-platform validation..."
docker build -t antigravity-engine:test .

echo "Testing Docker image CLI entrypoint..."
docker run --rm antigravity-engine:test --help

echo "Cross-platform Docker tests successful."
