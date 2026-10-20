"""Create an event-centered HTML visualization of the project RDF graph."""

import argparse
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from pyvis.network import Network
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "rdf" / "Integrated_KG.ttl"
DEFAULT_ONTOLOGY = ROOT / "ontology" / "Curzon_Ontology.ttl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "event_sample.html"

MDHN = Namespace("https://github.com/MehranDHN//Persia-and-the-Persian-question_LOUD/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

EVENT_ROOT = MDHN.RevolutionaryEvent
AGENT_ROOT = MDHN.HistoricalPerson
SPATIAL_ROOT = MDHN.SpatialEntity
TEMPORAL_ROOT = MDHN.TemporalEntity
DOCUMENT_ROOT = MDHN.DocumentOrConcession
FACTION_ROOT = MDHN.PoliticalFaction

INITIATED_BY = MDHN.initiatedBy
PARTICIPATED_IN = MDHN.participatedIn
HAS_TARGET = MDHN.hasTarget
OCCURRED_AT = MDHN.occurredAt
HAS_TEMPORAL_ANCHOR = MDHN.hasTemporalAnchor
SOURCE_PAGE_REFERENCE = MDHN.sourcePageReference
GREGORIAN_DATE = MDHN.gregorianDate

RELATIONS = (
    (INITIATED_BY, "initiated by", "agent", "outgoing"),
    (PARTICIPATED_IN, "participated in", "agent", "incoming"),
    (HAS_TARGET, "targets", "agent", "outgoing"),
    (OCCURRED_AT, "occurred at", "spatial", "outgoing"),
    (HAS_TEMPORAL_ANCHOR, "time anchor", "temporal", "outgoing"),
)

TYPE_COLORS = {
    "HistoricalPerson": "#477eb5",
    "Monarch": "#e1a43b",
    "Cleric": "#8665ad",
    "MilitaryLeader": "#d66a52",
    "IntellectualOrator": "#c47736",
    "FinancialAdministrator": "#63798a",
    "ReligiousLeader": "#bd668a",
    "PoliticalFaction": "#876db4",
    "RevolutionaryEvent": "#d5664f",
    "Protest": "#ed9063",
    "ConflictEvent": "#a94343",
    "DiplomaticCrisis": "#bd762d",
    "PoliticalTransition": "#a95672",
    "SpatialEntity": "#3c9b88",
    "City": "#247c73",
    "MonumentOrBuilding": "#64a685",
    "TemporalEntity": "#4e91c6",
    "DocumentOrConcession": "#64748b",
    "PrimarySourceBook": "#85919b",
}
FALLBACK_TYPE_COLOR = "#9aa5b1"
SHAPES = {
    "event": "diamond",
    "agent": "dot",
    "spatial": "triangle",
    "temporal": "box",
    "document": "database",
    "faction": "hexagon",
    "other": "ellipse",
}
CATEGORY_LABELS = {
    "event": "Events",
    "agent": "Agents",
    "spatial": "Places",
    "temporal": "Time anchors",
    "document": "Documents",
    "faction": "Factions",
    "other": "Other",
}


def parse_graph(data_path: Path, ontology_path: Path) -> Tuple[Graph, Graph]:
    data = Graph()
    data.parse(str(data_path), format="turtle")
    ontology = Graph()
    ontology.parse(str(ontology_path), format="turtle")

    combined = Graph()
    for triple in ontology:
        combined.add(triple)
    for triple in data:
        combined.add(triple)
    return data, combined


def descendants(graph: Graph, root: URIRef) -> Set[URIRef]:
    found = {root}
    pending = [root]
    while pending:
        parent = pending.pop()
        for child in graph.subjects(RDFS.subClassOf, parent):
            if isinstance(child, URIRef) and child not in found:
                found.add(child)
                pending.append(child)
    return found


def literal_value(graph: Graph, subject: URIRef, predicate: URIRef) -> str:
    values = [str(value).strip() for value in graph.objects(subject, predicate) if isinstance(value, Literal)]
    return next((value for value in values if value), "")


def resource_name(resource: URIRef) -> str:
    text = str(resource).rstrip("/#")
    return text.rsplit("#", 1)[-1].rsplit("/", 1)[-1] or text


def preferred_label(graph: Graph, resource: URIRef) -> str:
    labels = [value for value in graph.objects(resource, RDFS.label) if isinstance(value, Literal)]
    if not labels:
        labels = [value for value in graph.objects(resource, SKOS.prefLabel) if isinstance(value, Literal)]
    if labels:
        labels.sort(key=lambda value: (0 if value.language == "en" else 1, str(value).casefold()))
        return str(labels[0]).strip()
    return resource_name(resource)


def direct_type_labels(graph: Graph, data: Graph, resource: URIRef) -> List[str]:
    labels = []
    for rdf_type in data.objects(resource, RDF.type):
        if isinstance(rdf_type, URIRef):
            labels.append(preferred_label(graph, rdf_type))
    return sorted(set(labels), key=str.casefold)


def primary_type(data: Graph, resource: URIRef) -> Optional[URIRef]:
    types = [value for value in data.objects(resource, RDF.type) if isinstance(value, URIRef)]
    return sorted(types, key=resource_name)[0] if types else None


def association_nodes(data: Graph, event: URIRef) -> Dict[str, Set[URIRef]]:
    agents = set(data.objects(event, INITIATED_BY)) | set(data.objects(event, HAS_TARGET))
    agents.update(data.subjects(PARTICIPATED_IN, event))
    return {
        "agent": {node for node in agents if isinstance(node, URIRef)},
        "spatial": {node for node in data.objects(event, OCCURRED_AT) if isinstance(node, URIRef)},
        "temporal": {
            node for node in data.objects(event, HAS_TEMPORAL_ANCHOR) if isinstance(node, URIRef)
        },
    }


def event_completeness(data: Graph, event: URIRef) -> Dict[str, bool]:
    associations = association_nodes(data, event)
    return {
        "agent": bool(associations["agent"]),
        "spatial": bool(associations["spatial"]),
        "temporal": bool(associations["temporal"]),
        "page": any(isinstance(value, Literal) and str(value).strip() for value in data.objects(event, SOURCE_PAGE_REFERENCE)),
    }


def category_for(
    resource: URIRef,
    data: Graph,
    event_types: Set[URIRef],
    agent_types: Set[URIRef],
    spatial_types: Set[URIRef],
    temporal_types: Set[URIRef],
    document_types: Set[URIRef],
    faction_types: Set[URIRef],
    agent_nodes: Set[URIRef],
    spatial_nodes: Set[URIRef],
    temporal_nodes: Set[URIRef],
) -> str:
    types = {value for value in data.objects(resource, RDF.type) if isinstance(value, URIRef)}
    if types & event_types:
        return "event"
    if types & agent_types or resource in agent_nodes:
        return "agent"
    if types & spatial_types or resource in spatial_nodes:
        return "spatial"
    if types & temporal_types or resource in temporal_nodes:
        return "temporal"
    if types & document_types:
        return "document"
    if types & faction_types:
        return "faction"
    return "other"


def tooltip(
    graph: Graph,
    data: Graph,
    resource: URIRef,
    category: str,
    event_types: Set[URIRef],
) -> str:
    details = [preferred_label(graph, resource)]
    types = direct_type_labels(graph, data, resource)
    if types:
        details.append("Type: {}".format(", ".join(types)))
    if category == "event":
        completeness = event_completeness(data, resource)
        associations = association_nodes(data, resource)
        details.append(
            "Links: {} agent(s), {} place(s), {} time anchor(s)".format(
                len(associations["agent"]), len(associations["spatial"]), len(associations["temporal"])
            )
        )
        missing = [name for name, present in completeness.items() if not present]
        details.append("Missing: {}".format(", ".join(missing) if missing else "none"))
        page_reference = literal_value(data, resource, SOURCE_PAGE_REFERENCE)
        if page_reference:
            details.append("Source reference: {}".format(page_reference))
    comment = literal_value(graph, resource, RDFS.comment)
    if comment:
        details.append(comment)
    date = literal_value(graph, resource, GREGORIAN_DATE)
    if date:
        details.append("Date: {}".format(date))
    aliases = sorted(
        {str(value).strip() for value in graph.objects(resource, SKOS.altLabel) if isinstance(value, Literal)}
    )
    if aliases:
        details.append("Also known as: {}".format(", ".join(aliases)))
    details.append("URI: {}".format(str(resource)))
    return "\n".join(details)


def shorten(text: str, limit: int = 42) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def build_event_view(
    data: Graph, graph: Graph, max_events: int
) -> Tuple[Network, Dict[str, int], Dict[str, int], Dict[str, str], Dict[str, int], int]:
    event_types = descendants(graph, EVENT_ROOT)
    agent_types = descendants(graph, AGENT_ROOT)
    spatial_types = descendants(graph, SPATIAL_ROOT)
    temporal_types = descendants(graph, TEMPORAL_ROOT)
    document_types = descendants(graph, DOCUMENT_ROOT)
    faction_types = descendants(graph, FACTION_ROOT)

    events = {
        subject
        for subject, rdf_type in data.subject_objects(RDF.type)
        if isinstance(subject, URIRef) and rdf_type in event_types
    }
    if not events:
        raise ValueError("No event instances typed with the ontology's event classes were found.")

    ranked_events = sorted(
        events,
        key=lambda event: (
            -sum(len(nodes) for nodes in association_nodes(data, event).values()),
            preferred_label(graph, event).casefold(),
        ),
    )
    selected_events = ranked_events if max_events == 0 else ranked_events[:max_events]
    selected_set = set(selected_events)

    links = []
    nodes: Set[URIRef] = set(selected_set)
    agent_nodes: Set[URIRef] = set()
    spatial_nodes: Set[URIRef] = set()
    temporal_nodes: Set[URIRef] = set()
    for event in selected_events:
        associations = association_nodes(data, event)
        agent_nodes.update(associations["agent"])
        spatial_nodes.update(associations["spatial"])
        temporal_nodes.update(associations["temporal"])
        nodes.update(associations["agent"])
        nodes.update(associations["spatial"])
        nodes.update(associations["temporal"])
        for predicate, label, relation_category, direction in RELATIONS:
            if direction == "incoming":
                endpoints = ((subject, event) for subject in data.subjects(predicate, event))
            else:
                endpoints = ((event, obj) for obj in data.objects(event, predicate))
            for source, target in endpoints:
                if isinstance(source, URIRef) and isinstance(target, URIRef):
                    links.append((source, target, label, relation_category))

    net = Network(
        height="850px",
        width="100%",
        directed=True,
        bgcolor="#f6f8f7",
        font_color="#1f2933",
        notebook=False,
        cdn_resources="in_line",
    )
    net.show_buttons(filter_=["physics"])
    net.set_options(
        """
        {
          "nodes": {
            "borderWidth": 2,
            "font": {"face": "Arial", "size": 16, "color": "#1f2933"},
            "shadow": {"enabled": true, "size": 5, "x": 1, "y": 2}
          },
          "edges": {
            "arrows": {"to": {"enabled": true, "scaleFactor": 0.7}},
            "font": {"face": "Arial", "size": 12, "background": "#ffffff", "strokeWidth": 0},
            "smooth": {"type": "dynamic"}
          },
          "configure": {"enabled": false},
          "interaction": {"hover": true, "navigationButtons": true, "tooltipDelay": 100},
          "physics": {
            "enabled": true,
            "barnesHut": {"gravitationalConstant": -15000, "centralGravity": 0.25, "springLength": 190, "springConstant": 0.035, "damping": 0.12},
            "minVelocity": 0.75,
            "solver": "barnesHut"
          }
        }
        """
    )

    category_counts: Counter = Counter()
    type_counts: Counter = Counter()
    type_colors: Dict[str, str] = {}
    for node in sorted(nodes, key=lambda item: preferred_label(graph, item).casefold()):
        category = category_for(
            node,
            data,
            event_types,
            agent_types,
            spatial_types,
            temporal_types,
            document_types,
            faction_types,
            agent_nodes,
            spatial_nodes,
            temporal_nodes,
        )
        category_counts[category] += 1
        label = preferred_label(graph, node)
        rdf_type = primary_type(data, node)
        type_label = preferred_label(graph, rdf_type) if rdf_type else CATEGORY_LABELS[category]
        color = TYPE_COLORS.get(resource_name(rdf_type), FALLBACK_TYPE_COLOR) if rdf_type else FALLBACK_TYPE_COLOR
        type_counts[type_label] += 1
        type_colors[type_label] = color
        size = 34 if category == "event" else 24
        net.add_node(
            str(node),
            label=shorten(label),
            title=tooltip(graph, data, node, category, event_types),
            group=category,
            color={"background": color, "border": "#ffffff", "highlight": {"background": color, "border": "#17212b"}},
            shape=SHAPES[category],
            size=size,
            font={"face": "Arial", "size": 16 if category == "event" else 14, "color": "#1f2933"},
        )

    edge_colors = {"agent": "#c17b38", "spatial": "#338b7d", "temporal": "#477faf"}
    seen_links = set()
    for source, target, label, relation_category in links:
        edge_key = (source, target, label)
        if edge_key in seen_links or str(source) not in {str(node) for node in nodes} or str(target) not in {str(node) for node in nodes}:
            continue
        seen_links.add(edge_key)
        net.add_edge(
            str(source),
            str(target),
            label=label,
            title=label,
            color={"color": edge_colors[relation_category], "highlight": "#1f2933"},
            width=2.2 if relation_category != "agent" else 1.8,
            arrows="to",
        )

    coverage = Counter()
    for event in selected_events:
        coverage.update(event_completeness(data, event))
    return net, dict(category_counts), dict(type_counts), type_colors, dict(coverage), len(events)


def legend_panel(
    type_counts: Dict[str, int],
    type_colors: Dict[str, str],
    coverage: Dict[str, int],
    selected_count: int,
    total_events: int,
) -> str:
    legend_items = []
    for label in sorted(type_counts, key=str.casefold):
        legend_items.append(
            '<span class="legend-item"><i style="background:{}"></i>{} ({})</span>'.format(
                type_colors[label], escape(label), type_counts[label]
            )
        )
    coverage_text = "Event links present: agents {}/{}, places {}/{}, time anchors {}/{}; page references {}/{}".format(
        coverage.get("agent", 0),
        selected_count,
        coverage.get("spatial", 0),
        selected_count,
        coverage.get("temporal", 0),
        selected_count,
        coverage.get("page", 0),
        selected_count,
    )
    return """
    <header id="kg-header">
      <div class="kg-title">Curzon Knowledge Graph <span>Event association sample</span></div>
      <div class="kg-legend">{legend}</div>
      <div class="kg-coverage">Showing {selected} of {total} events, ranked by linked agent, place, and time nodes. {coverage}</div>
    </header>
    """.format(
        legend="".join(legend_items),
        selected=selected_count,
        total=total_events,
        coverage=escape(coverage_text),
    )


def add_header(html_text: str, panel: str) -> str:
    styles = """
    <style>
      html, body { margin: 0; padding: 0; font-family: Arial, sans-serif; background: #f6f8f7; }
      #kg-header { box-sizing: border-box; min-height: 112px; padding: 12px 18px; color: #1f2933; background: #ffffff; border-bottom: 1px solid #d6dedb; }
      .kg-title { font-size: 19px; font-weight: 700; }
      .kg-title span { margin-left: 10px; color: #65736e; font-size: 14px; font-weight: 400; }
      .kg-legend { display: flex; flex-wrap: wrap; gap: 7px 16px; margin-top: 9px; }
      .legend-item { display: inline-flex; align-items: center; gap: 6px; color: #40504a; font-size: 12px; }
      .legend-item i { display: inline-block; width: 11px; height: 11px; border-radius: 50%; }
      .kg-coverage { margin-top: 8px; color: #52615c; font-size: 12px; }
      #mynetwork { height: calc(100vh - 112px) !important; min-height: 520px; }
      @media (max-width: 700px) {
        #kg-header { min-height: 150px; padding: 10px 12px; }
        .kg-title { font-size: 17px; }
        .kg-title span { display: block; margin: 3px 0 0; }
        #mynetwork { height: calc(100vh - 150px) !important; min-height: 450px; }
      }
    </style>
    """
    if "</head>" in html_text:
        html_text = html_text.replace("</head>", styles + "</head>", 1)
    if "<body>" in html_text:
        return html_text.replace("<body>", "<body>" + panel, 1)
    if "</body>" in html_text:
        return html_text.replace("</body>", panel + "</body>", 1)
    return html_text + panel


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an event-centered sample of the Curzon RDF knowledge graph.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="RDF Turtle data file")
    parser.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY, help="Ontology Turtle file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML file")
    parser.add_argument(
        "--max-events",
        type=int,
        default=12,
        help="Maximum number of connected events to display; use 0 to include all events",
    )
    args = parser.parse_args()
    if args.max_events < 0:
        parser.error("--max-events must be zero or a positive integer")
    if not args.data.is_file():
        parser.error("RDF data file not found: {}".format(args.data))
    if not args.ontology.is_file():
        parser.error("Ontology file not found: {}".format(args.ontology))

    try:
        data, combined = parse_graph(args.data, args.ontology)
        network, category_counts, type_counts, type_colors, coverage, total_events = build_event_view(
            data, combined, args.max_events
        )
    except Exception as error:
        parser.exit(2, "Could not build event visualization: {}\n".format(error))

    selected_count = category_counts.get("event", 0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    network.write_html(str(args.output), notebook=False, open_browser=False)
    html_text = args.output.read_text(encoding="utf-8")
    html_text = add_header(
        html_text,
        legend_panel(type_counts, type_colors, coverage, selected_count, total_events),
    )
    args.output.write_text(html_text, encoding="utf-8")

    print("Wrote {}".format(args.output.resolve()))
    print("Events displayed: {} / {}".format(selected_count, total_events))
    print("Nodes by category: {}".format(", ".join("{}={}".format(key, value) for key, value in sorted(category_counts.items()))))
    print("Events with agent/place/time/page links: {}/{}/{}/{} of {}".format(
        coverage.get("agent", 0),
        coverage.get("spatial", 0),
        coverage.get("temporal", 0),
        coverage.get("page", 0),
        selected_count,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
