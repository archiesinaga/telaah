import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", LLM_MODEL)
# Free API tiers cap requests per minute (Gemini flash-lite: 15): retry with the server's Retry-After instead of failing
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
# Minimum seconds between LLM calls (0 = off). 15 requests/min -> 4.5; retries alone cannot keep an agent under the cap.
LLM_MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "0"))
EMBED_MODEL =os.getenv("EMBED_MODEL", "BAAI/bge-m3")
QDRANT_PATH = str(ROOT / os.getenv("QDRANT_PATH", "data/qdrant"))
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
COLLECTION = "telaah"
TOP_K = int(os.getenv("TOP_K", "5"))
# Output caps: at temperature 0 the 7B can fall into a repetition loop and never stop.
MAX_ANSWER_TOKENS = int(os.getenv("MAX_ANSWER_TOKENS", "800"))
MAX_JUDGE_TOKENS = int(os.getenv("MAX_JUDGE_TOKENS", "300"))

# ColPali page-image retrieval (index built on Kaggle, see KAGGLE_SETUP.md)
COLPALI_DIR = ROOT / os.getenv("COLPALI_DIR", "data/colpali")
COLPALI_MODEL = os.getenv("COLPALI_MODEL", "vidore/colqwen2-v1.0")

# Vision model that transcribes chart pages (Gemini via its OpenAI-compatible API).
# Empty key = vision step disabled. Put GEMINI_API_KEY in .env (never commit it).
VISION_API_KEY = os.getenv("VISION_API_KEY") or os.getenv("GEMINI_API_KEY", "")
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
VISION_MODEL = os.getenv("VISION_MODEL", "gemini-3.8-flash")
VISION_PAGES = int(os.getenv("VISION_PAGES", "2"))  # top retrieved pages read as images
VISION_DPI = int(os.getenv("VISION_DPI", "130"))
