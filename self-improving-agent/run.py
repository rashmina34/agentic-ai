# #!/usr/bin/env python3
# # run.py — CLI entrypoint for the self-improving agent scaffold
# """
# Usage:
#     python run.py --task "List all Python files in this project"
#     python run.py --self-improve
#     python run.py --self-improve --next-version v0.2.0
# """

# import argparse
# import sys
# import os

# # Make sure we can import from agents/
# sys.path.insert(0, os.path.dirname(__file__))

# from agents.v0_1_0.agent import Agent   # note: Python package uses underscores


# def main():
#     parser = argparse.ArgumentParser(
#         description="Self-Improving Agent Scaffold v0.1.0"
#     )
#     parser.add_argument(
#         "--task", "-t",
#         type=str,
#         default=None,
#         help="Task for the agent to execute.",
#     )
#     parser.add_argument(
#         "--self-improve", "-s",
#         action="store_true",
#         help="Run the self-improvement loop (reads own source, proposes & writes vNEXT).",
#     )
#     parser.add_argument(
#         "--next-version",
#         type=str,
#         default="v0.2.0",
#         help="Target version string for self-improvement output. Default: v0.2.0",
#     )
#     parser.add_argument(
#         "--quiet", "-q",
#         action="store_true",
#         help="Suppress verbose step-by-step output.",
#     )
#     args = parser.parse_args()

#     if not os.environ.get("ANTHROPIC_API_KEY"):
#         print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
#         sys.exit(1)

#     agent = Agent(verbose=not args.quiet)

#     if args.self_improve:
#         result = agent.self_improve(next_version=args.next_version)
#         print("\n" + "═" * 60)
#         print("Self-improvement cycle complete.")
#         print("═" * 60)
#         print(result)
#     elif args.task:
#         result = agent.run(args.task)
#         print("\n" + "═" * 60)
#         print("Final Answer:")
#         print("═" * 60)
#         print(result)
#     else:
#         parser.print_help()
#         sys.exit(0)


# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
# run.py
# import argparse
# import sys
# import os

# sys.path.insert(0, os.path.dirname(__file__))

# from agents.v0_1_0.agent import Agent


# def main():
#     parser = argparse.ArgumentParser(description="Self-Improving Agent Scaffold v0.1.0")
#     parser.add_argument("--task", "-t", type=str, default=None)
#     parser.add_argument("--self-improve", "-s", action="store_true")
#     parser.add_argument("--next-version", type=str, default="v0.2.0")
#     parser.add_argument("--quiet", "-q", action="store_true")
#     args = parser.parse_args()

#     if not os.environ.get("GEMINI_API_KEY"):
#         print("ERROR: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
#         sys.exit(1)

#     agent = Agent(verbose=not args.quiet)

#     if args.self_improve:
#         result = agent.self_improve(next_version=args.next_version)
#     elif args.task:
#         result = agent.run(args.task)
#     else:
#         parser.print_help()
#         sys.exit(0)

#     print("\n" + "═" * 60)
#     print(result)


# if __name__ == "__main__":
#     main()



#  uncomment it if run only v0.1.0

#!/usr/bin/env python3
# run.py
# import argparse
# import sys
# import os

# sys.path.insert(0, os.path.dirname(__file__))

# from agents.v0_1_0.agent import Agent


# def main():
#     parser = argparse.ArgumentParser(description="Self-Improving Agent Scaffold v0.1.0")
#     parser.add_argument("--task", "-t", type=str, default=None)
#     parser.add_argument("--self-improve", "-s", action="store_true")
#     parser.add_argument("--next-version", type=str, default="v0.2.0")
#     parser.add_argument("--quiet", "-q", action="store_true")
#     args = parser.parse_args()

#     if not os.environ.get("GROQ_API_KEY"):
#         print("ERROR: GROQ_API_KEY environment variable not set.", file=sys.stderr)
#         sys.exit(1)

#     agent = Agent(verbose=not args.quiet)

#     if args.self_improve:
#         result = agent.self_improve(next_version=args.next_version)
#     elif args.task:
#         result = agent.run(args.task)
#     else:
#         parser.print_help()
#         sys.exit(0)

#     print("\n" + "═" * 60)
#     print(result)


# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
# run.py — CLI entrypoint (auto-detects latest version)
"""
Usage:
    python run.py --task "your task"
    python run.py --self-improve
    python run.py --version v0.1.0 --task "your task"
    python run.py --logs
"""

import argparse
import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))


def load_agent(version: str):
    if version == "v0.2.0":
        from agents.v0_2_0.agent import Agent
    elif version == "v0.1.0":
        from agents.v0_1_0.agent import Agent
    else:
        print(f"ERROR: Unknown version '{version}'", file=sys.stderr)
        sys.exit(1)
    return Agent


def show_logs():
    from agents.v0_2_0.config import RUNS_LOG_PATH
    if not RUNS_LOG_PATH.exists():
        print("No run logs yet.")
        return
    print(f"{'RUN_ID':<10} {'VERSION':<10} {'STEPS':<6} {'OUTCOME':<20} {'TASK'}")
    print("─" * 80)
    with open(RUNS_LOG_PATH) as f:
        for line in f:
            r = json.loads(line)
            task_preview = r['task'][:40] + ("..." if len(r['task']) > 40 else "")
            print(f"{r['run_id']:<10} {r['version']:<10} {r['steps']:<6} {r['outcome']:<20} {task_preview}")


def main():
    parser = argparse.ArgumentParser(description="Self-Improving Agent Scaffold")
    parser.add_argument("--task", "-t", type=str, default=None)
    parser.add_argument("--self-improve", "-s", action="store_true")
    parser.add_argument("--next-version", type=str, default="v0.3.0")
    parser.add_argument("--version", "-v", type=str, default="v0.2.0",
                        help="Agent version to use. Default: v0.2.0")
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--logs", "-l", action="store_true",
                        help="Show experiment run log.")
    args = parser.parse_args()

    if args.logs:
        show_logs()
        return

    if not os.environ.get("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    AgentClass = load_agent(args.version)
    agent = AgentClass(verbose=not args.quiet)

    if args.self_improve:
        result = agent.self_improve(next_version=args.next_version)
    elif args.task:
        result = agent.run(args.task)
    else:
        parser.print_help()
        sys.exit(0)

    print("\n" + "═" * 60)
    print(result)


if __name__ == "__main__":
    main()
# ```

# ---

# ## CHANGELOG — v0.2.0
# ```
# ## [0.2.0] — 2026-03-09

# ### Added
# - ContextManager: sliding-window context (keeps last 6 pairs, summarizes overflow)
# - Persistent SQLite memory via memory_store / memory_search tools
# - shell_run tool with command whitelist [SAFETY: whitelist in config.SHELL_WHITELIST]
# - Retry/backoff on 429/503 API errors (3 attempts, exponential backoff)
# - RunLogger: every run appended to .agent_data/runs.jsonl
# - --logs CLI flag to view experiment history
# - --version CLI flag to select agent version

# ### Improved
# - prompts.py: cleaner memory usage guidelines, summarization prompt
# - tools.py: 7 tools (up from 4), consistent error message format
# - agent.py: clean separation of _call_model / react_loop / summarization

# ### Architecture
# - New modules: memory.py, context.py, logger.py
# - Data stored in .agent_data/ (gitignore this in production)