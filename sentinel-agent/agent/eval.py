"""Compare ROOT_CAUSE to each scenario's expected.root_cause. Needs Postgres + Java."""

import yaml

import config
from agent.investigate import investigate, root_cause_line

# Alerts the playbooks already match. kind comes from the YAML.
ALERTS = {
    "checkout_db_pool": "checkout p99 is high",
    "inventory_lag": "inventory kafka consumer lag is high; checkout may be overselling",
    "promo_pricing": "checkout showing $0.00 payable after a promotions config push",
    "credential_stuffing": "login failure rate is high",
    "sa_rotate_failed": "payment can no longer open Postgres; charges stop",
    "pci_table_read": "unexpected SELECT on the payments table",
}


def _tokens(text: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) > 2}


def grade(expected: str, actual: str) -> bool:
    exp, got = _tokens(expected), _tokens(actual)
    if not exp:
        return False
    return len(exp & got) / len(exp) >= 0.4


def main() -> int:
    passed = 0
    for path in sorted(config.SCENARIOS.glob("*.yaml")):
        scenario = yaml.safe_load(path.read_text())
        sid = scenario["id"]
        kind = scenario.get("kind") or "incident"
        expected = (scenario.get("expected") or {}).get("root_cause") or ""
        alert = ALERTS.get(sid) or scenario.get("title") or sid
        print(f"\n=== {sid} ({kind}) ===")
        report = investigate(alert, kind=kind)
        actual = root_cause_line(report)
        ok = grade(expected, actual)
        passed += int(ok)
        print(f"expected: {expected}")
        print(f"actual:   {actual}")
        print("PASS" if ok else "FAIL")
    total = len(ALERTS)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
