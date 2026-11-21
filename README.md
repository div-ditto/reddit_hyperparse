# reddit_hyperparse

Every day, finds Reddit posts and comments from the **last 24 hours** that mention Indian
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

## Where the data comes from

| Source | When | Notes |
|---|---|---|
| **Arctic Shift** (default) | no Reddit keys set | A free, open Reddit archive ([arctic-shift](https://github.com/ArthurHeitmann/arctic_shift)) that saves posts and comments the moment they're posted. No login, no key. |
| **Reddit API** | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` set | Reddit's official API. It adds all-of-Reddit brand search and real scores. Needs an approved Reddit app. |

Force one with the `SOURCE` variable: `arctic` or `reddit`. The default `auto` picks the API when keys exist.

**What Arctic Shift covers:** Arctic Shift can't search all of Reddit by keyword; every
search must name a subreddit. So the app reads three groups of subreddits from `config.toml`:

| Group | Count | What counts as a match |
|---|---|---|
| `insurance` | 13 | every post and comment, on any keyword |
| `regional` | 11 | posts that say "health insurance" / "term insurance" or name a brand, plus their comments |
| `discovered` | 68 | posts that name a brand or plan, plus their comments |

The `discovered` list holds the subreddits where your past matches came from, back when
Reddit's own search still worked. Together the three groups cover **about 85% of the 1,760
past rows** (Jun–Nov 2026). The rest were one-off hits spread over about 245 subreddits.
Rebuild the list from newer sheet data now and then:

```
python -m hyperparse.discover path	o\your_sheet_export.xlsx
```

and paste its output over `discovered = [...]` in `config.toml`. A run reads about 3,000 posts
and comments and takes about 4 minutes. Score and comment count stay 0–1 in the archive for
about 36 hours, so they are left blank.

Arctic Shift is a free volunteer service with no uptime guarantee, and it asks users to "be
considerate". The app sends at most 2 requests at a time, about 1 a second, and backs off
when the service is busy. Reddit's direct feeds refuse no-login reads, and its robots.txt
disallows crawling, so this app never scrapes Reddit's site and uses no proxies or IP rotation.

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
| `REDDIT_CLIENT_ID` | optional, only for the Reddit API source |
| `REDDIT_CLIENT_SECRET` | optional, only for the Reddit API source |

Optional **variables**: `LOOKBACK_HOURS` (default 24), `SOURCE` (`auto` / `arctic` / `reddit`),
`REDDIT_USER_AGENT`.

Then Actions → *Daily Reddit scrape* → **Run workflow** to test. The run page shows a summary,
and the Excel files are under **Artifacts**. Artifacts are kept for 90 days. They are not
committed, because this repo is public and the rows contain Reddit usernames.

> **Full-day coverage.** The run at 09:00 IST looks back 24 hours, so each day picks up
> exactly where the previous one stopped. If GitHub starts a run late, the small overlap is
> harmless: rows already in the sheet are never added twice.

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
`0` OK · `1` scraped, but the sheet push failed (Excel still written) · `2` the data
source could not be read.

## Development
```
python -m pytest -q
```
The tests run the whole pipeline against a fake Arctic Shift server, a fake Reddit API (paging, the time cutoff, the
fallback when a combined subreddit read is refused, nested comments, filters, Excel) and a
fake sheet.
