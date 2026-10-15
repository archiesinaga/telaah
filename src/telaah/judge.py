import re

from openai import OpenAI

from telaah.config import JUDGE_MODEL, LLM_API_KEY, LLM_BASE_URL, LLM_MAX_RETRIES, MAX_JUDGE_TOKENS

SCORE_RE = re.compile(r'"score"\s*:\s*([01])')

CORRECT = """Kamu penilai. Bandingkan JAWABAN dengan JAWABAN_EMAS untuk PERTANYAAN.
Nilai 1 jika JAWABAN memuat makna dan angka yang sama dengan JAWABAN_EMAS, selain itu 0.
Balas hanya JSON: {{"score": 0 atau 1}}

PERTANYAAN: {question}
JAWABAN_EMAS: {gold}
JAWABAN: {answer}"""

FAITHFUL = """Kamu penilai. Nilai 1 jika SEMUA klaim dalam JAWABAN didukung oleh KONTEKS,
nilai 0 jika ada klaim yang tidak ada di KONTEKS. Abaikan format sitasi.
Balas hanya JSON: {{"score": 0 atau 1}}

KONTEKS:
{context}

JAWABAN: {answer}"""


def parse_score(text: str) -> float | None:
    m = SCORE_RE.search(text)
    return float(m.group(1)) if m else None


def _judge(prompt: str) -> float | None:
    llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, max_retries=LLM_MAX_RETRIES)
    resp = llm.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        max_tokens=MAX_JUDGE_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_score(resp.choices[0].message.content or "")


def judge_correctness(question: str, gold: str, answer: str) -> float | None:
    return _judge(CORRECT.format(question=question, gold=gold, answer=answer))


def judge_faithfulness(answer: str, context: str) -> float | None:
    return _judge(FAITHFUL.format(context=context, answer=answer))
