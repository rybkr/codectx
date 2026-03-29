import argparse
import asyncio


async def run(args: argparse.Namespace) -> None:
    from experiments.harness import run_and_print

    exit_code = await run_and_print(args.scenarios or None)
    if exit_code:
        raise SystemExit(exit_code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.eval_invalidation",
        description="run reproducible invalidation scenarios",
    )
    parser.add_argument("scenarios", nargs="*", help="optional scenario names to run")
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
