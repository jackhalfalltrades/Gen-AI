# Payment cannot open Postgres / charges stop / password expired

Named principal: svc-payment-db.

1. search_logs(service="payment", query="password_expired", window="30m")
2. search_logs(service="payment", query="account_locked", window="30m")
3. get_metrics(service="payment", name="iam.service_account_auth_failures", window="30m")
4. get_downstream(dataset="payments.transactions")
5. lookup_iam(principal="svc-payment-db")
