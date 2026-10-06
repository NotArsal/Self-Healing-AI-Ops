from kavach.scenarios.schema import ServiceDef


class TopologyGraph:
    def __init__(self, services: dict[str, ServiceDef]):
        self.services = services
        # Map of service -> list of services it depends on
        self.edges = {name: (srv.depends_on or []) for name, srv in services.items()}

        # Map of service -> list of services that depend on IT
        self.reverse_edges = {name: [] for name in services}
        for src, dests in self.edges.items():
            for dest in dests:
                if dest in self.reverse_edges:
                    self.reverse_edges[dest].append(src)

    def get_dependencies(self, service_name: str) -> list[str]:
        """Return a list of services that this service depends on."""
        return self.edges.get(service_name, [])

    def get_dependents(self, service_name: str) -> list[str]:
        """Return a list of services that depend on this service."""
        return self.reverse_edges.get(service_name, [])

    def describe_topology(self) -> str:
        """Returns a textual description of the topology for the LLM."""
        lines = []
        for srv, deps in self.edges.items():
            if deps:
                lines.append(f"- {srv} depends on: {', '.join(deps)}")
            else:
                lines.append(f"- {srv} has no upstream dependencies")
        return "\n".join(lines)


def build_topology_graph(services: dict[str, ServiceDef]) -> TopologyGraph:
    return TopologyGraph(services)
