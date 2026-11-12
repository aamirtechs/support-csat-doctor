"""Support CSAT survey analysis CLI.

Reads a CSV export of customer satisfaction survey responses
and turns it into an actionable report: the overall average
score, the satisfied share (top-two-box), detractors, a
per-agent table with averages and low-score counts, and a
finding per problem. Low scores without a comment are flagged
because a score with no reason cannot be coached on, and
comments carrying negative keywords are flagged with the words
that matched, so a manager can read the why instead of only
the number.

Zendesk's built-in CSAT needs Suite Professional or higher
(about $115 per agent per month) and its Explore reporting
gives summary metrics without trend analysis or deep insight,
so teams on lower plans export the survey CSV and work from
that. This tool is the offline analysis of that export: it
reads the file, flags every problem with a rule name and a
severity, and never touches the helpdesk.

Each problem is a finding with a ticket id, a rule name, a
severity (error or warning), and a message. Errors are the
ones that break the analysis or show an agent below target;
warnings are individual responses worth following up. --check
exits 1 when any error is found, and --strict also fails on
warnings.

Zero dependencies, Python 3.10 or newer, standard library only.

Usage:
    python3 support_csat_doctor.py examples/csat.csv
    python3 support_csat_doctor.py csat.csv --json --check
    python3 support_csat_doctor.py csat.csv --scale 10 --sent 400
"""

import argparse
import csv
import datetime
import json
import re
import sys

__version__ = "1.0.0"

NEGATIVE_KEYWORDS = (
    "slow", "rude", "unhelpful", "terrible", "never", "worst",
    "waited", "ignored", "useless", "broken", "angry",
    "frustrated", "long", "late", "poor", "bad", "awful",
    "horrible", "disappointing", "unhappy", "unacceptable",
    "worse", "hate", "ridiculous", "pathetic",
)

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y")

DEFAULT_MIN_RESPONSES = 3
DEFAULT_MIN_RESPONSE_RATE = 0.10


class Finding:
    """One analysis finding for one response or one agent."""

    def __init__(self, ticket, rule, severity, message):
        self.ticket = ticket
        self.rule = rule
        self.severity = severity
        self.message = message

    def as_dict(self):
        """Return the finding as a plain dict."""
        return {"ticket": self.ticket, "rule": self.rule,
                "severity": self.severity, "message": self.message}

    def __str__(self):
        return "%s [%s] %s: %s" % (self.severity.upper(), self.rule,
                                   self.ticket, self.message)


def parse_score(value, scale):
    """Parse a score string, or return None when it is invalid.

    A blank value returns None, as does a value that is not a
    number or falls outside 1 to the scale.
    """
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        score = float(value)
    except ValueError:
        return None
    if score < 1 or score > scale:
        return None
    return score


def parse_date(value):
    """Parse a date string, or return None when it is invalid.

    Accepted formats are YYYY-MM-DD, YYYY/MM/DD, and DD/MM/YYYY.
    A blank value returns None.
    """
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def negative_words(comment):
    """Return the negative keywords found in a comment.

    Matching is case-insensitive and word-boundary based, so
    "slowly" does not match "slow" and "badly" does not match
    "bad".
    """
    if not comment:
        return []
    lowered = comment.lower()
    return [word for word in NEGATIVE_KEYWORDS
            if re.search(r"\b" + re.escape(word) + r"\b", lowered)]


def low_threshold(scale, override=None):
    """Return the score at or below which a response is low."""
    if override is not None:
        return override
    return 2 if scale == 5 else 4


def satisfied_threshold(scale):
    """Return the score at or above which a response is satisfied."""
    return 4 if scale == 5 else 8


def default_min_average(scale):
    """Return the default per-agent minimum average score."""
    return 3.5 if scale == 5 else 7.0


class Response:
    """One survey response, parsed from one CSV row."""

    def __init__(self, ticket, agent, score, date, comment):
        self.ticket = ticket
        self.agent = agent
        self.score = score
        self.date = date
        self.comment = comment


