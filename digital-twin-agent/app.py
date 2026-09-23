"""
app.py — Slack-like Gradio UI. No RAG or graph logic lives here.

    uv run python app.py     →  http://127.0.0.1:7860

What this file is allowed to do
    - Hold one CompactSession in gr.State (must not reset on each question).
    - Yield "Peravelli is typing" *before* ask_stream() so the wait is visible.
    - Route #skills / #experience through ask_stream(..., route=...) not chat.
    - Style Gradio until it looks like Slack (CSS is loaded at launch —
      restart the process after static/app.css changes).

Why the sidebar is HTML, not Gradio Buttons
    Gradio buttons flex-grow, pick up theme styles after a response, and
    cannot share a grid with a "# Channels" heading. The visible list is
    plain divs. Hidden Gradio buttons (off-screen) still fire the Python
    handlers; APP_JS clicks them.

Async generators yield typing first, then stream tokens from ask_stream()
so the Gradio event loop can serve other sessions while this one waits.
"""

from datetime import datetime
from pathlib import Path

import gradio as gr

from ask import ask_stream
from context import build_system_prompt
from memory import CompactSession

ROOT = Path(__file__).resolve().parent
# Read at import time — Gradio does not watch this file.
CSS = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
USER_AVATAR = str(ROOT / "static" / "avatars" / "user.svg")
BOT_AVATAR = str(ROOT / "static" / "avatars" / "chandra.svg")

# Force light Slack chrome even if the OS is in dark mode. Every
# *_dark token is set to the light value on purpose.

theme = gr.themes.Base(
    primary_hue="green",
    secondary_hue="slate",
    neutral_hue="slate",
    font=gr.themes.GoogleFont("Lato"),
    radius_size=gr.themes.sizes.radius_sm,
).set(
    body_background_fill="#ffffff",
    body_background_fill_dark="#ffffff",
    body_text_color="#1d1c1d",
    body_text_color_dark="#1d1c1d",
    background_fill_primary="#ffffff",
    background_fill_primary_dark="#ffffff",
    background_fill_secondary="#ffffff",
    background_fill_secondary_dark="#ffffff",
    block_background_fill="#ffffff",
    block_background_fill_dark="#ffffff",
    block_border_width="0px",
    block_border_width_dark="0px",
    block_shadow="none",
    block_shadow_dark="none",
    panel_background_fill="#ffffff",
    panel_background_fill_dark="#ffffff",
    input_background_fill="#ffffff",
    input_background_fill_dark="#ffffff",
    border_color_primary="#e8e8e8",
    border_color_primary_dark="#e8e8e8",
)


HEADER_RESUME = """
<div class="slack-header">
  <div>
    <h1># interactive-resume</h1>
    <p>Grounded on Chandra’s resume and profile.</p>
  </div>
  <span class="slack-online">● Chandra</span>
</div>
"""

HEADER_SKILLS = """
<div class="slack-header">
  <div>
    <h1># skills</h1>
    <p>Grounded on Chandra’s resume and profile.</p>
  </div>
  <span class="slack-online">● Chandra</span>
</div>
"""

HEADER_EXPERIENCE = """
<div class="slack-header">
  <div>
    <h1># experience</h1>
    <p>Grounded on Chandra’s resume and profile.</p>
  </div>
  <span class="slack-online">● Chandra</span>
</div>
"""

TYPING_ON = (
    '<div class="slack-typing" aria-live="polite">Peravelli is typing</div>'
)
TYPING_OFF = '<div class="slack-typing" hidden></div>'


# _new_session: empty CompactSession with the hand-written system prompt.
def _new_session() -> CompactSession:
    """Fresh window + the hand-written system prompt from context.py."""
    return CompactSession(build_system_prompt())


# _stamp: Slack-style clock for the You / Chandra byline.
def _stamp() -> str:
    """Slack-style '2:54 PM' without a leading zero on the hour."""
    return datetime.now().strftime("%I:%M %p").lstrip("0")


# _stream_into: grow the last assistant bubble as ask_stream yields text.
async def _stream_into(history: list, stamp: str, question: str, session, route: str):
    """
    Yield (history, session) only after the first token.

    Do not append an empty Chandra bubble first — guard + RAG run
    before any text, and that empty banner looked like a stuck reply.
    Typing stays on from the handler until this yields.
    """
    history = list(history)
    started = False
    async for partial in ask_stream(question, session, route=route):
        bubble = {"role": "assistant", "content": f"**Chandra**  {stamp}\n\n{partial}"}
        shown = list(history)
        if not started:
            shown.append(bubble)
            started = True
        else:
            shown[-1] = bubble
        history = shown
        yield history, session


