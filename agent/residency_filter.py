#!/usr/bin/env python3
"""Residency Filter Agent.

Screens artist residencies against the client profile in criteria.json.
Anything that cannot work is disqualified with a reason. Anything with a
gate-critical unknown goes to a verify list. The rest is scored out of 100
and ranked, with deadline status alongside.

  python3 residency_filter.py                        screen and write reports
  python3 residency_filter.py --explain gasworks     score breakdown for one residency
  python3 residency_filter.py --add inbox/file.json  merge new research, then screen
  python3 residency_filter.py --today 2026-09-10     screen as of a given date

Standard library only. Change the client profile in criteria.json, not here.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "residencies.json"
CRITERIA_PATH = HERE / "criteria.json"
OUT_DIR = HERE / "output"

BLANK = {"", "none", "null", "n/a", "na", "unknown", "not stated", "not provided",
         "not specified", "not confirmed", "unclear", "-"}
INCLUSIVE_WORDS = ["sculpt", "installation", "mixed media", "mixed-media", "all disciplines", "any discipline",
                   "all creative disciplines", "all medium", "any medium"]
NEGATION = re.compile(r"\b(not|no|non|without|excluding|except|nor|isn't|lacks?|unclear|unknown|"
                      r"weak|poor|stretch|mismatch|unlikely)\b")


# ---------------------------------------------------------------- helpers

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def norm(text):
    ascii_text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def filled(value):
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (list, dict)):
        return bool(value)
    return str(value).strip().lower() not in BLANK


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def section(record, key):
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def live(mapping):
    """Drop documentation keys that start with an underscore."""
    return {k: v for k, v in mapping.items() if not k.startswith("_")}


def amounts(text):
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", str(text or ""))]


def charges_fee(fee):
    if not filled(fee):
        return False
    text = str(fee).lower()
    if re.search(r"\b(no (application )?fee|free|none|waived|not required|no cost)\b", text):
        return False
    return any(a > 0 for a in amounts(text))


def has_materials_budget(budget):
    if not filled(budget):
        return False
    text = str(budget).lower()
    if re.search(r"\bno separate|\bnot separate|\bnone stated|\bnot stated|\bnot listed", text):
        return False
    if any(a > 0 for a in amounts(text)):
        return True
    return not NEGATION.search(text)


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def money_to_artist(fu):
    """True if any stipend or grant is paid, False if confirmed none, None if unknown."""
    flags = [fu.get(k) for k in ("has_stipend", "living_stipend", "production_grant")]
    if True in flags:
        return True
    if fu.get("has_stipend") is False or (fu.get("living_stipend") is False and fu.get("production_grant") is False):
        return False
    return None


def keyword_hits(text, keywords):
    """Keywords match as word prefixes, or whole words when they end in $.
    A hit is ignored when a negating word appears earlier in the same clause."""
    text = str(text or "").lower()
    hits = []
    for kw in keywords:
        whole = kw.endswith("$")
        stem = kw[:-1] if whole else kw
        pattern = re.compile(r"\b" + re.escape(stem.lower()) + (r"\b" if whole else ""))
        for m in pattern.finditer(text):
            clause_start = max(text.rfind(ch, 0, m.start()) for ch in ".;\n") + 1
            if NEGATION.search(text[clause_start:m.start()]):
                continue
            hits.append(stem)
            break
    return hits


def country_entry(country, table):
    target = norm(country)
    entries = {k: v for k, v in live(table).items() if isinstance(v, dict)}
    names_for = {k: [norm(k)] + [norm(a) for a in v.get("aliases", [])] for k, v in entries.items()}
    for name, names in names_for.items():
        if target and target in names:
            return name, entries[name]
    for name, names in names_for.items():
        if target and any(n and re.search(r"\b" + re.escape(n) + r"\b", target) for n in names):
            return name, entries[name]
    return None, table.get("_default", {"score": 0.6, "why": "Country not in the table."})


def deadline_info(record, today):
    raw = record.get("deadline")
    if not filled(raw):
        return {"state": "unknown", "days": None, "label": "No deadline published. Monitor."}
    text = str(raw).strip().lower()
    if text.startswith("rolling"):
        return {"state": "rolling", "days": None, "label": "Rolling. Apply any time."}
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not m:
        return {"state": "unknown", "days": None, "label": f"Unclear deadline: {raw}"}
    due = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    days = (due - today).days
    if days < 0:
        return {"state": "closed", "days": days, "date": due.isoformat(),
                "label": f"Closed {due}, {-days} days ago. Watch for the next call."}
    urgency = " Urgent." if days <= 21 else ""
    return {"state": "open", "days": days, "date": due.isoformat(),
            "label": f"Open, {days} days left ({due}).{urgency}"}


# ---------------------------------------------------------------- the screen

def check_gates(record, crit):
    g = crit["hard_gates"]
    el, fu, di = section(record, "eligibility"), section(record, "funding"), section(record, "discipline")
    reasons = []
    if g.get("require_stipend") and money_to_artist(fu) is False:
        reasons.append("No stipend or grant.")
    if g.get("require_india_eligible") and el.get("india_eligible") is False:
        reasons.append("Closed to India-based artists on the current call.")
    if g.get("exclude_digital_only") and di.get("digital_only") is True:
        reasons.append("Scoped to digital or media art only.")
    if (g.get("require_mixed_media_or_sculpture") and di.get("mixed_media_ok") is False
            and di.get("sculpture_installation_ok") is False):
        reasons.append("Excludes both mixed media and sculpture or installation.")
    if g.get("exclude_collective_only") and el.get("collective_required") is True:
        reasons.append("Requires a duo or collective, and the client applies solo.")
    if g.get("exclude_established_only") and str(el.get("career_stage") or "").lower() == "established":
        reasons.append("For established artists only.")
    need, have = el.get("min_years_experience"), crit["client"].get("years_practising")
    if g.get("enforce_min_experience") and is_number(need) and is_number(have) and have < need:
        reasons.append(f"Needs {need:g}+ years of practice and the client has {have:g}.")

    if g.get("exclude_host_country_india") and str(record.get("country") or "").strip().lower() == "india":
        reasons.append("Hosted in India, and the brief is for a residency abroad.")

    if g.get("exclude_single_material_only") and single_craft_lock(record):
        reasons.append(f"Locked to a single craft or material ({single_craft_lock(record)}), "
                       "and the practice is mixed media.")

    cap = g.get("max_application_fee_inr")
    if is_number(cap):
        fee, waived = application_fee_inr(fu, g)
        if is_number(fee) and fee > cap and not waived:
            reasons.append(f"Application fee of about INR {fee:,.0f}, and the rule is no fee at all."
                           if cap == 0 else
                           f"Application fee of about INR {fee:,.0f}, over the INR {cap:,.0f} cap.")

    stay_cap = g.get("max_stay_cost_per_week_inr")
    if is_number(stay_cap):
        weekly = stay_cost_per_week_inr(fu)
        if is_number(weekly) and weekly > stay_cap:
            reasons.append(f"Costs about INR {weekly:,.0f} a week to stay, over the INR {stay_cap:,.0f} cap.")
    return reasons


def _per_week(text, amount):
    """Normalise an amount to a weekly figure using the period named in `text`."""
    if re.search(r"per month|/ ?month|a month|monthly|pro Monat", text, re.I):
        return amount / 4.345
    if re.search(r"per day|/ ?day|a day|daily|per night", text, re.I):
        return amount * 7
    m = re.search(r"per (\d+) weeks?", text, re.I)
    if m:
        return amount / float(m.group(1))
    if re.search(r"per week|/ ?week|a week|weekly", text, re.I):
        return amount
    return None


# Rates are approximate and only decide gate pass or fail, never a quoted figure.
_INR = {"INR": 1, "RS": 1, "USD": 88, "US$": 88, "$": 88, "EUR": 103, "€": 103, "GBP": 118, "£": 118,
        "CHF": 110, "CAD": 64, "AUD": 58, "NZD": 53, "SGD": 68, "JPY": 0.60, "¥": 0.60, "CNY": 12.3,
        "AED": 24, "SEK": 9.2, "NOK": 8.6, "DKK": 13.8, "CZK": 4.1, "PLN": 24, "ZAR": 4.9}
_FREE = re.compile(r"\b(no (application )?fee|fee[- ]free|free to apply|none|not required|no cost|no charge)\b", re.I)
_AMOUNT = re.compile(r"(US\$|CA\$|NZ\$|A\$|S\$|CHF|EUR|USD|GBP|JPY|INR|CAD|AUD|SGD|CNY|AED|Rs\.?|[$€£¥₹])\s*"
                     r"([0-9][0-9,.]*)|([0-9][0-9,.]*)\s*(CHF|EUR|USD|GBP|JPY|INR|CAD|AUD|SGD|CNY|AED|euros?|dollars?|pounds?|yen)", re.I)
_SYM = {"US$": "USD", "CA$": "CAD", "NZ$": "NZD", "A$": "AUD", "S$": "SGD", "$": "USD", "€": "EUR",
        "£": "GBP", "¥": "JPY", "₹": "INR", "RS": "INR", "EUROS": "EUR", "EURO": "EUR",
        "DOLLARS": "USD", "DOLLAR": "USD", "POUNDS": "GBP", "POUND": "GBP", "YEN": "JPY"}


def _to_inr(text):
    """Largest money amount in `text`, converted to INR. None when there is no amount."""
    best = None
    for m in _AMOUNT.finditer(str(text)):
        cur, amt = (m.group(1), m.group(2)) if m.group(2) else (m.group(4), m.group(3))
        try:
            value = float(str(amt).replace(",", ""))
        except ValueError:
            continue
        code = _SYM.get(str(cur).upper().strip(), str(cur).upper().strip())
        rate = _INR.get(code)
        if rate is None:
            continue
        inr = value * rate
        best = inr if best is None else max(best, inr)
    return best


def application_fee_inr(funding, gates):
    """(fee in INR or None, waived?). A waiver counts only when the host names the client's category."""
    raw = funding.get("application_fee")
    if raw is None or str(raw).strip() == "":
        return None, False
    text = str(raw)
    waived = False
    if str(gates.get("application_fee_waiver_counts_as_free")) == "explicit_category_only":
        if re.search(r"\bwaive", text, re.I) and re.search(r"\bindia|\bindian", text, re.I):
            waived = True
    amount = _to_inr(text)
    if amount is None:
        return (0.0 if _FREE.search(text) else None), waived
    if _FREE.search(text) and not re.search(r"\bfee (is|of)\b", text, re.I):
        return 0.0, waived
    return amount, waived


