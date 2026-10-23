"""Add exact-label page occurrence references from the review CSV to the RDF graph."""

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Set, Tuple

from rdflib import Graph, Literal, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, SKOS, XSD


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "rdf" / "Integrated_KG.ttl"
CSV_PATH = ROOT / "analysis" / "reports" / "volume1_entity_review.csv"
MDHN = "https://github.com/MehranDHN//Persia-and-the-Persian-question_LOUD/"
MDHN_DATA = "https://github.com/MehranDHN/Persia-and-the-Persian-question_LOUD/data/"
PREDICATE_ORDER = (
    RDF.type,
    RDFS.label,
    SKOS.altLabel,
    SKOS.prefLabel,
    RDFS.comment,
    OWL.sameAs,
    DCTERMS.creator,
    DCTERMS.issued,
    DCTERMS.description,
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def read_exact_rows() -> Dict[str, Set[int]]:
    pages: DefaultDict[str, Set[int]] = defaultdict(set)
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("status") != "exact_existing":
                continue
            candidate = normalize(row.get("candidate", ""))
            try:
                page = int(row.get("page", ""))
            except ValueError:
                continue
            if candidate:
                pages[candidate].add(page)
    return dict(pages)


def build_alias_index(graph: Graph) -> Dict[str, Set[URIRef]]:
    aliases: DefaultDict[str, Set[URIRef]] = defaultdict(set)
    subjects = {subject for subject in graph.subjects(RDF.type, None) if isinstance(subject, URIRef)}
    for subject in subjects:
        for predicate in (RDFS.label, SKOS.altLabel):
            for value in graph.objects(subject, predicate):
                if isinstance(value, Literal):
                    alias = normalize(str(value))
                    if alias:
                        aliases[alias].add(subject)
    return dict(aliases)


def add_page_references(graph: Graph, page_matches: Dict[str, Set[int]]) -> Tuple[int, int]:
    aliases = build_alias_index(graph)
    page_property = URIRef(MDHN + "sourcePageReference")
    matched_labels = 0
    matched_resources: Set[URIRef] = set()
    for label, pages in sorted(page_matches.items()):
        subjects = aliases.get(label, set())
        if not subjects:
            continue
        matched_labels += 1
        reference = Literal(
            "Vol. 1 printed pages {}; exact label occurrence in the page-marked Frank Cass "
            "1966 transcription; lexical evidence only, verify the claim against the 1892 scan.".format(
                ", ".join(str(page) for page in sorted(pages))
            )
        )
        for subject in subjects:
            matched_resources.add(subject)
            graph.add((subject, page_property, reference))
    return matched_labels, len(matched_resources)


def _bind_prefixes(graph: Graph) -> None:
    graph.bind("dcterms", DCTERMS, override=True)
    graph.bind("lcnaf", "http://id.loc.gov/authorities/names/", override=True)
    graph.bind("mdhn", MDHN, override=True)
    graph.bind("mdhn_data", MDHN_DATA, override=True)
    graph.bind("owl", OWL, override=True)
    graph.bind("rdfs", RDFS, override=True)
    graph.bind("skos", SKOS, override=True)
    graph.bind("wd", "http://www.wikidata.org/entity/", override=True)
    graph.bind("xsd", XSD, override=True)


def _subject_key(subject: URIRef) -> Tuple[int, str]:
    text = str(subject)
    if text.startswith(MDHN) and not text.startswith(MDHN_DATA):
        group = 0
    elif text.startswith(MDHN_DATA):
        group = 1
    else:
        group = 2
    return group, text.casefold()


def _predicate_key(predicate: URIRef) -> Tuple[int, str]:
    if str(predicate).endswith("sourcePageReference"):
        return len(PREDICATE_ORDER) + 1, str(predicate).casefold()
    try:
        rank = PREDICATE_ORDER.index(predicate)
    except ValueError:
        rank = len(PREDICATE_ORDER)
    return rank, str(predicate).casefold()


def _object_lines(graph: Graph, objects: List[object]) -> List[str]:
    return [value.n3(graph.namespace_manager) for value in objects]


def write_one_statement_per_subject(graph: Graph, path: Path) -> None:
    """Write each subject as one Turtle statement containing all of its triples."""
    _bind_prefixes(graph)
    grouped: DefaultDict[URIRef, DefaultDict[URIRef, List[object]]] = defaultdict(lambda: defaultdict(list))
    for subject, predicate, obj in graph:
        if not isinstance(subject, URIRef) or not isinstance(predicate, URIRef):
            raise ValueError("Refusing to rewrite a triple whose subject or predicate is not a URI.")
        values = grouped[subject][predicate]
        if obj not in values:
            values.append(obj)

    lines = [
        "@prefix dcterms: <http://purl.org/dc/terms/> .",
        "@prefix lcnaf: <http://id.loc.gov/authorities/names/> .",
        "@prefix mdhn: <{}> .".format(MDHN),
        "@prefix mdhn_data: <{}> .".format(MDHN_DATA),
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix wd: <http://www.wikidata.org/entity/> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]
    for subject in sorted(grouped, key=_subject_key):
        predicates = grouped[subject]
        predicate_list = sorted(predicates, key=_predicate_key)
        lines.append(subject.n3(graph.namespace_manager))
        for index, predicate in enumerate(predicate_list):
            objects = sorted(predicates[predicate], key=lambda value: value.n3(graph.namespace_manager))
            closing = " ." if index == len(predicate_list) - 1 else " ;"
            object_lines = _object_lines(graph, objects)
            predicate_text = "a" if predicate == RDF.type else predicate.n3(graph.namespace_manager)
            if len(object_lines) == 1:
                lines.append("    {} {}{}".format(predicate_text, object_lines[0], closing))
            else:
                lines.append("    {} {},".format(predicate_text, object_lines[0]))
                for object_line in object_lines[1:-1]:
                    lines.append("        {},".format(object_line))
                lines.append("        {}{}".format(object_lines[-1], closing))
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    graph = Graph()
    graph.parse(str(DATA_PATH), format="turtle")
    before = set(graph)
    page_matches = read_exact_rows()
    matched_labels, matched_resources = add_page_references(graph, page_matches)
    write_one_statement_per_subject(graph, DATA_PATH)

    check = Graph()
    check.parse(str(DATA_PATH), format="turtle")
    if set(check) != set(graph):
        raise SystemExit("Rewrite changed the RDF triples.")
    print("Exact CSV labels with ontology-backed RDF matches: {}".format(matched_labels))
    print("Existing resources receiving page references: {}".format(matched_resources))
    print("Subjects written as one statement each: {}".format(len({subject for subject, _, _ in check})))
    print("Validated RDF triples after update: {}".format(len(check)))
    print("Triples present before page references were added: {}".format(len(before)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
