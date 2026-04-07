## Goal

Implement **Challenge 2 — LLM-Powered Feature** on top of the existing project, assuming **Challenge 1 is already complete**.

The existing system already has:
- ingestion / validation / preprocessing
- computed metrics
- metrics service / API
- tests / lint / type-check / automation

Your job is to add an **LLM integration layer** that is production-minded, cleanly separated, swappable, and well tested.

We will use an **OpenAI API key** as the provider for the project.

Important:
- Use OpenAI for the real provider implementation
- In unit tests, treat the LLM as a **black box** and **mock it**
- It is acceptable to add **optional integration tests** that hit the real OpenAI API, but only behind an env var gate so they are not required in normal CI

---

## What to implement

Add the following capabilities:

1. **Natural language metrics summary**
   - An endpoint that takes computed metrics and returns a plain-English station health summary

2. **Natural language query interface**
   - An endpoint that accepts a natural-language question and translates it into a validated structured query over computed metrics
   - The final metric computation must remain deterministic and done by our service, not by the LLM

3. **Data quality report generator**
   - An endpoint that produces a plain-English summary of data quality issues found during ingestion / validation

---

## Architectural principles

These are mandatory.

### 1) The LLM must not perform metric computation
The LLM is only allowed to do:
- **language generation**
- **language understanding / structured extraction**

The LLM must **not**:
- compute averages
- compute uptime
- compute trends
- detect data quality issues directly from raw data
- generate SQL / pandas code / arbitrary code for execution

All computation, aggregation, filtering, and data quality detection must remain deterministic in our service layer.

### 2) Use a provider abstraction
Do not couple application logic directly to OpenAI SDK calls.

Create a provider interface / protocol and an OpenAI-backed implementation behind it.

### 3) Use validated structured schemas
For the natural-language query endpoint, the LLM should produce a **bounded structured query object**, which must be validated before execution.

Never allow free-form execution.

### 4) Graceful degradation
If the LLM is slow or unavailable:
- do not crash the whole service unnecessarily
- return deterministic structured data where possible
- clearly indicate that natural-language rendering failed

### 5) Tests must verify integration plumbing, not model intelligence
Mock the LLM in unit tests.
Do not write brittle tests that assert exact wording from the model.

---

## Desired high-level design

Build an **LLM application layer around the existing metrics system**.

Conceptually:

- Existing metrics / quality services remain the source of truth
- New LLM services sit above them
- OpenAI lives behind an adapter / gateway

Suggested layering:

- `api/`
- `application/metrics/`
- `application/llm/`
- `domain/`
- `infrastructure/llm/`
- `infrastructure/persistence/` (reuse existing repos/services as appropriate)

You do **not** need to force this exact folder structure if the current project already has a good structure. Adapt to the current codebase. Preserve the existing project conventions.

---

## Required components

Implement the following conceptual pieces.

### A. LLM provider abstraction

Create an interface / protocol for LLM operations.

It should support two use cases:
1. generate free text
2. generate structured output validated against a schema

Suggested shape:

- `generate_text(...)`
- `generate_structured(...)`

The application layer must depend on this abstraction, not directly on OpenAI.

### B. OpenAI provider implementation

Implement the real provider using the OpenAI API key from environment variables.

Requirements:
- configurable model name via env
- request timeout support
- retry on transient failures
- no retry on invalid input / validation errors
- clear exception mapping

### C. Prompt builder / prompt templates

Prompts must be centralized.
Do not scatter long prompt strings across endpoints.

We need prompts for:
- station health summarization
- natural-language query parsing
- data quality report generation

Prompts must strongly instruct the model:
- to use only provided data
- not to invent numbers
- not to invent unsupported metrics
- to respect the required schema when doing structured extraction

### D. Structured query schema

Create a validated schema for natural-language metric queries.

Use a bounded DSL-like schema instead of raw SQL or code.

The schema should support at least:
- station id
- metric name
- aggregation
- time window / time range
- possibly unit if relevant
- possibly a `needs_clarification` wrapper if the request is ambiguous

Supported metrics should reflect whatever the current project already computes.
Do not invent features the current project does not have.

### E. LLM application use cases

Create application-layer use cases for:

1. **Summarize station health**
   - gets deterministic metrics from existing service(s)
   - builds a structured snapshot
   - passes snapshot to LLM
   - returns summary plus raw computed data