def stay_cost_per_week_inr(funding):
    """
    NET weekly cost of being there, in INR. None when nothing chargeable is stated.

    Net, not gross: a fellowship paying EUR 1,600 a month while charging EUR 250 rent costs the artist
    nothing to attend. Counting the 250 alone would disqualify the best-funded residency on the list.
    """
    pays = funding.get("artist_pays")
    parts = pays if isinstance(pays, list) else [pays] if pays else []
    gross = None
    for part in parts:
        text = str(part)
        # Costs he would carry anywhere, and never a reason to disqualify.
        if re.search(r"visa|flight|airfare|travel|material|art suppl|equipment|insurance|shipping|car hire|rent a car", text, re.I):
            continue
        # A line describing the stipend rather than a charge: "living costs beyond the EUR 350/week stipend".
        if re.search(r"stipend|bursary|grant|honorarium|beyond the", text, re.I):
            continue
        amount = _to_inr(text)
        if amount is None:
            continue
        weekly = _per_week(text, amount)
        if weekly is None:
            continue          # no period stated, so it cannot be normalised
        gross = weekly if gross is None else max(gross, weekly)
    if gross is None:
        return None
    return max(0.0, gross - (stipend_per_week_inr(funding) or 0.0))


def stipend_per_week_inr(funding):
    """What the residency pays the artist, normalised to INR per week. None when it pays nothing."""
    if funding.get("has_stipend") is False:
        return None
    best = None
    for key in ("stipend_detail", "materials_budget"):
        text = str(funding.get(key) or "")
        for m in _AMOUNT.finditer(text):
            # Look only BEHIND the figure for words that make it a charge. A wider window would let
            # "a contribution of 250 EUR" further down the sentence mask the 1,600 EUR being paid.
            before = text[max(0, m.start() - 40):m.start()]
            if re.search(r"contribution|payable back|pay back|deduct|rent of|towards incidental", before, re.I):
                continue
            amount = _to_inr(m.group(0))
            if amount is None:
                continue
            weekly = _per_week(text[m.start():m.end() + 40], amount)
            if weekly is None:
                continue
            best = weekly if best is None else max(best, weekly)
    return best


