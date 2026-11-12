# Changelog

## 1.0.0 - 2026-11-10

Initial release.

* CSAT survey analysis over a CSV export: overall average,
  satisfied share (top-two-box), detractors, a per-agent table
  with response counts, averages, and low-score counts, and a
  finding per problem.
* Low scores flagged with the low threshold (2 on a 5 scale, 4
  on a 10 scale), low scores with no comment flagged because a
  score with no reason cannot be coached on, and comments
  carrying negative keywords flagged with the words that
  matched.
* Agent below target flagged as an error when an agent with at
  least --min-responses (default 3) scored responses averages
  below --min-average (default 3.5 on a 5 scale, 7.0 on a 10
  scale).
* Data errors reported and skipped, never a crash: invalid
  scores, duplicate responses for one ticket, responses with
  no agent, malformed rows, and missing ticket ids. Duplicate
  responses are left out of the averages so one customer cannot
  count twice.
* Optional --sent flag reports the response rate and warns
  when it falls below --min-response-rate (default 10%), since
  a low response rate means the scores come from a small,
  likely polarized slice of customers.
* 5 and 10 point scales supported with --scale, plus
  --low-threshold, --min-average, and --min-responses
  overrides. Dates accepted as YYYY-MM-DD, YYYY/MM/DD, or
  DD/MM/YYYY; invalid, missing, and future dates are warnings.
* Findings carry a ticket id, a rule name, a severity (error or
  warning), and a message; errors and warnings are counted in
  the summary.
* Text and --json output, --out file output, and a --check CI
  gate that exits 1 on errors (and on warnings with --strict).
* Zero dependencies, Python 3.10 or newer.
