# Graph and risk query contracts

## Graph materializer

The graph service consumes `raw.shipping`, `raw.weather`, `raw.supplier_erp`,
`raw.iot`, and `raw.geopolitical` with consumer group `graph-service`.
Messages are acknowledged only after all node and relationship `MERGE` writes
complete. Invalid messages are retried up to `GRAPH_MAX_RETRIES` and then
published to `raw.dlq` before their offset is committed.

The stable identity keys are `Company.company_id`, `Shipment.shipment_id`, and
`Route.route_id`. Startup creates uniqueness constraints for these keys, so
replaying an event updates a node rather than creating a duplicate.

## Query API

The Risk Engine exposes:

| Endpoint | Required input | Response |
| --- | --- | --- |
| `GET /dependencies?company_id=supplier-1&max_hops=5` | Company ID; `max_hops` 1-5 | `{root_company_id, nodes[]}` with each node's tier |
| `GET /blast-radius?company_id=supplier-1` | Failed company ID | `{company_id, affected_count, affected_company_ids[]}` |
| `GET /alternatives?company_id=supplier-1` | Company ID | `{company_id, alternatives[]}` |

The Cypher traversal is fixed to `[:SUPPLIES*1..5]`; the wrapper and HTTP
validation reject values outside 1-5. Every query has a parameterized result
limit and a five-second timeout by default. API and Risk Engine code should
call `GraphQueryService` rather than duplicating Cypher.

Relationships maintained by the materializer:

* `(:Company)-[:SUPPLIES]->(:Company)`
* `(:Shipment)-[:SHIPS_VIA]->(:Route)`
* `(:Company)-[:ALTERNATIVE_FOR]->(:Company)`
