# Wrong price / $0.00 payable / promotion config

discount_bps is a log line, not a metric. ROOT_CAUSE must cite the catch-all
and the number: discount_bps=10000. Do not say "full price" instead.

1. search_logs(service="promotions", query="applied config rev", window="15m")
2. search_logs(service="promotions", query="discount_bps", window="15m")
3. get_metrics(service="promotions", name="promotions.zero_price_rate", window="15m")
4. get_downstream(dataset="promotions.rules")
5. search_logs(service="checkout", query="payable_cents=0", window="15m")
6. lookup_iam — skip (bad config push, not a principal)
