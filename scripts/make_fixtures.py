"""Regenerate deterministic test fixtures.

The dataset and draft are designed together so the end-to-end test can
assert specific outcomes:

* ref 1 ("Machine Learning Methods for Financial Fraud Detection") is a
  near-verbatim match for the draft's first Introduction claim -> must
  rank 1 with verdict SUPPORTED.
* ref 8 carries a "no significant" / "contradicts" phrasing against the
  same claim -> must be capped at 20%.
* ref 11 has a DOI containing "notfound" -> mock Scopus misses it, so it
  ends up INCOMPLETE and capped at 45%.
* ref 12 has no identifier at all -> INCOMPLETE, exercises the warning path.
* refs 4, 6 and 9 ship without abstracts and are filled in from the Scopus
  payload fixtures below, each using a different awkward response shape
  (coredata description, bibrecord paragraphs, single-element collapsing).

Run with: make fixtures
"""

import json
from pathlib import Path

import pandas as pd
from docx import Document

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

REFERENCES = [
    {
        "NO.": 1,
        "YEAR": 2024,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Smith, J.; Doe, A.",
        "DOCUMENT TITLE": "Machine Learning Methods for Financial Fraud Detection",
        "SOURCE TITLE": "Expert Systems with Applications",
        "LINK": "https://doi.org/10.1016/j.eswa.2024.100001",
        "ABSTRACT": (
            "Machine learning techniques have substantially improved the ability to identify "
            "complex fraud patterns in financial transactions. We evaluate gradient boosting, "
            "random forests, and deep neural networks on a large transaction corpus and show "
            "that learned models detect evolving and previously unseen fraud schemes far more "
            "reliably than conventional rule-based systems, raising recall by 23 percent at a "
            "fixed false positive budget."
        ),
        "AUTHOR KEYWORDS": "fraud detection; machine learning; financial transactions",
    },
    {
        "NO.": 2,
        "YEAR": 2023,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Hidayat, R.; Putra, B.",
        "DOCUMENT TITLE": "Blockchain Adoption and Transparency in Accounting Processes",
        "SOURCE TITLE": "International Journal of Accounting Information Systems",
        "LINK": "https://www.scopus.com/inward/record.uri?eid=2-s2.0-85100000002&partnerID=40",
        "ABSTRACT": (
            "This study examines how distributed ledger technology affects transparency in "
            "corporate accounting. Drawing on twelve organisational case studies, we find that "
            "blockchain-based recording increases auditability and reduces the opportunity for "
            "undisclosed adjustment of financial records, while imposing substantial integration "
            "costs on existing enterprise systems."
        ),
        "AUTHOR KEYWORDS": "blockchain; accounting; transparency; audit",
    },
    {
        "NO.": 3,
        "YEAR": 2022,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Chen, L.; Wang, X.",
        "DOCUMENT TITLE": "Transformer Architectures Outperform Classical Models in Text Classification",
        "SOURCE TITLE": "Neurocomputing",
        "LINK": "https://doi.org/10.1016/j.neucom.2022.100003",
        "ABSTRACT": (
            "We benchmark transformer-based language models against support vector machines, "
            "naive Bayes, and gradient boosted trees across eight text classification datasets. "
            "Transformer models outperform the classical baselines on every dataset, with the "
            "largest gains on tasks requiring long-range contextual reasoning."
        ),
        "AUTHOR KEYWORDS": "transformers; text classification; benchmarking",
    },
    {
        "NO.": 4,
        "YEAR": 2021,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Nakamura, S.",
        "DOCUMENT TITLE": "Class Imbalance Strategies for Transaction Anomaly Detection",
        "SOURCE TITLE": "Knowledge-Based Systems",
        "LINK": "https://doi.org/10.1016/j.knosys.2021.100004",
        "ABSTRACT": (
            "Fraudulent transactions represent a tiny fraction of payment traffic, which makes "
            "anomaly detectors prone to majority-class bias. We compare resampling, cost-sensitive "
            "learning, and synthetic minority oversampling, and report that cost-sensitive "
            "objectives give the most stable precision-recall trade-off in production settings."
        ),
        "AUTHOR KEYWORDS": "class imbalance; anomaly detection; SMOTE",
    },
    {
        "NO.": 5,
        "YEAR": 2023,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Okafor, N.; Ali, M.",
        "DOCUMENT TITLE": "Explainability Requirements for Automated Credit Decisions",
        "SOURCE TITLE": "Decision Support Systems",
        "LINK": "https://doi.org/10.1016/j.dss.2023.100005",
        "ABSTRACT": (
            "Regulatory frameworks increasingly require that automated credit and risk decisions "
            "be explainable to affected customers. We survey post-hoc explanation methods and "
            "argue that feature attribution alone does not satisfy contestability requirements."
        ),
        "AUTHOR KEYWORDS": "explainable AI; credit scoring; regulation",
    },
    {
        "NO.": 6,
        "YEAR": 2020,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Garcia, P.",
        "DOCUMENT TITLE": "Graph Neural Networks for Payment Network Analysis",
        "SOURCE TITLE": "IEEE Access",
        "LINK": "https://doi.org/10.1109/ACCESS.2020.100006",
        "ABSTRACT": (
            "Payment systems form dense transaction graphs whose structure carries signal about "
            "coordinated abuse. We apply graph neural networks to inter-account transfer graphs "
            "and detect collusive rings that node-level classifiers miss entirely."
        ),
        "AUTHOR KEYWORDS": "graph neural networks; payment networks; collusion",
    },
    {
        "NO.": 7,
        "YEAR": 2024,
        "FIELD OF STUDY": "Information Systems",
        "AUTHORS": "Bianchi, F.; Rossi, G.",
        "DOCUMENT TITLE": "A Survey of Real-Time Streaming Architectures in Banking",
        "SOURCE TITLE": "Journal of Systems and Software",
        "LINK": "https://doi.org/10.1016/j.jss.2024.100007",
        "ABSTRACT": (
            "We survey streaming data architectures deployed by retail banks, covering ingestion, "
            "windowed aggregation, and latency budgets. The review is descriptive and does not "
            "evaluate detection accuracy of any downstream model."
        ),
        "AUTHOR KEYWORDS": "streaming; architecture; banking",
    },
    {
        "NO.": 8,
        "YEAR": 2022,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Petrov, D.",
        "DOCUMENT TITLE": "Reassessing Learned Models Against Rule Engines in Card Fraud Screening",
        "SOURCE TITLE": "Computers and Security",
        "LINK": "https://doi.org/10.1016/j.cose.2022.100008",
        "ABSTRACT": (
            "In a controlled twelve-month deployment we find no significant improvement from "
            "machine learning classifiers over a well-tuned rule engine for card fraud screening. "
            "Our result contradicts the widely reported claim that learned models identify complex "
            "fraud patterns in financial transactions more effectively, once alert-handling capacity "
            "is held constant."
        ),
        "AUTHOR KEYWORDS": "fraud detection; rule engines; replication",
    },
    {
        "NO.": 9,
        "YEAR": 2021,
        "FIELD OF STUDY": "Statistics",
        "AUTHORS": "Lindqvist, K.",
        "DOCUMENT TITLE": "Evaluation Metrics for Highly Imbalanced Binary Classification",
        "SOURCE TITLE": "Pattern Recognition Letters",
        "LINK": "https://doi.org/10.1016/j.patrec.2021.100009",
        "ABSTRACT": (
            "Accuracy is misleading when the positive class is rare. We formalise the relationship "
            "between precision-recall area and cost-weighted utility, and recommend reporting "
            "partial AUC at operationally relevant false positive rates."
        ),
        "AUTHOR KEYWORDS": "evaluation metrics; imbalanced data; precision-recall",
    },
    {
        "NO.": 10,
        "YEAR": 2023,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Yusuf, A.; Tan, W.",
        "DOCUMENT TITLE": "Concept Drift in Deployed Fraud Detection Systems",
        "SOURCE TITLE": "Expert Systems with Applications",
        "LINK": "https://doi.org/10.1016/j.eswa.2023.100010",
        "ABSTRACT": (
            "Fraud strategies change faster than model retraining cycles. We quantify performance "
            "decay in three production detectors and show that unattended models lose roughly a "
            "third of their recall within six months of deployment."
        ),
        "AUTHOR KEYWORDS": "concept drift; model decay; fraud detection",
    },
    {
        # DOI deliberately unresolvable -> mock Scopus returns a miss -> INCOMPLETE
        "NO.": 11,
        "YEAR": 2019,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Unknown, U.",
        "DOCUMENT TITLE": "An Unindexed Workshop Paper on Transaction Screening",
        "SOURCE TITLE": "Workshop Proceedings",
        "LINK": "https://doi.org/10.9999/notfound.2019.000011",
        "ABSTRACT": "",
        "AUTHOR KEYWORDS": "",
    },
    {
        # No identifier at all -> import warning + INCOMPLETE
        "NO.": 12,
        "YEAR": 2018,
        "FIELD OF STUDY": "Computer Science",
        "AUTHORS": "Anonymous",
        "DOCUMENT TITLE": "Internal Technical Note on Alert Triage",
        "SOURCE TITLE": "Technical Report",
        "LINK": "https://intranet.example.org/notes/triage",
        "ABSTRACT": "",
        "AUTHOR KEYWORDS": "",
    },
]

