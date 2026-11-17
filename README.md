# btcmake-fun

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/faturahmanagus3/btcmake-fun/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/faturahmanagus3/btcmake-fun/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A deterministic cbBTC trading bot for the `agent-fun/bars-replay/v1` protocol, written in stdlib-only Python 3.13. It buys stretched dips below the 360-bar simple moving average once a dip has stabilised and started to bounce, sells when the price reverts to the average, and skips dips whose average is itself collapsing (a crash in progress, not a dip). On the competition's frozen dev window it nets +$13.34 over four round trips with a 0.72% maximum drawdown. All arithmetic is integer-only — no floats, no clock, no randomness — so two runs on the same bars produce byte-identical replies.

## Run it

```sh
python3 -P -s main.py
# The harness feeds it NDJSON on stdin (a hello, then one batch per minute)
# and reads exactly one JSON reply per batch on stdout.
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=dontol&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