def load_responses(path, scale, low):
    """Read the survey CSV and return (responses, findings).

    A duplicate ticket id is reported once and the duplicate
    row is left out of the analysis, so one customer cannot
    count twice. A malformed row is reported and skipped, never
    a crash.
    """
    responses = []
    findings = []
    seen_tickets = set()
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return responses, findings
        expected = len(header)
        for line_no, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != expected:
                findings.append(Finding(
                    "row %d" % line_no, "malformed-row", "error",
                    "row has %d fields but the header has %d, so the "
                    "row was skipped" % (len(row), expected)))
                continue
            record = dict(zip(header, row))
            ticket = (record.get("ticket_id") or "").strip()
            agent = (record.get("agent") or "").strip()
            score_text = (record.get("score") or "").strip()
            date_text = (record.get("date") or "").strip()
            comment = (record.get("comment") or "").strip()
            if not ticket:
                findings.append(Finding(
                    "row %d" % line_no, "missing-ticket", "warning",
                    "row has no ticket id, so the response cannot be "
                    "traced back to a ticket"))
                ticket = "row %d" % line_no
            if ticket in seen_tickets:
                findings.append(Finding(
                    ticket, "duplicate-response", "error",
                    "ticket already has a survey response, so this "
                    "duplicate was left out of the analysis"))
                continue
            seen_tickets.add(ticket)
            score = parse_score(score_text, scale)
            if score is None:
                findings.append(Finding(
                    ticket, "invalid-score", "error",
                    "score %r is not a number between 1 and %d, so "
                    "the response was left out of the averages"
                    % (score_text, scale)))
            if not agent:
                findings.append(Finding(
                    ticket, "missing-agent", "error",
                    "response has no agent, so it counts toward the "
                    "overall average but not toward any agent"))
            date = parse_date(date_text)
            if date_text and date is None:
                findings.append(Finding(
                    ticket, "invalid-date", "warning",
                    "date %r is not YYYY-MM-DD, YYYY/MM/DD, or "
                    "DD/MM/YYYY" % date_text))
            elif date is not None and date > datetime.date.today():
                findings.append(Finding(
                    ticket, "future-date", "warning",
                    "response date %s is in the future" % date))
            elif not date_text:
                findings.append(Finding(
                    ticket, "missing-date", "warning",
                    "response has no date, so it cannot be placed in "
                    "a trend"))
            if score is not None and score <= low:
                findings.append(Finding(
                    ticket, "low-score", "warning",
                    "score %.0f is at or below the low threshold of "
                    "%d" % (score, low)))
                if not comment:
                    findings.append(Finding(
                        ticket, "missing-comment", "warning",
                        "a low score with no comment cannot be coached "
                        "on, because there is no reason recorded"))
            words = negative_words(comment)
            if words:
                findings.append(Finding(
                    ticket, "negative-comment", "warning",
                    "comment carries negative wording: %s"
                    % ", ".join(words)))
            responses.append(Response(ticket, agent, score, date,
                                      comment))
    return responses, findings


def analyze(responses, scale, min_average, min_responses, low):
    """Build per-agent stats and return (agents, findings).

    Only scored responses count toward an average. An agent
    with at least min_responses scored responses and an average
    below min_average is flagged as below target.
    """
    agents = {}
    for response in responses:
        if not response.agent or response.score is None:
            continue
        stats = agents.setdefault(response.agent, {
            "responses": 0, "total": 0.0, "low": 0})
        stats["responses"] += 1
        stats["total"] += response.score
        if response.score <= low:
            stats["low"] += 1
    findings = []
    for name in sorted(agents):
        stats = agents[name]
        stats["average"] = stats["total"] / stats["responses"]
        if stats["responses"] >= min_responses \
                and stats["average"] < min_average:
            findings.append(Finding(
                name, "agent-below-target", "error",
                "average %.2f over %d scored responses is below the "
                "target of %.2f" % (stats["average"],
                                    stats["responses"], min_average)))
    return agents, findings


def analyze_file(path, scale, min_average, min_responses,
                 sent=None, min_response_rate=DEFAULT_MIN_RESPONSE_RATE,
                 low_override=None):
    """Analyze one survey file and return (report dict)."""
    low = low_threshold(scale, low_override)
    responses, findings = load_responses(path, scale, low)
    agents, agent_findings = analyze(responses, scale, min_average,
                                     min_responses, low)
    findings = findings + agent_findings
    scored = [r for r in responses if r.score is not None]
    total = sum(r.score for r in scored)
    satisfied = sum(1 for r in scored
                    if r.score >= satisfied_threshold(scale))
    detractors = sum(1 for r in scored
                     if r.score <= low)
    summary = {
        "responses": len(responses),
        "scored": len(scored),
        "average": round(total / len(scored), 2) if scored else 0.0,
        "satisfied": satisfied,
        "satisfied_percent": round(100.0 * satisfied / len(scored))
        if scored else 0,
        "detractors": detractors,
        "agents": len(agents),
        "findings": len(findings),
        "errors": sum(1 for f in findings if f.severity == "error"),
        "warnings": sum(1 for f in findings
                        if f.severity == "warning"),
    }
    if sent is not None:
        rate = len(responses) / sent if sent else 0.0
        summary["sent"] = sent
        summary["response_rate_percent"] = round(100.0 * rate)
        if rate < min_response_rate:
            findings.append(Finding(
                "(survey)", "low-response-rate", "warning",
                "response rate %.0f%% (%d of %d sent) is below the "
                "%.0f%% minimum, so the scores come from a small, "
                "likely polarized slice of customers"
                % (100.0 * rate, len(responses), sent,
                   100.0 * min_response_rate)))
            summary["findings"] = len(findings)
            summary["warnings"] = sum(
                1 for f in findings if f.severity == "warning")
    agent_rows = []
    for name in sorted(agents):
        stats = agents[name]
        agent_rows.append({"agent": name,
                           "responses": stats["responses"],
                           "average": round(stats["average"], 2),
                           "low": stats["low"]})
    return {"summary": summary, "agents": agent_rows,
            "findings": [f.as_dict() for f in findings]}


