"""Tests for support_csat_doctor."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import support_csat_doctor as scd

HEADER = "ticket_id,agent,score,date,comment\n"


def analyze_text(text, **kwargs):
    """Analyze CSV text and return the report dict."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                     delete=False) as handle:
        handle.write(text)
        path = handle.name
    try:
        return scd.analyze_file(
            path, kwargs.get("scale", 5),
            kwargs.get("min_average",
                       scd.default_min_average(kwargs.get("scale", 5))),
            kwargs.get("min_responses", 3),
            sent=kwargs.get("sent"),
            min_response_rate=kwargs.get("min_response_rate", 0.10),
            low_override=kwargs.get("low_override"))
    finally:
        os.unlink(path)


def rules(report):
    """Return the sorted list of rule names in the report."""
    return sorted(f["rule"] for f in report["findings"])


def finding_for(report, rule):
    """Return the first finding with this rule, or None."""
    for finding in report["findings"]:
        if finding["rule"] == rule:
            return finding
    return None


class TestParsing(unittest.TestCase):
    def test_parse_score(self):
        self.assertEqual(scd.parse_score("5", 5), 5.0)
        self.assertEqual(scd.parse_score("4.5", 5), 4.5)
        self.assertIsNone(scd.parse_score("6", 5))
        self.assertIsNone(scd.parse_score("0", 5))
        self.assertIsNone(scd.parse_score("abc", 5))
        self.assertIsNone(scd.parse_score("", 5))
        self.assertEqual(scd.parse_score("10", 10), 10.0)
        self.assertIsNone(scd.parse_score("11", 10))

    def test_parse_date(self):
        import datetime
        self.assertEqual(scd.parse_date("2026-11-01"),
                         datetime.date(2026, 11, 1))
        self.assertEqual(scd.parse_date("2026/11/01"),
                         datetime.date(2026, 11, 1))
        self.assertEqual(scd.parse_date("01/11/2026"),
                         datetime.date(2026, 11, 1))
        self.assertIsNone(scd.parse_date("Nov 1 2026"))
        self.assertIsNone(scd.parse_date(""))
        self.assertIsNone(scd.parse_date(None))

    def test_negative_words(self):
        self.assertEqual(scd.negative_words("Agent was rude."),
                         ["rude"])
        self.assertEqual(scd.negative_words("Terrible, never fixed."),
                         ["terrible", "never"])
        self.assertEqual(scd.negative_words("Great help, fixed fast."),
                         [])
        self.assertEqual(scd.negative_words(""), [])
        self.assertEqual(scd.negative_words(None), [])

    def test_negative_words_word_boundary(self):
        self.assertEqual(scd.negative_words("It went slowly."),
                         [])
        self.assertEqual(scd.negative_words("That was badly done."),
                         [])

    def test_thresholds(self):
        self.assertEqual(scd.low_threshold(5), 2)
        self.assertEqual(scd.low_threshold(10), 4)
        self.assertEqual(scd.low_threshold(5, override=1), 1)
        self.assertEqual(scd.satisfied_threshold(5), 4)
        self.assertEqual(scd.satisfied_threshold(10), 8)
        self.assertEqual(scd.default_min_average(5), 3.5)
        self.assertEqual(scd.default_min_average(10), 7.0)


