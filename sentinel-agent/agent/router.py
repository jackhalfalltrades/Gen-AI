"""Triage: pick incident vs security from the alert text.

Fill in route(). Graph node route_kind calls this when kind was not supplied.
"""


def route(alert: str) -> str:
    """Return 'incident' or 'security'.

    Keyword v1: login / pci / select / svc- /
    password / credential / iam / auth → security, else incident.
    """
    text = alert.lower()
    for word in ("login", "pci", "select", "svc-", "password", "credential", "iam", "auth"):
        if word in text:
            return "security"
    return "incident"

