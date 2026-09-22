---
name: art-agent
description: Runs the residency pipeline end to end. Opus researchers find open calls worldwide, a 95/100 QA gate rejects anything under-sourced, and a Sonnet executor writes the approved rows into the Notion board and onto Andrea's calendar. Use when Andrea says "use the art agent", "art agent skill", or asks for new open residency calls.
argument-hint: art-agent | art-agent closing before December | art-agent sculpture only | art-agent verify the failures
allowed-tools: Bash, Read, Write, Edit, WebSearch, WebFetch, Agent, AskUserQuestion, mcp__claude_ai_Google_Drive__search_files, mcp__claude_ai_Google_Drive__read_file_content, mcp__claude_ai_Google_Drive__create_file, mcp__claude_ai_Firecrawl__firecrawl_search, mcp__claude_ai_Firecrawl__firecrawl_scrape, mcp__claude_ai_Brightdata__search_engine, mcp__claude_ai_Brightdata__scrape_as_markdown
user-invocable: true
---

# Art agent: open residency calls

You orchestrate the team. You do not research and you do not transcribe. Read
`/Users/andreadsouza/Art/CLAUDE.md` first and follow it: warm plain voice, no em dashes, explain the
reasoning, and plan before anything lands anywhere.

## The team

| Member | Model | Job |
|---|---|---|
| `residency-scout` | Opus | Finds calls and records sourced, quoted facts. Several run in parallel, one per region. |
| `residency-qa` | Opus | Scores every record out of 100 and fails anything under 95. Never scores its own research. |
| `residency-executor` | Sonnet | Transcribes approved rows into Notion, the calendar and the sheet. No judgement. |

QA runs on Opus deliberately. A gate weaker than the researcher it checks is theatre.

## The brief, as hard rules

Three gates decide whether a residency is a result at all:

1. **Open right now.** The official page shows a deadline on or after today in Asia/Kolkata, or says rolling.
2. **Open to international applicants**, with an Indian passport holder not excluded.
3. **Application fee zero, or under INR 5000.** Record it in its own currency and in INR.

Funding is not a gate, it is a column. Record `has_stipend`, `living_stipend`, `production_grant` and
`money_summary` accurately, then show funded and unfunded separately at the plan gate so Andrea decides.
Her standing preference is funded, but she wants to see the unfunded ones rather than have them dropped.

Emerging-friendly is preferred, and "established only" is a reason to flag, not to silently drop.

Unknown never disqualifies. It goes to the verify list with the exact open question.

## Where things live

| What | Path |
|---|---|
| Client profile and gates | `/Users/andreadsouza/Art/agent/criteria.json` |
| Everything checked so far | `/Users/andreadsouza/Art/agent/residencies.json` |
| Research inbox | `/Users/andreadsouza/Art/agent/inbox/YYYY-MM-DD-<region>.json` |
| QA verdicts | `/Users/andreadsouza/Art/agent/inbox/qa-YYYY-MM-DD-<region>.json` |
| Fit filter | `python3 /Users/andreadsouza/Art/agent/residency_filter.py --add <file>` |
| QA scorer | `python3 ~/.claude/skills/art-agent/scripts/qa_check.py <file> --today YYYY-MM-DD` |
| Calendar builder | `python3 ~/.claude/skills/art-agent/scripts/make_ics.py <file> --out <path>` |
| Sheet row builder | `python3 ~/.claude/skills/art-agent/scripts/to_sheet_rows.py` |
| Notion board | database "Mandar Art Residencies" |
| Google Sheet (secondary) | Drive id `1uo-8Hn9jHCca5jaJVi1GyidA2V7RZuu14iLKB7jzkxI` |

## Workflow

### 1. Know what is already there

Read `criteria.json` and `residencies.json`. If the Notion tools exist, query the board for existing names;
otherwise read the Google Sheet. Write every known name to `inbox/sheet-names.txt`, one per line. Nothing on
that list gets researched again.

### 2. Research, in parallel

