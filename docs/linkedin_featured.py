"""LinkedIn Featured thumbnail: Digital Twin + Sentinel architecture."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("linkedin-featured.png")
W, H = 1200, 627

BG = (11, 16, 28)
LANE = (17, 24, 40)
INNER = (14, 22, 36)
BOX = (26, 36, 56)
LINE = (62, 82, 114)
INK = (236, 240, 248)
MUTED = (148, 160, 182)
TEAL = (45, 212, 191)
AMBER = (251, 191, 36)
BLUE = (96, 165, 250)
ROSE = (251, 113, 133)
ARROW = (128, 144, 172)

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
TITLE = ImageFont.truetype(str(FONT_DIR / "DIN Alternate Bold.ttf"), 26)
BODY = ImageFont.truetype(str(FONT_DIR / "Arial Bold.ttf"), 13)
TINY = ImageFont.truetype(str(FONT_DIR / "Arial.ttf"), 11)


def _box(draw, xy, title, sub="", accent=None):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=8, fill=BOX, outline=LINE, width=2)
    if accent:
        draw.rectangle((x0, y0, x0 + 4, y1), fill=accent)
    pad = 12 if accent else 10
    draw.text((x0 + pad, y0 + 8), title, font=BODY, fill=INK)
    if sub:
        draw.text((x0 + pad, y0 + 28), sub, font=TINY, fill=MUTED)


def _right(draw, x0, x1, y):
    draw.line([(x0, y), (x1, y)], fill=ARROW, width=2)
    draw.polygon([(x1, y), (x1 - 7, y - 4), (x1 - 7, y + 4)], fill=ARROW)


def _down(draw, x, y0, y1):
    draw.line([(x, y0), (x, y1)], fill=ARROW, width=2)
    draw.polygon([(x, y1), (x - 4, y1 - 7), (x + 4, y1 - 7)], fill=ARROW)


def _tool_loop(draw, ax0, ax1, ay, bx0, bx1, by):
    """call_model (top) ⇄ tools (below-left)."""
    mid_x = (ax0 + bx1) // 2
    draw.line([(ax0, ay), (mid_x, ay), (mid_x, by), (bx1, by)], fill=TEAL, width=2)
    draw.polygon([(bx1, by), (bx1 - 7, by - 4), (bx1 - 7, by + 4)], fill=TEAL)
    draw.line([(bx0, by), (bx0 - 12, by), (bx0 - 12, ay), (ax0, ay)], fill=TEAL, width=2)
    draw.polygon([(ax0, ay), (ax0 - 4, ay + 6), (ax0 + 4, ay + 6)], fill=TEAL)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.text((24, 10), "Gen-AI", font=TITLE, fill=INK)
    draw.text((128, 18), "two LangGraph systems", font=TINY, fill=MUTED)

    # ── Twin ──────────────────────────────────────────────────
    draw.rounded_rectangle((14, 46, 1186, 328), radius=14, fill=LANE, outline=LINE, width=1)
    draw.text((28, 56), "DIGITAL TWIN", font=BODY, fill=TEAL)
    draw.text((156, 57), "recruiter UI  →  guard  →  retrieve  →  judge", font=TINY, fill=MUTED)

    _box(draw, (28, 84, 158, 140), "Recruiter", "question", TEAL)
    _right(draw, 158, 174, 112)
    _box(draw, (174, 84, 324, 140), "Gradio :7860", "#chat #skills #exp", TEAL)
    _right(draw, 324, 340, 112)
    _box(draw, (340, 84, 512, 140), "CompactSession", "window + compact", BLUE)

    draw.rounded_rectangle((528, 76, 1172, 246), radius=10, fill=INNER, outline=LINE, width=1)
    draw.text((542, 82), "LangGraph", font=TINY, fill=TEAL)

    _box(draw, (542, 102, 678, 154), "#skills", "SkillInventory")
    _box(draw, (690, 102, 840, 154), "#experience", "roles newest first")
    _box(draw, (852, 102, 996, 154), "input_guard", "off-topic → END", AMBER)
    _right(draw, 996, 1012, 128)
    _box(draw, (1012, 102, 1158, 154), "call_model", "force search_profile", TEAL)

    _box(draw, (852, 186, 996, 234), "tools", "search_profile", TEAL)
    _box(draw, (1012, 186, 1158, 234), "evaluate_output", "grounded? fallback", AMBER)
    _tool_loop(draw, 1012, 1158, 154, 852, 996, 210)
    _down(draw, 1085, 154, 186)

    _box(draw, (28, 262, 220, 314), "Postgres :5432", "pgvector", AMBER)
    _box(draw, (236, 262, 468, 314), "profile", "resume + LinkedIn chunks")
    _box(draw, (484, 262, 728, 314), "session_memory", "recalled by similarity")
    _box(draw, (744, 262, 1172, 314), "embeddings: text-embedding-3-small", "OpenAI even if chat model swaps")

    # ── Sentinel ──────────────────────────────────────────────
    draw.rounded_rectangle((14, 344, 1186, 614), radius=14, fill=LANE, outline=LINE, width=1)
    draw.text((28, 354), "SENTINEL", font=BODY, fill=AMBER)
    draw.text((122, 355), "alert in  →  look it up  →  analyst reviews  →  human decides", font=TINY, fill=MUTED)

    _box(draw, (28, 382, 158, 438), "Alert", "incident | security", AMBER)
    _right(draw, 158, 174, 410)
    _box(draw, (174, 382, 324, 438), "FastAPI :8080", "investigate / decide", AMBER)

    draw.rounded_rectangle((340, 374, 1172, 530), radius=10, fill=INNER, outline=LINE, width=1)
    draw.text((354, 380), "LangGraph   thread_id = case_id", font=TINY, fill=AMBER)

    _box(draw, (354, 400, 478, 452), "route_kind", "keyword if omitted")
    _right(draw, 478, 492, 426)
    _box(draw, (492, 400, 640, 452), "attach_runbook", "skills/*.md always")
    _right(draw, 640, 654, 426)
    _box(draw, (654, 400, 830, 452), "investigator", "tools + ROOT_CAUSE", TEAL)
    _right(draw, 830, 844, 426)
    _box(draw, (844, 400, 990, 452), "analyst", "more / hold / pass", BLUE)
    _right(draw, 990, 1004, 426)
    _box(draw, (1004, 400, 1158, 452), "await_approval", "human interrupt", ROSE)

    _box(draw, (654, 476, 830, 520), "tools", "4 Java MCP calls", TEAL)
    _tool_loop(draw, 654, 830, 452, 654, 830, 498)
    draw.text((850, 490), "analyst talks to investigator only", font=TINY, fill=MUTED)

    _box(draw, (28, 550, 280, 602), "Java MCP :8090", "logs · metrics · lineage · IAM", TEAL)
    _box(draw, (296, 550, 560, 602), "Postgres :5433", "events + cases + checkpoints")
    _box(draw, (576, 550, 820, 602), "eval 6/6", "ROOT_CAUSE vs YAML")
    _box(draw, (836, 550, 1172, 602), "shared get_chat_llm()", "OpenAI · Anthropic · Gemini · Ollama")

    img.save(OUT, "PNG")
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    main()