2. **Answer natural-language query**
   - sends the user question to LLM for structured parsing
   - validates the parsed query
   - executes it deterministically against existing computed metrics
   - optionally uses the LLM to phrase the result in English
   - returns both:
     - interpreted structured query
     - deterministic result
     - natural-language answer if available

3. **Generate data quality report**
   - obtains structured quality findings from existing ingestion / validation / DQ logic
   - passes only the structured findings to the LLM
   - returns report plus raw findings

### F. API endpoints

Add three endpoints.

Use the current project’s routing conventions, naming style, request/response modeling, and dependency injection patterns.

The endpoints conceptually are:

1. station summary endpoint
2. natural-language query endpoint
3. data quality report endpoint

You may choose route names that match the codebase style, but they should be clear and consistent.

Recommended behavior:

#### Station summary endpoint
Input:
- station id
- time window / date range

Flow:
- fetch deterministic metrics
- generate summary
- return summary + raw metrics

#### Natural-language query endpoint
Input:
- plain English question

Flow:
- parse into validated structured query
- execute deterministically
- return interpreted query + deterministic result + optional natural-language answer

#### Data quality report endpoint
Input:
- station id and/or time window depending on current project design

Flow:
- fetch deterministic DQ findings
- generate report
- return report + structured findings

---

## Non-negotiable behavior

### For the natural-language query endpoint

The LLM must not answer the question directly from its own reasoning.

Correct flow:
1. user asks question
2. LLM parses question into structured query
3. app validates query
4. app executes deterministic query
5. app optionally asks LLM to phrase the result nicely

This distinction is critical.

### Always return structured data
For summary/report endpoints, include the structured source data or findings in the response.
For the query endpoint, include:
- parsed query
- deterministic numeric result
- optional phrased answer

This improves transparency and debuggability.

### No arbitrary execution
Do not let the LLM produce:
- SQL
- pandas code
- Python code
- repository method names
- anything executable

Only allow bounded structured output.

---

## Error handling requirements

Implement production-minded behavior.

### Timeouts
Every LLM call must have a timeout budget.
Use reasonable defaults and make them configurable.

### Retries
Retry only on transient issues such as:
- timeouts from provider
- temporary network failure
- rate limit / 429
- provider 5xx-like transient errors

Do not retry on:
- invalid structured response
- local validation error
- unsupported user request
- malformed prompt input

Use exponential backoff with jitter.

### Graceful fallback
If the LLM fails:
- summary/report endpoints may return structured data with a warning if no NL summary is available
- query endpoint should still return deterministic results if parsing succeeded or can be resolved deterministically
- if parsing itself fails, return a clear error or a `needs_clarification` style response depending on the current API design

### Clear exceptions
Create clean error types / mappings around LLM failures so routes do not depend on raw SDK exceptions.

---

## Observability requirements

Add useful logging / telemetry hooks consistent with the project.

At minimum, log:
- which LLM capability was invoked
- latency
- retries
- timeout occurrences
- degraded/fallback responses
- provider/model name where appropriate

Do not log secrets.
Do not log overly large prompts verbatim if that would be noisy or unsafe.
It is okay to log structured metadata.

If the project already has metrics instrumentation, integrate with it.

---

## Configuration

Use environment variables and project config patterns already present.