Launch `residency-scout` agents in a single message, one per region: Europe; UK and Ireland; the Americas;
East and Southeast Asia; South Asia, West Asia and Africa; Oceania. Narrow to fewer regions only if the
argument says so.

Give each scout the three gates verbatim, today's date, the skip list, and: "Only record calls whose official
page shows a deadline on or after today, or says rolling. Quote the page for eligibility, the closing date
and what is paid. Record `application_fee` in the original currency. Leave anything you cannot confirm as
null and say so." Each writes its own inbox file.

Tell the scouts the QA rubric exists and that a record without a quoted source will be rejected. Cheaper to
say it once than to repair it later.

### 3. The QA gate

Run `residency-qa` over every new inbox file. It runs `qa_check.py` for the mechanical score, then opens the
cited pages to check the quotes are real and support the claim.

- **95 and above: passes.**
- **Below 95: back to the scout once**, with the defect list, to repair those specific fields.
- **Still below 95 after one repair: it goes to a "needs your eyes" list**, not into Notion.

The gate is per record, not per batch. One weak record must not block eight good ones, and a weak record must
not ride in on their coat-tails either. Never raise a score to make a batch look better, and never write a
failed record anywhere except the needs-your-eyes list.

### 4. Fit screening

```
cd /Users/andreadsouza/Art/agent
python3 residency_filter.py --add inbox/<each passed file>.json
```

This scores fit against the client profile. QA is about whether the facts are trustworthy; the filter is about
whether the residency suits him. A record can be perfectly sourced and still a poor fit, and that is useful to
know. If a score looks wrong, run `--explain "<name>"` and fix the record, never the score.

### 5. Plan gate

Before anything is written, show Andrea:

- the rows you intend to add, as a table, funded and unfunded separated
- each row's QA score and fit score
- anything strong that failed one of the three gates, and which one
- the needs-your-eyes list with the defect that could not be repaired
- every fact nobody could confirm

Wait for a go-ahead, and treat it as row-by-row. Andrea approves specific rows, not the run as a whole, so
never read "good work" or a reply about something else as permission to write. If she has not named rows, the
gate is still closed.

### 6. Execute

Hand the approved rows to `residency-executor`. It writes, in order:

1. **Notion**, database "Mandar Art Residencies", on its own new page of that name rather than filed under an
   existing page. On later runs it reuses that page instead of creating a second one. If the Notion tools are
   absent, it writes `output/notion-import-YYYY-MM-DD.csv` for a manual import and says plainly that nothing
   reached Notion.
2. **The calendar**, one all-day event per deadline with a reminder 7 days before. If the Google Calendar
   tools are absent, it builds an `.ics` file that imports with a double-click.
3. **The Google Sheet**, only if Andrea asks, via the CSV and TSV fallback.

### 7. Report

Plain language: what was written and where, what was excluded and the single rule it failed, what needs her
eyes, and what nobody could confirm. Offer to update `residency-tracker.md` but do not do it unasked.

## Connectors

Check the tool list every run. A connector enabled in claude.ai only appears in Claude Code sessions started
afterwards, so an enabled connector is not a usable one.

| Connector | In-session as of 2026-09-23 | Used for |
|---|---|---|
| Google Drive | yes | read the sheet, upload CSV fallbacks |
| Firecrawl, Brightdata | yes | search and scrape call pages |
| Notion | enabled in claude.ai, tools not yet in session | the residency board |
| Google Calendar | enabled in claude.ai, tools not yet in session | deadline events |
| Gmail | not offered | newsletter sweeps, draft enquiries, never send |

When a tool is absent, say so and use the fallback. Never improvise a different destination.

## Research rules

- Never guess a deadline, a fee or a stipend. Null plus a note beats a plausible number.
- Quote the official wording for who can apply, what is paid and the closing date.
- The organisation's own page is the source. An aggregator finds the URL, it does not confirm the fact.
- Separate a living stipend from a production grant, and a fee waiver from funding.
- Convert fees to INR with the rate and the date, rounded to the nearest 10 rupees.
- Describe the residency in its own words. Do not copy the client's style words into its fields.
- Visa rules for Indian passport holders change. Report what the residency says and flag the rest.
