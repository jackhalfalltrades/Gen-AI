# MCP tools

Four tools. Every scenario uses this **same** list. The agent picks **which** to call and **what arguments**.

Spring AI 2.0 MCP server (Streamable-HTTP, port **8090**). Same methods on `GET /tools/...` for curl.

```bash
cd sentinel-agent/mcp-java
./start.sh          # mvn spring-boot:run in the background, :8090
./stop.sh
```

Uses `.mvn/settings.xml` (Maven Central). `~/.m2/settings.xml` mirrors `*` to Cloudera Nexus, which this machine cannot reach.

---

## search_logs

**What it does:** Find event rows already in Postgres `events`.

**Arguments:** `service` (id from `services.yaml`), `query` (substring), `window` (e.g. `30m`). Window is lookback from the newest event **for that service**, not wall clock and not the newest row in the whole table.

**Reads:** `events` where `kind IN ('log', 'auth', 'iam')`.

**Returns:** `{ timestamp, service, message }[]`.

**Does not:** read application source, Kafka, or YAML signatures. Does not score or pick a root cause.

**Example return:**
```json
[
  {
    "timestamp": "2026-09-23T18:20:00Z",
    "service": "checkout",
    "message": "HikariPool-1 - Connection is not available, request timed out after 30000ms."
  }
]
```

---

## get_metrics

**What it does:** Latest metric value for one service and name.

**Arguments:** `service` (id from `services.yaml`), `name` (e.g. `hikari.connections.active`), `window` (e.g. `30m`).

**Reads:** `events` where `kind = 'metric'`.

**Returns:** `{ service, name, value }` — `value` is `null` if nothing matched.

**Does not:** average or chart a series. One latest row only.

**Example return:**
```json
{
  "service": "checkout",
  "name": "hikari.connections.active",
  "value": "20"
}
```

---

## get_downstream

**What it does:** Who drinks this dataset, plus classification tags.

**Arguments:** `dataset` (id from `lineage.yaml`).

**Reads:** `world/lineage.yaml` `datasets`.

**Returns:** `{ dataset, downstream, tags }`. Unknown id → empty lists.

**Does not:** say the incident is an oversell or a $0 price. It only names the blast radius.

**Example return:**
```json
{
  "dataset": "payments.transactions",
  "downstream": ["checkout.orders", "fulfillment.shipments"],
  "tags": ["PCI", "PII"]
}
```

---

## lookup_iam

**What it does:** Roles for a service account.

**Arguments:** `principal` (id from `lineage.yaml`, e.g. `svc-analytics`).

**Reads:** `world/lineage.yaml` `principals`.

**Returns:** `{ principal, roles, notes }`. Unknown id → `roles: []`, `notes: "not in lineage.yaml"`.

**Does not:** decide if the principal is guilty. Skip this tool when the story is not a `svc-*` account.

**Example return:**
```json
{
  "principal": "svc-analytics",
  "roles": ["warehouse.read"],
  "notes": "Must not SELECT payments.transactions (PCI)."
}
```

---

## Worked example — `checkout_db_pool` only

Alert: checkout p99 is high.

```text
1. search_logs(service="checkout", query="HikariPool", window="30m")
   → HikariPool-1 - Connection is not available, request timed out after 30000ms.

2. get_metrics(service="checkout", name="hikari.connections.active", window="30m")
   → 20  (pool max in the scenario)

3. get_downstream(dataset="payments.transactions")
   → checkout.orders, fulfillment.shipments
   → tags: [PCI, PII]
   (checkout was stuck looking up this table; blast radius if it stays down)

4. lookup_iam(principal="svc-checkout")
   → roles: [checkout.write]
   (optional here — this outage is a pool, not a bad actor)

Conclusion (must match expected.root_cause):
  checkout database connection pool exhausted (Hikari max=20)
```

`lookup_iam` is more important for `pci_table_read` (`svc-analytics`) and `sa_rotate_failed` (`svc-payment-db`).

---

## Worked example — `inventory_lag`

Alert: inventory kafka consumer lag is high; checkout may be overselling.

```text
1. search_logs(service="inventory", query="consumer lag", window="20m")
   → kafka consumer lag 92000ms on inventory.sync.v1

2. get_metrics(service="inventory", name="kafka.consumer.lag_ms", window="20m")
   → 92000
   (inventory.sync.v1 is not draining; stock in the app is stale)

3. get_downstream(dataset="inventory.stock")
   → inventory.availability.v1, checkout.orders
   → tags: []
   (who drinks stale stock: the availability topic, then checkout orders.
    This tool does not say "oversold" — it only names the blast radius.)

4. search_logs(service="checkout", query="oversell", window="20m")
   → oversell reserved_qty exceeded stock for sku
   (proof checkout already sold more than real on-hand)

5. search_logs(service="fulfillment", query="pick failed", window="20m")
   → pick failed, on-hand 0 for sku already sold
   (warehouse cannot pick what checkout already sold)

6. lookup_iam — skip
   (this is lag + stale data, not a bad principal)

Conclusion (must match expected.root_cause):
  inventory-sync Kafka consumer lag; checkout used stale stock
```

