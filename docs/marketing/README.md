# Distribution artifacts

Drafts for getting CSIS in front of an audience. None of these have been published; the repo owner picks the channels and timing.

| File | Channel | Effort to publish |
|---|---|---|
| [`01-show-hn.md`](01-show-hn.md) | Hacker News (Show HN) | Copy title + URL + body comment; submit at https://news.ycombinator.com/submit |
| [`02-reddit-localllama.md`](02-reddit-localllama.md) | r/LocalLLaMA | Copy title + body; submit at https://reddit.com/r/LocalLLaMA |
| [`03-reddit-machinelearning.md`](03-reddit-machinelearning.md) | r/MachineLearning | Copy title + body; submit at https://reddit.com/r/MachineLearning with [P] flair |
| [`04-social-preview.html`](04-social-preview.html) | GitHub social preview image | Open in browser at 1280×640; screenshot; upload at https://github.com/jim4226/CSIS/settings (Social preview section) |

## Recommended order of operations

1. **First**: upload the social preview image (`04`). It's what every share will display, including the HN/Reddit submissions below. Doing it after the posts means the first wave of clicks sees the GitHub default card.
2. **Then**: pick ONE primary channel for the first post — Show HN is the recommended starter because its audience overlaps most with the target users and the format rewards exactly the framing this repo has.
3. **24-48 hours later**: secondary channels. r/LocalLLaMA is the strongest secondary because the mock backend lets people try without API credit; r/MachineLearning is third because the bar is higher and the framing has to lead with methodology.
4. **Don't cross-post verbatim.** Each draft has a distinct framing for its audience. Verbatim copies across channels get flagged.

## What NOT to do

- Don't post to all four channels in the same hour. Reddit's anti-spam cross-references; you'll get shadow-banned.
- Don't auto-respond from a script. HN moderates aggressively against that; Reddit too.
- Don't reply defensively to every "but what about X." Engage substantive critiques; ignore vibe takes.
- Don't link your other social profiles in the OP. HN/Reddit downvote anything that smells of self-promotion past the project itself.

## Generating the social preview image

The HTML at [`04-social-preview.html`](04-social-preview.html) is hand-tuned for 1280×640. Two ways to get a PNG out:

**Option A — Chrome / Edge headless** (clean, no manual screenshotting):

```bash
# macOS / Linux
chrome --headless --disable-gpu --screenshot=social-preview.png --window-size=1280,640 file:///absolute/path/to/docs/marketing/04-social-preview.html

# Windows (PowerShell)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless --disable-gpu --screenshot=social-preview.png --window-size=1280,640 file:///C:/Users/jaron/OneDrive/Pictures/Desktop/Superintellegnce/docs/marketing/04-social-preview.html
```

**Option B — Browser devtools** (manual but visual):

1. Open `04-social-preview.html` in Chrome / Edge / Firefox
2. Open devtools (F12); toggle device toolbar (Ctrl+Shift+M)
3. Set responsive viewport to 1280 × 640
4. Devtools → ⋮ menu → "Capture full-size screenshot"
5. Save as `social-preview.png`

Then upload at https://github.com/jim4226/CSIS/settings → "Social preview" → "Edit" → "Upload an image".

## After the first wave

- If a post lands and generates real engagement, write a follow-up. The cycle-9 H2/H11 deferrals are the strongest "next post" hook because they invite the AI-safety crowd to weigh in on the right escalation path (process-level isolation vs in-process hardening).
- If posts go nowhere, that's data — the framing or the channel was wrong, not necessarily the project. Try a different angle (e.g., "I built an agent system; here's the bug that took me three cycles to fix the right way" — narrative-first rather than methodology-first).
- Track inbound issues/PRs as the actual marketing signal. Stars are noisy; an issue from someone who actually ran the code is the real metric.
