package io.sentinel.mcp.http;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.sentinel.mcp.store.EventStore.LogHit;
import io.sentinel.mcp.store.EventStore.MetricHit;
import io.sentinel.mcp.store.LineageCatalog.Downstream;
import io.sentinel.mcp.store.LineageCatalog.IamRecord;
import io.sentinel.mcp.tool.SentinelTools;

@RestController
@RequestMapping("/tools")
public class ToolController {

    private final SentinelTools tools;

    public ToolController(SentinelTools tools) {
        this.tools = tools;
    }

    @GetMapping("/search_logs")
    public List<LogHit> searchLogs(
            @RequestParam String service,
            @RequestParam String query,
            @RequestParam(defaultValue = "30m") String window) {
        return tools.searchLogs(service, query, window);
    }

    @GetMapping("/get_metrics")
    public MetricHit getMetrics(
            @RequestParam String service,
            @RequestParam String name,
            @RequestParam(defaultValue = "30m") String window) {
        return tools.getMetrics(service, name, window);
    }

    @GetMapping("/get_downstream")
    public Downstream getDownstream(@RequestParam String dataset) {
        return tools.getDownstream(dataset);
    }

    @GetMapping("/lookup_iam")
    public IamRecord lookupIam(@RequestParam String principal) {
        return tools.lookupIam(principal);
    }
}
