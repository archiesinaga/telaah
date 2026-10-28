import argparse
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(prog="telaah")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="parse PDFs in data/raw")
    i.add_argument("--only", nargs="*", help="doc_ids to parse (default: all)")
    i.add_argument("--no-en", action="store_true", help="skip *_en English copies")
    i.add_argument("--workers", type=int, default=1, help="files parsed in parallel")
    sub.add_parser("inventory", help="write data/inventory.csv")
    sub.add_parser("index", help="embed pages into Qdrant")
    t = sub.add_parser("transcribe", help="transcribe chart-heavy pages with the vision model (data/page_transcripts)")
    t.add_argument("--docs", nargs="+", required=True, help="report doc_ids, e.g. bca_2025 mandiri_2025")
    t.add_argument("--limit", type=int, default=0, help="transcribe at most this many pages")
    sub.add_parser("transcripts-index", help="embed the page transcriptions (used with TELAAH_TRANSCRIPTS=1)")
    a = sub.add_parser("ask", help="ask one question")
    a.add_argument("question")
    a.add_argument("--rag", action="store_true", help="skip the router and use single-shot RAG")
    g = sub.add_parser("agent", help="ask one question with the planner/executor/verifier agent")
    g.add_argument("question")
    e = sub.add_parser("eval", help="run eval/seed_questions.jsonl")
    e.add_argument("--agent", action="store_true", help="answer with the agent instead of single-shot RAG")
    e.add_argument("--types", nargs="*", help="only these question types")
    e.add_argument("--router", action="store_true", help="route each question to RAG or the agent")
    e.add_argument("--ids", nargs="*", help="only these question ids (fast subset runs)")
    e.add_argument("--resume", help="a eval/runs/*.partial.jsonl file: run only the questions missing from it")
    e.add_argument("--judge-on-fail", action="store_true", help="skip the LLM judges when numeric/recall/citation checks already pass")
    e.add_argument("--workers", type=int, default=1, help="run this many questions at once (mind the Gemini rate limit and daily quota)")
    e.add_argument("--file", type=Path, help="question file (default eval/seed_questions.jsonl; eval/bench/dev.jsonl)")
    args = ap.parse_args()

    if args.cmd == "ingest":
        from telaah.ingest.parse import ingest_all

        ingest_all(args.only, args.no_en, args.workers)
    elif args.cmd == "inventory":
        from telaah.ingest.inventory import build_inventory

        build_inventory()
    elif args.cmd == "index":
        from telaah.index import build_index

        build_index()
    elif args.cmd == "transcribe":
        from telaah.transcripts import transcribe

        transcribe(args.docs, args.limit)
    elif args.cmd == "transcripts-index":
        from telaah.transcripts import build_embeddings

        build_embeddings()
    elif args.cmd == "ask":
        if args.rag:
            from telaah.answer import ask

            r = ask(args.question)
        else:
            from telaah.router import run_routed

            r = run_routed(args.question)
            print("route:", r["route"])
        print(r["answer"])
        print("retrieved:", r["retrieved"])
        if r.get("unsupported"):
            print("unsupported:", r["unsupported"])
    elif args.cmd == "agent":
        from telaah.agent import run_agent

        r = run_agent(args.question)
        print(r["answer"])
        print("verified:", r["verified"], "| steps:", [(s["q"], s["status"]) for s in r["steps"]])
        if r["unsupported"]:
            print("unsupported:", r["unsupported"])
    elif args.cmd == "eval":
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
        from run_eval import run

        kw = {"path": args.file.resolve()} if args.file else {}
        run(agent=args.agent, types=args.types, router=args.router, ids=args.ids, resume=args.resume, judge_on_fail=args.judge_on_fail, workers=args.workers, **kw)
