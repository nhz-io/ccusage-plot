#!/usr/bin/env python3
"""Plot Claude Code usage data by reading local conversation logs directly."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# -- Theme colors --
BG_DARK = "#1a1a2e"
BG_AXES = "#16213e"
BORDER = "#2a2a4a"
TEXT = "#e0e0e0"
TEXT_DIM = "#8888aa"
GRID = "#2a2a4a"

COLORS = {
    "inputTokens": "#00d4aa",
    "outputTokens": "#ff8c42",
    "cacheCreateTokens": "#aa55ff",
    "cacheReadTokens": "#ff3366",
    "totalTokens": "#00d4ff",
    "costUSD": "#ffdd00",
}

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Chart definitions: (title, key, is_currency)
CHARTS = [
    ("Input Tokens", "inputTokens", False),
    ("Output Tokens", "outputTokens", False),
    ("Cache Create Tokens", "cacheCreateTokens", False),
    ("Cache Read Tokens", "cacheReadTokens", False),
    ("Total Tokens", "totalTokens", False),
    ("Cost (USD)", "costUSD", True),
]


def human_format(value, is_currency=False):
    prefix = "$" if is_currency else ""
    for suffix, threshold, fmt in [
        ("B", 1e9, ".2f"),
        ("M", 1e6, ".2f"),
        ("K", 1e3, ".1f"),
    ]:
        if abs(value) >= threshold:
            formatted = f"{value / threshold:{fmt}}"
            if "." in formatted:
                formatted = formatted.rstrip("0").rstrip(".")
            return f"{prefix}{formatted}{suffix}"
    if is_currency:
        return f"${value:,.2f}"
    return f"{int(value)}"


def make_formatter(is_currency):
    return ticker.FuncFormatter(lambda v, _: human_format(v, is_currency))


def parse_period(period_str):
    m = re.fullmatch(r"(\d+)\s*([hdwm])", period_str.strip().lower())
    if not m:
        print(
            f"Error: invalid period '{period_str}'. Use e.g. 6h, 3d, 1w, 2m",
            file=sys.stderr,
        )
        sys.exit(1)
    value, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)
    elif unit == "m":
        return timedelta(days=value * 30)


# Approximate cost per token by model (USD)
# input, output, cache_create, cache_read
MODEL_PRICING = {
    "claude-opus-4-6": (15 / 1e6, 75 / 1e6, 18.75 / 1e6, 1.5 / 1e6),
    "claude-opus-4-5-20251101": (15 / 1e6, 75 / 1e6, 18.75 / 1e6, 1.5 / 1e6),
    "claude-sonnet-4-6": (3 / 1e6, 15 / 1e6, 3.75 / 1e6, 0.3 / 1e6),
    "claude-sonnet-4-5-20250929": (3 / 1e6, 15 / 1e6, 3.75 / 1e6, 0.3 / 1e6),
    "claude-haiku-4-5-20251001": (0.8 / 1e6, 4 / 1e6, 1 / 1e6, 0.08 / 1e6),
}
DEFAULT_PRICING = (3 / 1e6, 15 / 1e6, 3.75 / 1e6, 0.3 / 1e6)


def estimate_cost(model, input_t, output_t, cache_create_t, cache_read_t):
    pricing = DEFAULT_PRICING
    for prefix, p in MODEL_PRICING.items():
        if model and model.startswith(prefix.rsplit("-", 1)[0]):
            pricing = p
            break
    pi, po, pcc, pcr = pricing
    return input_t * pi + output_t * po + cache_create_t * pcc + cache_read_t * pcr


def load_events(cutoff):
    """Read conversation JSONL files and extract assistant message usage data."""
    events = []
    if not PROJECTS_DIR.exists():
        print(f"Error: projects dir not found: {PROJECTS_DIR}", file=sys.stderr)
        sys.exit(1)

    jsonl_files = list(PROJECTS_DIR.rglob("*.jsonl"))
    print(f"Scanning {len(jsonl_files)} conversation files...", file=sys.stderr)

    for path in jsonl_files:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("type") != "assistant":
                        continue

                    ts_raw = obj.get("timestamp")
                    if not ts_raw:
                        continue
                    # timestamp can be ISO string or unix millis
                    if isinstance(ts_raw, (int, float)):
                        ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)
                    else:
                        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))

                    if ts < cutoff:
                        continue

                    msg = obj.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage:
                        continue

                    model = msg.get("model", "unknown")
                    input_t = usage.get("input_tokens", 0) or 0
                    output_t = usage.get("output_tokens", 0) or 0
                    cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                    cache_read = usage.get("cache_read_input_tokens", 0) or 0

                    events.append(
                        {
                            "timestamp": ts,
                            "model": model,
                            "inputTokens": input_t,
                            "outputTokens": output_t,
                            "cacheCreateTokens": cache_create,
                            "cacheReadTokens": cache_read,
                            "totalTokens": input_t
                            + output_t
                            + cache_create
                            + cache_read,
                            "costUSD": estimate_cost(
                                model, input_t, output_t, cache_create, cache_read
                            ),
                        }
                    )
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    events.sort(key=lambda e: e["timestamp"])
    return events


def apply_theme():
    plt.rcParams.update(
        {
            "figure.facecolor": BG_DARK,
            "axes.facecolor": BG_AXES,
            "axes.edgecolor": BORDER,
            "text.color": TEXT,
            "xtick.color": TEXT_DIM,
            "ytick.color": TEXT_DIM,
            "grid.color": GRID,
            "grid.alpha": 0.4,
            "font.family": "monospace",
        }
    )


def style_axes(ax):
    ax.set_facecolor(BG_AXES)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(1.5)
    ax.tick_params(colors=TEXT_DIM, labelsize=9)


TZ_ALIASES = {
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "PT": "America/Los_Angeles",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "MT": "America/Denver",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "CT": "America/Chicago",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "ET": "America/New_York",
    "GMT": "UTC",
    "UTC": "UTC",
    "BST": "Europe/London",
    "CET": "Europe/Berlin",
    "CEST": "Europe/Berlin",
    "IST": "Asia/Kolkata",
    "JST": "Asia/Tokyo",
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
}


def resolve_tz(tz_str):
    """Resolve a timezone string (alias or IANA name) to a ZoneInfo object."""
    if tz_str is None:
        return None
    key = tz_str.upper()
    if key in TZ_ALIASES:
        return ZoneInfo(TZ_ALIASES[key])
    try:
        return ZoneInfo(tz_str)
    except KeyError:
        print(
            f"Error: unknown timezone '{tz_str}'. Use e.g. PST, EST, UTC, Asia/Tokyo",
            file=sys.stderr,
        )
        sys.exit(1)

def get_user_plan():
    """Read the subscription type from Claude Code credentials file."""
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if creds_path.exists():
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Check inside claudeAiOauth
                if not plan and "claudeAiOauth" in data:
                    plan = data["claudeAiOauth"].get("subscriptionType")
                
                if plan:
                    return str(plan).upper()
        except Exception:
            pass
    return "Free" # A generic fallback - as Free users can't use the CLI I don't think this is necessary.

HIGHLIGHT_COLOR = "#ffffff"
HIGHLIGHT_ALPHA = 0.06


def parse_highlight(highlight_str):
    """Parse '5-11' or '5:00-11:00' into (start_hour, end_hour) as floats."""
    m = re.fullmatch(
        r"(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?", highlight_str.strip()
    )
    if not m:
        print(
            f"Error: invalid highlight '{highlight_str}'. Use e.g. 5-11 or 5:00-11:30",
            file=sys.stderr,
        )
        sys.exit(1)
    sh = int(m.group(1)) + (int(m.group(2)) / 60 if m.group(2) else 0)
    eh = int(m.group(3)) + (int(m.group(4)) / 60 if m.group(4) else 0)
    return sh, eh


def add_highlight_bands(ax, timestamps, start_hour, end_hour, tz):
    """Add vertical shaded bands for each day's highlight window, clipped to current xlim."""
    if not timestamps:
        return
    display_tz = tz if tz else timezone.utc

    # Save current x-axis limits before adding spans
    xlim = ax.get_xlim()

    dates_seen = set()
    for ts in timestamps:
        dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(display_tz)
        dates_seen.add(dt.date())

    for d in sorted(dates_seen):
        band_start = datetime(
            d.year,
            d.month,
            d.day,
            int(start_hour),
            int((start_hour % 1) * 60),
            tzinfo=display_tz,
        )
        band_end = datetime(
            d.year,
            d.month,
            d.day,
            int(end_hour),
            int((end_hour % 1) * 60),
            tzinfo=display_tz,
        )
        ax.axvspan(
            band_start, band_end, alpha=HIGHLIGHT_ALPHA, color=HIGHLIGHT_COLOR, zorder=1
        )

    # Restore x-axis limits so highlight bands don't expand the view
    ax.set_xlim(xlim)


