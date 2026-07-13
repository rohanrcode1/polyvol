# Polymarket Volatility Research: Complete Index

**Everything you need to understand and reproduce this research.**

---

## Your Files (Click to Start)

### 📄 Reading (Start Here)

| File | Purpose | Time | Read If... |
|------|---------|------|-----------|
| **[README.md](README.md)** | GitHub landing page & quick summary | 10 min | You want the overview first |
| **[EXECUTIVE_SUMMARY.txt](EXECUTIVE_SUMMARY.txt)** | One-page summary (print-friendly) | 5 min | You need a quick reference |
| **[VISUAL_SUMMARY.md](VISUAL_SUMMARY.md)** | Infographic-style findings | 12 min | You're a visual learner |
| **[RESEARCH_MEMO.md](RESEARCH_MEMO.md)** | Full detailed research paper | 25-30 min | You want the complete story |

### 💻 Code & Data

| File | Purpose | Platform | Use If... |
|------|---------|----------|-----------|
| **[polyvol](polyvol)** | Complete research framework | Python 3.11+ | You want to reproduce results |
| **[edge_economics.py](edge_economics.py)** | Economic quantification backtest | Python 3.11+ | You want to run one key script |

### 🛠️ Setup & Configuration

| File | Purpose | Use If... |
|------|---------|-----------|
| **[INDEX.md](INDEX.md)** | Navigation & guide | You're lost |

---

## Recommended Reading Order

### ⚡ Quick Path (15 minutes)
1. **EXECUTIVE_SUMMARY.txt** — Get the verdict
2. **VISUAL_SUMMARY.md** — See the evidence visually
3. **README.md** — Understand the implications

### 🔬 Full Research Path (45 minutes)
1. **README.md** — Get context
2. **RESEARCH_MEMO.md** — Read the complete story
3. **VISUAL_SUMMARY.md** — Review the findings visually

### 🧑‍💻 Technical Path (2+ hours)
1. **RESEARCH_MEMO.md** (methodology section)
2. Clone repo
3. Follow the code walkthrough
4. Run the scripts yourself
5. **edge_economics.py** — Run the final backtest

---

## What Each File Contains

### README.md
**GitHub landing page**

- What the research is about
- Key findings (table format)
- Why it matters
- How to read it
- How to run the code
- Caveats and limitations

→ **Use this**: To understand what the research is and where to start

---

### EXECUTIVE_SUMMARY.txt
**Print-friendly one-page summary.**

Contains:
- Research question
- Methodology (bullet points)
- Results (key statistics)
- The mechanism of why it doesn't work
- Confidence level
- Implications for different audiences

→ **Use this**: For quick reference or to print

→ **Length**: 5 minutes to read

→ **Best for**: People who want the answer before the story

---

### VISUAL_SUMMARY.md
**Infographic-style findings with diagrams and heat maps.**

Contains:
- The research arc timeline
- The strategy visually explained
- The plot twist (reversion exists but uncapturable)
- The fee moat diagram
- Statistical results at a glance
- Q&A format answers
- Lessons for traders, researchers, designers

→ **Use this**: If you think visually

→ **Length**: 12 minutes to read

---

### RESEARCH_MEMO.md
**Complete research paper**

