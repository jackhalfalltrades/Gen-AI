package io.sentinel.mcp.tool;

import java.util.List;

import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

import io.sentinel.mcp.store.EventStore;
import io.sentinel.mcp.store.EventStore.LogHit;
import io.sentinel.mcp.store.EventStore.MetricHit;
import io.sentinel.mcp.store.LineageCatalog;
import io.sentinel.mcp.store.LineageCatalog.Downstream;
import io.sentinel.mcp.store.LineageCatalog.IamRecord;

@Component
public class SentinelTools {

    private final EventStore events;
    private final LineageCatalog lineage;

    public SentinelTools(EventStore events, LineageCatalog lineage) {
        this.events = events;
        this.lineage = lineage;
    }

    @McpTool(name = "search_logs", description = "Find log/auth/iam rows in Postgres events.")
    public List<LogHit> searchLogs(
            @McpToolParam(description = "Service id from services.yaml") String service,
            @McpToolParam(description = "Substring match on message") String query,
            @McpToolParam(description = "Lookback such as 30m") String window) {
        return events.searchLogs(service, query, window);
    }

    @McpTool(name = "get_metrics", description = "Latest metric value for a service and name.")
    public MetricHit getMetrics(
            @McpToolParam(description = "Service id from services.yaml") String service,
            @McpToolParam(description = "Metric name, e.g. hikari.connections.active") String name,
            @McpToolParam(description = "Lookback such as 30m") String window) {
        return events.getMetrics(service, name, window);
    }

    @McpTool(name = "get_downstream", description = "Who drinks this dataset, plus classification tags.")
    public Downstream getDownstream(
            @McpToolParam(description = "Dataset id from lineage.yaml") String dataset) {
        return lineage.getDownstream(dataset);
    }

    @McpTool(name = "lookup_iam", description = "Roles for a service account in lineage.yaml.")
    public IamRecord lookupIam(
            @McpToolParam(description = "Principal id, e.g. svc-analytics") String principal) {
        return lineage.lookupIam(principal);
    }
}
