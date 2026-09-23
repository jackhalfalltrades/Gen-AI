package io.sentinel.mcp.store;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.Yaml;

@Component
public class LineageCatalog {

    private final List<Map<String, Object>> datasets;
    private final List<Map<String, Object>> principals;

    @SuppressWarnings("unchecked")
    public LineageCatalog(@Value("${sentinel.lineage-path}") String lineagePath) throws IOException {
        Path path = Path.of(lineagePath).toAbsolutePath().normalize();
        if (!Files.exists(path)) {
            throw new IllegalStateException("lineage.yaml not found at " + path);
        }
        try (InputStream in = Files.newInputStream(path)) {
            Map<String, Object> root = new Yaml().load(in);
            this.datasets = (List<Map<String, Object>>) root.getOrDefault("datasets", List.of());
            this.principals = (List<Map<String, Object>>) root.getOrDefault("principals", List.of());
        }
    }

    public Downstream getDownstream(String dataset) {
        Map<String, Object> row = datasets.stream()
                .filter(d -> dataset.equals(d.get("id")))
                .findFirst()
                .orElse(null);
        if (row == null) {
            return new Downstream(dataset, List.of(), List.of());
        }
        return new Downstream(
                dataset,
                asStringList(row.get("downstream")),
                asStringList(row.get("tags")));
    }

    public IamRecord lookupIam(String principal) {
        Map<String, Object> row = principals.stream()
                .filter(p -> principal.equals(p.get("id")))
                .findFirst()
                .orElse(null);
        if (row == null) {
            return new IamRecord(principal, List.of(), "not in lineage.yaml");
        }
        Object notes = row.get("notes");
        return new IamRecord(
                principal,
                asStringList(row.get("roles")),
                notes == null ? "" : notes.toString());
    }

    @SuppressWarnings("unchecked")
    private static List<String> asStringList(Object value) {
        if (value instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        return List.of();
    }

    public record Downstream(String dataset, List<String> downstream, List<String> tags) {}

    public record IamRecord(String principal, List<String> roles, String notes) {}
}