#: (style, text) — "Heading 1"/"Heading 2" become section titles.
DRAFT_PARAGRAPHS = [
    ("Title", "Adaptive Machine Learning for Financial Fraud Detection"),
    ("Heading 1", "Introduction"),
    (
        "Normal",
        "Machine learning techniques have improved the ability to identify complex fraud patterns "
        "in financial transactions. Fraudulent activity nevertheless remains a rare event relative "
        "to legitimate payment volume. This paper investigates whether adaptive retraining narrows "
        "that gap.",
    ),
    (
        "Normal",
        "Prior studies show that blockchain increases transparency in accounting processes [2]. "
        "Transformer-based models outperform traditional machine learning methods in text "
        "classification. We do not address natural language inputs in this work.",
    ),
    ("Heading 1", "Related Work"),
    (
        "Normal",
        "Several studies report that class imbalance degrades the precision of anomaly detectors "
        "on transaction data. Graph-based representations reveal collusive behaviour that "
        "account-level features cannot capture. According to Smith et al. (2024), learned models "
        "adapt to previously unseen fraud schemes.",
    ),
    (
        "Normal",
        "Deployed detectors lose a substantial share of their recall within months of release, "
        "e.g. as retraining cycles fall behind changing attacker behaviour. Table 1 summarises "
        "the reviewed systems.",
    ),
    ("Heading 1", "Methodology"),
    (
        "Normal",
        "This study uses a quantitative experimental design. The next section describes the "
        "proposed retraining framework. We evaluate all models on the same held-out period.",
    ),
    ("Heading 1", "Results"),
    (
        "Normal",
        "Adaptive retraining raised recall by 8.4 percent relative to the static baseline. "
        "Accuracy is a misleading metric when the positive class is rare. Table 2 presents the "
        "experimental results.",
    ),
]