_CRAFT_LOCK = [("ceramic", r"ceramics?[- ]only|only ceramics?|ceramic art centre|ceramics? residency|pottery"),
               ("glass", r"glass[- ]only|only glass|glass studio residency|glassmaking programme"),
               ("wood or furniture", r"wood(work)?[- ]only|furniture making|only furniture"),
               ("textile", r"textiles?[- ]only|only textiles?|weaving[- ]only"),
               ("printmaking", r"printmaking[- ]only|only printmaking"),
               ("performance", r"performing arts only|performance only")]


def single_craft_lock(record):
    """Name of the craft a programme is locked to, or None when it takes a range of media."""
    di = section(record, "discipline")
    if di.get("mixed_media_ok") is True or di.get("sculpture_installation_ok") is True:
        pass  # still check: a ceramics centre may tick sculpture yet accept only clay
    hay = " ".join(str(di.get(k) or "") for k in
                   ("required_material", "thematic_constraint", "programme_focus")).lower()
    required = str(di.get("required_material") or "").strip().lower()
    for name, pattern in _CRAFT_LOCK:
        if re.search(pattern, hay):
            return name
        if required and required.startswith(name[:6]):
            return name
    return None


def open_questions(record, crit):
    el, fu, di = section(record, "eligibility"), section(record, "funding"), section(record, "discipline")
    q = []
    if not record.get("verified"):
        q.append("not yet verified against an official source")
    if money_to_artist(fu) is None:
        q.append("whether it pays a stipend or grant")
    need, have = el.get("min_years_experience"), crit["client"].get("years_practising")
    if is_number(need) and not is_number(have):
        q.append(f"whether the client has the {need:g}+ years of practice it requires")
    if el.get("india_eligible") is None:
        q.append("whether India-based artists can apply")
    if di.get("mixed_media_ok") is None and di.get("sculpture_installation_ok") is None:
        q.append("whether mixed media and sculpture are in scope")
    if not filled(record.get("deadline")):
        q.append("next deadline")
    return q


