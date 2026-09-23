# Checkout latency / p99 high

This retailer does not emit Prometheus names like request_duration_p99.

1. search_logs(service="checkout", query="HikariPool", window="30m")
2. get_metrics(service="checkout", name="hikari.connections.active", window="30m")
3. get_metrics(service="checkout", name="checkout.p99_ms", window="30m")
4. get_downstream(dataset="payments.transactions")
5. lookup_iam — skip unless a svc-* principal is in the logs

Pool max in this world is 20. Latency is the symptom; say what saturated.
