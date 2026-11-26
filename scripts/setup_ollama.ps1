# Prepare the local LLM for the demo: check Ollama, pull the base model, create the 8k-context variant.
#   .\scripts\setup_ollama.ps1
# Afterwards:  $env:LLM_MODEL = "qwen2.5:7b-gpu"; python app.py
$ErrorActionPreference = "Stop"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama is not installed. Get it from https://ollama.com, then run this script again."
    exit 1
}
try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:11434 | Out-Null
} catch {
    Write-Host "Ollama is not running. Start the Ollama app (or run 'ollama serve' in another window), then run this script again."
    exit 1
}
$root = Split-Path -Parent $PSScriptRoot
ollama pull qwen2.5:7b-instruct
ollama create qwen2.5:7b-gpu -f (Join-Path $root "ollama\Modelfile")
Write-Host ""
Write-Host "Done. Run the demo with:"
Write-Host '  $env:LLM_MODEL = "qwen2.5:7b-gpu"; python app.py'
