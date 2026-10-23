"""Extract page-cited entity candidates and compare them with the current RDF graph."""

import argparse
import csv
import difflib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef

try:
    from analysis.entity_extraction.cues import context_method
except ImportError:
    from entity_extraction.cues import context_method


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEXT = ROOT / "plain_text_books" / "plain_curzon_vol1.txt"
DEFAULT_DATA = ROOT / "rdf" / "Integrated_KG.ttl"
DEFAULT_ONTOLOGY = ROOT / "ontology" / "Curzon_Ontology.ttl"
DEFAULT_OUTPUT_DIR = ROOT / "analysis" / "reports"

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
PAGE_MARKER = re.compile(r"^\s*-\s*\[Page\s+(\d+)\]\s*$", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'\[])")
CAPITALIZED_WORD = r"(?:[A-ZÀ-ÖØ-Þ]\.|[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ’'-]*)"
NAME_PARTICLE = r"(?:and|of|the|de|del|di|al|el|ibn|bin|van|von|la|le|du)"
NAME_SEQUENCE = re.compile(
    r"\b" + CAPITALIZED_WORD + r"(?:\s+(?:" + CAPITALIZED_WORD + r"|" + NAME_PARTICLE + r")){1,5}\b"
)
HONORIFIC = re.compile(
    r"^(?:sir|mr|mrs|miss|dr|professor|prof|colonel|col|major|general|gen|captain|capt|lieutenant|lieut|baron|lord|sheikh|mirza|haji|madame|prince|princess)\b",
    re.IGNORECASE,
)
SENTENCE_OPENERS = {
    "a", "about", "above", "accordingly", "actually", "after", "afterwards", "all", "also",
    "although", "among", "and", "another", "any", "as", "at", "before", "both", "but", "by",
    "certainly", "consequently", "during", "finally", "for", "from", "he", "here", "however",
    "if", "in", "indeed", "it", "its", "let", "meanwhile", "moreover", "my", "nevertheless",
    "nor", "not", "now", "of", "on", "only", "or", "otherwise", "perhaps", "since", "she",
    "should", "so", "still", "the", "then", "there", "these", "they", "this", "those", "though",
    "thus", "to", "today", "unlike", "we", "when", "where", "which", "while", "who", "yet",
}
COMMON_SINGLE_CAPS = SENTENCE_OPENERS | {
    "chapter", "contents", "page", "persia", "persian", "british", "english", "russian",
    "india", "east", "west", "north", "south", "shah", "government", "volume",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def read_pages(path: Path) -> Dict[int, str]:
    pages: Dict[int, List[str]] = {}
    current_page: Optional[int] = None
    with path.open("r", encoding="utf-8-sig") as source:
        for line in source:
            match = PAGE_MARKER.match(line)
            if match:
                current_page = int(match.group(1))
                pages.setdefault(current_page, [])
            elif current_page is not None:
                pages[current_page].append(line.rstrip())
    return {number: "\n".join(lines).strip() for number, lines in pages.items()}


def load_graph(data_path: Path, ontology_path: Path) -> Tuple[Graph, Graph]:
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


def existing_aliases(data: Graph, labels_graph: Graph) -> Dict[str, Set[Tuple[str, str]]]:
    aliases: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    for subject in set(data.subjects(RDF.type, None)):
        if not isinstance(subject, URIRef):
            continue
        types = sorted(
            {
                str(labels_graph.value(rdf_type, RDFS.label) or rdf_type).strip()
                for rdf_type in data.objects(subject, RDF.type)
                if isinstance(rdf_type, URIRef)
            }
        )
        type_label = "; ".join(types)
        for predicate in (RDFS.label, SKOS.altLabel):
            for value in data.objects(subject, predicate):
                if isinstance(value, Literal):
                    label = str(value).strip()
                    normalized = normalize(label)
                    if normalized:
                        aliases[normalized].add((label, type_label))
    return aliases


def page_snippet(text: str, phrase: str) -> str:
    flattened = " ".join(text.split())
    match = re.search(re.escape(phrase), flattened, re.IGNORECASE)
    if not match:
        return flattened[:400]
    start = max(0, match.start() - 150)
    end = min(len(flattened), match.end() + 250)
    prefix = "..." if start else ""
    suffix = "..." if end < len(flattened) else ""
    return prefix + flattened[start:end] + suffix


def add_mention(
    mentions: Dict[Tuple[str, str], Dict[int, Dict[str, object]]],
    page_number: int,
    page_text: str,
    phrase: str,
    detection_method: str,
) -> None:
    normalized = normalize(phrase)
    if len(normalized) < 3:
        return
    key = (normalized, detection_method)
    page_record = mentions[key].setdefault(
        page_number,
        {"phrase": phrase, "count": 0, "snippet": page_snippet(page_text, phrase)},
    )
    page_record["count"] = int(page_record["count"]) + 1


def extract_mentions(
    pages: Dict[int, str], known_aliases: Set[str]
) -> Dict[Tuple[str, str], Dict[int, Dict[str, object]]]:
    mentions: Dict[Tuple[str, str], Dict[int, Dict[str, object]]] = defaultdict(dict)
    for page_number, page_text in pages.items():
        for paragraph in re.split(r"\n\s*\n", page_text):
            paragraph = " ".join(paragraph.split())
            if len(paragraph) < 25:
                continue
            for sentence in SENTENCE_SPLIT.split(paragraph):
                sentence = sentence.strip()
                sentence_start = normalize(sentence.split(" ", 1)[0])
                for match in NAME_SEQUENCE.finditer(sentence):
                    phrase = match.group(0).strip(" .,:;–—-")
                    normalized = normalize(phrase)
                    first_word = normalized.split(" ", 1)[0] if normalized else ""
                    if phrase.isupper():
                        continue
                    if first_word in SENTENCE_OPENERS and first_word != "the":
                        continue
                    if first_word == "the" and sentence_start == "the":
                        continue
                    method = "honorific_pattern" if HONORIFIC.match(phrase) else "capitalized_sequence"
                    add_mention(mentions, page_number, page_text, phrase, method)

                for match in re.finditer(CAPITALIZED_WORD, sentence):
                    phrase = match.group(0).strip(" .,:;–—-")
                    normalized = normalize(phrase)
                    if not normalized or normalized in COMMON_SINGLE_CAPS:
                        continue
                    if match.start() == 0 and normalized in SENTENCE_OPENERS:
                        continue
                    contextual = context_method(sentence, match.start(), match.end())
                    if normalized in known_aliases:
                        method = "known_single_label"
                    elif contextual:
                        method = contextual
                    else:
                        method = "repeated_single_term"
                    add_mention(mentions, page_number, page_text, phrase, method)

    page_counts: Counter = Counter()
    for (normalized, method), page_records in mentions.items():
        if method == "repeated_single_term":
            page_counts[normalized] += len(page_records)
    return {
        key: page_records
        for key, page_records in mentions.items()
        if key[1] != "repeated_single_term" or page_counts[key[0]] >= 3
    }


def match_candidate(
    normalized: str,
    aliases: Dict[str, Set[Tuple[str, str]]],
    fuzzy_threshold: float,
) -> Tuple[str, str, str, float]:
    exact = aliases.get(normalized)
    if exact:
        values = sorted(exact)
        labels = "; ".join(sorted({label for label, _ in values}))
        types = "; ".join(sorted({type_label for _, type_label in values if type_label}))
        return "exact_existing", labels, types, 1.0

    best_ratio = 0.0
    best_labels: Set[str] = set()
    best_types: Set[str] = set()
    for alias, resources in aliases.items():
        ratio = difflib.SequenceMatcher(None, normalized, alias).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_labels = {label for label, _ in resources}
            best_types = {type_label for _, type_label in resources if type_label}
        elif ratio == best_ratio:
            best_labels.update(label for label, _ in resources)
            best_types.update(type_label for _, type_label in resources if type_label)
    if best_ratio >= fuzzy_threshold:
        return (
            "possible_existing",
            "; ".join(sorted(best_labels)),
            "; ".join(sorted(best_types)),
            round(best_ratio, 3),
        )
    return "new_candidate", "", "", 0.0


def write_report(
    mentions: Dict[Tuple[str, str], Dict[int, Dict[str, object]]],
    aliases: Dict[str, Set[Tuple[str, str]]],
    output_path: Path,
    fuzzy_threshold: float,
) -> Tuple[Counter, int]:
    stats: Counter = Counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=[
                "status",
                "candidate",
                "detection_method",
                "existing_type_match",
                "existing_label_match",
                "match_score",
                "page",
                "mentions_on_page",
                "evidence_snippet",
            ],
        )
        writer.writeheader()
        for (normalized, entity_type), page_records in sorted(
            mentions.items(), key=lambda item: (item[0][0], item[0][1])
        ):
            status, labels, suggested_type, score = match_candidate(
                normalized, aliases, fuzzy_threshold
            )
            if entity_type == "repeated_single_term" and status == "new_candidate":
                status = "ambiguous_term"
            stats[status] += 1
            stats["mentions"] += sum(int(record["count"]) for record in page_records.values())
            for page_number, record in sorted(page_records.items()):
                writer.writerow(
                    {
                        "status": status,
                        "candidate": record["phrase"],
                        "detection_method": entity_type,
                        "existing_type_match": suggested_type,
                        "existing_label_match": labels,
                        "match_score": score,
                        "page": page_number,
                        "mentions_on_page": record["count"],
                        "evidence_snippet": record["snippet"],
                    }
                )
    return stats, len(mentions)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract page-cited entity candidates and compare them to the current RDF graph."
    )
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT, help="Page-marked source text")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Integrated RDF Turtle graph")
    parser.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY, help="Ontology Turtle file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "volume1_entity_review.csv")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.90)
    args = parser.parse_args()

    for path in (args.text, args.data, args.ontology):
        if not path.is_file():
            parser.error("File not found: {}".format(path))
    if not 0.0 <= args.fuzzy_threshold <= 1.0:
        parser.error("--fuzzy-threshold must be between 0 and 1")

    try:
        pages = read_pages(args.text)
        if not pages:
            raise ValueError("No '- [Page n]' markers found in the source text.")
        data, labels_graph = load_graph(args.data, args.ontology)
        aliases = existing_aliases(data, labels_graph)
        mentions = extract_mentions(pages, set(aliases))
        stats, unique_count = write_report(mentions, aliases, args.output, args.fuzzy_threshold)
    except (LookupError, RuntimeError, ValueError) as error:
        parser.exit(2, "Entity review failed: {}\n".format(error))

    print("Pages analyzed: {} ({}-{})".format(len(pages), min(pages), max(pages)))
    print("Unique entity candidates: {}".format(unique_count))
    print(
        "Candidate statuses: exact existing={}, possible existing={}, new candidate={}".format(
            stats["exact_existing"], stats["possible_existing"], stats["new_candidate"]
        )
    )
    print("Total mentions: {}".format(stats["mentions"]))
    print("Review CSV: {}".format(args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