# respond: composer submit — typing on, stream tokens, typing off.
async def respond(message: str, history: list, session: CompactSession | None):
    """
    Chat path. First yield: user bubble + typing on.
    Then stream the assistant bubble. Last yield: typing off.
    Empty submit is a no-op so Enter on a blank box does not clear history.
    """
    if session is None:
        session = _new_session()
    message = (message or "").strip()
    if not message:
        yield "", history, session, HEADER_RESUME, TYPING_OFF
        return

    history = list(history or [])
    stamp = _stamp()
    history.append({"role": "user", "content": f"**You**  {stamp}\n\n{message}"})
    yield "", history, session, HEADER_RESUME, TYPING_ON

    async for history, session in _stream_into(history, stamp, message, session, "chat"):
        yield "", history, session, HEADER_RESUME, TYPING_ON
    yield "", history, session, HEADER_RESUME, TYPING_OFF


# show_skills: #skills click — await ask(route="skills") on the same session.
async def show_skills(history: list, session: CompactSession | None):
    """#skills click. Same session — do not reset the recruiter's thread."""
    if session is None:
        session = _new_session()
    history = list(history or [])
    stamp = _stamp()
    yield history, session, HEADER_SKILLS, TYPING_ON, gr.update(placeholder="Message #skills")

    async for history, session in _stream_into(history, stamp, "", session, "skills"):
        yield history, session, HEADER_SKILLS, TYPING_ON, gr.update(placeholder="Message #skills")
    yield history, session, HEADER_SKILLS, TYPING_OFF, gr.update(placeholder="Message #skills")


# show_experience: #experience click — await ask(route="experience").
async def show_experience(history: list, session: CompactSession | None):
    """#experience click. route=experience skips input_guard and the chat model."""
    if session is None:
        session = _new_session()
    history = list(history or [])
    stamp = _stamp()
    yield history, session, HEADER_EXPERIENCE, TYPING_ON, gr.update(placeholder="Message #experience")

    async for history, session in _stream_into(history, stamp, "", session, "experience"):
        yield history, session, HEADER_EXPERIENCE, TYPING_ON, gr.update(placeholder="Message #experience")
    yield history, session, HEADER_EXPERIENCE, TYPING_OFF, gr.update(placeholder="Message #experience")


# show_resume: #interactive-resume — header only, keep history.
def show_resume(history: list, session: CompactSession | None):
    """#interactive-resume: header only. History stays so they can keep chatting."""
    if session is None:
        session = _new_session()
    return history or [], session, HEADER_RESUME, TYPING_OFF, gr.update(placeholder="Message #interactive-resume")


# reset: redo icon — new session, empty chatbot, resume header.
def reset():
    """Redo icon next to Send — new CompactSession, empty chatbot, resume header."""
    return [], _new_session(), HEADER_RESUME, TYPING_OFF, gr.update(value="", placeholder="Message #interactive-resume")


