# Good first issues

Seeded issues for new contributors. File each one on GitHub with
the `good first issue` and `help wanted` labels.

## 1. Add a weekly trend table

Title: Show the average score per week

Description: Add a --trend flag that prints, after the per-agent
table, the average score and response count per ISO week, so a
manager can see whether satisfaction is improving or slipping
instead of reading one overall average. Responses with no date
or an invalid date are left out of the trend and counted in a
footnote line.

Difficulty: Easy

Acceptance criteria: the trend for the sample file shows the
week of 2026-11-03 with the correct average; a test checks the
weekly rows; README documents the flag.

## 2. Add a satisfaction reason breakdown

Title: Count responses by satisfaction reason

Description: Many CSAT exports carry a `reason` column for
negative ratings (for example "Issue not resolved" or
"Response took too long"). When the column is present, print a
breakdown of low-score responses by reason after the per-agent
table, so a manager can see the top reason for dissatisfaction
at a glance. When the column is absent, print nothing.

Difficulty: Easy

Acceptance criteria: a sample file with a reason column shows
the correct counts; a file without the column is unchanged; a
test covers both cases; README documents the column.

## 3. Support a custom negative keywords file

Title: Let teams supply their own negative keywords

Description: Add a --keywords flag that reads a file of
negative keywords (one per line) and uses it instead of the
built-in list, so a team can flag its own wording like
"escalated" or "refund" without changing the code.

Difficulty: Easy

Acceptance criteria: a file containing "escalated" flags a
comment with that word and does not flag "slow"; without the
flag the built-in list still applies; a test covers both cases;
README documents the flag.

## 4. Add a detractor follow-up list

Title: Export the low-score responses as a follow-up CSV

Description: Add a --followup-out flag that writes a CSV of
the low-score responses (ticket id, agent, score, date,
comment) so a manager can work through the follow-ups and
reach out to the unhappy customers. The file must contain only
responses already in the export.

Difficulty: Medium

Acceptance criteria: the export for the sample file lists the
four detractor tickets (T-204, T-206, T-207, T-208); a test
round-trips the export; README documents the flag.
