# Setting Up Your Research on GitHub Pages

This guide will help you host the research memo and supporting materials as a professional website on GitHub Pages.

## What You Have

The research package includes:

1. **EXECUTIVE_SUMMARY.txt** (5.2 KB) — One-page summary for quick reference
2. **README.md** (8.9 KB) — Landing page with navigation and key findings
3. **RESEARCH_MEMO.md** (26 KB) — Full detailed memo (25-30 minute read)
4. **edge_economics.py** (11 KB) — Final backtest script for economic quantification
5. **polyvol_v5.zip** (61 KB) — Complete research framework with all scripts

## Step 1: Create a GitHub Repository

```bash
# Create a new repository on GitHub
# Repository name: polymarket-research (or similar)
# Description: "Volatility Harvesting on Polymarket: A Complete Falsification Study"
# Make it PUBLIC
# Add a README (we'll replace it)
# License: MIT (optional but recommended)
```

## Step 2: Clone and Structure Your Repo

```bash
git clone https://github.com/YOUR_USERNAME/polymarket-research.git
cd polymarket-research

# Directory structure to create:
mkdir -p docs
mkdir -p code
mkdir -p data

# Copy files:
# Replace default README.md with our README.md
# Put RESEARCH_MEMO.md in docs/
# Put EXECUTIVE_SUMMARY.txt in root (optional, reference only)
# Put edge_economics.py in code/
# Put polyvol_v5.zip in code/
```

Final structure:
```
polymarket-research/
├── README.md                 ← GitHub landing page (our README.md)
├── EXECUTIVE_SUMMARY.txt     ← Quick reference (for docs/)
├── docs/
│   ├── RESEARCH_MEMO.md     ← Full memo
│   └── index.md             ← Optional custom home page
├── code/
│   ├── edge_economics.py    ← Highlight script
│   ├── polyvol_v5.zip       ← Full framework
│   └── README.md            ← Instructions to run code
└── LICENSE
```

## Step 3: Enable GitHub Pages

1. Go to your GitHub repository
2. Settings → Pages (on the left sidebar)
3. Under "Build and deployment":
   - Source: Deploy from a branch
   - Branch: main (or master), folder: / (root)
4. Click Save

Your site will be available at: `https://YOUR_USERNAME.github.io/polymarket-research`

## Step 4: Create the Site Structure

### Root README.md (already provided)
This serves as your main landing page. It:
- Summarizes the research
- Links to the full memo
- Lists key findings
- Explains the code structure
- Includes the "start here" link

### Optional: docs/index.md
Create a custom home page (more stylized than README):

```markdown
# Volatility Harvesting on Polymarket

A research investigation into an apparently profitable trading strategy—
and why it actually isn't.

## Quick Facts

- **Tested on**: 6,742 real Polymarket markets
- **Data**: 1.4 million trades, 1.9 million orderbook snapshots
- **Finding**: No edge for retail traders (EV = −5¢/pair)
- **Reason**: Fee structure engineered as targeted defense
- **Confidence**: Very high (t > 30 across all tests)

## Read the Research

- [Executive Summary](EXECUTIVE_SUMMARY.txt) (5 min read)
- [Full Research Memo](RESEARCH_MEMO.md) (25 min read)
- [Access Code & Data](../code/)

## Key Insight

Polymarket's fee formula (0.07 × p × (1−p)) peaks at exactly 50¢, where 
mean reversion would be strongest. This isn't accident—it's engineered 
defense. The strategy isn't forbidden. It's just expensive.

---

Questions? Open an issue or email.
```

### code/README.md
Help people run the code:

```markdown
# Research Code

The complete `polyvol` research framework for reproducing all results.

## Contents

- `polyvol_v5.zip` — Complete framework (1,500+ lines)
- `edge_economics.py` — Final backtest script
- `*.csv` (if included) — Sample results

## Quick Start

```bash
unzip polyvol_v5.zip
cd polyvol
pip install -r requirements.txt  # pandas, numpy, scipy, matplotlib

# Run the null model test
python scripts/run_synthetic.py

# Run mean reversion diagnostics
python scripts/mean_reversion_test.py --synthetic

# Run economic backtests (requires HF dataset)
python scripts/edge_economics.py fade --bbo data/hf/bbo_5m.parquet
```

## Data Sources

All data is free and public (no API keys required):
- Polymarket Gamma API (market discovery)
- Polymarket Data API (executed trades)
- HuggingFace dataset: `aliplayer1/polymarket-crypto-updown`

See full research memo for detailed methodology.
```

