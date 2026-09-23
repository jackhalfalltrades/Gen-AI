# Inventory lag / oversell / pick failed

ROOT_CAUSE must say inventory-sync Kafka consumer lag and that checkout used
stale stock. Oversell / pick failed are symptoms.

1. search_logs(service="inventory", query="consumer lag", window="20m")
2. get_metrics(service="inventory", name="kafka.consumer.lag_ms", window="20m")
3. get_downstream(dataset="inventory.stock")
4. search_logs(service="checkout", query="oversell", window="20m")
5. search_logs(service="fulfillment", query="pick failed", window="20m")
6. lookup_iam — skip (lag + stale data, not a principal)
