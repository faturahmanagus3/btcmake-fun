"""Dip-buying bot for the cbBTC bars-replay race (agent-fun/bars-replay/v1).

The market model makes trading expensive: a full-size round trip on cbBTC
costs roughly 35 bps in fees, modelled slippage and constant-product pool
impact, while a typical minute moves only a few bps. Fast systems bleed
their stake to those costs (the house's own EMA-cross bot loses heavily on
the dev window). This bot therefore trades only the day's stretched dips:

  Entry: the close sits at least DIP_BPS under its TREND_N-bar simple
  moving average, the dip has stopped falling (the lowest close of the
  last LOW_N bars is at least STAB_N bars old), and the close has bounced
  BOUNCE_BPS off that low. It buys with all the cash it holds. A dip is
  skipped when the average itself has fallen more than MAX_FALL_BPS over
  the last SLOPE_BACK bars: that is a crash in progress, not a dip.

  Exit: the close returns to the moving average (the dip has reverted),
  or a hard stop HARD_STOP_BPS under the entry reference close fires --
  the guard against a dip that is really a crash beginning.

  Fallback: if no dip trade has happened by FALLBACK_SEQ and the close is
  above the moving average, it buys once and holds, so a day that only
  trends up still makes its required trade.

On the dev window this makes four round trips, each a small reversion win,
with a maximum drawdown under 1%: capital preservation first, because the
race pays the ten best net PnLs among the entries that clear its
guardrails, whatever their sign.

All arithmetic is on integers (prices are integers at the symbol's price
scale), so two runs on the same bars produce byte-identical replies: no
floats, no clock, no randomness, no files, no environment.

Run as the grader runs it: python3 -P -s /bot/main.py with PYTHONHASHSEED=0.
-P leaves this file's directory off sys.path, so vendor/ is added by hand.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (see the module docstring) ---
TREND_N = 360         # the moving average the dip is measured against
DIP_BPS = 50          # enter a dip at least this many bps under the average
LOW_N = 120           # the running low is taken over the last LOW_N closes
BOUNCE_BPS = 10       # the close must be this many bps above that low
STAB_N = 10           # and the low must be at least this many bars old
HARD_STOP_BPS = 150   # exit if the close falls this many bps under the entry reference
MAX_FALL_BPS = 40     # skip a dip when the average itself fell more than this over SLOPE_BACK bars
SLOPE_BACK = 120      # lookback for that falling-average check
FALLBACK_SEQ = 900    # if never held by this batch, buy above the average and hold
LAST_ENTRY_SEQ = 1395  # no new entries decided on or after this batch
BUY_SLIP_BPS = 200    # max_slippage_bps on buys: slippage + own impact + a gap allowance
SELL_SLIP_BPS = 600   # max_slippage_bps on sells: wide, an exit should not be blocked

MIN_NOTIONAL = 1_000_000  # fees.min_notional_quote_units from hello (1 USDC)


class Strategy:
    """The bot's memory: the closes seen, and the open trade's reference points."""

    def __init__(self):
        self.closes = []        # every close seen, oldest first (ints, price scale)
        self.entry_ref = None   # the close at the entry decision, while a position is open
        self.pending_ref = None  # the close at a buy decision not yet seen filled
        self.ever_held = False  # a position has been seen at least once

    def sma_sum(self, back=0):
        """Sum of the TREND_N closes ending `back` bars before the latest, or None if too few."""
        if len(self.closes) < TREND_N + back:
            return None
        end = len(self.closes) - back
        return sum(self.closes[end - TREND_N:end])

    def dip_signal(self, close, seq):
        """A stretched dip under the average that has stopped falling (see docstring)."""
        s = self.sma_sum()
        if s is None or len(self.closes) < LOW_N:
            return False
        # In a dip when close < SMA * (1 - DIP_BPS/10000), cross-multiplied to integers.
        if close * 10_000 * TREND_N >= s * (10_000 - DIP_BPS):
            # Not in a dip: the fallback keeps an uptrend day traded.
            return not self.ever_held and seq >= FALLBACK_SEQ and close * TREND_N > s
        if MAX_FALL_BPS != 0:
            then = self.sma_sum(back=SLOPE_BACK)
            if then is not None and s * 10_000 < then * (10_000 - MAX_FALL_BPS):
                return False  # the average itself is collapsing: a crash, not a dip
        window = self.closes[-LOW_N:]
        low = min(window)
        age = 0
        for j in range(len(window) - 1, -1, -1):
            if window[j] == low:
                age = len(window) - 1 - j
                break
        if age < STAB_N:
            return False
        # Bounced when close >= low * (1 + BOUNCE_BPS/10000).
        return close * 10_000 >= low * (10_000 + BOUNCE_BPS)

    def exit_signal(self, close):
        """The dip has reverted to the average, or the hard stop has fired."""
        s = self.sma_sum()
        if s is not None and close * TREND_N >= s:
            return True
        if self.entry_ref is not None:
            return (self.entry_ref - close) * 10_000 > HARD_STOP_BPS * self.entry_ref
        return False

    def decide(self, state, batch):
        bar = None
        for b in batch["bars"]:
            if b["symbol"] == SYMBOL:
                bar = b
                break
        if bar is None:
            return []
        close = int(bar["c"])
        self.closes.append(close)
        holding = state.positions.get(SYMBOL)

        if holding is not None:
            self.ever_held = True
            if self.entry_ref is None:
                # First batch that shows the position: adopt the decision close.
                self.entry_ref = self.pending_ref if self.pending_ref is not None else close
            if self.exit_signal(close):
                return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                         "max_slippage_bps": SELL_SLIP_BPS}]
            return []

        # Flat: forget any stale reference, then look for a dip (or the fallback).
        self.entry_ref = None
        if state.warming_up or state.seq > LAST_ENTRY_SEQ:
            return []
        if not self.dip_signal(close, state.seq):
            return []
        notional = state.cash
        room = state.weight_room(SYMBOL)
        if room < notional:
            notional = room
        if notional < MIN_NOTIONAL:
            return []
        self.pending_ref = close
        return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": notional,
                 "max_slippage_bps": BUY_SLIP_BPS}]


_strategy = Strategy()


def on_hello(state):
    global _strategy
    _strategy = Strategy()


def on_batch(state, batch):
    return _strategy.decide(state, batch)


if __name__ == "__main__":
    makefun_bars.run(on_batch, on_hello=on_hello)