def format_text(report):
    """Render the analysis as plain text."""
    summary = report["summary"]
    lines = []
    for finding in report["findings"]:
        lines.append("%s [%s] %s: %s"
                     % (finding["severity"].upper(),
                        finding["rule"], finding["ticket"],
                        finding["message"]))
    if report["agents"]:
        lines.append("")
        lines.append("Per agent:")
        for row in report["agents"]:
            noun = "response" if row["responses"] == 1 else "responses"
            lines.append("%s: %d %s, average %.2f, low "
                         "scores %d" % (row["agent"], row["responses"],
                                        noun, row["average"],
                                        row["low"]))
    lines.append("")
    lines.append("Responses: %d, scored: %d, average: %.2f, "
                 "satisfied: %d (%d%%), detractors: %d, findings: "
                 "%d, errors: %d, warnings: %d"
                 % (summary["responses"], summary["scored"],
                    summary["average"], summary["satisfied"],
                    summary["satisfied_percent"], summary["detractors"],
                    summary["findings"], summary["errors"],
                    summary["warnings"]))
    if "response_rate_percent" in summary:
        lines.append("Response rate: %d%% (%d of %d sent)"
                     % (summary["response_rate_percent"],
                        summary["responses"], summary["sent"]))
    if not report["findings"]:
        lines.append("All responses clean.")
    return "\n".join(lines) + "\n"


def format_json(report):
    """Render the analysis as JSON."""
    return json.dumps(report, indent=2) + "\n"


def main(argv=None):
    """Entry point for the support-csat-doctor CLI."""
    parser = argparse.ArgumentParser(
        description="Analyze a CSAT survey CSV export: averages, "
                    "per-agent scores, and follow-up flags.")
    parser.add_argument("path", help="CSV file of survey responses")
    parser.add_argument("--scale", type=int, choices=(5, 10),
                        default=5,
                        help="survey scale, 5 or 10 (default: 5)")
    parser.add_argument("--min-average", type=float, default=None,
                        help="per-agent minimum average (default: 3.5 "
                             "on a 5 scale, 7.0 on a 10 scale)")
    parser.add_argument("--min-responses", type=int,
                        default=DEFAULT_MIN_RESPONSES,
                        help="scored responses before an agent is "
                             "judged (default: 3)")
    parser.add_argument("--low-threshold", type=int, default=None,
                        help="score at or below which a response is "
                             "low (default: 2 on a 5 scale, 4 on a 10 "
                             "scale)")
    parser.add_argument("--sent", type=int, default=None,
                        help="surveys sent, to report the response rate")
    parser.add_argument("--min-response-rate", type=float,
                        default=DEFAULT_MIN_RESPONSE_RATE,
                        help="minimum response rate as a fraction "
                             "(default: 0.10)")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of text")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any error is found")
    parser.add_argument("--strict", action="store_true",
                        help="with --check, also exit 1 on warnings")
    parser.add_argument("--out", help="write the report to a file")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    min_average = args.min_average
    if min_average is None:
        min_average = default_min_average(args.scale)
    try:
        report = analyze_file(args.path, args.scale, min_average,
                              args.min_responses, sent=args.sent,
                              min_response_rate=args.min_response_rate,
                              low_override=args.low_threshold)
    except FileNotFoundError:
        print("error: file not found: %s" % args.path, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.path, exc),
              file=sys.stderr)
        return 2
    if args.json:
        output = format_json(report)
    else:
        output = format_text(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output, end="")
    summary = report["summary"]
    if args.check:
        if summary["errors"]:
            return 1
        if args.strict and summary["warnings"]:
            return 1
    return 0


def main_entry():
    """Console script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
