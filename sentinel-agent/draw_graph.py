"""Write the compiled investigation graph as a PNG for the README."""

from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from agent.graph import _build_graph

OUT = Path(__file__).resolve().parent / "docs" / "graph.png"


def main() -> None:
    png = _build_graph(MemorySaver()).get_graph().draw_mermaid_png()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(png)
    print(f"wrote {OUT} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
