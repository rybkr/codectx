from __future__ import annotations

import asyncio

from benchmarks.harness import load_cases, run_case


async def main() -> int:
    results: list = []
    for case in load_cases():
        results.append(await run_case(case))

    for result in results:
        status: str = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}")
        print(f"  changed:  {result.changed_symbols}")
        print(f"  impacted: {result.impacted_symbols}")
        print(f"  agents:   {result.affected_agents}")
        print(f"  stale:    {result.stale_symbols}")

    return not all(result.passed for result in results)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
