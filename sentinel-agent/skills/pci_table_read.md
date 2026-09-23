# Unexpected SELECT on payments / PCI read / warehouse account

Named principal: svc-analytics. Severity comes from PCI tags, not from the prompt.

1. search_logs(service="payment", query="SELECT", window="30m")
2. search_logs(service="payment", query="payments.transactions", window="30m")
3. get_metrics(service="payment", name="iam.unexpected_pci_reads", window="30m")
4. get_downstream(dataset="payments.transactions")
5. lookup_iam(principal="svc-analytics")
