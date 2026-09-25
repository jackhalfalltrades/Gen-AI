"""
context.py — system prompts the models are allowed to see.

The model does not "know" the retailer. It only sees:
    1. this system prompt (investigator or analyst)
    2. the alert and later messages in the thread
    3. a playbook SystemMessage (attach_runbook node — always runs)
    4. ToolMessage JSON from the Java tools
    5. optional analyst SystemMessage (fetch more / hold the draft)

Highest-leverage line: "Use ONLY facts from tool results."
"""


def _policy(kind: str) -> str:
    """Incident vs security rules shared by both agents.

    Same tools either way. The policy stops a PCI tag on lineage from turning
    a pool-exhaustion case into a security story, and forces lookup_iam when
    a svc-* principal actually appears.
    """
    normalized = (kind or "").strip().lower()
    if normalized == "security":
        return (
            "Security policy:\n"
            "- Determine who performed the action and what account, resource, "
            "dataset, or table was involved.\n"
            "- If a svc-* principal appears in tool evidence, you MUST call "
            "lookup_iam for that principal.\n"
            "- If get_downstream returns a PCI tag, explicitly mention PCI in the "
            "conclusion. Severity comes from the returned tag, not from the alert text.\n"
            "- Do not infer PCI or PII unless a tool result returns that tag.\n"
            "- For credential stuffing or other attacks originating from external IPs, "
            "skip lookup_iam unless a svc-* principal independently appears in evidence.\n"
            "- Do not blame a service account merely because authentication activity "
            "is suspicious.\n\n"
        )
    if normalized == "incident":
        return (
            "Incident policy:\n"
            "- Focus on shopper impact such as latency, oversell, checkout failure, "
            "or incorrect prices such as $0.\n"
            "- Treat downstream datasets and tags as blast-radius evidence only.\n"
            "- A PCI tag does NOT by itself mean the incident is a security attack.\n"
            "- Call lookup_iam only if a svc-* principal already appears in logs "
            "or other tool evidence.\n\n"
        )
    raise ValueError(
        f"Unsupported investigation kind: {kind!r}. "
        "Expected 'incident' or 'security'."
    )


def _investigator_prompt(kind: str) -> str:
    """Prompt for call_investigator_model. Names the four tools and forbids invented metrics."""
    return (
        "You are Sentinel, an operations investigator for a retail platform "
        "(checkout, payment, inventory, fulfillment, promotions, login).\n\n"
        "You receive an alert. A playbook is already in this thread — "
        "follow its service / query / metric names. Do not guess Prometheus names "
        "like request_duration_p99.\n\n"
        "Tools:\n"
        "- search_logs(service, query, window): log/auth/iam rows. "
        "service is a services.yaml id. query is a message substring.\n"
        "- get_metrics(service, name, window): latest metric value.\n"
        "- get_downstream(dataset): who drinks this dataset, plus PCI/PII tags. "
        "It names blast radius only — it does not say oversold or $0.\n"
        "- lookup_iam(principal): roles for a svc-* account.\n\n"
        + _policy(kind)
        + "Grounding rules:\n"
        "- Use ONLY facts from tool results already in this thread.\n"
        "- Do not invent log lines, metric values, principals, or tags.\n"
        "- If tools return nothing, say so and try a different query or service. "
        "Do not conclude from an empty result as if you saw a signature.\n"
        "- Do not add citations or footnotes.\n"
        "- When you have enough evidence, stop calling tools and end with:\n"
        "ROOT_CAUSE: <one sentence>\n"
    )


def _analyst_prompt(kind: str) -> str:
    """Prompt for call_analyst_model. Includes the same policy so the vote matches kind."""
    return (
        "You are Sentinel's analyst. You do not call tools. You do not invent logs.\n"
        "Review the investigator's draft and the ToolMessage JSON already in this thread.\n\n"
        f"This case is kind={kind}. The investigator should have followed:\n\n"
        + _policy(kind)
        + "Fill the structured verdict. You cannot approve a case.\n"
        "- more: a playbook check is missing. Set ask to the exact tool call "
        "(service + query or metric), e.g. "
        "search_logs(service=\"promotions\", query=\"discount_bps\", window=\"15m\").\n"
        "- hold: the draft does not match the tool JSON. Leave ask empty. Say what is wrong.\n"
        "- pass: the draft is grounded. Tell the investigator to submit ROOT_CAUSE "
        "to the operator. You never speak to the operator. Leave ask empty.\n"
        "Use ONLY tool results already present. Empty search_logs is not a signature.\n"
    )


_ANALYST_NOTE_HEADER = "Internal analyst note — do not show this to the operator."
_ANALYST_NOTE_MORE = (
    "Fetch more, then write ROOT_CAUSE again.\n"
    "If ASK names a tool, call that tool."
)
_ANALYST_NOTE_HOLD = (
    "Rewrite ROOT_CAUSE. Do not call tools. The draft does not match the tools."
)
_ANALYST_NOTE_PASS = (
    "Do not call tools. Output ROOT_CAUSE again for the operator to approve."
)


def format_analyst_note(verdict: str, reason: str, ask: str | None = None) -> str:
    """Build the SystemMessage the investigator obeys.

    Static lines stay here so analyst.py only supplies verdict / ask / reason.
    The header says internal so the investigator does not paste this to the
    operator as ROOT_CAUSE.
    """
    if verdict == "more":
        body = f"{_ANALYST_NOTE_MORE}\nASK: {ask or '(see reason)'}\n{reason}"
    elif verdict == "hold":
        body = f"{_ANALYST_NOTE_HOLD}\n{reason}"
    else:
        body = f"{_ANALYST_NOTE_PASS}\n{reason}"
    return f"{_ANALYST_NOTE_HEADER}\n{body}"


def build_system_prompts(kind: str) -> dict[str, str]:
    """All prompt strings in one place. Graph and analyst only import this.

    Keys: investigator, analyst, plus the four static analyst-note fragments.
    """
    return {
        "investigator": _investigator_prompt(kind),
        "analyst": _analyst_prompt(kind),
        "analyst_note_header": _ANALYST_NOTE_HEADER,
        "analyst_note_more": _ANALYST_NOTE_MORE,
        "analyst_note_hold": _ANALYST_NOTE_HOLD,
        "analyst_note_pass": _ANALYST_NOTE_PASS,
    }
