from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import settings
from .services import MemoryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dianjia", description="Dianjia AI memory system MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p = sub.add_parser("ingest", help="Import a file or '-' for stdin"); p.add_argument("file", type=Path); p.add_argument("--date")
    p = sub.add_parser("ingest-dir", help="Import all .md/.txt files in a directory"); p.add_argument("directory", type=Path); p.add_argument("--date")
    p = sub.add_parser("daily"); p.add_argument("--date")
    p = sub.add_parser("extract"); p.add_argument("--date")
    p = sub.add_parser("process"); p.add_argument("candidate_file", nargs="?", type=Path)
    p = sub.add_parser("run-daily", help="Run daily summary, extraction, and processing"); p.add_argument("--date")
    memory = sub.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_action", required=True)
    p = memory_sub.add_parser("extract"); p.add_argument("--date")
    p = memory_sub.add_parser("process"); p.add_argument("candidate_file", nargs="?", type=Path)
    p = sub.add_parser("search"); p.add_argument("keyword"); p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("ask", help="Retrieve knowledge and answer a question"); p.add_argument("question"); p.add_argument("--limit", type=int, default=5); p.add_argument("--context-only", action="store_true", help="Only print retrieved context")
    p = sub.add_parser("show"); p.add_argument("memory_id")
    sub.add_parser("rebuild-index")
    sub.add_parser("status")
    p = sub.add_parser("web", help="Start the local web console"); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = MemoryService(settings)
    if args.command == "init":
        service.init(); print(f"Initialized knowledge base: {settings.knowledge_root}")
    elif args.command == "ingest":
        if str(args.file) == "-": print(service.ingest_text(sys.stdin.read(), "stdin", args.date, "stdin"))
        else: print(service.ingest(args.file, args.date))
    elif args.command == "ingest-dir": print("\n".join(str(path) for path in service.ingest_directory(args.directory, args.date)))
    elif args.command == "daily": print(service.daily(args.date))
    elif args.command == "extract" or (args.command == "memory" and args.memory_action == "extract"): print(service.extract(args.date))
    elif args.command == "process" or (args.command == "memory" and args.memory_action == "process"): print("\n".join(service.process(args.candidate_file)))
    elif args.command == "search":
        for row in service.search(args.keyword, args.limit): print(f"{row['id']}\t{row['title']}\t{row['path']}")
    elif args.command == "ask":
        if args.context_only:
            context, memories = service.build_context(args.question, args.limit)
            print(context)
            print(f"\n检索到 {len(memories)} 条记忆。")
        else:
            answer, memories = service.ask(args.question, args.limit)
            print(answer)
            if memories:
                print("\n参考记忆：")
                for memory in memories: print(f"- {memory['title']} ({memory['path']})")
    elif args.command == "show": print(service.show(args.memory_id))
    elif args.command == "run-daily": print("\n".join(service.run_daily(args.date)))
    elif args.command == "rebuild-index": print(f"Indexed {service.rebuild_index()} memories")
    elif args.command == "status": print(service.status())
    elif args.command == "web":
        from .web import serve
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
