#!/usr/bin/env bash
# Prepare the local LLM for the demo: check Ollama, pull the base model, create the 8k-context variant.
#   bash scripts/setup_ollama.sh
# Afterwards:  LLM_MODEL=qwen2.5:7b-gpu python app.py
set -euo pipefail
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Get it from https://ollama.com, then run this script again."
  exit 1
fi
if ! curl -fsS --max-time 5 http://127.0.0.1:11434 >/dev/null 2>&1; then
  echo "Ollama is not running. Start it (e.g. 'ollama serve' in another terminal), then run this script again."
  exit 1
fi
root="$(cd "$(dirname "$0")/.." && pwd)"
ollama pull qwen2.5:7b-instruct
ollama create qwen2.5:7b-gpu -f "$root/ollama/Modelfile"
echo
echo "Done. Run the demo with:"
echo "  LLM_MODEL=qwen2.5:7b-gpu python app.py"
