#!/usr/bin/env python3
"""Turn the residency filter's output into rows for the Mandar_Art residencies sheet.

Keeps residencies that passed every gate, have an open or rolling deadline, and charge no fee or a fee
under the INR cap. Prints them in the sheet's third-tab column order.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

AGENT = Path("/Users/andreadsouza/Art/agent")

COLUMNS = [
    "Residence", "Location", "Time", "Theme/ Media", "Eligibility", "Deadline", "Fee", "Cover",
    "Application Requirements", "Contact", "", "IMP Links", "USP",
]

# Approximate INR per unit. Override with --rates '{"USD": 90}' and state the rate you used.
RATES = {
    "INR": 1.0, "USD": 88.0, "EUR": 96.0, "GBP": 112.0, "JPY": 0.58, "CAD": 63.0, "AUD": 57.0,
    "SGD": 67.0, "CHF": 105.0, "KRW": 0.062, "NZD": 52.0, "SEK": 8.6, "NOK": 8.4, "DKK": 12.9,
    "PLN": 22.0, "CZK": 3.9, "HUF": 0.24, "TWD": 2.8, "THB": 2.6, "IDR": 0.0054, "MXN": 4.7,
    "BRL": 16.0, "ZAR": 4.9, "AED": 24.0, "TRY": 2.1,
}
SYMBOLS = {"$": "USD", "US$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP",
           "¥": "JPY", "JPY": "JPY", "₹": "INR", "INR": "INR", "RS": "INR", "S$": "SGD", "SGD": "SGD",
           "C$": "CAD", "CA$": "CAD", "CAD": "CAD", "A$": "AUD", "AUD": "AUD", "CHF": "CHF", "KRW": "KRW",
           "₩": "KRW", "NZ$": "NZD", "NZD": "NZD", "AED": "AED", "MXN": "MXN", "BRL": "BRL", "ZAR": "ZAR"}

WORDS = {"dollars?": "USD", "euros?": "EUR", "pounds?": "GBP", "yen": "JPY", "rupees?": "INR",
         "francs?": "CHF", "won": "KRW"}

FREE = re.compile(r"\b(no (application )?fee|free|none|waived|not required|no cost|0)\b", re.I)
AMOUNT = re.compile(r"(US\$|CA\$|NZ\$|C\$|A\$|S\$|[$€£¥₹₩]|\b[A-Z]{3}\b|\bRs\.?)\s*([\d][\d,]*(?:\.\d+)?)"
                    r"|([\d][\d,]*(?:\.\d+)?)\s*(US\$|C\$|A\$|S\$|[$€£¥₹₩]|\b[A-Z]{3}\b)")
NOT_STATED = re.compile(r"\b(none|not|nothing|no fee)\s+(stated|mentioned|listed|published|specified|given|found)\b", re.I)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def records_list(data):
    if isinstance(data, list):
        return data
    for value in data.values():
        if isinstance(value, list):
            return value
    return []


def norm(name):
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def fee_in_inr(text, rates):
    """Return (inr_amount or None, status) where status is free | ok | over | unknown."""
    if not text or not str(text).strip():
        return None, "unknown"
    s = str(text).strip()
    for word, code in WORDS.items():
        s = re.sub(rf"\b{word}\b", code, s, flags=re.I)
    if NOT_STATED.search(s) and not AMOUNT.search(s):
        return None, "unknown"
    if FREE.search(s) and not AMOUNT.search(s):
        return 0.0, "free"
    m = AMOUNT.search(s)
    if not m:
        return None, "unknown"
    sym = (m.group(1) or m.group(4) or "").upper()
    num = (m.group(2) or m.group(3) or "").replace(",", "")
    code = SYMBOLS.get(sym) or SYMBOLS.get(sym.replace(".", ""))
    if not code or code not in rates:
        return None, "unknown"
    try:
        inr = float(num) * rates[code]
    except ValueError:
        return None, "unknown"
    return inr, "ok"


def join(*parts):
    return " · ".join(p.strip() for p in parts if p and str(p).strip())


def build_row(result, record, fee_note):
    el = record.get("eligibility", {}) or {}
    fu = record.get("funding", {}) or {}
    di = record.get("discipline", {}) or {}
    dl = result.get("deadline", {}) or {}
    deadline = dl.get("date") or record.get("deadline") or ""
    if dl.get("state") == "rolling":
        deadline = "Rolling"
    deadline = join(deadline, record.get("deadline_notes"))
    stage = el.get("career_stage")
    eligibility = join(el.get("eligibility_notes"), f"career stage: {stage}" if stage else "",
                       "India eligible" if el.get("india_eligible") else "")
    links = record.get("source_urls") or result.get("source_urls") or []
    return [
        record.get("name") or result.get("name", ""),
        join(record.get("location"), record.get("country")),
        record.get("duration", ""),
        join(di.get("programme_focus"), di.get("thematic_constraint")),
        eligibility,
        deadline,
        join(fu.get("application_fee") or "", fee_note),
        record.get("money_summary") or result.get("money", ""),
        record.get("notes", ""),
        "",
        "",
        "  ".join(links),
        join(record.get("style_fit_reason"), " ".join(record.get("cautions") or [])),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-fee-inr", type=float, default=5000)
    ap.add_argument("--rates", help="JSON object of INR-per-unit overrides, e.g. '{\"USD\": 90}'")
    ap.add_argument("--skip-names", help="text file, one residency name per line, already on the sheet")
    ap.add_argument("--include-verify", action="store_true", help="also emit the verify bucket, marked")
    ap.add_argument("--format", choices=["tsv", "csv", "json"], default="tsv")
    ap.add_argument("--header", action="store_true", help="print the column header row first")
    args = ap.parse_args()

    rates = dict(RATES)
    if args.rates:
        rates.update(json.loads(args.rates))

    shortlist = load_json(AGENT / "output" / "shortlist.json")
    records = {norm(r.get("name")): r for r in records_list(load_json(AGENT / "residencies.json"))}
    skip = set()
    if args.skip_names:
        skip = {norm(line) for line in Path(args.skip_names).read_text(encoding="utf-8").splitlines() if line.strip()}

    rows, dropped = [], []
    for res in shortlist.get("results", []):
        name = res.get("name", "")
        key = norm(name)
        bucket = (res.get("bucket") or "").lower()
        state = (res.get("deadline") or {}).get("state")
        if key in skip:
            dropped.append((name, "already on the sheet")); continue
        if bucket.startswith("disq"):
            dropped.append((name, "failed a hard gate: " + "; ".join(res.get("disqualified_because") or []))); continue
        if bucket.startswith("verif") and not args.include_verify:
            dropped.append((name, "verify list: " + "; ".join(res.get("open_questions") or []))); continue
        if state not in ("open", "rolling"):
            dropped.append((name, (res.get("deadline") or {}).get("label", "deadline not open"))); continue
        record = records.get(key, {})
        inr, status = fee_in_inr((record.get("funding") or {}).get("application_fee"), rates)
        if status == "over" or (status == "ok" and inr >= args.max_fee_inr):
            dropped.append((name, f"fee about INR {inr:,.0f}, cap is {args.max_fee_inr:,.0f}")); continue
        if status == "free":
            fee_note = "free"
        elif status == "ok":
            fee_note = f"about INR {round(inr, -1):,.0f}"
        else:
            fee_note = "CHECK FEE"
        row = build_row(res, record, fee_note)
        if bucket.startswith("verif"):
            row[4] = join("[VERIFY] " + "; ".join(res.get("open_questions") or []), row[4])
        rows.append(row)

    if args.format == "json":
        json.dump({"columns": COLUMNS, "rows": rows, "dropped": dropped}, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        writer = csv.writer(sys.stdout, delimiter="\t" if args.format == "tsv" else ",", lineterminator="\n")
        if args.header:
            writer.writerow(COLUMNS)
        writer.writerows(rows)
        if dropped:
            print("\n# Not included", file=sys.stderr)
            for name, why in dropped:
                print(f"# {name}: {why}", file=sys.stderr)
        print(f"\n# {len(rows)} row(s) ready, {len(dropped)} not included", file=sys.stderr)


if __name__ == "__main__":
    main()