Contains:
- Executive summary
- Full table of contents
- Setup (what are prediction markets?)
- Hypothesis (why this seemed possible)
- Theory (why it shouldn't work)
- All four experiments with results
- The plot twist (reversion found)
- Forensic analysis (what the reversion really is)
- Fee moat explanation
- Implications and conclusions
- Tools used (all documented)
- References

→ **Use this**: For the complete, detailed story

→ **Length**: 25-30 minutes to read

---

### polyvol_v5.zip
**Complete Python research framework.**

Inside:
- `polyvol/` — Core library
  - `fees.py` — Polymarket fee model
  - `synthetic.py` — Martingale generator (20,000 markets)
  - `strategy.py` — Entry/hedge engine
  - `backtest.py` — Grid search and analytics
  - `reconstruct.py` — Trade path reconstruction
  - `polymarket_api.py` — Free API clients
  - `strategy_bbo.py` — Order-book-aware execution

- `scripts/` — Experiment runners
  - `run_synthetic.py` — Null model test
  - `run_real_backtest.py` — Polymarket API backtest
  - `mean_reversion_test.py` — Autocorrelation test
  - `bbo_mid_reversion.py` — Quote test
  - `spot_lag_test.py` — Book-to-spot analysis
  - `edge_economics.py` — Economic backtest

- `output/` — Sample results (CSVs, PNGs)

→ **Use this**: To reproduce every result

→ **Requirements**: Python 3.11+, pandas, numpy, scipy, matplotlib

→ **Data**: All free (Polymarket APIs, HuggingFace dataset)

→ **Time to run**: ~30 minutes for full analysis

---

### edge_economics.py
**Standalone backtest at real executable prices.**

Highlighted script from the framework. Tests:
- **Fade strategy**: Buy dipped side, exit at bid after hold
- **Spotmom strategy**: Trade spot momentum with 1s latency

Both with:
- Real bid/ask quotes
- Real executable sizes
- Taker fees (full cost)
- Clustered statistical tests
- Walk-forward validation (first half vs. second half)

→ **Use this**: To understand economic quantification

→ **Run standalone**: `python edge_economics.py fade --bbo <path>`

→ **Lines**: ~350

---

## How to Use These Files

### For Reading/Understanding
1. Start with **EXECUTIVE_SUMMARY.txt** (5 min)
2. Then **VISUAL_SUMMARY.md** (12 min)
3. If interested, **RESEARCH_MEMO.md** (25 min)
4. **README.md** for context and links

### For Reproducing Results
1. Clone the repository
2. Install requirements: `pip install pandas numpy scipy matplotlib`
3. Run **scripts/run_synthetic.py** (null model test)
4. Run **scripts/mean_reversion_test.py** (signal test)
5. Run **scripts/edge_economics.py** (economic test)




---

## File Relationships & Reading Paths

```
START HERE
    ↓
EXECUTIVE_SUMMARY.txt
    ↓ (want more detail?)
VISUAL_SUMMARY.md
    ↓ (want the full story?)
RESEARCH_MEMO.md

AND READ ALONGSIDE EVERYTHING:
README.md (contains links to all)
```

---

## Key Statistics (For Reference)

| Metric | Value |
|--------|-------|
| Synthetic markets tested | 20,000 |
| Real markets analyzed | 6,742 |
| Trade rows processed | 1.4 million |
| Quote snapshots | 1.9 million |
| Expected value (taker) | −5.1¢/pair |
| Statistical significance | t > 9.7 (p < 0.0001) |
| Mean reversion signal | beta = −0.06 to −0.59 |
| Cost hurdle | 3−5¢/pair |
| Recoverable signal | 0.5−1.5¢/pair |
| Confidence | High |

---

## For Different Audiences

### High School Student
→ Read: **EXECUTIVE_SUMMARY.txt** + **VISUAL_SUMMARY.md**
→ Time: 20 minutes
→ Learn: How markets work and how they defend themselves

### College Student / Aspiring Trader
→ Read: **README.md** + **RESEARCH_MEMO.md**
→ Time: 40 minutes
→ Do: Run the code to see results yourself
→ Learn: How to test trading strategies rigorously

### Professional Researcher / Quant
→ Read: **RESEARCH_MEMO.md** (methodology section)
→ Do: Clone the repo, audit the code
→ Replicate: Run on your own market data
→ Learn: Methodology template for your own research

### Platform Designer / Market Maker
→ Read: **RESEARCH_MEMO.md** (fee moat section)
→ Key insight: How fee structures maintain market integrity
→ Action: Apply this principle to your own platform


---

## Common Questions

**Q: Where do I start?**  
A: Read **EXECUTIVE_SUMMARY.txt** first (5 min).

**Q: Can I reproduce the results?**  
A: Yes. Clone the repository, install Python libraries, run the scripts.

**Q: What if I find a bug in the code?**  
A: All code is open source. You can modify and improve it.

**Q: Is this a recommendation to not trade Polymarket?**  
A: This is evidence that this specific strategy doesn't work. Other strategies might.

**Q: Can I extend this research?**  
A: Absolutely. The framework is documented.

---

## Suggested Next Steps

1. **Understand**  
   Read EXECUTIVE_SUMMARY.txt + VISUAL_SUMMARY.md (20 min)

2. **Believe**  
   Read RESEARCH_MEMO.md to see the full methodology (30 min)

3. **Verify**  
   Run the code from polyvol to reproduce results (30 min)

4. **Apply**  
   Use this methodology for your own strategy research

---

## File Checklist

- [x] EXECUTIVE_SUMMARY.txt — Quick reference
- [x] README.md — GitHub landing page
- [x] VISUAL_SUMMARY.md — Infographics
- [x] RESEARCH_MEMO.md — Full paper
- [x] polyvol — Reproducible code
- [x] edge_economics.py — Key backtest
- [x] INDEX.md — This file (navigation)

---

## Questions? Issues? Extensions?

This research is open source and reproducible. If you find:
- **Bugs**: Fix them and submit
- **Improvements**: Implement them
- **Counter-evidence**: Test and publish
- **Interesting extensions**: Build on it

---

*Last updated: July 13, 2026*  
*All files are in `/mnt/user-data/outputs/`*
