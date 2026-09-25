"""Investigator tools. HTTP to the Java MCP — the model never sees YAML files.

Four tools only. Playbooks are not in this list on purpose (see attach_runbook).
"""

import httpx
from langchain_core.tools import tool

import config

BASE_URL = config.SENTINEL_MCP_URL


def _get(path: str, **params) -> str:
    """GET /tools/... on :8090. timeout so a dead Java box fails the tool, not the process."""
    r = httpx.get(f"{BASE_URL}{path}", params=params, timeout=10.0)
    r.raise_for_status()
    return r.text

@tool
def search_logs(service: str, query: str, window: str = "30m") -> list[dict]:
    """Find log/auth/iam rows already in Postgres events.

    service: id from services.yaml (checkout, payment, inventory, fulfillment, promotions, login).
    query: substring in the message (HikariPool, login_failed, payable_cents=0).
    window: lookback such as 30m. Does not return metrics.
    """
    return _get("/tools/search_logs",service=service, query=query, window=window)


@tool
def get_metrics(service: str, name: str, window: str = "30m") -> dict:
    """Latest metric value for one service and name.

    service: id from services.yaml.
    name: metric name (hikari.connections.active, login.fail_rate, promotions.zero_price_rate).
    window: lookback such as 30m. One latest row, not a series.
    """
    return _get("/tools/get_metrics", service=service, name=name, window=window)
    

@tool
def get_downstream(dataset: str) -> dict:
    """Who drinks this dataset, plus classification tags (PCI, PII).

    dataset: id from lineage.yaml (payments.transactions, inventory.stock, promotions.rules, identity.sessions).
    Returns downstream names and tags. Does not say the incident is an oversell or a $0 price.
    """
    return _get("/tools/get_downstream", dataset=dataset)


@tool
def lookup_iam(principal: str) -> dict:
    """Roles for a service account in lineage.yaml.

    principal: id such as svc-checkout, svc-analytics, svc-payment-db.
    Skip when the story is external attackers, not a svc-* account.
    """
    return _get("/tools/lookup_iam", principal=principal)


TOOLS = [search_logs, get_metrics, get_downstream, lookup_iam]