## Step 5: Push to GitHub

```bash
git add .
git commit -m "Initial research publication"
git push origin main
```

Your site will auto-build and publish within 1-2 minutes.

## Step 6: Customize (Optional)

### Add a Custom Domain
1. Settings → Pages → Custom domain
2. Point your domain CNAME to `YOUR_USERNAME.github.io`

### Add a Custom Theme
Create `_config.yml` in the root:

```yaml
theme: jekyll-theme-minimal
title: Polymarket Volatility Research
description: A complete falsification study of volatility harvesting strategies
show_downloads: true
```

Other themes: jekyll-theme-slate, jekyll-theme-cayman, etc.

### Add a Custom Sidebar (for minimal theme)
Edit the theme in `_config.yml`:

```yaml
theme: jekyll-theme-minimal
sidebar_links:
  - name: Home
    href: /
  - name: Research Memo
    href: /docs/RESEARCH_MEMO.md
  - name: Code & Data
    href: /code/
  - name: GitHub
    href: https://github.com/YOUR_USERNAME/polymarket-research
```

## Step 7: Link from Your Website / LinkedIn

Once published, you can reference it:

- **LinkedIn**: Link to `https://github.com/YOUR_USERNAME/polymarket-research` in your headline or post
- **Portfolio**: Add it as a featured research project
- **Founder Talk**: Use this research as the foundation for a post about empirical testing and negative results

## Markdown Tips for GitHub Pages

GitHub Pages uses standard Markdown with some extras:

- **Links**: `[text](url)` or `[text](path/to/file.md)`
- **Anchors**: Create with `## Section Name`, link with `[link](#section-name)`
- **Code blocks**: Use triple backticks with language specifier
  ```python
  def example():
      pass
  ```
- **Images**: `![alt text](path/to/image.png)`
- **Tables**: Rendered automatically

## Best Practices

1. **Keep README.md concise** — People will read the first 2 minutes
2. **Link early to the full memo** — You want engaged readers to find the deep dive
3. **Make results scannable** — Use tables, bullet points, short paragraphs
4. **Include code clearly** — Link to the GitHub repo, not embedded in pages
5. **Use consistent formatting** — Markdown headers, emphasis, code blocks

## SEO & Discoverability

Add this to `_config.yml`:

```yaml
description: Volatility harvesting strategy research. Testing mean reversion on Polymarket prediction markets.
keywords: 
  - polymarket
  - prediction-markets
  - trading-strategy
  - quantitative-research
  - mean-reversion
```

## Example Final Site Structure

```
Your GitHub Pages Site
├── Home (README.md with summary and links)
├── Research Memo (full detailed study)
├── Executive Summary (quick reference)
├── Code & Data (link to framework)
└── About / Contact
```

## Traffic & Analytics

To add Google Analytics (optional):

1. Create a Google Analytics account
2. Add to `_config.yml`:
   ```yaml
   google_analytics: UA-XXXXXXXXX-X
   ```
3. Add to `_layouts/default.html` (if using custom theme):
   ```html
   {% if site.google_analytics %}
     <script async src="...google-analytics..."></script>
   {% endif %}
   ```

## Publishing Checklist

- [ ] Repository created and public
- [ ] All markdown files are readable (no typos)
- [ ] Links are working (test locally or on GitHub)
- [ ] Code examples are valid
- [ ] GitHub Pages is enabled
- [ ] Site is published and accessible
- [ ] Links work from the live site (not just locally)
- [ ] PDF of memo is downloadable (if desired)

## Troubleshooting

**Site not updating after push?**
- Wait 1-2 minutes for GitHub to rebuild
- Check Actions tab for build errors
- Clear browser cache (Ctrl+F5)

**Links broken?**
- Use relative paths: `docs/RESEARCH_MEMO.md` not full URLs
- Test locally with `jekyll serve`

**Markdown not rendering?**
- Check for missing newlines between sections
- Ensure consistent indentation
- Validate with an online Markdown checker

## Next Steps

Once published:

1. **Reference it in your professional profiles** — This is high-quality research
2. **Consider expanding it** — Other strategies, other markets, live trading results
3. **Keep it updated** — Link to new market regimes or fee changes
4. **Share the findings** — Blog posts, talks, papers can all reference this work

---

**Your research is now publicly accessible, professionally presented, and reproducible. That's the goal.**