def score(record, crit):
    weights = live(crit["weights"])
    el, fu, di = section(record, "eligibility"), section(record, "funding"), section(record, "discipline")
    # What the residency says about itself. Research notes are kept out on purpose:
    # they often repeat the client's own style words and would inflate the match.
    programme_text = " . ".join(str(x) for x in (
        record.get("name"), el.get("eligibility_notes"), di.get("thematic_constraint"),
        di.get("programme_focus"), record.get("past_residents")) if filled(x))
    facility_text = " . ".join(str(x) for x in (di.get("facilities"), record.get("notes")) if filled(x))
    visa_text = " . ".join(str(x) for x in (programme_text, facility_text, fu.get("stipend_detail")) if filled(x)).lower()
    parts = {}

    # Funding strength
    pts, why = 0, []
    living, grant, paid = fu.get("living_stipend"), fu.get("production_grant"), fu.get("has_stipend")
    if living is True or (paid is True and living is None and grant is not True):
        pts += 14
        why.append("living stipend +14")
    elif grant is True or paid is True:
        pts += 5
        why.append("grant for production only +5")
        if living is False:
            pts -= 3
            why.append("living costs self-funded -3")
    if grant is True or has_materials_budget(fu.get("materials_budget")):
        pts += 4
        why.append("production or materials money +4")
    for key, value, label in (("travel_covered", 6, "travel covered"),
                              ("accommodation", 5, "accommodation"), ("studio", 3, "studio")):
        if fu.get(key) is True:
            pts += value
            why.append(f"{label} +{value}")
    if charges_fee(fu.get("application_fee")):
        pts -= 2
        why.append("application fee -2")
    # Unknowns are not costs, so items like "visa not addressed" are skipped.
    pays = [p for p in (fu.get("artist_pays") or []) if filled(p)
            and not re.search(r"not (addressed|confirmed|stated|described)|unverified|unconfirmed", str(p).lower())]
    if pays:
        penalty = min(4, len(pays))
        pts -= penalty
        why.append(f"artist pays {len(pays)} cost item(s) -{penalty}")
    parts["funding_strength"] = (clamp(pts / 30), why or ["no funding confirmed"])

    # India access
    notes = str(el.get("eligibility_notes") or "").lower()
    india_specific = el.get("india_specific") is True or bool(re.search(
        r"india[- ](specific|focused|only)|(artists|practitioners) (from|based in|living in) india\b|"
        r"indian (artists|nationals|citizens) only", notes))
    if el.get("india_eligible") is False:
        ia, why = 0.0, ["closed to India-based artists"]
    elif india_specific:
        ia, why = 1.0, ["India-specific call"]
    elif el.get("india_eligible") is True and el.get("international_open") is True:
        ia, why = 0.7, ["open internationally, India confirmed eligible"]
    elif el.get("india_eligible") is True:
        ia, why = 0.6, ["India confirmed eligible"]
    elif el.get("international_open") is True:
        ia, why = 0.45, ["international call, India not explicitly confirmed"]
    else:
        ia, why = 0.3, ["India eligibility unknown"]
    visa_help = fu.get("visa_support") is True or bool(
        re.search(r"visa[^.;]{0,30}(support|assist|letter|sponsor|invitation)|(support|assist|help)[^.;]{0,30}visa", visa_text)
        and not re.search(r"\b(no|not|without)\b[^.;]{0,20}visa", visa_text))
    if visa_help and ia > 0:
        ia = clamp(ia + 0.15)
        why.append("visa support")
    parts["india_access"] = (ia, why)

    # Country practicality for an Indian passport holder
    cname, entry = country_entry(record.get("country"), crit["country_practicality"])
    parts["country_practicality"] = (clamp(float(entry.get("score", 0.6))),
                                     [f"{cname or record.get('country') or 'country unknown'}: {entry.get('why', '')}"])

    # Discipline fit
    dp, why = 0.0, []
    for key, full, label in (("sculpture_installation_ok", 0.45, "sculpture/installation"),
                             ("mixed_media_ok", 0.40, "mixed media")):
        value = di.get(key)
        if value is True:
            dp += full
            why.append(f"{label} welcome")
        elif value is None:
            dp += 0.2
            why.append(f"{label} unconfirmed")
        else:
            why.append(f"{label} not accepted")
    facilities = keyword_hits(facility_text, crit["facility_keywords"])
    if facilities:
        dp += 0.15
        why.append("facilities: " + ", ".join(facilities))
    if filled(di.get("required_material")):
        dp -= 0.25
        why.append(f"must work mainly in {di['required_material']}")
    theme = str(di.get("thematic_constraint") or "")
    inclusive = re.match(r"\s*(none|no theme|no\b)", theme.lower()) or keyword_hits(theme, INCLUSIVE_WORDS)
    off_theme = [] if inclusive else keyword_hits(theme, live(crit["style_keywords"])["negative"])
    if off_theme:
        dp -= 0.3
        why.append("theme pulls away: " + ", ".join(off_theme))
    parts["discipline_fit"] = (clamp(dp), why)

    # Style resonance
    manual = record.get("style_fit")
    if isinstance(manual, (int, float)) and not isinstance(manual, bool):
        parts["style_resonance"] = (clamp(float(manual)),
                                    [f"assessed: {record.get('style_fit_reason') or 'no reason recorded'}"])
    else:
        kw = live(crit["style_keywords"])
        pos, neg = keyword_hits(programme_text, kw["positive"]), keyword_hits(programme_text, kw["negative"])
        sr = 0.5 + min(0.5, 0.1 * len(pos)) - min(0.5, 0.2 * len(neg))
        why = []
        if pos:
            why.append("aligned: " + ", ".join(pos))
        if neg:
            why.append("misaligned: " + ", ".join(neg))
        parts["style_resonance"] = (clamp(sr), why or ["no style signals in the programme description, neutral"])

    # Emerging-artist fit
    stage = str(el.get("career_stage") or "").strip().lower()
    stages = {"emerging": 1.0, "early-career": 1.0, "early career": 1.0, "any": 0.7,
              "mid-career": 0.3, "mid career": 0.3, "established": 0.0}
    need = el.get("min_years_experience")
    if is_number(need) and need >= 5:
        em, why = 0.3, [f"requires {need:g}+ years of practice"]
    elif stage in stages:
        em, why = stages[stage], [f"career stage: {stage}"]
    elif is_number(need) and need > 0:
        em, why = 0.6, [f"requires {need:g}+ years of practice"]
    elif re.search(r"\b(emerging|early[- ]career|young artists?|recent graduates?)\b", programme_text.lower()):
        em, why = 0.9, ["emerging-artist language in the programme description"]
    else:
        em, why = 0.5, ["career stage not stated"]
    parts["emerging_fit"] = (em, why)

    total = sum(parts.get(k, (0, []))[0] * wt for k, wt in weights.items())
    return round(total, 1), parts


