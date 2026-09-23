package io.sentinel.mcp.store;

import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {

    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Window is relative to the newest row for that service, not wall clock
     * and not the newest row in the whole table. Six scenarios share one
     * events table; a global MAX(timestamp) hid older promotions/inventory
     * signatures inside a 15m/20m window.
     */
    public List<LogHit> searchLogs(String service, String query, String window) {
        Instant cutoff = cutoff(window, service);
        return jdbc.query(
                """
                SELECT timestamp, service, message
                FROM events
                WHERE service = ?
                  AND kind IN ('log', 'auth', 'iam')
                  AND message ILIKE ?
                  AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 50
                """,
                (rs, rowNum) -> new LogHit(
                        rs.getTimestamp("timestamp").toInstant(),
                        rs.getString("service"),
                        rs.getString("message")),
                service,
                "%" + query + "%",
                Timestamp.from(cutoff));
    }

    public MetricHit getMetrics(String service, String name, String window) {
        Instant cutoff = cutoff(window, service);
        List<MetricHit> rows = jdbc.query(
                """
                SELECT service,
                       COALESCE(attrs->>'metric', split_part(message, '=', 1)) AS name,
                       COALESCE(attrs->>'metric_value', split_part(message, '=', 2)) AS value
                FROM events
                WHERE service = ?
                  AND kind = 'metric'
                  AND timestamp >= ?
                  AND (
                        attrs->>'metric' = ?
                     OR message ILIKE ?
                  )
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (rs, rowNum) -> new MetricHit(
                        rs.getString("service"),
                        rs.getString("name"),
                        rs.getString("value")),
                service,
                Timestamp.from(cutoff),
                name,
                name + "%");
        return rows.isEmpty() ? new MetricHit(service, name, null) : rows.get(0);
    }

    private Instant cutoff(String window, String service) {
        Duration lookback = parseWindow(window);
        Instant latest = latestTimestamp(service);
        return latest.minus(lookback);
    }

    private Instant latestTimestamp(String service) {
        Instant forService = jdbc.query(
                "SELECT MAX(timestamp) AS ts FROM events WHERE service = ?",
                rs -> rs.next() && rs.getTimestamp("ts") != null
                        ? rs.getTimestamp("ts").toInstant()
                        : null,
                service);
        if (forService != null) {
            return forService;
        }
        Instant any = jdbc.query(
                "SELECT MAX(timestamp) AS ts FROM events",
                rs -> rs.next() && rs.getTimestamp("ts") != null
                        ? rs.getTimestamp("ts").toInstant()
                        : null);
        return any != null ? any : Instant.now();
    }

    static Duration parseWindow(String window) {
        if (window == null || window.isBlank()) {
            return Duration.ofMinutes(30);
        }
        String raw = window.trim();
        char unit = Character.toLowerCase(raw.charAt(raw.length() - 1));
        long n = Long.parseLong(raw.substring(0, raw.length() - 1));
        return switch (unit) {
            case 'h' -> Duration.ofHours(n);
            case 's' -> Duration.ofSeconds(n);
            default -> Duration.ofMinutes(n);
        };
    }

    public record LogHit(Instant timestamp, String service, String message) {}

    public record MetricHit(String service, String name, String value) {}
}
