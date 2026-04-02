# ccusage-plot

A dark-themed CLI tool that visualizes your Claude Code token usage and costs by reading local conversation logs (`~/.claude/projects/**/*.jsonl`).

Generates a PNG dashboard with per-call scatter plots, cumulative lines, cost-by-model breakdown, and token category breakdown.

## Quick Start

```bash
python3 -m pip install matplotlib && curl -s https://raw.githubusercontent.com/nhz-io/ccusage-plot/main/ccusage_plot.py | python3 - -p 7d --tz PST
```

## Requirements

- Python 3.9+
- `matplotlib`

```bash
pip install matplotlib
```

## Usage

```bash
python ccusage_plot.py [options]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-p`, `--period` | Time period to display: `6h`, `3d`, `1w`, `2m`, etc. | `24h` |
| `-o`, `--output` | Output PNG file path | `ccusage_{period}.png` |
| `--tz` | Timezone for x-axis (`PST`, `EST`, `UTC`, `Asia/Tokyo`, etc.) | UTC |
| `--highlight` | Highlight a daily time window, e.g. `5-11` or `5:00-11:30` | none |

### Examples

```bash
# Last 24 hours (default)
python ccusage_plot.py

# Last 7 days in Pacific time
python ccusage_plot.py -p 7d --tz PST

# Last 2 weeks, highlight working hours, custom output
python ccusage_plot.py -p 2w --tz EST --highlight 9-17 -o usage.png

# Last 3 months
python ccusage_plot.py -p 3m
```

## Charts

The output PNG contains 8 panels:

1. **Input Tokens** — per-call scatter + cumulative line
2. **Output Tokens** — per-call scatter + cumulative line
3. **Cache Create Tokens** — per-call scatter + cumulative line
4. **Cache Read Tokens** — per-call scatter + cumulative line
5. **Total Tokens** — per-call scatter + cumulative line
6. **Cost (USD)** — estimated cost per call + cumulative
7. **Cost by Model** — horizontal bar chart with per-model totals
8. **Token Breakdown** — horizontal bar chart by token category

## Supported Models

Cost estimation uses published pricing for:

- Claude Opus 4.6
- Claude Sonnet 4.6
- Claude Haiku 4.5

Unknown models fall back to Sonnet-tier pricing.

## License

MIT