def tier_for(points, crit):
    ordered = sorted(crit["tiers"], key=lambda t: -t[0])
    for threshold, label in ordered:
        if points >= threshold:
            return label
    return ordered[-1][1]


def screen(db, crit, today):
    rows = []
    for record in db["residencies"]:
        gates = check_gates(record, crit)
        points, parts = score(record, crit)
        fu, el = section(record, "funding"), section(record, "eligibility")
        if gates:
            bucket = "disqualified"
        elif (not record.get("verified") or money_to_artist(fu) is None or el.get("india_eligible") is None
              or (is_number(el.get("min_years_experience")) and not is_number(crit["client"].get("years_practising")))):
            bucket = "verify"
        else:
            bucket = "shortlist"
        rows.append({"record": record, "name": record.get("name"), "country": record.get("country"),
                     "score": points, "tier": tier_for(points, crit), "parts": parts, "gates": gates,
                     "questions": open_questions(record, crit), "deadline": deadline_info(record, today),
                     "bucket": bucket})
    rows.sort(key=lambda r: -r["score"])
    return rows


# ---------------------------------------------------------------- output

def cell(text, limit=90):
    text = re.sub(r"\s+", " ", str(text or "")).replace("|", "/").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def money_line(record):
    fu = section(record, "funding")
    if filled(record.get("money_summary")):
        return cell(record["money_summary"], 90)
    if fu.get("living_stipend") is False and fu.get("production_grant") is True:
        head = "Production grant only, living costs self-funded"
    elif filled(fu.get("stipend_detail")):
        head = cell(fu["stipend_detail"], 70)
    elif fu.get("has_stipend") is True:
        head = "Paid, amount unconfirmed"
    elif fu.get("has_stipend") is False:
        head = "No stipend"
    else:
        head = "Stipend unconfirmed"
    extras = [label for key, label in (("travel_covered", "travel"), ("accommodation", "housing"),
                                       ("studio", "studio")) if fu.get(key) is True]
    return head + (f" · plus {', '.join(extras)}" if extras else "")


