import sys
import time

from app.agent import ask


def main(repo_id: int, question: str, verbose: bool, max_steps: int) -> None:
    def show_step(step) -> None:
        args = ", ".join(f"{k}={v!r}" for k, v in step.arguments.items())
        print(f"  tool: {step.name}({args})")
        if verbose:
            print("-" * 60)
            print(step.result)
            print("-" * 60)

    start = time.time()
    result = ask(repo_id, question, max_steps=max_steps, on_step=show_step)
    print("\n" + result.answer)
    print(f"\n[{len(result.steps)} tool calls, {result.tokens} tokens, {time.time() - start:.1f}s]")
    if result.hit_step_limit:
        print("(stopped at the step limit)")


if __name__ == "__main__":
    args = sys.argv[1:]
    verbose = "--verbose" in args
    args = [a for a in args if a != "--verbose"]

    max_steps = 8
    if "--max-steps" in args:
        i = args.index("--max-steps")
        max_steps = int(args[i + 1])
        del args[i:i + 2]

    if len(args) < 2:
        sys.exit("Usage: python -m scripts.ask <repo_id> <question> [--verbose] [--max-steps N]")
    main(int(args[0]), " ".join(args[1:]), verbose, max_steps)