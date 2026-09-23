# Login failures / fail rate high / accounts locked

Attackers are external users on rotating IPs, not a svc-* account.
ROOT_CAUSE must say credential stuffing from rotating IPs.

1. search_logs(service="login", query="login_failed", window="30m")
2. search_logs(service="login", query="account_locked", window="30m")
3. get_metrics(service="login", name="login.fail_rate", window="30m")
4. get_downstream(dataset="identity.sessions")
5. lookup_iam — skip
