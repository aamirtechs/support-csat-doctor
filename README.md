# support-csat-doctor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/support-csat-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/support-csat-doctor/issues)

A zero-dependency Python CLI that turns a CSAT survey CSV
export into an actionable report: the overall average score,
the satisfied share, detractors, a per-agent table with
averages and low-score counts, and a finding per problem. Low
scores without a comment are flagged, because a score with no
reason cannot be coached on, and comments carrying negative
wording are flagged with the words that matched, so a manager
reads the why instead of only the number.

Zendesk's built-in CSAT needs Suite Professional or higher,
and its Explore reporting gives summary metrics without trend
analysis or deep insight. Teams on lower plans export the
survey CSV and work from that, and this tool is the offline
analysis of that export.

## Install

Requires Python 3.10 or newer. No dependencies beyond the
standard library.

```bash
pip install support-csat-doctor
```

Or run it straight from the source checkout:

```bash
python3 support_csat_doctor.py examples/csat.csv
```

## Input format

A CSV export with a header row. Columns used: `ticket_id`,
`agent`, `score`, `date`, and `comment`. Optional columns
`channel` and `reason` are ignored for now. A UTF-8 BOM header
is handled. Dates are accepted as YYYY-MM-DD, YYYY/MM/DD, or
DD/MM/YYYY.

```csv
ticket_id,agent,score,date,comment
T-201,Ana,5,2026-11-01,"Great help, issue fixed fast."
T-204,Ana,2,2026-11-04,Took too long to get a reply.
T-206,Ben,2,2026-11-06,Agent was rude and unhelpful.
T-207,Ben,1,2026-11-07,"Terrible, issue never fixed."
T-208,Ben,2,2026-11-08,
```

## What it checks

Errors, the ones that break the analysis or show an agent
below target:

* `agent-below-target`: an agent with at least
  `--min-responses` (default 3) scored responses averaging
  below `--min-average` (default 3.5 on a 5 scale, 7.0 on a
  10 scale).
* `invalid-score`: a score that is not a number between 1 and
  the scale. The response is left out of the averages.
* `duplicate-response`: a ticket that already has a survey
  response. The duplicate is left out of the analysis, so one
  customer cannot count twice.
* `missing-agent`: a response with no agent. It counts toward
  the overall average but not toward any agent.
* `malformed-row`: a row with the wrong number of fields. The
  row is skipped and reported, never a crash.

Warnings, individual responses worth following up:

* `low-score`: a score at or below the low threshold (2 on a
  5 scale, 4 on a 10 scale).
* `missing-comment`: a low score with no comment, so there is
  no reason recorded to coach on.
* `negative-comment`: a comment carrying negative wording.
  The matched words are listed, for example "rude,
  unhelpful". Matching is word-boundary based, so "slowly"
  does not match "slow".
* `missing-ticket`: a row with no ticket id, so the response
  cannot be traced back to a ticket.
* `invalid-date`: a date that is not YYYY-MM-DD, YYYY/MM/DD,
  or DD/MM/YYYY.
* `missing-date`: a response with no date, so it cannot be
  placed in a trend.
* `future-date`: a response date in the future.
* `low-response-rate`: with `--sent`, the response rate falls
  below `--min-response-rate` (default 10%). A low response
  rate means the scores come from a small, likely polarized
  slice of customers, usually the very happiest or the very
  angriest.

## Usage

```bash
python3 support_csat_doctor.py examples/csat.csv
```

Captured output:

