# reddit_hyperparse

Every day, finds Reddit posts and comments from the **last 14 hours** that mention Indian
health/term insurance brands, plans or jargon. It scores them by priority and then:

- pushes new rows into the Google Sheet's **New Cases** tab (through the Apps Script web app), and
- writes an **Excel** file for the run, plus a running `reddit_master.xlsx`.

Keywords, subreddits and scoring weights match the Apps Script (`apps_script/Code.gs`), so the
sheet and this app give the same `priority_score`.

```
GitHub Actions (daily 09:00 IST)
   └─ python -m hyperparse
        ├─ Reddit  ── insurance subs: all new posts + comments (one combined read)
        │          ── regional subs: "health insurance" / "term insurance" search
        │          ── all of Reddit: brand + plan names (12 per search)
        │          ── comments of matched posts outside the insurance subs
        ├─ match + filter (motor, excluded subs) + score
        ├─ Google Sheet  → New Cases   (dedupes against New Cases, reddit, Sheet1)
        └─ Excel         → output/reddit_<date>.xlsx + output/reddit_master.xlsx
```

## How it reads Reddit (read this first)

| Mode | When | Notes |
|---|---|---|
| **OAuth app** (recommended) | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` set | No Reddit user login: the app signs in as itself. About 100 requests/min, full data (score, comment count). A full run takes 1–3 minutes. |
| **Public feeds** | no keys | The same no-login `.json`/`.rss` feeds the Apps Script uses. Reddit now refuses these from many networks, including GitHub's servers and, as of Nov 2026, the network this was built on. In that case the run stops in seconds and says so. |

There is deliberately **no proxy or IP rotation**. Reddit's terms forbid getting around its
blocks and rate limits, and doing so risks Reddit banning the account or the company. If
the public feeds are refused, the fix is an API key.

**Getting a key.** Sign in at <https://www.reddit.com/prefs/apps> → *create another app* →
type **script** → redirect URI `http://localhost:8080`. The string under the app name is the
client ID; the *secret* is the client secret. Since 2025 Reddit's Responsible Builder Policy
can require approval before new apps get API access. Ditto is a company, so tracking brand
mentions counts as **commercial use**, which Reddit's Data API terms say needs Reddit's
written approval. Follow the approval steps Reddit shows when you create the app, and settle
commercial use with Reddit before relying on the data.

## Setup

### 1. Google Sheet (once)
1. Sheet → Extensions → Apps Script → paste `apps_script/Code.gs` → Save.
2. Run `hyperparseSetup` → Allow. Copy the **security key**.
3. Deploy → New deployment → Web app. Set *Execute as*: **Me**. Set *Who has access*:
   **Anyone**. "Anyone within Ditto" will not work, because GitHub cannot sign in to Google.
   Copy the URL ending in `/exec`.

The key still protects the sheet: without it the URL cannot read or write anything.

### 2. GitHub (once)
Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value |
|---|---|
| `SHEET_WEBAPP_URL` | the `/exec` URL |
| `SHEET_KEY` | the security key |
| `REDDIT_CLIENT_ID` | from reddit.com/prefs/apps |
| `REDDIT_CLIENT_SECRET` | from reddit.com/prefs/apps |

Optional **variables**: `LOOKBACK_HOURS` (default 14), `REDDIT_USER_AGENT`.

Then Actions → *Daily Reddit scrape* → **Run workflow** to test. The run page shows a summary,
and the Excel files are under **Artifacts**. Artifacts are kept for 90 days. They are not
committed, because this repo is public and the rows contain Reddit usernames.

> **14 hours vs. once a day.** A daily run looking back 14 hours misses the other 10 hours
> of the day. To cover every hour, either set `LOOKBACK_HOURS` to `24`, or add a second
> schedule line `- cron: "30 15 * * *"` (21:00 IST). Rows already in the sheet are never
> added twice.

### 3. Run on your own PC (optional)
```powershell
cd reddit_hyperparse
python -m pip install -r requirements.txt
copy .env.example .env      # fill it in
python -m hyperparse --dry-run          # look only, prints top rows
python -m hyperparse                    # sheet + Excel in .\output
python -m hyperparse --hours 24 --no-sheet
```
To run it daily on Windows, use Task Scheduler → Create Basic Task → Daily → Program
`python`, arguments `-m hyperparse`, start in the `reddit_hyperparse` folder.

## Changing what is tracked
Edit `config.toml`. It holds the subreddits, keywords, excluded subs, motor words, scoring
weights and request rate. If you change keywords or weights, change the same lists in
`apps_script/Code.gs` too, so the sheet's re-scoring agrees.

## Output columns
`post_id, created_utc (IST), subreddit, title, author, permalink, matched_terms,
source_type (post|comment), score, num_comments, priority_score, priority_breakdown`.
Comment IDs are `<post>_<comment>`. Rows that mention Ditto are green.
`priority_breakdown` is `F` freshness, `B` brand, `I` intent, `S` subreddit, `M` specificity.

## Exit codes
`0` OK · `1` scraped, but the sheet push failed (Excel still written) · `2` Reddit could
not be read.

## Development
```
python -m pytest -q
```
The tests run the whole pipeline against a fake Reddit API (paging, the 14-hour cutoff, the
fallback when a combined subreddit read is refused, nested comments, filters, Excel) and a
fake sheet.