def plot_timeline(events, period_str, output_path, tz=None, highlight=None):
    apply_theme()

    if tz:
        timestamps = [e["timestamp"].astimezone(tz) for e in events]
        tz_label = str(tz)
        # Shorten IANA names for display
        for alias, iana in TZ_ALIASES.items():
            if iana == str(tz):
                tz_label = alias
                break
    else:
        timestamps = [e["timestamp"] for e in events]
        tz_label = "UTC"

    fig, axes = plt.subplots(4, 2, figsize=(18, 16))
    axes = axes.flatten()

    total_cost = sum(e["costUSD"] for e in events)
    total_reqs = len(events)

    # Actual date range from data
    display_tz = tz if tz else timezone.utc
    first_ts = (
        timestamps[0]
        if timestamps[0].tzinfo
        else timestamps[0].replace(tzinfo=display_tz)
    )
    last_ts = (
        timestamps[-1]
        if timestamps[-1].tzinfo
        else timestamps[-1].replace(tzinfo=display_tz)
    )
    date_range_str = f"{first_ts.strftime('%b %d %H:%M')} \u2013 {last_ts.strftime('%b %d %H:%M')} {tz_label}"

    # Get the plan name
    plan_name = get_user_plan()

    fig.suptitle(
        f"Claude Code Usage Dashboard | Plan: {plan_name}",
        fontsize=18, fontweight="bold", color="#ffffff", y=0.99,
    )
    subtitle_parts = [
        date_range_str,
        f"{total_reqs} API calls",
        f"${total_cost:.2f} total",
    ]
    if highlight:
        subtitle_parts.append(
            f"Highlight: {int(highlight[0])}:00\u2013{int(highlight[1])}:00"
        )
    fig.text(
        0.5,
        0.96,
        "  |  ".join(subtitle_parts),
        ha="center",
        fontsize=11,
        color=TEXT_DIM,
    )

    for idx, (title, key, is_currency) in enumerate(CHARTS):
        ax = axes[idx]
        style_axes(ax)

        values = [e[key] for e in events]
        color = COLORS[key]

        # Scatter for individual requests
        ax.scatter(
            timestamps,
            values,
            color=color,
            alpha=0.5,
            s=12,
            zorder=3,
            edgecolors="none",
        )

        # Cumulative line on secondary y-axis
        cumulative = []
        running = 0
        for v in values:
            running += v
            cumulative.append(running)

        ax2 = ax.twinx()
        ax2.plot(timestamps, cumulative, color=color, alpha=0.8, linewidth=2, zorder=4)
        ax2.fill_between(timestamps, cumulative, alpha=0.06, color=color, zorder=2)
        ax2.yaxis.set_major_formatter(make_formatter(is_currency))
        ax2.tick_params(colors=TEXT_DIM, labelsize=8)
        ax2.spines["right"].set_color(BORDER)

        if cumulative:
            total_val = cumulative[-1]
            ax2.annotate(
                f"Total: {human_format(total_val, is_currency)}",
                xy=(timestamps[-1], total_val),
                xytext=(-10, 8),
                textcoords="offset points",
                fontsize=10,
                color=color,
                fontweight="bold",
                ha="right",
                va="bottom",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=BG_AXES,
                    edgecolor=color,
                    alpha=0.8,
                ),
            )

        ax.set_title(title, fontsize=13, fontweight="bold", color=TEXT, pad=10)
        ax.yaxis.set_major_formatter(make_formatter(is_currency))
        ax.set_ylabel("per call", fontsize=8, color=TEXT_DIM)
        ax2.set_ylabel("cumulative", fontsize=8, color=TEXT_DIM)
        ax.grid(True, alpha=0.2, color=GRID)

        if highlight:
            add_highlight_bands(ax, timestamps, highlight[0], highlight[1], tz)

        # Adaptive x-axis
        span_h = (
            (timestamps[-1] - timestamps[0]).total_seconds() / 3600
            if len(timestamps) > 1
            else 1
        )
        fmt_tz = tz if tz else timezone.utc
        if span_h <= 6:
            ax.xaxis.set_major_locator(mdates.HourLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=fmt_tz))
        elif span_h <= 24:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=fmt_tz))
        elif span_h <= 24 * 3:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M", tz=fmt_tz))
        elif span_h <= 24 * 7:
            ax.xaxis.set_major_locator(mdates.DayLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d", tz=fmt_tz))
        elif span_h <= 24 * 60:
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d", tz=fmt_tz))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y", tz=fmt_tz))
        ax.tick_params(axis="x", rotation=0, labelsize=8)

    # Cost by model panel
    ax_summary = axes[len(CHARTS)]
    style_axes(ax_summary)
    model_costs = {}
    model_reqs = {}
    for e in events:
        m = e["model"]
        model_costs[m] = model_costs.get(m, 0) + e["costUSD"]
        model_reqs[m] = model_reqs.get(m, 0) + 1

    models = sorted(model_costs.keys(), key=lambda m: model_costs[m], reverse=True)
    bar_colors = list(COLORS.values())
    y_pos = list(range(len(models)))
    costs = [model_costs[m] for m in models]
    short_names = [m.replace("claude-", "").split("-2")[0] for m in models]
    c = [bar_colors[i % len(bar_colors)] for i in range(len(models))]

    bars = ax_summary.barh(y_pos, costs, color=c, alpha=0.85, height=0.5, zorder=3)
    for bar, m in zip(bars, models):
        val = model_costs[m]
        reqs = model_reqs[m]
        ax_summary.text(
            bar.get_width() + max(costs) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"${val:.2f} ({reqs} calls)",
            va="center",
            ha="left",
            fontsize=10,
            color=TEXT,
            fontweight="bold",
        )

    ax_summary.set_yticks(y_pos)
    ax_summary.set_yticklabels(short_names, fontsize=10)
    ax_summary.set_title(
        "Cost by Model", fontsize=13, fontweight="bold", color=TEXT, pad=10
    )
    ax_summary.xaxis.set_major_formatter(make_formatter(True))
    ax_summary.grid(True, axis="x", alpha=0.3, color=GRID)
    ax_summary.invert_yaxis()
    if costs and max(costs) > 0:
        ax_summary.set_xlim(0, max(costs) * 1.4)

    # Token breakdown panel
    ax_breakdown = axes[len(CHARTS) + 1]
    style_axes(ax_breakdown)
    token_categories = [
        ("Input", "inputTokens", COLORS["inputTokens"]),
        ("Output", "outputTokens", COLORS["outputTokens"]),
        ("Cache Create", "cacheCreateTokens", COLORS["cacheCreateTokens"]),
        ("Cache Read", "cacheReadTokens", COLORS["cacheReadTokens"]),
    ]
    cat_labels = [c[0] for c in token_categories]
    cat_totals = [sum(e[c[1]] for e in events) for c in token_categories]
    cat_colors = [c[2] for c in token_categories]
    y_pos_bd = list(range(len(cat_labels)))

    bars_bd = ax_breakdown.barh(
        y_pos_bd, cat_totals, color=cat_colors, alpha=0.85, height=0.5, zorder=3
    )
    for bar, total in zip(bars_bd, cat_totals):
        if total > 0:
            pct = total / sum(cat_totals) * 100 if sum(cat_totals) > 0 else 0
            ax_breakdown.text(
                bar.get_width() + max(cat_totals) * 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{human_format(total)} ({pct:.1f}%)",
                va="center",
                ha="left",
                fontsize=10,
                color=TEXT,
                fontweight="bold",
            )

    ax_breakdown.set_yticks(y_pos_bd)
    ax_breakdown.set_yticklabels(cat_labels, fontsize=10)
    ax_breakdown.set_title(
        "Token Breakdown", fontsize=13, fontweight="bold", color=TEXT, pad=10
    )
    ax_breakdown.xaxis.set_major_formatter(make_formatter(False))
    ax_breakdown.grid(True, axis="x", alpha=0.3, color=GRID)
    ax_breakdown.invert_yaxis()
    if cat_totals and max(cat_totals) > 0:
        ax_breakdown.set_xlim(0, max(cat_totals) * 1.35)

    # Hide unused axes slots
    for i in range(len(CHARTS) + 2, len(axes)):
        axes[i].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_DARK)
    plt.close()
    print(f"Saved: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Plot Claude Code usage from local conversation logs"
    )
    parser.add_argument(
        "-p",
        "--period",
        default="24h",
        help="Time period to display, e.g. 6h, 3d, 1w, 2m (default: 24h)",
    )
    parser.add_argument(
        "-o", "--output", help="Output PNG path (default: ccusage_{period}.png)"
    )
    parser.add_argument(
        "--tz",
        default=None,
        help="Timezone for x-axis, e.g. PST, EST, UTC, Asia/Tokyo (default: local)",
    )
    parser.add_argument(
        "--highlight",
        default=None,
        help="Highlight a daily time window, e.g. 5-11 or 5:00-11:30 (uses --tz)",
    )
    args = parser.parse_args()

    delta = parse_period(args.period)
    cutoff = datetime.now(timezone.utc) - delta

    print(f"Reading conversation logs from {PROJECTS_DIR} ...", file=sys.stderr)
    events = load_events(cutoff)

    if not events:
        print(f"No API calls found in the past {args.period}.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(events)} API calls in the past {args.period}.", file=sys.stderr)

    tz = resolve_tz(args.tz) if args.tz else None

    output_path = args.output or f"ccusage_{args.period}.png"
    highlight = parse_highlight(args.highlight) if args.highlight else None

    plot_timeline(events, args.period, output_path, tz=tz, highlight=highlight)


if __name__ == "__main__":
    main()
