import hashlib

from .schema import SCHEMA, TABLE

EXTRACT = """You are a QA reviewer for data-analysis reports.

DATA AVAILABLE:
{schema}

TASK: Split the REPORT below into atomic claims (one fact or one judgment each).
For each claim return:
- "id": "C1", "C2", ...
- "quote": the exact words from the report (verbatim, shortest span that holds the claim)
- "kind": "numeric" if the claim states a number or a comparison that the data can check,
          "judgment" if it is a conclusion, cause, forecast or recommendation
- "stated_value": the number the claim states, in the column's unit (e.g. 16.9 for "16.9%").
          For a comparison ("X is higher than Y") use 1 for true.
          For a percent change use the stated percent. null for judgments.
- "sql": ONE DuckDB SELECT over table `{table}` returning ONE number that measures exactly
          what the claim says, so it can be compared to stated_value. null for judgments.
          Percent change = 100.0*(new-old)/old. Percentage-point change = new-old.
          "X% per year on average" over a period = compound annual growth rate:
          100.0*(POWER(new/old, 1.0/years)-1).
          Comparisons: SELECT CASE WHEN ... THEN 1 ELSE 0 END.

RULES:
- Encode what the claim SAYS, even if you think it is wrong. Never correct the report.
- Use the {entity} and {time} the claim refers to. If a {time} is implied by context, use it.
- Return JSON: {{"claims": [...]}}

REPORT:
<<<
{report}
>>>"""


JUDGE = """You are a senior analyst reviewing a junior analyst's report before it goes to the client.

CLIENT REQUIREMENTS:
{requirements}

REPORT:
<<<
{report}
>>>

FACTS ALREADY CHECKED AGAINST THE DATA (actual values from the database):
{facts}

DATA CONTEXT (straight from the database, for the countries and years the report mentions;
use it to check causes, comparisons and trends, including ones the report does not mention):
{context}

TASKS:
1. For each JUDGMENT claim below, decide if the facts, the data context and the report's own numbers
   support it.
   "supported"   = follows reasonably from the data. A risk or recommendation that is grounded
                   in numbers from the data counts as supported.
   "unsupported" = only if it is contradicted by the data or relies on facts not in the data
                   (e.g. a cause the data does not show, or a forecast with no basis).
   JUDGMENT CLAIMS: {judgments}
2. For each client requirement, decide if the report answers it:
   "covered", "partial" or "missing", with the report quote that answers it (or null).
   A requirement answered for a different scope than asked (wrong period, wrong comparison group,
   wrong metric) is "partial", not "covered"; its reason must say what was asked vs what was answered.

Return JSON:
{{"judgments": [{{"id": "...", "verdict": "supported|unsupported", "reason": "one sentence"}}],
  "requirements": [{{"id": "R1", "status": "covered|partial|missing", "evidence": "quote or null",
                     "reason": "one sentence"}}]}}"""


def prompt_version() -> str:
    """Short hash of both prompt templates: results made with other prompts are stale."""
    return hashlib.sha256((EXTRACT + JUDGE).encode()).hexdigest()[:8]


def extract_prompt(report: str, schema: str = SCHEMA, table: str = TABLE,
                   entity: str | None = "country", time: str | None = "year") -> str:
    """Prompt that splits a report into claims and writes one SQL query per numeric claim."""
    return EXTRACT.format(schema=schema, table=table, entity=entity or "entity", time=time or "period",
                          report=report)


def judge_prompt(report: str, requirements: str, facts: str, judgments: str, context: str = "(none)") -> str:
    """Prompt that judges conclusions against the checked facts and data context, and checks coverage."""
    return JUDGE.format(report=report, requirements=requirements, facts=facts, judgments=judgments,
                        context=context)
