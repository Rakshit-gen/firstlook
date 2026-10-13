# firstlook

An on-call agent that takes the first look at an incident. It reads the
alerts, digs through metrics, logs, deploys and runbooks with tools, says
which service the problem starts in and why, and proposes one fix. Nothing
happens until a person says yes.

Built with LangGraph (a state graph with a tool loop, a call budget,
`interrupt()` for approval and a SQLite checkpointer) and LangChain tools and
structured output. The model is Groq by default.

## Quickstart

```
uv tool install git+https://github.com/Rakshit-gen/firstlook
firstlook scenarios
firstlook run bad-deploy                     # rules only without GROQ_API_KEY
GROQ_API_KEY=... firstlook run bad-deploy    # the agent, asks before acting
firstlook eval                               # score every scenario
```

Without a key, `run` and `eval` use a rules-only triager instead of a model,
so everything works offline. The tests never call a model either.

## What a run looks like

`examples/scripted_run.py` runs the real graph on the bad-deploy scenario with
a scripted model (it replays fixed tool calls and a fixed conclusion, so no
key is needed). The tools, the checks and the approval step are real. Its
output, trimmed:

```
## Evidence

- `14:58 UTC payments v2.14.0`
- `TypeError: cannot read property 'last4' of undefined at RefundHandler.tokenize`

## Action

Proposed: roll back payments (back to the previous version).
Approved by demo.
Result: roll back payments (back to the previous version): done, and the alerts cleared.

## How the agent got there (5 tool calls)

1. `dependencies(service='checkout')`
2. `query_metric(service='payments', metric='error_rate')`
3. `recent_deploys(service='payments')`
4. `search_logs(service='payments')`
5. `read_runbook(service='payments')`

## Notes

- evidence not found in any tool answer: 'upstream payments returned 500'
```

The scripted conclusion quotes one line that no tool returned. The checks
drop it and say so. A conclusion with no real evidence left is never acted
on: it becomes an escalation.

## Guard rails

- **Approval.** Any action other than escalate stops the graph with
  `interrupt()`. `run` asks on the terminal, `--approve` says yes up front,
  and `--pause` saves the run to SQLite so someone can `firstlook decide RUN
  yes|no` later. `firstlook waiting` lists paused runs.
- **Evidence.** Every quote in the conclusion has to appear in a tool answer.
- **Budget.** 12 tool calls by default. Repeated identical calls aren't run
  again, and tool answers are capped at 1500 characters.
- **No production access.** Actions go to an executor. In scenarios it plays
  the action against the known answer; in `live` mode it is a dry run that
  only records what it would have done.

## Scenarios

Eight built-in incidents, each a short JSON file with a known answer:

```
bad-deploy           Checkout failing for some customers
cert-expiry          Every login failing at the gateway
db-pool              Orders timing out after a reports release
disk-full            Event ingest dropping events
flag-flip            Cart totals wrong and checkout erroring in Germany
memory-leak          Notification emails delayed
slow-vendor          Store search slow right after a search release
traffic-spike        Slow pages during the flash sale
```

Most have a red herring: a recent deploy to the wrong service, a caller that
alerts louder than the cause, or a cause that isn't in the alerting service's
call path at all.

## How the rules baseline does

`firstlook eval` with no model, on all eight:

```
model: rules
scenario             service cause fix  harmful evidence tools
bad-deploy           yes     yes   yes  -              3     0
cert-expiry          -       -     -    YES            2     0
db-pool              -       -     -    YES            2     0
disk-full            yes     -     -    -              2     0
flag-flip            yes     -     yes  -              3     0
memory-leak          yes     -     -    -              2     0
slow-vendor          yes     yes   yes  -              2     0
traffic-spike        -       yes   -    YES            2     0
solved 2/8, harmful actions 3
```

The rules look for the earliest step change below the alerting services and
blame a deploy if one just landed. That gets the plain bad deploy and the
slow vendor. It can't see a release to a sibling service (db-pool), reads a
traffic drop as a flood (cert-expiry), misses slow climbs (disk-full,
memory-leak), and calls a flag change a deploy. Three of its proposals would
make things worse, like restarting the orders database the runbook says not
to restart. That's the bar for the agent.

Model results aren't in this README: the numbers here only come from runs
that need no API key. Run `firstlook eval --model groq:<model>` to score one
yourself; it makes one investigation per scenario.

## Live mode

```
firstlook live examples/live/firstlook.toml
```

The config names a Prometheus server, one PromQL query per metric (with
`{service}` filled in), the call graph, and JSON-lines files for deploys and
logs. Alerts come from Prometheus's `ALERTS` series. See
[examples/live/firstlook.toml](examples/live/firstlook.toml).

## Options

```
firstlook run SCENARIO [--model rules|groq:<id>] [--approve] [--pause] [-o FILE] [-q]
firstlook live CONFIG  [--model rules|groq:<id>] [--approve] [-o FILE] [-q]
firstlook eval [SCENARIO ...] [--model ...] [--json] [-q]
firstlook decide RUN yes|no [--by NAME]
firstlook waiting
firstlook scenarios
```

The default model is `groq:openai/gpt-oss-120b` when `GROQ_API_KEY` is set.
Paused runs are kept in `~/.firstlook/runs.db` (or `$FIRSTLOOK_DB`, or
`--db`). `eval` exits 1 unless every scenario is solved.

More detail on the graph, tools and checks: [docs/how-it-works.md](docs/how-it-works.md).

## Measured vs Claimed

| Claim | Value | How measured | Date |
|---|---|---|---|
| Rules baseline | 2 of 8 solved, 3 harmful | `firstlook eval` with no key | 2026-10-13 |
| Rules eval time | 0.70 s for all 8 scenarios | wall clock, best of 3, Apple M4, Python 3.11 | 2026-10-13 |
| Tests | 90, no network or API calls | `uv run pytest` | 2026-10-13 |

## Status

Works: everything above. The agent has only been run with a scripted model
here; there are no live model results yet.

Not done: executors that act on real systems (by design for now), log
backends other than a JSON-lines file, and alert thresholds in live mode
(firstlook shows that an alert fired, not its value).
