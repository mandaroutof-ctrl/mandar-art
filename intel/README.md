# Intel · the Vitrine

The research record behind Loplop, Andrea's art-management assistant. Theme: surrealism and mixed
media. Every file is dated. Treat each one as a starting point, and re-verify anything
time-sensitive before acting on it.

## Files

| File | What it answers | Last researched | Refresh when |
|---|---|---|---|
| [legal-policy.md](legal-policy.md) | Copyright and moral rights in India, collage and appropriation, surrealist estates, AI and copyright, GST and income tax, shipping and customs, materials law, platforms and data | 2026-09-10 | Older than 30 days, or before any legal decision |
| [deal-structures.md](deal-structures.md) | Manager, gallery, commission, licensing and fashion collab terms, the magazine, opportunity vetting and scams, pricing, sales admin, funding map, operating blueprint | 2026-09-10 | Older than 90 days. Deadlines every time |
| [market-and-news.md](market-and-news.md) | Global market, fairs and biennales, India and South Asia, recent headlines, calendar to December 2027, publication watchlist | 2026-09-10 | News older than 7 days |
| [surrealism-mixed-media.md](surrealism-mixed-media.md) | Surrealism now, contemporary and South Asian practitioners, typography meets surrealism, materials, recent interviews, fashion crossovers, open calls | 2026-09-10 | Older than 30 days |
| [online-discourse.md](online-discourse.md) | What artists say on Reddit and elsewhere, the manager question, scams, the reality of process reels, voices to follow | 2026-09-10 | Older than 30 days |
| [sources.md](sources.md) | One consolidated watchlist for briefings | 2026-09-10 | When a source dies or a better one appears |
| [briefings/](briefings/) | Dated news briefings, one file per run | Per file | Each run starts where the last one ended |

## Using Loplop

Loplop is a Claude Code agent defined at `~/.claude/agents/loplop.md`, available in every session.
Call it with `@agent-loplop` followed by the request, or ask in plain words ("ask Loplop to...").

It picks a working mode from the request. Naming the mode is optional, and gets a fixed output format.

| Mode | For | Try |
|---|---|---|
| Frottage | Legal, policy and contract review | "Review this consignment agreement" |
| Collage | Blueprints and strategy | "Build a six-month plan for the signature series" |
| Exquisite Corpse | Collaborations and deal structures | "Structure a t-shirt collaboration with a fashion label" |
| Decalcomania | Scouting and vetting opportunities | "Is this open call legitimate?" |
| Objet Trouvé | News, discourse and interview briefings | "Brief me on the last two weeks" |
| Automatism | Drafting pitches, statements, applications | "Draft a pitch email to a fashion label" |

Where things go: drafts in `~/Art/drafts/`, plans in `~/Art/strategy/`, briefings in
`briefings/`. Loplop never sends anything. Its own working memory, meaning how Andrea likes things
done, lives at `~/.claude/agent-memory/loplop/`. Project facts stay here in `~/Art`.