class TestResponseRules(unittest.TestCase):
    def test_low_score(self):
        report = analyze_text(
            HEADER + "T-1,Ana,2,2026-11-01,Slow reply.\n")
        self.assertIn("low-score", rules(report))

    def test_high_score_not_low(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,2026-11-01,Great.\n")
        self.assertNotIn("low-score", rules(report))

    def test_missing_comment_on_low_score(self):
        report = analyze_text(
            HEADER + "T-1,Ana,1,2026-11-01,\n")
        self.assertIn("missing-comment", rules(report))

    def test_comment_on_low_score_is_clean(self):
        report = analyze_text(
            HEADER + "T-1,Ana,1,2026-11-01,Product was broken.\n")
        self.assertNotIn("missing-comment", rules(report))

    def test_negative_comment(self):
        report = analyze_text(
            HEADER + "T-1,Ana,4,2026-11-01,Okay but slow.\n")
        self.assertIn("negative-comment", rules(report))
        finding = finding_for(report, "negative-comment")
        self.assertIn("slow", finding["message"])

    def test_invalid_score(self):
        report = analyze_text(
            HEADER + "T-1,Ana,6,2026-11-01,Great.\n")
        self.assertIn("invalid-score", rules(report))
        self.assertEqual(report["summary"]["scored"], 0)

    def test_unparseable_score(self):
        report = analyze_text(
            HEADER + "T-1,Ana,high,2026-11-01,Great.\n")
        self.assertIn("invalid-score", rules(report))

    def test_duplicate_response(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-1,Ana,4,2026-11-02,Good.\n")
        self.assertIn("duplicate-response", rules(report))
        self.assertEqual(report["summary"]["responses"], 1)
        self.assertEqual(report["summary"]["scored"], 1)

    def test_missing_agent(self):
        report = analyze_text(
            HEADER + "T-1,,4,2026-11-01,Good.\n")
        self.assertIn("missing-agent", rules(report))
        self.assertEqual(report["summary"]["scored"], 1)
        self.assertEqual(report["agents"], [])

    def test_malformed_row(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-2,Ana,4\n"
            + "T-3,Ana,5,2026-11-02,Great.\n")
        self.assertIn("malformed-row", rules(report))
        self.assertEqual(report["summary"]["responses"], 2)

    def test_missing_ticket(self):
        report = analyze_text(
            HEADER + ",Ana,5,2026-11-01,Great.\n")
        self.assertIn("missing-ticket", rules(report))

    def test_invalid_date(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,Nov 1 2026,Great.\n")
        self.assertIn("invalid-date", rules(report))

    def test_missing_date(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,,Great.\n")
        self.assertIn("missing-date", rules(report))

    def test_future_date(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,2999-01-01,Great.\n")
        self.assertIn("future-date", rules(report))

    def test_bom_header(self):
        report = analyze_text(
            "\ufeff" + HEADER + "T-1,Ana,5,2026-11-01,Great.\n")
        self.assertEqual(report["findings"], [])

    def test_empty_file(self):
        report = analyze_text("")
        self.assertEqual(report["summary"]["responses"], 0)
        self.assertEqual(report["summary"]["average"], 0.0)

    def test_blank_lines_skipped(self):
        report = analyze_text(
            HEADER + "\nT-1,Ana,5,2026-11-01,Great.\n\n")
        self.assertEqual(report["summary"]["responses"], 1)


class TestAgentAnalysis(unittest.TestCase):
    def test_agent_below_target(self):
        report = analyze_text(
            HEADER
            + "T-1,Ben,3,2026-11-01,Okay.\n"
            + "T-2,Ben,2,2026-11-02,Slow.\n"
            + "T-3,Ben,1,2026-11-03,Terrible.\n")
        self.assertIn("agent-below-target", rules(report))
        finding = finding_for(report, "agent-below-target")
        self.assertEqual(finding["ticket"], "Ben")

    def test_agent_below_min_responses_not_judged(self):
        report = analyze_text(
            HEADER
            + "T-1,Ben,1,2026-11-01,Terrible.\n"
            + "T-2,Ben,2,2026-11-02,Slow.\n")
        self.assertNotIn("agent-below-target", rules(report))

    def test_agent_above_target_not_flagged(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-2,Ana,4,2026-11-02,Good.\n"
            + "T-3,Ana,5,2026-11-03,Great.\n")
        self.assertNotIn("agent-below-target", rules(report))

    def test_min_responses_override(self):
        report = analyze_text(
            HEADER
            + "T-1,Ben,1,2026-11-01,Terrible.\n"
            + "T-2,Ben,2,2026-11-02,Slow.\n",
            min_responses=2)
        self.assertIn("agent-below-target", rules(report))

    def test_min_average_override(self):
        report = analyze_text(
            HEADER
            + "T-1,Ben,3,2026-11-01,Okay.\n"
            + "T-2,Ben,3,2026-11-02,Okay.\n"
            + "T-3,Ben,3,2026-11-03,Okay.\n",
            min_average=4.0)
        self.assertIn("agent-below-target", rules(report))

    def test_per_agent_table(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-2,Ana,4,2026-11-02,Good.\n"
            + "T-3,Ben,2,2026-11-03,Slow.\n")
        self.assertEqual(report["agents"], [
            {"agent": "Ana", "responses": 2, "average": 4.5, "low": 0},
            {"agent": "Ben", "responses": 1, "average": 2.0, "low": 1},
        ])

    def test_scale_10(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,9,2026-11-01,Great.\n"
            + "T-2,Ana,8,2026-11-02,Good.\n"
            + "T-3,Ben,3,2026-11-03,Terrible.\n",
            scale=10)
        self.assertEqual(report["summary"]["satisfied"], 2)
        self.assertEqual(report["summary"]["detractors"], 1)
        self.assertIn("low-score", rules(report))

    def test_low_threshold_override(self):
        report = analyze_text(
            HEADER + "T-1,Ana,3,2026-11-01,Okay.\n",
            low_override=3)
        self.assertIn("low-score", rules(report))

    def test_response_rate_warning(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-2,Ana,4,2026-11-02,Good.\n",
            sent=100)
        self.assertIn("low-response-rate", rules(report))
        self.assertEqual(report["summary"]["response_rate_percent"], 2)

    def test_response_rate_clean(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-2,Ana,4,2026-11-02,Good.\n",
            sent=10)
        self.assertNotIn("low-response-rate", rules(report))
        self.assertEqual(report["summary"]["response_rate_percent"], 20)

    def test_summary_math(self):
        report = analyze_text(
            HEADER
            + "T-1,Ana,5,2026-11-01,Great.\n"
            + "T-2,Ana,4,2026-11-02,Good.\n"
            + "T-3,Ben,2,2026-11-03,Slow.\n"
            + "T-4,Ben,1,2026-11-04,Terrible.\n")
        summary = report["summary"]
        self.assertEqual(summary["responses"], 4)
        self.assertEqual(summary["scored"], 4)
        self.assertEqual(summary["average"], 3.0)
        self.assertEqual(summary["satisfied"], 2)
        self.assertEqual(summary["satisfied_percent"], 50)
        self.assertEqual(summary["detractors"], 2)


class TestExamples(unittest.TestCase):
    def _example(self, name):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        return os.path.join(base, "examples", name)

    def test_sample_counts(self):
        report = scd.analyze_file(
            self._example("csat.csv"), 5,
            scd.default_min_average(5), 3)
        summary = report["summary"]
        self.assertEqual(summary["responses"], 14)
        self.assertEqual(summary["scored"], 13)
        self.assertEqual(summary["average"], 3.54)
        self.assertEqual(summary["satisfied"], 8)
        self.assertEqual(summary["satisfied_percent"], 62)
        self.assertEqual(summary["detractors"], 4)
        self.assertEqual(summary["findings"], 14)
        self.assertEqual(summary["errors"], 5)
        self.assertEqual(summary["warnings"], 9)
        self.assertEqual(report["agents"], [
            {"agent": "Ana", "responses": 4, "average": 4.0, "low": 1},
            {"agent": "Ben", "responses": 4, "average": 2.0, "low": 3},
            {"agent": "Cara", "responses": 4, "average": 4.5,
             "low": 0},
        ])

    def test_clean_example(self):
        report = scd.analyze_file(
            self._example("clean.csv"), 5,
            scd.default_min_average(5), 3)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["summary"]["errors"], 0)

    def test_warnings_only_example(self):
        report = scd.analyze_file(
            self._example("warnings-only.csv"), 5,
            scd.default_min_average(5), 3)
        summary = report["summary"]
        self.assertEqual(summary["errors"], 0)
        self.assertEqual(summary["warnings"], 2)


class TestOutput(unittest.TestCase):
    def test_json_shape(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,2026-11-01,Great.\n")
        parsed = json.loads(scd.format_json(report))
        self.assertEqual(parsed["summary"]["responses"], 1)
        self.assertEqual(parsed["agents"][0]["agent"], "Ana")

    def test_text_summary_line(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,2026-11-01,Great.\n")
        text = scd.format_text(report)
        self.assertIn("Responses: 1, scored: 1, average: 5.00, "
                      "satisfied: 1 (100%), detractors: 0, findings: "
                      "0, errors: 0, warnings: 0", text)
        self.assertIn("All responses clean.", text)

    def test_text_per_agent_singular(self):
        report = analyze_text(
            HEADER + "T-1,Ana,5,2026-11-01,Great.\n")
        text = scd.format_text(report)
        self.assertIn("Ana: 1 response, average 5.00, low scores 0",
                      text)

    def test_finding_str(self):
        finding = scd.Finding("T-1", "low-score", "warning", "low")
        self.assertEqual(str(finding), "WARNING [low-score] T-1: low")

    def test_check_exit_codes(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        script = os.path.join(base, "support_csat_doctor.py")
        clean = os.path.join(base, "examples", "clean.csv")
        sample = os.path.join(base, "examples", "csat.csv")
        warnings_only = os.path.join(base, "examples",
                                     "warnings-only.csv")
        self.assertEqual(subprocess.run(
            [sys.executable, script, clean, "--check"]).returncode, 0)
        self.assertEqual(subprocess.run(
            [sys.executable, script, sample, "--check"]).returncode, 1)
        self.assertEqual(subprocess.run(
            [sys.executable, script, warnings_only, "--check"]
            ).returncode, 0)
        self.assertEqual(subprocess.run(
            [sys.executable, script, warnings_only, "--check",
             "--strict"]).returncode, 1)

    def test_missing_file_exit_code(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        script = os.path.join(base, "support_csat_doctor.py")
        result = subprocess.run(
            [sys.executable, script, "no-such-file.csv"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_out_flag(self):
        base = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        script = os.path.join(base, "support_csat_doctor.py")
        sample = os.path.join(base, "examples", "clean.csv")
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as handle:
            out_path = handle.name
        try:
            result = subprocess.run(
                [sys.executable, script, sample, "--out", out_path],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            with open(out_path, encoding="utf-8") as handle:
                self.assertIn("All responses clean.", handle.read())
        finally:
            os.unlink(out_path)


if __name__ == "__main__":
    unittest.main()