#: Abstracts deliberately withheld from the spreadsheet so the enrichment
#: stage has real work to do; keyed by the row's DOI.
WITHHELD_ABSTRACTS = {
    4: (
        "Fraudulent transactions represent a tiny fraction of payment traffic, which makes "
        "anomaly detectors prone to majority-class bias. We compare resampling, cost-sensitive "
        "learning, and synthetic minority oversampling, and report that cost-sensitive "
        "objectives give the most stable precision-recall trade-off in production settings."
    ),
    6: (
        "Payment systems form dense transaction graphs whose structure carries signal about "
        "coordinated abuse. We apply graph neural networks to inter-account transfer graphs "
        "and detect collusive rings that node-level classifiers miss entirely."
    ),
    9: (
        "Accuracy is misleading when the positive class is rare. We formalise the relationship "
        "between precision-recall area and cost-weighted utility, and recommend reporting "
        "partial AUC at operationally relevant false positive rates."
    ),
}


def _coredata(row: dict, abstract: str | None) -> dict:
    return {
        "dc:title": row["DOCUMENT TITLE"],
        "dc:description": abstract,
        "prism:doi": row["LINK"].split("doi.org/")[-1] if "doi.org" in row["LINK"] else None,
        "prism:publicationName": row["SOURCE TITLE"],
        "prism:coverDate": f"{row['YEAR']}-01-01",
        "citedby-count": str(10 + row["NO."]),
        "subtypeDescription": "Article",
        "eid": f"2-s2.0-8510000{row['NO.']:04d}",
        "dc:identifier": f"SCOPUS_ID:8510000{row['NO.']:04d}",
    }


