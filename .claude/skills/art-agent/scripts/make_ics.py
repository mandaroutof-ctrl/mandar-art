#!/usr/bin/env python3
"""Turn approved residency records into a calendar file.

One all-day event per deadline, with a reminder 7 days before and another on the day. Import it into Google
Calendar by double-clicking, or with Settings, Import and export. Used when no Google Calendar connector is
available.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys


def get(record, path, default=""):
    cur = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
    return default if cur is None else cur


def esc(text):
    s = str(text or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    return s.replace("\r\n", r"\n").replace("\n", r"\n")


def fold(line):
    """iCalendar lines wrap at 75 octets."""
    out, current = [], line
    while len(current.encode("utf-8")) > 73:
        cut = 73
        while len(current[:cut].encode("utf-8")) > 73:
            cut -= 1
        out.append(current[:cut])
        current = " " + current[cut:]
    out.append(current)
    return out


def records_from(data):
    if isinstance(data, list):
        return data
    for key in ("approved", "records", "results", "rows"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help="JSON files of approved records")
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", help="YYYY-MM-DD, defaults to the system date")
    ap.add_argument("--remind-days", type=int, default=7)
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//art-agent//residency deadlines//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Residency deadlines"]

    added, skipped = 0, []
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            for record in records_from(json.load(f)):
                name = record.get("name") or "(unnamed)"
                raw = str(record.get("deadline") or "").strip()
                if raw.lower() == "rolling":
                    skipped.append((name, "rolling, no fixed date")); continue
                try:
                    date = dt.date.fromisoformat(raw[:10])
                except ValueError:
                    skipped.append((name, f"no usable deadline: {raw or 'empty'}")); continue
                if date < today:
                    skipped.append((name, f"closed on {date.isoformat()}")); continue

                urls = record.get("source_urls") or []
                desc = " | ".join(x for x in [
                    get(record, "money_summary"),
                    f"Fee: {get(record, 'funding.application_fee') or 'not recorded'}",
                    f"Duration: {record.get('duration')}" if record.get("duration") else "",
                    urls[0] if urls else "",
                ] if x)
                uid = hashlib.sha1(f"{name}{date}".encode("utf-8")).hexdigest()[:20]

                lines += ["BEGIN:VEVENT", f"UID:{uid}@art-agent", f"DTSTAMP:{stamp}",
                          f"DTSTART;VALUE=DATE:{date.strftime('%Y%m%d')}",
                          f"DTEND;VALUE=DATE:{(date + dt.timedelta(days=1)).strftime('%Y%m%d')}",
                          f"SUMMARY:{esc('Residency deadline: ' + name)}",
                          f"DESCRIPTION:{esc(desc)}",
                          f"LOCATION:{esc(' '.join(x for x in [record.get('location'), record.get('country')] if x))}",
                          "TRANSP:TRANSPARENT",
                          "BEGIN:VALARM", f"TRIGGER:-P{args.remind_days}D", "ACTION:DISPLAY",
                          f"DESCRIPTION:{esc(name + ' closes in ' + str(args.remind_days) + ' days')}", "END:VALARM",
                          "BEGIN:VALARM", "TRIGGER:-PT9H", "ACTION:DISPLAY",
                          f"DESCRIPTION:{esc(name + ' closes today')}", "END:VALARM",
                          "END:VEVENT"]
                added += 1

    lines.append("END:VCALENDAR")

    folded = []
    for line in lines:
        folded.extend(fold(line))
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(folded) + "\r\n")

    print(f"{added} event(s) written to {args.out}")
    for name, why in skipped:
        print(f"  skipped {name}: {why}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