---

## Worked example — `promo_pricing`

Alert: checkout showing $0.00 payable after a promotions config push.

```text
1. search_logs(service="promotions", query="applied config rev", window="15m")
   → applied config rev=2024-11-28.14 config_sha=badf00d

2. search_logs(service="promotions", query="discount_bps", window="15m")
   → rule catchall discount_bps=10000
   (10000 bps = 100% off everything that matches the catch-all.
    This is a log line, not a metric — get_metrics has no "discount" name.)

3. get_metrics(service="promotions", name="promotions.zero_price_rate", window="15m")
   → 0.41
   (41% of priced lines going out at $0. Service is promotions, not inventory.)

4. get_downstream(dataset="promotions.rules")
   → promotions.prices.v1, checkout.orders
   → tags: []
   (who drinks the bad rule: the prices topic, then checkout orders.
    This tool does not say "$0" — it only names the blast radius.)

5. search_logs(service="checkout", query="payable_cents=0", window="15m")
   → payable_cents=0 for sku with list_cents>0
   (proof checkout charged $0 on items that still have a list price)

6. lookup_iam — skip
   (this is a bad config push, not a bad principal)

Conclusion (must match expected.root_cause):
  promotion config push set catch-all discount_bps=10000
```

---

## Worked example — `credential_stuffing`

Alert: login failure rate is high.

```text
1. search_logs(service="login", query="login_failed", window="30m")
   → login_failed reason=invalid_password
   (YAML kind is auth, not log. Same four tools — search_logs is the
    only finder; the Java server can include auth rows or you rely on
    the metric + account_locked log below.)

2. search_logs(service="login", query="account_locked", window="30m")
   → account_locked after 8 failures
   (a few real accounts lock. This is leaked email+password pairs from
    rotating IPs — not a random-password brute force.)

3. get_metrics(service="login", name="login.fail_rate", window="30m")
   → 0.97
   (97% of /login POSTs fail. Sudden surge, not a broken config.)

4. get_downstream(dataset="identity.sessions")
   → (none)
   → tags: [PII]
   (blast stops at the sessions table. PII, not PCI — no payment data.)

5. lookup_iam — skip
   (attackers are external users on rotating IPs, not a svc-* principal.
    lookup_iam only answers "what roles does this service account have?"
    There is no svc-login in lineage.yaml. Call it on sa_rotate_failed
    and pci_table_read, where a named principal is the story.)

Conclusion (must match expected.root_cause):
  credential stuffing against login from rotating IPs
```

---

## Worked example — `sa_rotate_failed`

Alert: payment can no longer open Postgres; charges stop.

```text
1. search_logs(service="payment", query="password_expired", window="30m")
   → authentication failed principal=svc-payment-db reason=password_expired
   (YAML kind is iam. Same four tools — search_logs is the only finder.)

2. search_logs(service="payment", query="account_locked", window="30m")
   → database authentication failed user=svc-payment-db account_locked=true
   (retries after expiry locked the account. Payment DB ops fail after this.)

3. get_metrics(service="payment", name="iam.service_account_auth_failures", window="30m")
   → 1
   (auth to the payment DB is failing, not shopper /login.)

4. get_downstream(dataset="payments.transactions")
   → checkout.orders, fulfillment.shipments
   → tags: [PCI, PII]
   (who is stuck if payment cannot open this table: checkout, then ship.
    PCI is on the table; the fault is an expired password, not a PCI read.)

5. lookup_iam(principal="svc-payment-db")
   → roles: [payment.db]
   (this account is how payment opens Postgres. Lineage note: password
    must rotate; expired lock stops charges. That is the story.)

Conclusion (must match expected.root_cause):
  svc-payment-db password expired and account became locked
```

---

## Worked example — `pci_table_read`

Alert: unexpected SELECT on the payments table.

```text
1. search_logs(service="payment", query="SELECT", window="30m")
   → SELECT on payments.transactions principal=svc-analytics
   (YAML kind is iam. Named principal + PCI table — this is the smoking gun.)

2. search_logs(service="payment", query="payments.transactions", window="30m")
   → audit deny? false rows=48000 table=payments.transactions
   (48k rows left. deny=false means the query ran, not that warehouse.read
    was allowed to touch PCI — lineage says it must not.)

3. get_metrics(service="payment", name="iam.unexpected_pci_reads", window="30m")
   → 1
   (a PCI read happened. Count is the signal, not a checkout outage.)

4. get_downstream(dataset="payments.transactions")
   → checkout.orders, fulfillment.shipments
   → tags: [PCI, PII]
   (severity comes from these tags, not from the prompt. Week 5 security
    graph escalates because related_dataset.tags contains PCI.)

5. lookup_iam(principal="svc-analytics")
   → roles: [warehouse.read]
   (warehouse.read is for the warehouse, not card data. Lineage note:
    must not SELECT payments.transactions. Privilege misuse, not an outage.)

Conclusion (must match expected.root_cause):
  svc-analytics SELECT on PCI-tagged payments.transactions
```
