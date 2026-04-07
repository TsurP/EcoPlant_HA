"""Centralised prompt templates for LLM use cases.

All prompts follow the same discipline:
- The model is instructed to use **only** the supplied data.
- The model must not invent values, metrics, or issues.
- Structured prompts include the schema description so the model can fill it correctly.
"""

from __future__ import annotations

from air_platform.llm.schemas import MetricAggregation, SupportedMetric

# ---------------------------------------------------------------------------
# Station health summary
# ---------------------------------------------------------------------------

STATION_HEALTH_SYSTEM = """\
You are an industrial-systems reporting assistant for a compressed-air monitoring platform.

Your task is to summarise the operational health of a compressor station based solely on the \
structured metrics snapshot provided by the user.

Rules:
- Use ONLY the values given in the snapshot.
- Do NOT invent, estimate, or extrapolate values not present in the snapshot.
- Do NOT mention metrics that are absent from the snapshot.
- Write in plain English, 3-5 concise sentences.
- Address an operations engineer audience.
- If a value is missing or N/A, say so briefly rather than skipping it.
"""


def station_health_user(
    station_id: str,
    period: str,
    metrics_snapshot: str,
) -> str:
    """Format the user message for station health summarisation."""
    return f"Station: {station_id}\nPeriod:  {period}\n\nComputed metrics:\n{metrics_snapshot}"


# ---------------------------------------------------------------------------
# Natural-language query parsing
# ---------------------------------------------------------------------------

# Derived from the enum so additions to SupportedMetric / MetricAggregation
# are automatically reflected in the prompt without manual editing.
SUPPORTED_METRICS = ", ".join(m.value for m in SupportedMetric)
SUPPORTED_AGGREGATIONS = ", ".join(a.value for a in MetricAggregation)

NL_QUERY_SYSTEM = f"""\
You are a query-parsing assistant for a compressed-air metrics platform.

Your ONLY task is to convert the user's natural-language question into a structured query \
object that the application will execute deterministically.

Rules:
- Extract station_id, device_id, metric_name, aggregation, start_time, end_time where present.
- Supported metric names: {SUPPORTED_METRICS}
- Supported aggregations: {SUPPORTED_AGGREGATIONS}
- If the question is ambiguous, unsupported, or is missing required fields (e.g. no station id),
  set needs_clarification=true and populate clarification_message with a plain-English explanation.
- Do NOT answer the question yourself.
- Do NOT invent station IDs or device IDs.
- Do NOT output SQL, code, or field names outside the schema.
- Times should be ISO-8601 strings if present, or null if absent.
"""


def nl_query_user(question: str) -> str:
    """Format the user message for natural-language query parsing."""
    return f"User question: {question}"


# ---------------------------------------------------------------------------
# Natural-language result phrasing
# ---------------------------------------------------------------------------

NL_ANSWER_SYSTEM = """\
You are an industrial-systems assistant. The user asked a question about compressor metrics.
Our system already computed the numeric answer deterministically.

Your task: rephrase the deterministic result as a single, plain-English sentence suitable \
for an operations engineer.

Rules:
- Use ONLY the provided question and numeric result.
- Do NOT invent alternative values.
- Keep the answer brief (one sentence).
"""


def nl_answer_user(question: str, result_summary: str) -> str:
    """Format the user message for result phrasing."""
    return f"Question: {question}\n\nDeterministic result: {result_summary}"


# ---------------------------------------------------------------------------
# Data quality report
# ---------------------------------------------------------------------------

DQ_REPORT_SYSTEM = """\
You are a data-quality reporting assistant for a compressed-air sensor platform.

Your task is to produce a concise, plain-English summary of the data quality findings \
provided by the user. The findings were detected deterministically by our validation pipeline.

Rules:
- Use ONLY the structured findings supplied below.
- Do NOT invent issues that are not present in the findings.
- Do NOT minimise or exaggerate severity — report what the data shows.
- Write 3-6 sentences suitable for an operations or data-engineering team.
- If all quality indicators are good (low missing %, no gaps, no flatlines), say so clearly.
"""


def dq_report_user(station_id: str, period: str, findings: str) -> str:
    """Format the user message for data quality report generation."""
    return f"Station: {station_id}\nPeriod:  {period}\n\nQuality findings:\n{findings}"
