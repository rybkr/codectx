from __future__ import annotations


def print_heading(title: str) -> None:
    print(title)
    print("=" * len(title))


def print_kv(label: str, value: object) -> None:
    print(f"{label:<16} {value}")


def print_list(title: str, items: list[str] | tuple[str, ...]) -> None:
    print(f"{title} ({len(items)})")
    for item in items:
        print(f"  {item}")