with gr.Blocks(
    title="Chandra Peravelli — Interactive Resume",
    fill_width=True,
    fill_height=True,
) as twin:
    # None until the first question — we construct CompactSession lazily
    # so opening the page does not create an unused LLM/memory object.
    session = gr.State(None)

    with gr.Row(elem_id="workspace", scale=1):
        with gr.Column(elem_id="sidebar", scale=0, min_width=200):
            gr.HTML(
                """
                <div class="slack-side">
                  <div class="slack-ws">
                    <div>
                      Peravelli
                      <small>Interactive resume</small>
                    </div>
                  </div>
                  <div class="slack-nav">
                    <div class="slack-row heading"><span class="hash">#</span><span>Channels</span></div>
                    <div class="slack-row active" data-channel="resume" role="button" tabindex="0">
                      <span class="hash">#</span><span>interactive-resume</span>
                    </div>
                    <div class="slack-row" data-channel="experience" role="button" tabindex="0">
                      <span class="hash">#</span><span>experience</span>
                    </div>
                    <div class="slack-row" data-channel="skills" role="button" tabindex="0">
                      <span class="hash">#</span><span>skills</span>
                    </div>
                  </div>
                </div>
                """,
                apply_default_css=False,
            )
        with gr.Column(elem_id="main-pane", scale=1, min_width=280):
            with gr.Row(elem_id="header-row"):
                header = gr.HTML(HEADER_RESUME, elem_id="header", apply_default_css=False)
            chatbot = gr.Chatbot(
                elem_id="chatbot",
                scale=1,
                height=None,
                min_height=160,
                label=None,
                show_label=False,
                container=False,
                buttons=[],
                placeholder="This is the very beginning of **#interactive-resume**. Ask about Chandra’s roles, skills, or experience.",
                layout="panel",
                avatar_images=(USER_AVATAR, BOT_AVATAR),
            )
            typing = gr.HTML(TYPING_OFF, elem_id="typing", apply_default_css=False)
            with gr.Column(elem_id="composer-box", scale=0):
                box = gr.Textbox(
                    elem_id="composer",
                    placeholder="Message #interactive-resume",
                    show_label=False,
                    container=False,
                    lines=1,
                    max_lines=6,
                )
                with gr.Row(elem_id="composer-bar"):
                    gr.HTML(
                        """
                        <div class="slack-tools">
                          <span title="Attach">+</span>
                          <span title="Format">Aa</span>
                          <span title="Emoji">☺</span>
                          <span title="Mention">@</span>
                          <span title="Record">●</span>
                          <span title="Slash command">/</span>
                        </div>
                        """,
                        apply_default_css=False,
                    )
                    with gr.Row(elem_id="composer-actions"):
                        clear = gr.Button(
                            "New conversation",
                            elem_id="reset-btn",
                            size="sm",
                        )
                        send = gr.Button("Send", elem_id="ask-btn", size="sm")

    # Off-screen Gradio buttons. CSS parks #hidden-chans at left:-9999px.
    # APP_JS clicks these so Python handlers still run. visible=False
    # buttons are not in the DOM, so JS click() cannot fire them.
    with gr.Row(elem_id="hidden-chans"):
        chan_resume = gr.Button("resume", elem_id="chan-resume")
        chan_experience = gr.Button("experience", elem_id="chan-experience")
        chan_skills = gr.Button("skills", elem_id="chan-skills")

    box.submit(
        respond,
        [box, chatbot, session],
        [box, chatbot, session, header, typing],
        show_progress="hidden",
    )
    send.click(
        respond,
        [box, chatbot, session],
        [box, chatbot, session, header, typing],
        show_progress="hidden",
    )
    chan_skills.click(
        show_skills,
        [chatbot, session],
        [chatbot, session, header, typing, box],
        show_progress="hidden",
    )
    chan_experience.click(
        show_experience,
        [chatbot, session],
        [chatbot, session, header, typing, box],
        show_progress="hidden",
    )
    chan_resume.click(
        show_resume,
        [chatbot, session],
        [chatbot, session, header, typing, box],
        show_progress="hidden",
    )
    clear.click(
        reset,
        outputs=[chatbot, session, header, typing, box],
        show_progress="hidden",
    )


# Capture-phase listeners so Gradio does not eat Enter before we send.
# fireChan clicks the hidden Gradio button by id (not the HTML row).
APP_JS = """
function() {
  /* Show or hide the "Peravelli is typing" line under the chat. */
  function setTyping(on) {
    const host = document.querySelector("#typing");
    if (!host) return;
    let node = host.querySelector(".slack-typing");
    if (!node) {
      host.insertAdjacentHTML(
        "beforeend",
        '<div class="slack-typing" aria-live="polite">Peravelli is typing</div>'
      );
      node = host.querySelector(".slack-typing");
    }
    if (on) node.removeAttribute("hidden");
    else node.setAttribute("hidden", "");
  }

  /* Blue Slack highlight on the HTML channel row matching name. */
  function markChannel(name) {
    document.querySelectorAll(".slack-row[data-channel]").forEach((el) => {
      el.classList.toggle("active", el.dataset.channel === name);
    });
  }

  /* Click the hidden Gradio button so the Python handler actually runs. */
  function fireChan(id) {
    const host = document.getElementById(id);
    const btn = host && (host.matches("button") ? host : host.querySelector("button"));
    if (btn) btn.click();
  }

  markChannel("resume");

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
    const field = e.target.closest("#composer textarea, #composer input");
    if (!field) return;
    e.preventDefault();
    e.stopPropagation();
    setTyping(true);
    document.getElementById("ask-btn")?.click();
  }, true);

  document.addEventListener("click", (e) => {
    const send = e.target.closest("#ask-btn");
    const redo = e.target.closest("#reset-btn");
    const chan = e.target.closest(".slack-row[data-channel]");
    if (chan) {
      const name = chan.dataset.channel;
      markChannel(name);
      if (name === "experience") {
        setTyping(true);
        fireChan("chan-experience");
      } else if (name === "skills") {
        setTyping(true);
        fireChan("chan-skills");
      } else {
        fireChan("chan-resume");
      }
    } else if (redo) {
      markChannel("resume");
      setTyping(false);
    } else if (send) {
      setTyping(true);
    }
  }, true);
}
"""


if __name__ == "__main__":
    twin.launch(css=CSS, theme=theme, js=APP_JS)
