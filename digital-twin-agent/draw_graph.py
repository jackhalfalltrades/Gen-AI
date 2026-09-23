"""
draw_graph.py — write the compiled LangGraph as a PNG for the README.

LangGraph can render itself:

    from IPython.display import Image, display
    from graph import build_graph
    display(Image(build_graph().get_graph().draw_mermaid_png()))

This script writes digital-twin-agent/docs/graph.png (the twin README image).

Conditional edges must have a path map in graph.py or mermaid only
draws __start__ → __end__.
"""

from pathlib import Path

from graph import build_graph

OUT = Path(__file__).resolve().parent / "docs" / "graph.png"


def main() -> None:
    """Compile the graph, render mermaid PNG, write docs/graph.png."""
    graph = build_graph()
    png = graph.get_graph().draw_mermaid_png()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(png)
    print(f"wrote {OUT} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