Add support for at least:
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS` or equivalent
- retry-related settings if the project has a config system

Use sane defaults where appropriate, but fail clearly if the API key is required and missing.

If the codebase already uses Pydantic settings or similar, follow that pattern.

---

## Testing requirements

This is very important.

### Unit tests
Unit tests must mock the LLM provider.

Test:
- provider abstraction is invoked correctly
- retries happen for transient failures
- timeouts are handled correctly
- invalid structured output is handled correctly
- degraded responses are returned correctly
- endpoints preserve structured source data in responses

Do **not** test the quality of real model wording.

Bad test:
- assert the exact English sentence from the model

Good test:
- assert that the use case called the provider
- assert that the structured result is returned
- assert that fallback behavior occurs when the provider fails

### Integration tests
You may add optional integration tests using the real OpenAI provider, but they must:
- be skipped unless `OPENAI_API_KEY` is present
- not be required for standard local test runs or CI
- assert only coarse-grained behavior, not exact wording

If you add them, keep them minimal.

### Black-box testing principle
Treat the model as a black box.
We are testing our code’s integration plumbing, not the intelligence of OpenAI.

---

## Implementation details to preserve

Because Challenge 1 already exists, first inspect the current project and integrate cleanly with it.

Specifically:
- reuse existing metric computation services
- reuse existing repositories
- reuse existing data-quality detection logic if present
- follow current dependency injection style
- follow current API style
- follow current response model style
- follow current linting / typing / test conventions
- do not rewrite unrelated parts of the codebase

This should feel like a natural extension of the current project, not a parallel mini-project.

---

## Suggested implementation plan

### Step 1
Inspect the current project structure and identify:
- where metrics are queried
- where data quality findings are produced
- how routes are organized
- how config is managed
- how dependencies are injected
- how tests are written

### Step 2
Add domain models / schemas for:
- station summary input/output
- natural-language query request/result
- data quality report input/output
- structured metric query schema

### Step 3
Add the LLM provider abstraction and OpenAI implementation.

### Step 4
Add prompt builders / prompt templates.

### Step 5
Add application-layer use cases for the 3 features.

### Step 6
Expose them through API endpoints.

### Step 7
Add robust tests with mocks.

### Step 8
Update README with:
- feature overview
- env vars
- how to run
- how to test
- note about optional OpenAI integration tests

---

## Prompting guidance

### Station health summary prompt
Input should be a structured snapshot of already computed values, for example:
- station id
- time period
- uptime
- average pressure
- pressure target
- trend info if already computed
- anomaly notes if already computed

Prompt requirements:
- summarize only the provided data
- do not invent values
- keep concise and plain-English
- mention only supported facts present in the input

### Natural-language query parsing prompt
Prompt requirements:
- convert the question into the supported structured query schema
- use only allowed metrics and aggregations
- if the question is ambiguous or unsupported, mark that clearly in structured output
- do not answer the question itself
- do not invent fields

### Data quality report prompt
Input should be already-detected structured issues, such as:
- missing percentages
- flatline windows
- invalid timestamps
- out-of-range counts
- duplicate rates
- whatever DQ findings already exist in the current codebase

Prompt requirements:
- summarize only the supplied findings
- do not invent additional issues
- keep concise and readable

---

## Response design guidance

Responses should be transparent.

### Summary endpoint response
Should contain:
- generated summary
- structured source metrics
- possibly warnings / degraded-mode info

### Natural-language query endpoint response
Should contain:
- original question
- interpreted structured query
- deterministic result
- optional natural-language answer
- warning if LLM rendering failed but deterministic result succeeded

### Data quality report endpoint response
Should contain:
- generated report
- structured findings
- possibly warnings / degraded-mode info

---

## Ambiguity handling

The natural-language query endpoint must handle ambiguous questions safely.

Examples:
- missing station name
- unsupported metric
- vague timeframe like “recently”
- question asks for something the current project does not compute

Preferred behavior:
- return a structured “needs clarification” result if your API style supports it
- otherwise return a clean 4xx response with an explanation of what is supported

Do not guess aggressively.

---

## Code quality expectations

Preserve production quality:
- strong typing
- clean module boundaries
- small focused classes/functions
- good docstrings where helpful
- no giant route handlers
- no duplicated prompt logic
- no provider-specific logic leaking into application layer

---

## README updates

Update the README to describe:
- the new LLM-powered features
- required environment variables
- how to run the API with OpenAI enabled
- how unit tests work with mocks
- how optional integration tests work with a real `OPENAI_API_KEY`

Make it easy for a reviewer to understand:
- why the LLM is only used for parsing/generation
- why deterministic computation remains in the service
- how provider abstraction makes the implementation swappable

---

## Acceptance criteria

The implementation is complete when:

1. There is a clean LLM provider abstraction
2. There is a real OpenAI implementation behind that abstraction
3. There are endpoints for:
   - station metrics summary
   - natural-language metrics query
   - data quality report
4. Natural-language query flow is:
   - NL question -> structured query -> validation -> deterministic execution -> optional NL phrasing
5. The LLM never performs the actual metric computation
6. Errors, timeouts, and retries are handled cleanly
7. Unit tests mock the LLM and verify plumbing / fallback behavior
8. Optional real-OpenAI integration tests are gated by env vars
9. README is updated
10. All existing lint/type/test commands still pass

---

## Important implementation note

Because the previous challenge is already done, do not start from scratch.
Inspect the repository first and implement this as an extension of the current system.

Favor:
- reuse
- consistency
- minimal disruption
- clear architecture

Do not make unnecessary framework or architectural changes unrelated to this challenge.