DIMENSION_NOTES = {
    "funding_strength": "A living stipend beats a production-only grant. Travel, housing, studio and materials money add. Fees and artist-paid costs subtract.",
    "india_access": "India-specific calls score highest, then open international calls. Visa support adds.",
    "country_practicality": "Visa friction, travel from India and cost of living for an Indian passport holder.",
    "discipline_fit": "Welcomes sculpture, installation and mixed media. Workshops add. A required single material or an off-theme constraint subtracts.",
    "style_resonance": "Programme leans towards surreal, figurative, material or conceptual work rather than digital or social practice.",
    "emerging_fit": "Explicitly for emerging or early-career artists. A multi-year experience minimum subtracts.",
}


def write_reports(rows, crit, today):
    OUT_DIR.mkdir(exist_ok=True)
    weights = live(crit["weights"])
    short = [r for r in rows if r["bucket"] == "shortlist"]
    verify = [r for r in rows if r["bucket"] == "verify"]
    out = [r for r in rows if r["bucket"] == "disqualified"]
    now = [r for r in short if r["deadline"]["state"] in ("open", "rolling")]
    client = crit["client"]

    md = ["# Residency Shortlist", "",
          f"Screened {today.isoformat()} · {len(rows)} residencies in the database · {len(short)} shortlisted · "
          f"{len(verify)} to verify · {len(out)} disqualified", "",
          f"**Client:** {client['career_stage']}, based in {client['base_country']}, {client['passport']} passport, "
          f"applies {client['applies_as']}. {client['practice']} {client['style']}", "",
          "## Apply now", ""]
    if now:
        for r in sorted(now, key=lambda x: (x["deadline"]["days"] is None, x["deadline"]["days"] or 0)):
            md.append(f"- **{r['name']}**, {r['country']} · fit {r['score']:.0f}/100 · {r['deadline']['label']}")
    else:
        md.append("Nothing on the shortlist has an open deadline today. Use the shortlist below to prepare for the next cycle.")

    md += ["", "## Ranked shortlist", "", "Passed every hard gate and verified. Ranked by fit, not by deadline.", ""]
    if short:
        md += ["| # | Residency | Country | Fit | Tier | Money | Deadline |", "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(short, 1):
            md.append(f"| {i} | {cell(r['name'], 50)} | {cell(r['country'], 25)} | {r['score']:.0f} | {r['tier']} | "
                      f"{money_line(r['record'])} | {cell(r['deadline']['label'], 60)} |")
    else:
        md.append("No verified residency passes every gate yet.")

    md += ["", "## Worth verifying", "",
           "Not ruled out, but a gate-critical fact is still unknown. Scores are provisional and show which to chase first.", ""]
    if verify:
        md += ["| Residency | Country | Provisional fit | Still unknown |", "|---|---|---|---|"]
        for r in verify:
            md.append(f"| {cell(r['name'], 50)} | {cell(r['country'], 25)} | {r['score']:.0f} | "
                      f"{cell('; '.join(r['questions']), 140)} |")
    else:
        md.append("Nothing outstanding.")

    flagged = [r for r in short + verify if r["record"].get("cautions")]
    if flagged:
        md += ["", "## Watch out for", ""]
        for r in flagged:
            md += [f"**{r['name']}**", ""] + [f"- {c}" for c in r["record"]["cautions"]] + [""]

    if md[-1] != "":
        md.append("")
    md += ["## Disqualified", ""]
    if out:
        md += ["| Residency | Country | Why |", "|---|---|---|"]
        for r in out:
            md.append(f"| {cell(r['name'], 50)} | {cell(r['country'], 25)} | {cell(' '.join(r['gates']), 180)} |")
    else:
        md.append("Nothing disqualified.")

    md += ["", "## How the screen works", "",
           "**Hard gates.** A residency is thrown out if it pays no stipend or grant, is closed to India-based artists, "
           "is digital-only, excludes both mixed media and sculpture, requires a duo or collective, is for established "
           "artists only, or needs more years of practice than the client has. Unknown is not the same as failing, so an unknown goes to the verify list instead.", "",
           "**Fit score.** Residencies that pass the gates are scored out of 100.", "",
           "| Dimension | Points | What earns them |", "|---|---|---|"]
    for k, wt in weights.items():
        md.append(f"| {k.replace('_', ' ').capitalize()} | {wt} | {DIMENSION_NOTES.get(k, '')} |")
    md += ["", "Tiers: " + " · ".join(f"{label} {t}+" for t, label in crit["tiers"] if t > 0) + ".", "",
           "Change the client profile, gates or weights in criteria.json. Run with --explain NAME to see exactly why a "
           "residency scored what it did.", ""]
    (OUT_DIR / "shortlist.md").write_text("\n".join(md), encoding="utf-8")

    save(OUT_DIR / "shortlist.json", {
        "screened": today.isoformat(),
        "counts": {"total": len(rows), "shortlist": len(short), "verify": len(verify), "disqualified": len(out)},
        "results": [{
            "name": r["name"], "country": r["country"], "bucket": r["bucket"], "score": r["score"],
            "tier": r["tier"], "deadline": r["deadline"], "money": money_line(r["record"]),
            "disqualified_because": r["gates"], "open_questions": r["questions"],
            "breakdown": {k: {"points": round(r["parts"].get(k, (0, []))[0] * wt, 1), "of": wt,
                              "why": r["parts"].get(k, (0, []))[1]} for k, wt in weights.items()},
            "source_urls": r["record"].get("source_urls", []),
        } for r in rows],
    })


def print_console(rows, today):
    print(f"\nResidency screen · {today.isoformat()}\n")
    for title, key in (("SHORTLIST", "shortlist"), ("VERIFY", "verify"), ("DISQUALIFIED", "disqualified")):
        group = [r for r in rows if r["bucket"] == key]
        print(f"{title} ({len(group)})")
        for r in group:
            if key == "disqualified":
                detail = r["gates"][0]
            elif key == "verify":
                detail = "unknown: " + "; ".join(r["questions"][:2])
            else:
                detail = r["deadline"]["label"]
            print(f"  {r['score']:5.1f}  {str(r['name'])[:44]:44}  {detail}")
        print()
    print(f"Reports written to {OUT_DIR}/shortlist.md and shortlist.json")


def explain(rows, query, crit):
    q = norm(query)
    hits = [r for r in rows if q in norm(r["name"]) or any(q in norm(a) for a in r["record"].get("aliases", []))]
    if not hits:
        print(f"No residency matches '{query}'.")
        return 1
    weights = live(crit["weights"])
    for r in hits:
        print(f"\n{r['name']} · {r['country']}")
        print(f"  Result:   {r['bucket']} · fit {r['score']}/100 · {r['tier']}")
        print(f"  Deadline: {r['deadline']['label']}")
        if r["gates"]:
            print("  Disqualified because:")
            for g in r["gates"]:
                print(f"    - {g}")
        if r["questions"]:
            print("  Still unknown:")
            for g in r["questions"]:
                print(f"    - {g}")
        for c in r["record"].get("cautions") or []:
            print(f"  Caution:  {c}")
        print("  Score breakdown:")
        for k, wt in weights.items():
            frac, why = r["parts"].get(k, (0, []))
            print(f"    {k.replace('_', ' '):22} {frac * wt:5.1f} / {wt:<3} {'; '.join(why)}")
        for url in r["record"].get("source_urls") or []:
            print(f"  Source: {url}")
    return 0


# ---------------------------------------------------------------- merging research

def extract_records(raw):
    """Accept a bare JSON array, an object with a residencies key, or prose with a JSON array inside."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        decoder, data = json.JSONDecoder(), None
        for m in re.finditer(r"\[\s*\{", raw):
            try:
                data, _ = decoder.raw_decode(raw[m.start():])
                break
            except json.JSONDecodeError:
                continue
        if data is None:
            raise SystemExit("No JSON array of residencies found in that file.")
    if isinstance(data, dict):
        data = data.get("residencies", [data])
    return [d for d in data if isinstance(d, dict) and d.get("name")]


def merge(db, incoming, today):
    records = db["residencies"]
    touched, updated, added = set(), [], []
    for new in incoming:
        target = norm(new.get("name"))
        match = None
        for i, old in enumerate(records):
            if i in touched:
                continue
            keys = [norm(old.get("name"))] + [norm(a) for a in old.get("aliases", [])]
            if any(k and (k == target or re.search(r"\b" + re.escape(k) + r"\b", target)) for k in keys):
                match = i
                break
        new["last_updated"] = today.isoformat()
        if match is None:
            records.append(new)
            touched.add(len(records) - 1)
            added.append(new["name"])
        else:
            new.setdefault("aliases", records[match].get("aliases", []))
            records[match] = new
            touched.add(match)
            updated.append(new["name"])
    print(f"Merged research: {len(updated)} updated, {len(added)} added.")
    for n in updated:
        print(f"  updated  {n}")
    for n in added:
        print(f"  added    {n}")


def main():
    ap = argparse.ArgumentParser(description="Screen artist residencies against the client profile.")
    ap.add_argument("--today", help="screen as of YYYY-MM-DD (default: today)")
    ap.add_argument("--explain", metavar="NAME", help="show the full score breakdown for one residency")
    ap.add_argument("--add", metavar="FILE", nargs="+", help="merge research JSON into the database first")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    crit, db = load(CRITERIA_PATH), load(DB_PATH)

    if args.add:
        for path in args.add:
            merge(db, extract_records(Path(path).read_text(encoding="utf-8")), today)
        save(DB_PATH, db)

    rows = screen(db, crit, today)
    if args.explain:
        return explain(rows, args.explain, crit)
    write_reports(rows, crit, today)
    print_console(rows, today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