def scopus_payloads() -> dict[str, dict]:
    """One payload per withheld-abstract row, each in a different shape."""
    by_no = {r["NO."]: r for r in REFERENCES}
    payloads: dict[str, dict] = {}

    # Shape A: abstract in coredata, authors as a proper list, keywords as
    # a list of {"$": ...} wrappers.
    row = by_no[4]
    payloads[row["LINK"].split("doi.org/")[-1]] = {
        "abstracts-retrieval-response": {
            "coredata": _coredata(row, WITHHELD_ABSTRACTS[4]),
            "authors": {
                "author": [
                    {"@auid": "7004", "ce:indexed-name": "Nakamura S."},
                    {"@auid": "7005", "ce:surname": "Ito", "ce:given-name": "Kenji"},
                ]
            },
            "authkeywords": {
                "author-keyword": [
                    {"$": "class imbalance"},
                    {"$": "anomaly detection"},
                    {"$": "SMOTE"},
                ]
            },
            "subject-areas": {"subject-area": [{"$": "Computer Science"}]},
        }
    }

    # Shape B: no coredata description at all — abstract lives in the
    # bibrecord as ce:para paragraphs.
    row = by_no[6]
    payloads[row["LINK"].split("doi.org/")[-1]] = {
        "abstracts-retrieval-response": {
            "coredata": _coredata(row, None),
            "item": {
                "bibrecord": {
                    "head": {
                        "abstracts": {
                            "abstract": {
                                "ce:para": [
                                    {"$": WITHHELD_ABSTRACTS[6][:120]},
                                    {"$": WITHHELD_ABSTRACTS[6][120:]},
                                ]
                            }
                        }
                    }
                }
            },
            # Single author collapsed to a bare object rather than a list.
            "authors": {"author": {"@auid": "7006", "ce:indexed-name": "Garcia P."}},
            "authkeywords": {"author-keyword": {"$": "graph neural networks"}},
        }
    }

    # Shape C: abstract as a plain string, keywords absent entirely.
    row = by_no[9]
    payloads[row["LINK"].split("doi.org/")[-1]] = {
        "abstracts-retrieval-response": {
            "coredata": _coredata(row, WITHHELD_ABSTRACTS[9]),
            "authors": {"author": {"@auid": "7009", "ce:indexed-name": "Lindqvist K."}},
        }
    }

    return payloads


def write_scopus_payloads() -> list[Path]:
    from app.services.mocks.mock_scopus import fixture_name

    directory = FIXTURES / "scopus"
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for identifier, payload in scopus_payloads().items():
        path = directory / fixture_name(identifier)
        path.write_text(json.dumps(payload, indent=2) + "\n")
        written.append(path)
    return written


def dataset_rows() -> list[dict]:
    """Spreadsheet view: withheld abstracts are blanked out."""
    rows = []
    for reference in REFERENCES:
        row = dict(reference)
        if row["NO."] in WITHHELD_ABSTRACTS:
            row["ABSTRACT"] = ""
        rows.append(row)
    return rows


def write_dataset() -> Path:
    path = FIXTURES / "sample_dataset.xlsx"
    pd.DataFrame(dataset_rows()).to_excel(path, index=False, engine="openpyxl")
    return path


def write_dataset_csv() -> Path:
    path = FIXTURES / "sample_dataset.csv"
    pd.DataFrame(dataset_rows()).to_csv(path, index=False)
    return path


def write_draft() -> Path:
    path = FIXTURES / "sample_draft.docx"
    document = Document()
    for style, text in DRAFT_PARAGRAPHS:
        document.add_paragraph(text, style=style)
    document.save(path)
    return path


def write_plain_drafts() -> list[Path]:
    md_lines: list[str] = []
    txt_lines: list[str] = []
    for style, text in DRAFT_PARAGRAPHS:
        if style == "Title":
            md_lines.append(f"# {text}")
        elif style.startswith("Heading"):
            md_lines.append(f"{'#' * (int(style[-1]) + 1)} {text}")
        else:
            md_lines.append(text)
            txt_lines.append(text)
    md = FIXTURES / "sample_draft.md"
    txt = FIXTURES / "sample_draft.txt"
    md.write_text("\n\n".join(md_lines) + "\n")
    txt.write_text("\n\n".join(txt_lines) + "\n")
    return [md, txt]


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    written = [
        write_dataset(),
        write_dataset_csv(),
        write_draft(),
        *write_plain_drafts(),
        *write_scopus_payloads(),
    ]
    for path in written:
        print(f"wrote {path.relative_to(FIXTURES.parent.parent)}")


if __name__ == "__main__":
    main()
