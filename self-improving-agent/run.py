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




#!/usr/bin/env python3
# run.py
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agents.v0_1_0.agent import Agent


def main():
    parser = argparse.ArgumentParser(description="Self-Improving Agent Scaffold v0.1.0")
    parser.add_argument("--task", "-t", type=str, default=None)
    parser.add_argument("--self-improve", "-s", action="store_true")
    parser.add_argument("--next-version", type=str, default="v0.2.0")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    agent = Agent(verbose=not args.quiet)

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