# Residency Filter Agent

Two parts that work together.

**The scout** is a Claude Code agent that researches residencies on the web and records verified, sourced facts. It is installed at `~/.claude/agents/residency-scout.md`. Ask Claude Code something like "use the residency scout to check whether Gasworks has a new India call" or "have the residency scout find funded sculpture residencies in Asia".

**The filter** is a Python script that decides fit. It applies the client's hard rules, scores whatever survives, and writes the shortlist. The same facts always give the same ranking, and every point can be traced back to a reason.

## Everyday commands

```
cd ~/Art/agent
python3 residency_filter.py                         # screen everything, write output/shortlist.md
python3 residency_filter.py --explain "l-air"       # why a residency scored what it did
python3 residency_filter.py --add inbox/file.json   # merge new research, then screen
```

## Files

| File | What it is |
|---|---|
| `criteria.json` | Client profile, hard gates, scoring weights and the country table. Edit this to change what the filter wants. |
| `residencies.json` | Every residency checked so far. |
| `inbox/` | Research files, kept after merging as a record of where facts came from. |
| `output/shortlist.md` | The readable report. |
| `output/shortlist.json` | The same results in machine-readable form. |

## The client's rules

**Hard gates.** A residency is disqualified if any of these is confirmed:

- it pays no stipend and no grant
- it is closed to India-based artists
- it is digital or media art only
- it excludes both mixed media and sculpture
- it requires a duo or collective
- it is for established artists only
- it needs more years of practice than the client has

An unknown never disqualifies. It moves the residency to a verify list instead.

**Fit score out of 100** for everything that passes:

| Dimension | Points | What earns them |
|---|---|---|
| Funding strength | 30 | A living stipend beats a production-only grant. Travel, housing, studio and a materials budget add. Fees and costs the artist pays subtract. |
| India access | 20 | India-specific calls score highest, then open international calls. Visa support adds. |
| Country practicality | 15 | Visa friction, travel from India and cost of living for an Indian passport holder. |
| Discipline fit | 15 | Welcomes sculpture, installation and mixed media. Workshops add. A required single material or an off-theme constraint subtracts. |
| Style resonance | 10 | The programme suits surreal, figurative and material work rather than digital or social practice. |
| Emerging fit | 10 | Explicitly for emerging or early-career artists. |

Tiers: Strong fit 75+ · Good fit 60+ · Possible 45+.

## One thing to fill in

`client.years_practising` in `criteria.json` is unknown. Some residencies, such as TOKAS, require a minimum number of years of practice. Until this is filled in, those residencies wait on the verify list.
