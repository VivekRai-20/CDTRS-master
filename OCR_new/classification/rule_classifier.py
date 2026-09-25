"""
classification/rule_classifier.py
-----------------------------------
Rule-based document classifier.

Rules are defined as a list of (keyword_set, label) pairs.
If any keyword in a set appears in the document text (case-insensitive),
the associated label is assigned.

Multiple matching rules are ranked by the number of matching keywords.
The rule with the most matches wins.

Configuration
-------------
Rules can be defined in ``config/classification_rules.yaml``::

    rules:
      - label: INVOICE
        keywords: [invoice, "total amount", gst, vendor, "bill to"]
      - label: LEAVE_APPLICATION
        keywords: [leave, absent, absence, "medical leave", "sick leave"]
      - label: TECHNICAL_REPORT
        keywords: [report, analysis, implementation, findings, conclusion]

If no rules file is found, a default set of rules is used.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from classification.base_classifier import BaseClassifier
from utils.logger import get_logger

log = get_logger(__name__)

_DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "label": "INVOICE",
        "keywords": [
            "invoice", "total amount", "gst", "tax", "vendor",
            "bill to", "due date", "payment", "amount due",
        ],
    },
    {
        "label": "LEAVE_APPLICATION",
        "keywords": [
            "leave", "absent", "absence", "sick leave", "medical leave",
            "vacation", "days off", "requesting leave",
        ],
    },
    {
        "label": "TECHNICAL_REPORT",
        "keywords": [
            "technical report", "analysis", "implementation", "findings",
            "methodology", "conclusion", "results", "evaluation",
        ],
    },
    {
        "label": "LETTER",
        "keywords": [
            "dear sir", "dear madam", "sincerely", "yours faithfully",
            "regards", "to whom it may concern",
        ],
    },
    {
        "label": "CONTRACT",
        "keywords": [
            "agreement", "contract", "terms and conditions",
            "hereby agree", "signed by", "witness",
        ],
    },
    {
        "label": "RESUME",
        "keywords": [
            "curriculum vitae", "cv", "resume", "work experience",
            "education", "skills", "references",
        ],
    },
]


class RuleClassifier(BaseClassifier):
    """
    Keyword-rule-based document classifier.

    Parameters
    ----------
    config : dict
        Full application configuration.
    """

    CLASSIFIER_NAME = "RuleClassifier"

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._rules = self._load_rules()

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def classify(self, text: str) -> dict[str, Any]:
        """
        Classify *text* using keyword rules.

        Returns
        -------
        dict with ``label``, ``confidence``, ``method``.
        """
        if not text.strip():
            return self._result("UNKNOWN", 0.0)

        text_lower = text.lower()
        best_label = "UNKNOWN"
        best_score = 0
        best_total = 1

        for rule in self._rules:
            label = rule["label"]
            keywords = rule["keywords"]
            matches = sum(
                1 for kw in keywords
                if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower)
            )
            if matches > best_score:
                best_score = matches
                best_label = label
                best_total = len(keywords)

        confidence = min(1.0, best_score / max(best_total * 0.3, 1))

        log.debug(
            "RuleClassifier: '%s' with %d keyword match(es).",
            best_label, best_score,
        )
        return self._result(best_label, confidence)

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _load_rules(self) -> list[dict[str, Any]]:
        rules_file = Path(
            self._config.get("classification", {}).get(
                "rules_file", "config/classification_rules.yaml"
            )
        )
        if not rules_file.is_absolute():  # relative to OCR_new, not the current folder
            rules_file = Path(__file__).resolve().parents[1] / rules_file

        if rules_file.exists():
            try:
                import yaml
                with open(rules_file, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                rules = data.get("rules", [])
                if rules:
                    log.info(
                        "Loaded %d classification rules from '%s'.",
                        len(rules), rules_file,
                    )
                    return rules
            except Exception as exc:
                log.warning("Failed to load rules file '%s': %s", rules_file, exc)

        log.debug("Using default classification rules.")
        return _DEFAULT_RULES
