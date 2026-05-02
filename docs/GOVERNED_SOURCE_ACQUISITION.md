# Governed Source Acquisition

This note records how to use Exa for the remaining governed inputs without
turning discovery into uncontrolled scraping.

## What Exa Is For

Use Exa to discover candidate source URLs, titles, metadata, and short snippets.
Do not treat Exa snippets as governed corpus text by themselves. A document only
becomes governed after it is downloaded or captured from an allowed source,
registered in the relevant manifest, reviewed for provenance/license, ingested,
and covered by a gate report.

## Source Candidates

### Dịch Vụ Công

Use Dịch Vụ Công for the production shadow pack and non-legal architecture
corpus examples:

- administrative procedure detail pages,
- procedure search/listing pages,
- FAQ/help pages,
- usage guidance pages,
- service-category pages for citizens and businesses.

Good fit:

- `policy_sop`
- `faq`
- table/list-heavy procedure pages
- production-shadow representative workflow documents

Example source areas:

- `https://dichvucong.gov.vn/p/home/dvc-trang-chu.html`
- `https://thutuc.dichvucong.gov.vn/p/home/dvc-trang-chu.html`
- procedure detail pages such as `dvc-chi-tiet-thu-tuc-hanh-chinh.html`

### Thư Viện Pháp Luật

Use Thư Viện Pháp Luật mainly for legal discovery and metadata, then prefer
official original files or clearly allowed original-document downloads for
corpus ingestion.

Good fit:

- legal architecture documents,
- legal regression pack,
- version/status questions,
- cross-reference and related-effect discovery.

Useful source signals visible on pages include document type, issuing body,
issued date, effective status, original/PDF link, related-effect link, and
download link.

Important constraint: `https://thuvienphapluat.vn/robots.txt` currently signals
`search=yes` and `ai-train=no`, and blocks several AI crawlers. Use Exa for
discovery and citation planning, but avoid bulk-ingesting page text unless the
source rights are explicitly acceptable for the project. Prefer official
`Văn bản gốc` / PDF sources and record the source URI and license/provenance in
the manifest.

## Mapping To Remaining Inputs

| Input | Exa role | Candidate source |
|---|---|---|
| Architecture corpus | discover 24-36 candidate URLs across archetypes | Dịch Vụ Công + Thư Viện Pháp Luật |
| MVP eval set | discover source docs and seed draft questions | both sites, followed by human rewrite/review |
| Legal regression pack | discover 12-20 legal docs with cross-reference/version clues | Thư Viện Pháp Luật, then official originals |
| Production shadow pack | discover representative procedure/workflow docs | Dịch Vụ Công |

## Minimum Workflow

1. Use Exa search to collect candidate URLs and metadata.
2. Select a balanced document set for each manifest.
3. Fetch only the chosen pages/files, respecting rights and source terms.
4. Register each item with `source_uri`, `source_hash`, `provenance_owner`,
   `license`, `status`, `doc_type`, `archetype`, and version fields.
5. Ingest the manifests and run parser bakeoff.
6. Author or rewrite the 80 eval questions and attach gold evidence IDs after
   ingestion.
7. Re-run readiness and release gates.
