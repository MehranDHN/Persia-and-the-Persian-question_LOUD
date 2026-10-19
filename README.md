# Persia and the Persian Question: Linked Open Data

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](LICENSE)

This project studies George N. Curzon's *Persia and the Persian Question* as a historical source and develops a structured, RDF-based knowledge graph about the people, places, events, documents, and political relationships it describes.

The aim is to make Curzon's account easier to explore and compare while identifying its omissions, ambiguities, and contested claims. The graph is an analytical aid, not a claim that Curzon's account is neutral or complete. Assertions should be traceable to a source and page wherever possible, and interpretations should be distinguished from facts reported by the source.

## Project Goals

- Represent historical entities and relationships using the project ontology.
- Preserve citations to the relevant volume and page, along with provenance for graph statements.
- Use stable, dereferenceable identifiers and standard RDF vocabularies where appropriate, so the published data can participate in the Linked Data web.
- Make the resulting data reusable for research, teaching, and further historical analysis.

## Technologies and Standards

![RDF 1.1](https://img.shields.io/badge/RDF-1.1-4b83c3)
![OWL 2](https://img.shields.io/badge/OWL-2-4b83c3)
![CIDOC CRM planned](https://img.shields.io/badge/CIDOC_CRM-planned-lightgrey)
![SPARQL planned](https://img.shields.io/badge/SPARQL-planned-lightgrey)
![SKOS planned](https://img.shields.io/badge/SKOS-planned-lightgrey)
![IIIF planned](https://img.shields.io/badge/IIIF-planned-lightgrey)

The current ontology is expressed in RDF/OWL. CIDOC CRM, SPARQL querying, SKOS vocabularies, and IIIF presentation are target integrations, not yet implemented in this repository.

## Repository Contents

| Path | Contents |
| --- | --- |
| `ontology/Curzon_Ontology.ttl` | RDF/OWL ontology in Turtle format. It defines classes for people, factions, events, places, time, documents, and source books, plus their properties. |
| `plain_text_books/Curzon_vol1.txt` | Internet Archive full-text page for volume 1. Despite the extension, this file currently contains HTML rather than clean plain text. |
| `plain_text_books/Curzon_vol2.txt` | Internet Archive full-text page for volume 2. Despite the extension, this file currently contains HTML rather than clean plain text. |

Source records: [Volume 1](https://archive.org/details/in.gov.ignca.11918) and [Volume 2](https://archive.org/details/in.gov.ignca.11917).

## Current Status

The repository contains the ontology and two source-page captures. It does not yet contain a published knowledge graph or a documented extraction and curation workflow. The ontology metadata currently describes a Browne/Shuster source corpus rather than Curzon; that metadata and the ontology namespace should be aligned with this project's Curzon scope before the graph is presented as a complete, interoperable Linked Data release. The current namespace uses GitHub-based IRIs, which should resolve to stable project documentation or data when published.

## Suggested Curation Workflow

1. Extract and review the book text, retaining the original source-page links and bibliographic details.
2. Identify entities and events, recording the volume, page, and evidence for each assertion.
3. Represent curated statements in RDF using the ontology, with provenance and uncertainty made explicit.
4. Validate the Turtle and links, then publish the ontology and dataset at stable, dereferenceable URLs.

## Licensing

The project's original ontology, authored annotations, and knowledge-graph data are licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**. See [LICENSE](LICENSE) for the scope and terms. Reusers must provide appropriate attribution, link to the license, and indicate changes.

This license does not cover the files in `plain_text_books/` or other third-party material. Those files are Internet Archive page captures; the page content and underlying digitized edition may have separate rights or terms. Verify the edition's public-domain status and the source provider's terms in the relevant jurisdiction before redistributing them. Software code, if added, should be licensed separately.

## Contributing

Contributions should include source and page references for historical claims, distinguish reported claims from editorial interpretation, and document uncertainty or disagreement rather than silently resolving it. Keep identifiers stable and validate RDF changes before proposing them.
