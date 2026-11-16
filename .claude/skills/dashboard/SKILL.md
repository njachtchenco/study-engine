---
name: dashboard
description: Open the Study Engine dashboard in the browser, rebuilt with today's numbers (and fresh news first, on a copy that has the optional news module, only if its morning refresh has not run). Use when the user says /dashboard, "pull up the dashboard", "open the dashboard", "show me the news", or "what's on today".
---

# Dashboard

Not a study role. It rebuilds the read-only view and opens it, so the day
starts on what is due.

## Procedure

1. **Rebuild:**
   ```bash
   python3 engine/build_view.py --news-if-stale
   ```
   Well under a second. `--news-if-stale` only matters on a copy that has the
   optional news module (`engine/news.py`): it fetches the news first if the
   scheduled morning refresh hasn't run since it was due. Without the module
   the flag does nothing. Pass `--news` instead only when the user asks for
   fresh news outright.

2. **Open it,** in Chrome when it's installed:
   ```bash
   open -a "Google Chrome" view/dashboard.html 2>/dev/null || open view/dashboard.html
   ```
   On Linux: `xdg-open view/dashboard.html`.

3. **Report in one or two lines,** from the JSON the rebuild printed:
   - `cards_due` and `redo_owed`. If cards are due, say `/review` runs them.
   - Only if the JSON has a `news` block: where the news came from
     (`fetched_now` true means "fetched just now", otherwise "from the
     morning refresh", with `as_of`), and any source in `unreachable`, whose
     column is showing its last stories. The project's notes on the news say
     what to check when the refresh didn't run.

   Do not summarize the headlines. They are on the page, one click away, and
   retelling them in chat does the reading for the learner.

## No topics yet

If the rebuild reports `"topics": 0`, the page says so. Tell them `/interview`
starts their first topic, and that `python3 engine/build_view.py --demo`
renders a sample topic to `view/demo.html` if they want to see a filled-in
dashboard first.
