#!/usr/bin/env python3
"""Mechanical half of the residency QA gate.

Scores each record out of 100 on whether it is sourced, quoted and complete enough to act on. It checks
structure, not truth: it can see that a quote is present, not that the quote is real. The QA agent adds the
judgement layer on top. Pass mark is 95 by default.
"""
import argparse
import datetime as dt
import json
import re
import sys
from urllib.parse import urlparse

AGGREGATORS = {
    "transartists.org", "resartis.org", "on-the-move.org", "artconnect.com", "curatorspace.com",
    "artrabbit.com", "e-flux.com", "akimbo.ca", "callforentry.org", "artist.callforentry.org",
    "submittable.com", "air-j.info", "rivet.artjobs.com", "artistcommunities.org", "visualarts.net.au",
    "nava.org.au", "instagram.com", "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "artsy.net", "artforum.com", "deadline.org", "artquest.org.uk", "a-n.co.uk",
}
QUOTE = re.compile(r"[\"'‘’“”]|「|」")
CURRENCY = re.compile(r"(US\$|CA\$|NZ\$|C\$|A\$|S\$|[$€£¥₹₩]|\b(?:USD|EUR|GBP|JPY|INR|CAD|AUD|SGD|CHF|KRW|NZD|AED)\b|\bRs\.?)", re.I)
FREE = re.compile(r"\b(no (application )?fee|free|none|not required|no cost|waived)\b", re.I)


def get(record, path, default=None):
    cur = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
    return default if cur is None else cur


def filled(value):
    return value is not None and str(value).strip() != ""


def domain(url):
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_aggregator(url):
    host = domain(url)
    return any(host == agg or host.endswith("." + agg) for agg in AGGREGATORS)


def parse_deadline(raw):
    """Return ('date', date) | ('rolling', None) | ('bad', None)."""
    if not filled(raw):
        return "bad", None
    text = str(raw).strip().lower()
    if text == "rolling":
        return "rolling", None
    try:
        return "date", dt.date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return "bad", None


def score_record(record, today):
    deductions = []

    def lose(points, field, why, fix):
        deductions.append({"points": points, "field": field, "why": why, "fix": fix})

    # Official source, 25
    urls = [u for u in (record.get("source_urls") or []) if filled(u)]
    if not urls:
        lose(25, "source_urls", "no source URL at all", "add the organisation's own call page")
    else:
        official = [u for u in urls if not is_aggregator(u)]
        if not official:
            lose(20, "source_urls", "every source is an aggregator listing",
                 "open the organisation's own site and cite that page")
        elif is_aggregator(urls[0]):
            lose(5, "source_urls", "an aggregator is listed before the official page",
                 "put the official call page first")

    # Deadline, 20
    state, date = parse_deadline(record.get("deadline"))
    if state == "bad":
        lose(15, "deadline", "not an ISO date and not 'rolling'", "record YYYY-MM-DD or the word rolling")
    elif state == "date" and date < today:
        lose(20, "deadline", f"closed on {date.isoformat()}, before today", "drop it, or record the next cycle")
    notes = record.get("deadline_notes")
    if not filled(notes):
        lose(5, "deadline_notes", "no evidence for the deadline", "quote the page's closing-date wording")
    elif not QUOTE.search(str(notes)) and state != "rolling":
        lose(4, "deadline_notes", "no quoted wording behind the date", "quote the page verbatim")

    # Fee, 15
    fee = get(record, "funding.application_fee")
    if not filled(fee):
        lose(15, "funding.application_fee", "fee not recorded at all",
             "record the amount and currency, or quote the page saying there is none")
    elif not (CURRENCY.search(str(fee)) or FREE.search(str(fee))):
        lose(7, "funding.application_fee", "no currency and no explicit 'no fee' wording",
             "record the amount with its currency, e.g. 'EUR 25', or quote the no-fee line")

    # Funding, 15
    has = get(record, "funding.has_stipend")
    if has is None:
        lose(8, "funding.has_stipend", "unknown whether it pays anything", "set true or false from the page")
    else:
        living = get(record, "funding.living_stipend")
        grant = get(record, "funding.production_grant")
        if has and not (living or grant):
            lose(5, "funding", "says it pays but neither living_stipend nor production_grant is set",
                 "classify it as a living stipend or a production grant")
        if (not has) and (living or grant):
            lose(5, "funding", "has_stipend is false but a stipend or grant is flagged", "resolve the contradiction")
    money = get(record, "money_summary", "")
    if not filled(money) or len(str(money)) < 15:
        lose(7, "money_summary", "no plain line on what the artist actually receives",
             "one line, e.g. 'EUR 800/month plus housing and studio'")

    # Eligibility, 15
    if get(record, "eligibility.india_eligible") is None:
        lose(5, "eligibility.india_eligible", "unknown whether an Indian passport holder can apply",
             "set from the eligibility wording")
    if get(record, "eligibility.international_open") is None:
        lose(3, "eligibility.international_open", "unknown whether it is open internationally", "set from the page")
    if not filled(get(record, "eligibility.career_stage")):
        lose(3, "eligibility.career_stage", "career stage not recorded",
             "emerging, early-career, any, mid-career or established")
    el_notes = get(record, "eligibility.eligibility_notes", "")
    if not filled(el_notes):
        lose(4, "eligibility.eligibility_notes", "no evidence for eligibility", "quote the who-can-apply wording")
    elif not QUOTE.search(str(el_notes)):
        lose(4, "eligibility.eligibility_notes", "eligibility is asserted, not quoted", "quote the page verbatim")

    # Completeness, 10
    if record.get("verified") is not True:
        lose(3, "verified", "not marked verified against an official source", "verify, then set true")
    if not filled(record.get("name")):
        lose(4, "name", "no residency name", "record the programme's own name")
    if not filled(record.get("country")):
        lose(4, "country", "no country", "record the host country")
    if not filled(record.get("notes")):
        lose(3, "notes", "no notes for the manager", "one or two lines on what matters before applying")

    score = max(0, 100 - sum(d["points"] for d in deductions))
    return score, deductions


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help="inbox JSON files of records")
    ap.add_argument("--today", help="YYYY-MM-DD, defaults to the system date")
    ap.add_argument("--threshold", type=float, default=95.0)
    ap.add_argument("--json", action="store_true", help="emit the full verdict as JSON")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    verdicts = []
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        records = data if isinstance(data, list) else data.get("records", [])
        for record in records:
            score, deductions = score_record(record, today)
            verdicts.append({
                "name": record.get("name") or "(unnamed)",
                "file": path,
                "mechanical": score,
                "verdict": "PASS" if score >= args.threshold else "FAIL",
                "deductions": deductions,
            })

    passed = [v for v in verdicts if v["verdict"] == "PASS"]
    if args.json:
        json.dump({"today": today.isoformat(), "threshold": args.threshold,
                   "passed": len(passed), "failed": len(verdicts) - len(passed),
                   "verdicts": verdicts}, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        for v in sorted(verdicts, key=lambda x: x["mechanical"]):
            print(f"{v['mechanical']:5.0f}  {v['verdict']:4}  {v['name']}")
            for d in v["deductions"]:
                print(f"         -{d['points']:<3} {d['field']}: {d['why']}. Fix: {d['fix']}")
        print(f"\n{len(passed)} passed, {len(verdicts) - len(passed)} failed, threshold {args.threshold:.0f}")

    return 0 if len(passed) == len(verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
