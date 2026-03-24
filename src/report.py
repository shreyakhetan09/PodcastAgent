from __future__ import annotations


def save_report(path: str, markdown_text: str) -> None:
    with open(path, "w", encoding="utf-8") as file:
        file.write(markdown_text)