```
WARNING [low-score] T-204: score 2 is at or below the low threshold of 2
WARNING [negative-comment] T-204: comment carries negative wording: long
WARNING [negative-comment] T-205: comment carries negative wording: slow
WARNING [low-score] T-206: score 2 is at or below the low threshold of 2
WARNING [negative-comment] T-206: comment carries negative wording: rude, unhelpful
WARNING [low-score] T-207: score 1 is at or below the low threshold of 2
WARNING [negative-comment] T-207: comment carries negative wording: terrible, never
WARNING [low-score] T-208: score 2 is at or below the low threshold of 2
WARNING [missing-comment] T-208: a low score with no comment cannot be coached on, because there is no reason recorded
ERROR [invalid-score] T-213: score '6' is not a number between 1 and 5, so the response was left out of the averages
ERROR [duplicate-response] T-205: ticket already has a survey response, so this duplicate was left out of the analysis
ERROR [missing-agent] T-214: response has no agent, so it counts toward the overall average but not toward any agent
ERROR [malformed-row] row 17: row has 3 fields but the header has 5, so the row was skipped
ERROR [agent-below-target] Ben: average 2.00 over 4 scored responses is below the target of 3.50

Per agent:
Ana: 4 responses, average 4.00, low scores 1
Ben: 4 responses, average 2.00, low scores 3
Cara: 4 responses, average 4.50, low scores 0

Responses: 14, scored: 13, average: 3.54, satisfied: 8 (62%), detractors: 4, findings: 14, errors: 5, warnings: 9
```

The sample has 14 responses after the duplicate and the
malformed row are left out, 13 of them scored. Ben averages
2.00 over 4 responses and is the only agent below target. The
four detractors are all worth a follow-up, and T-208 has no
comment at all, so there is nothing to coach on yet.

With `--sent`, the response rate is reported too:

```bash
python3 support_csat_doctor.py examples/csat.csv --sent 150
```

Captured summary:

```
Responses: 14, scored: 13, average: 3.54, satisfied: 8 (62%), detractors: 4, findings: 15, errors: 5, warnings: 10
Response rate: 9% (14 of 150 sent)
```

Use it as a CI gate: `--check` exits 1 when any error is
found, and 0 otherwise. On the sample above it exits 1:

```bash
python3 support_csat_doctor.py examples/csat.csv --check
```

On `examples/clean.csv`, three clean responses, it exits 0:

```
Responses: 3, scored: 3, average: 4.67, satisfied: 3 (100%), detractors: 0, findings: 0, errors: 0, warnings: 0
All responses clean.
```

With `--strict`, `--check` also fails on warnings.
`examples/warnings-only.csv` has two warnings, a low score
and its negative comment, so it passes `--check` (exit 0) and
fails `--check --strict` (exit 1).

`--json` emits the summary, per-agent table, and findings as
JSON, and `--out` writes the report to a file.

## Options

| Flag | Meaning |
| --- | --- |
| `--scale` | Survey scale, 5 or 10 (default: 5) |
| `--min-average` | Per-agent minimum average (default: 3.5 on a 5 scale, 7.0 on a 10 scale) |
| `--min-responses` | Scored responses before an agent is judged (default: 3) |
| `--low-threshold` | Score at or below which a response is low (default: 2 on a 5 scale, 4 on a 10 scale) |
| `--sent` | Surveys sent, to report the response rate |
| `--min-response-rate` | Minimum response rate as a fraction (default: 0.10) |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 if any error is found |
| `--strict` | With --check, also exit 1 on warnings |
| `--out` | Write the report to a file |

## Edge cases

* A duplicate response is left out of the analysis entirely,
  so its score, comment, and agent do not affect any average
  or count. The first response for the ticket is kept.
* A response with an invalid score still counts as a response
  but not as a scored response, so it appears in the response
  count and not in the average.
* A response with no agent counts toward the overall average
  but not toward any agent, so the per-agent table never shows
  a blank agent.
* An agent with fewer than `--min-responses` scored responses
  is never flagged below target, so a single bad survey cannot
  condemn an agent.
* A blank line in the file is skipped silently. A row with too
  many or too few fields is a malformed-row error and is
  skipped; the rest of the file is still analyzed.
* Negative keyword matching is word-boundary based, so
  "slowly" does not match "slow" and "badly" does not match
  "bad".

## Tests

```bash
python3 -m unittest discover -s tests -v
```

43 tests, all passing: score and date parsing, negative
keyword matching with word boundaries, low scores, missing
comments, invalid scores, duplicate responses, missing agents
and tickets, malformed rows, invalid, missing, and future
dates, BOM headers, per-agent averages and below-target rules
with min-responses and min-average overrides, 10 point scale,
low-threshold override, response rate, summary math, sample
counts, JSON output shape, and `--check` and `--strict` exit
codes.

## License

MIT. See [LICENSE](LICENSE).
