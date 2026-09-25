"""Keyword triage: incident vs security from the alert text.

This is not a second graph. It only picks which policy string
build_system_prompts() attaches. The tools and the approval node stay the same.
"""


def route(alert: str) -> str:
    """Return 'incident' or 'security'.

    Why keywords: six alerts, no classifier. login / pci / select / svc- /
    password / credential / iam / auth → security, else incident.
    route_kind skips this when the client already sent kind.
    """
    text = alert.lower()
    for word in ("login", "pci", "select", "svc-", "password", "credential", "iam", "auth"):
        if word in text:
            return "security"
    return "incident"
