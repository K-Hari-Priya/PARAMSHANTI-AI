"""
look.py - how PARAMSHANTI AI looks.

The idea behind the design:
  * A quiet night sky with one living point of light. The books describe the soul as a
    point of light, so that is the one thing on the screen that moves: it breathes slowly,
    and quickens while an answer is being prepared.
  * What the AI writes appears as light on the sky. What the books say appears as ink on a
    paper page, with the book's name on top and the page number at the foot, the way a
    printed page looks. The two can never be mistaken for each other.
  * The colours are the Paramshanti house colours (navy and gold) and the typeface is
    Garamond, as in the printed books. The font files are in static/fonts.
  * The sky takes a slightly different colour with the subject of the question.

Nothing in this file talks to Gnani, Gemini or the books. It only produces HTML and CSS.
"""
import base64
import html
import random
import re


def _stars(width: int, height: int, count: int, seed: int, small: bool) -> str:
    """A field of stars as a small picture (SVG) that CSS can repeat across the sky.
    The same seed always gives the same sky."""
    rnd = random.Random(seed)
    dots = []
    for _ in range(count):
        x, y = rnd.uniform(0, width), rnd.uniform(0, height)
        tint = rnd.choice(["#FFFFFF", "#FFFFFF", "#DCE6FF", "#DCE6FF", "#FFEBC8"])
        if small:
            r, alpha = rnd.uniform(0.35, 0.85), rnd.uniform(0.22, 0.70)
        else:
            r, alpha = rnd.uniform(0.80, 1.40), rnd.uniform(0.60, 1.00)
            if rnd.random() < 0.18:                  # a few stars have a soft halo
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 3.6:.2f}" fill="{tint}" opacity="0.09"/>')
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{tint}" opacity="{alpha:.2f}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">{"".join(dots)}</svg>')
    return "url('data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode() + "')"


CSS = """
<style>
/* ---------- colours ---------- */
:root {
  --ps-gold: #C9A84C;        /* house gold */
  --ps-gold-soft: #E3CB86;
  --ps-light: #FFF4D6;       /* the point of light */
  --ps-star: #ECE8F4;        /* text written on the sky */
  --ps-dim: #A9ADCB;         /* quieter text on the sky */
  --ps-paper: #F4ECD7;       /* a page of a book */
  --ps-ink: #2B2A33;
  --ps-ink-soft: #6A5B36;
}
/* The colours of the sky can change smoothly with the subject of the question.
   ("\\3C color>" is how CSS writes the word color inside angle brackets without the opening
   bracket itself, which Streamlit's safety filter would otherwise reject.) */
@property --haze-a { syntax: "\\3C color>"; inherits: true; initial-value: rgba(52, 84, 170, 0.50); }
@property --haze-b { syntax: "\\3C color>"; inherits: true; initial-value: rgba(96, 66, 170, 0.26); }
@property --haze-c { syntax: "\\3C color>"; inherits: true; initial-value: rgba(24, 104, 128, 0.20); }
@property --horizon { syntax: "\\3C color>"; inherits: true; initial-value: rgba(214, 150, 84, 0.00); }

/* ---------- the sky ---------- */
.stApp {
  isolation: isolate;
  background:
    radial-gradient(1100px 620px at 50% -6%, var(--haze-a), transparent 72%),
    radial-gradient(900px 640px at 96% 38%, var(--haze-b), transparent 70%),
    radial-gradient(820px 620px at -4% 78%, var(--haze-c), transparent 70%),
    radial-gradient(120% 40% at 50% 85%, var(--horizon), transparent 72%),
    linear-gradient(180deg, #050A1E 0%, #091230 46%, #0B1532 100%);
  transition: --haze-a 2.6s ease, --haze-b 2.6s ease, --haze-c 2.6s ease, --horizon 2.6s ease;
}
.stApp::before, .stApp::after {
  content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none;
}
.stApp::before { background-image: STARS_SMALL; background-size: 900px 900px; }
.stApp::after  { background-image: STARS_BRIGHT; background-size: 1300px 1100px;
                 animation: ps-shimmer 8s ease-in-out infinite alternate; }
@keyframes ps-shimmer { from { opacity: .55; } to { opacity: 1; } }

[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { max-width: 800px; }
[data-testid="stSidebar"] { background: rgba(7, 13, 36, .86); backdrop-filter: blur(14px);
                            border-right: 1px solid rgba(201, 168, 76, .16); }

/* ---------- the point of light and the title ---------- */
.ps-hero { text-align: center; padding-top: 1.6rem; margin: clamp(0rem, 1vh, 2rem) 0 1rem; }
.ps-hero:not(.ps-hero--small) .ps-light { margin-bottom: 2.5rem; }
.ps-light {
  position: relative; width: 12px; height: 12px; margin: 0 auto 4.6rem; border-radius: 50%;
  background: var(--ps-light);
  box-shadow: 0 0 10px 3px rgba(255, 240, 200, .95), 0 0 44px 14px rgba(240, 205, 120, .46),
              0 0 150px 62px rgba(120, 150, 255, .20);
  animation: ps-breathe 7s ease-in-out infinite;
}
.ps-light::before, .ps-light::after {
  content: ""; position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
}
.ps-light::before { width: 230px; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 240, 205, .80), transparent); }
.ps-light::after  { width: 1px; height: 150px;
  background: linear-gradient(180deg, transparent, rgba(255, 240, 205, .80), transparent); }
@keyframes ps-breathe {
  0%, 100% { transform: scale(1);    filter: brightness(1); }
  50%      { transform: scale(1.22); filter: brightness(1.3); }
}
/* While an answer is being prepared the light quickens. */
.stApp[data-test-script-state="running"] .ps-light { animation-duration: 1.7s; }
/* While the voice is speaking the light pulses with it (app.py marks the page as "speaking"). */
body.ps-speaking .ps-light { animation: ps-speak 1.25s ease-in-out infinite; }
@keyframes ps-speak {
  0%, 100% { transform: scale(1);    filter: brightness(1.05); }
  35%      { transform: scale(1.6);  filter: brightness(1.6); }
  70%      { transform: scale(1.2);  filter: brightness(1.2); }
}

.ps-title { font-weight: 500; font-size: clamp(2.2rem, 7vw, 3.7rem); line-height: 1.1;
            letter-spacing: .15em; padding-left: .15em; color: #F4E6BF;
            text-shadow: 0 0 30px rgba(201, 168, 76, .35); }
.ps-hero p.ps-tag  { color: var(--ps-star); font-size: 1.22rem; line-height: 1.5; max-width: 30em;
                     margin: 1.5rem auto 0; text-wrap: balance; }
.ps-hero p.ps-from { color: var(--ps-dim); font-size: 1.02rem; font-style: italic; max-width: 34em;
                     margin: .55rem auto 0; text-wrap: balance; }

/* Once there is an answer, the light and the title become one small line at the top. */
.ps-hero--small { display: flex; justify-content: center; align-items: center; gap: 1.5rem;
                  padding: 1.5rem 0 .9rem; margin: 0 0 .6rem; }
.ps-hero--small .ps-light { margin: 0; flex: 0 0 auto; width: 9px; height: 9px; }
.ps-hero--small .ps-light::before { width: 74px; }
.ps-hero--small .ps-light::after  { height: 50px; }
.ps-hero--small .ps-title { font-size: 1.45rem; letter-spacing: .2em; padding-left: 0; }

/* ---------- settings: language, voice on or off, which voice ---------- */
.st-key-settings { justify-content: center; }
.st-key-settings label p, .st-key-settings button p { font-size: .98rem; }
.st-key-settings [data-testid="stPopover"] button { border-color: transparent; background: transparent; }
@media (min-width: 900px) {          /* on a wide screen: a small glass bar in the top right corner */
  .st-key-settings {
    position: fixed; top: .7rem; right: 1.3rem; width: auto; z-index: 999995;
    padding: .28rem .35rem .28rem .5rem; border-radius: 999px;
    background: rgba(9, 16, 42, .64); border: 1px solid rgba(201, 168, 76, .22);
    backdrop-filter: blur(12px); box-shadow: 0 12px 34px -16px rgba(0, 0, 0, .8);
  }
}

/* ---------- asking: example questions and the question box ---------- */
[data-testid="stBottom"] > div {      /* what scrolls underneath fades out before it reaches the questions */
  background: linear-gradient(180deg, rgba(6, 11, 30, 0) 0, rgba(6, 11, 30, .92) 1.4rem, #060B1E 2.4rem);
}
[data-testid="stBottomBlockContainer"] { max-width: 800px; padding-top: 2.9rem; }
.st-key-examples { justify-content: center; }
.st-key-examples button {
  background: rgba(20, 31, 71, .55); border: 1px solid rgba(201, 168, 76, .34);
  color: var(--ps-star); padding: .3rem 1.05rem; min-height: 2.3rem;
  transition: border-color .15s ease, background .15s ease;
}
.st-key-examples button:hover, .st-key-examples button:focus-visible {
  border-color: var(--ps-gold); background: rgba(201, 168, 76, .12); color: #FFF7E0;
}
.st-key-examples button p { font-size: 1.02rem; }

[data-testid="stChatInput"] > div {
  background: rgba(17, 27, 64, .80); border: 1px solid rgba(201, 168, 76, .42);
  border-radius: 1.7rem; backdrop-filter: blur(10px);
  box-shadow: 0 14px 44px -12px rgba(0, 0, 0, .65);
}
[data-testid="stChatInput"]:focus-within > div {
  border-color: var(--ps-gold); box-shadow: 0 0 0 3px rgba(201, 168, 76, .18), 0 14px 44px -12px rgba(0, 0, 0, .65);
}
[data-testid="stChatInputTextArea"] { font-size: 1.16rem; color: var(--ps-star); }
[data-testid="stChatInputTextArea"]::placeholder { color: var(--ps-dim); opacity: .9; }
[data-testid="stChatInputMicButton"] { color: var(--ps-gold-soft); }

/* ---------- the answer ---------- */
[data-testid="stElementContainer"]:has(> [data-testid="stSpinner"]) { align-self: center; }
[data-testid="stSpinner"] { margin: 0 auto; color: var(--ps-dim); font-style: italic; }
.ps-asked-by { color: var(--ps-dim); font-size: .98rem; font-style: italic; margin-top: .4rem; }
.ps-asked { font-size: clamp(1.45rem, 4.2vw, 1.9rem); line-height: 1.28; font-style: italic;
            color: #F8F0DA; margin: .1rem 0 .5rem; text-wrap: balance; }
.ps-asked::before { content: "\\201C"; } .ps-asked::after { content: "\\201D"; }

.ps-h { font-size: 1.16rem; font-style: italic; color: var(--ps-gold-soft); margin: 1.5rem 0 .15rem; }
.ps-h--middle { text-align: center; margin-top: 2rem; }
.ps-note { display: block; font-size: .96rem; font-style: normal; color: var(--ps-dim); }
.st-key-explanation p { font-size: 1.3rem; line-height: 1.66; color: var(--ps-star); max-width: 35em; }

.ps-ornament { text-align: center; color: var(--ps-gold); letter-spacing: .7em; padding-left: .7em;
               margin: .6rem 0 0; font-size: 1.05rem; opacity: .9; }

/* A page of a book: the exact words, with the book's name on top and the page number below. */
.ps-page {
  background: linear-gradient(180deg, #F8F1DE 0%, var(--ps-paper) 100%); color: var(--ps-ink);
  border-radius: 3px; padding: 1.25rem 1.8rem 1.05rem; margin: .9rem 0 1.5rem;
  box-shadow: 0 0 0 1px rgba(201, 168, 76, .40), 0 22px 60px -22px rgba(0, 0, 0, .85),
              0 0 90px -26px rgba(240, 205, 120, .34);
}
.ps-page-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1.6rem;
                border-bottom: 1px solid rgba(106, 91, 54, .30); padding-bottom: .5rem; margin-bottom: .85rem;
                color: var(--ps-ink-soft); font-size: 1rem; }
.ps-book { font-variant-caps: small-caps; letter-spacing: .05em; font-weight: 600; color: #4A3C16; font-size: 1.08rem; }
.ps-chapter { font-style: italic; text-align: right; }
.ps-page p.ps-para { font-size: 1.24rem; line-height: 1.6; color: var(--ps-ink); margin: 0; }
.ps-page p.ps-para + p.ps-para { margin-top: .55em; }
.ps-page-foot { display: flex; justify-content: space-between; align-items: baseline; gap: 1.6rem;
                margin-top: .95rem; color: var(--ps-ink-soft); font-size: 1rem; }
.ps-page-foot a { color: #6A4E0E; text-decoration: underline; text-underline-offset: 3px; }
.ps-page-foot a:hover { color: #3F2E05; }
.ps-folio { font-style: italic; white-space: nowrap; }

/* How the answer was made: the steps drawn as a small constellation. */
.stMarkdown ol.ps-steps { list-style: none; display: grid; grid-template-columns: repeat(var(--n), 1fr);
                          position: relative; margin: .9rem 0 1.3rem; padding: 0; }
.stMarkdown ol.ps-steps::before { content: ""; position: absolute; top: 4px; height: 1px;
  left: calc(50% / var(--n)); right: calc(50% / var(--n));
  background: linear-gradient(90deg, rgba(201, 168, 76, .18), rgba(201, 168, 76, .60), rgba(201, 168, 76, .18)); }
.stMarkdown ol.ps-steps li { position: relative; text-align: center; margin: 0; padding: 1.15rem .25rem 0;
                             font-size: .9rem; line-height: 1.28; color: var(--ps-dim); }
.stMarkdown ol.ps-steps li::before { content: ""; position: absolute; top: 0; left: 50%; width: 9px; height: 9px;
  margin-left: -4.5px; border-radius: 50%; background: var(--ps-light); box-shadow: 0 0 9px 2px rgba(240, 205, 120, .70); }
.ps-step-time { display: block; color: var(--ps-star); font-size: 1.04rem; font-variant-numeric: tabular-nums; }
.ps-step-by { display: block; color: var(--ps-gold-soft); font-style: italic; }

/* The browser's own player is grey. A navy wash over it (colour only, not brightness) makes it
   belong to the night sky; clicks pass straight through the wash. */
div:has(> audio.stAudio) { position: relative; }
audio.stAudio { color-scheme: dark; border-radius: 999px; display: block; }
div:has(> audio.stAudio)::after { content: ""; position: absolute; inset: 0; border-radius: 999px;
                                  background: #1F3864; mix-blend-mode: color; pointer-events: none; }
[data-testid="stExpander"] details { background: rgba(14, 23, 56, .55); border-color: rgba(201, 168, 76, .22); }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
  background: rgba(201, 168, 76, .10); border: 1px solid rgba(201, 168, 76, .38); color: var(--ps-star); }
[data-testid="stAlertContentInfo"] p { color: var(--ps-star); font-size: 1.08rem; }
.st-key-welcome .ps-light { animation: ps-arrive 2s cubic-bezier(.2, 1.5, .35, 1) both, ps-breathe 7s ease-in-out 2s infinite; }
.st-key-welcome .ps-title { animation: ps-focus 2.4s cubic-bezier(.2, .7, .2, 1) 1.1s both; }
.st-key-welcome .ps-hero p.ps-tag { animation: ps-rise 1.3s ease 2.6s both; }
.st-key-welcome .ps-hero p.ps-from { animation: ps-rise 1.3s ease 3.3s both; }
.st-key-welcome p.ps-choose { animation: ps-rise 1.2s ease 4.1s both; }
.st-key-languages > div { animation: ps-rise .9s ease both; }
.st-key-languages > div:nth-child(1) { animation-delay: 4.50s; }
.st-key-languages > div:nth-child(2) { animation-delay: 4.59s; }
.st-key-languages > div:nth-child(3) { animation-delay: 4.68s; }
.st-key-languages > div:nth-child(4) { animation-delay: 4.77s; }
.st-key-languages > div:nth-child(5) { animation-delay: 4.86s; }
.st-key-languages > div:nth-child(6) { animation-delay: 4.95s; }
.st-key-languages > div:nth-child(7) { animation-delay: 5.04s; }
.st-key-languages > div:nth-child(8) { animation-delay: 5.13s; }
.st-key-languages > div:nth-child(9) { animation-delay: 5.22s; }
.st-key-languages > div:nth-child(10) { animation-delay: 5.31s; }
@keyframes ps-arrive { 0% { transform: scale(0); opacity: 0; } 55% { opacity: 1; } 100% { transform: scale(1); opacity: 1; } }
@keyframes ps-focus { 0% { opacity: 0; filter: blur(10px); transform: scale(1.07); } 100% { opacity: 1; filter: blur(0); transform: scale(1); } }
@keyframes ps-rise { 0% { opacity: 0; transform: translateY(12px); } 100% { opacity: 1; transform: translateY(0); } }
.st-key-welcome .ps-hero:not(.ps-hero--small) { margin-top: clamp(2rem, 13vh, 8rem); }
.stMarkdown p.ps-choose { text-align: center; font-style: italic; color: #E3CB86; font-size: 1.4rem; margin: 1.4rem 0 1.1rem; }
.st-key-languages { display: grid !important; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .9rem .8rem; width: 100%; }
.st-key-languages > div { width: 100% !important; }
.st-key-languages button { width: 100%; background: rgba(20,31,71,.6); border: 1px solid rgba(201,168,76,.45); padding: .75rem .3rem; }
.st-key-languages button p, .st-key-languages button div { font-size: 1.35rem; line-height: 1.5; white-space: nowrap; }
@media (max-width: 640px) { .st-key-languages { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.st-key-languages button:hover { border-color: #E6CB7C; background: rgba(40,56,112,.75); color: #F4E6BF; }
.st-key-settings [data-testid="stSelectbox"] { min-width: 8.5rem; }
.stMarkdown p.ps-foot { color: var(--ps-dim); font-size: .95rem; font-style: italic; text-align: center;
                        max-width: 34em; margin: 1.6rem auto 0; text-wrap: balance; opacity: .85; }

/* People who ask their computer for less motion get a still sky. */
@media (prefers-reduced-motion: reduce) {
  .st-key-welcome .ps-light, .st-key-welcome .ps-title, .st-key-welcome p, .st-key-languages > div { animation: none !important; }
  .ps-light, body.ps-speaking .ps-light, .stApp::after { animation: none; }
  .stApp { transition: none; }
}
@media (max-height: 750px) {          /* a laptop screen that is not very tall */
  .ps-hero:not(.ps-hero--small) { margin-top: 0; padding-top: .5rem; }
  .ps-hero:not(.ps-hero--small) .ps-light { margin-bottom: 1.1rem; }
  .ps-hero p.ps-from { display: none; }
  .ps-light::after { height: 104px; }
  .ps-title { font-size: clamp(2rem, 6vw, 3rem); }
  .ps-hero p.ps-tag { margin-top: 1rem; font-size: 1.14rem; }
  .ps-hero--small { padding: 1.3rem 0 .7rem; }
  .ps-hero--small .ps-title { font-size: 1.35rem; }
}
@media (max-width: 640px) {
  .ps-hero:not(.ps-hero--small) { padding-top: 4.4rem; margin-top: 0; }
  .ps-title { font-size: clamp(1.4rem, 7.2vw, 2.4rem); letter-spacing: .11em; padding-left: .11em; white-space: nowrap; }
  .ps-hero--small { gap: 1.1rem; }
  .ps-hero--small .ps-title { font-size: 1.15rem; letter-spacing: .16em; }
  .ps-hero p.ps-tag { font-size: 1.1rem; }
  .st-key-settings { gap: .35rem .9rem; }
  [data-testid="stChatInputTextArea"] { font-size: 1.02rem; }
  .ps-page { padding: 1.05rem 1.15rem .95rem; }
  .ps-page-head { flex-direction: column; gap: .1rem; }
  .ps-chapter { text-align: left; }
  .stMarkdown ol.ps-steps li { font-size: .8rem; }
  .st-key-examples { flex-wrap: nowrap; overflow-x: auto; justify-content: flex-start; scrollbar-width: none; }
  .st-key-examples > div { flex: 0 0 auto; }
}
</style>
""".replace("STARS_SMALL", _stars(900, 900, 170, seed=7, small=True)) \
   .replace("STARS_BRIGHT", _stars(1300, 1100, 56, seed=21, small=False))


# ---------------- the sky follows the subject of the question ----------------
# name: (light from above, haze on the right, haze on the left, glow on the horizon)
SKIES = {
    "stillness": ("rgba(52, 84, 170, .50)", "rgba(96, 66, 170, .26)", "rgba(24, 104, 128, .20)", "rgba(214, 150, 84, 0)"),
    "cosmos":    ("rgba(88, 62, 196, .54)", "rgba(172, 64, 172, .32)", "rgba(20, 130, 152, .30)", "rgba(214, 150, 84, 0)"),
    "water":     ("rgba(26, 100, 152, .54)", "rgba(24, 124, 140, .32)", "rgba(52, 76, 172, .24)", "rgba(214, 150, 84, 0)"),
    "dawn":      ("rgba(64, 74, 150, .46)", "rgba(152, 84, 120, .26)", "rgba(24, 104, 128, .16)", "rgba(226, 150, 84, .52)"),
}
_SUBJECTS = {
    "cosmos": r"univers|multivers|galax|cosmos|cosmic|alien|planet|astral|dimension|brahmand|creation|ufo|other worlds",
    "water":  r"anger|angry|stress|fear|afraid|anxi|worr|overthink|thought|mind|calm|tension|irritat|overwhelm|sad|depress|restless|sleep",
    "dawn":   r"death|dying|\bdie\b|rebirth|born again|karma|past li|destiny|fate|transformation|golden age|new age|after life|afterlife",
}


def sky_for(text: str) -> str:
    """Choose a sky from the words of the question: 'cosmos' for the universe, 'water' (still,
    cool) for the mind and its troubles, 'dawn' for death and rebirth, else 'stillness'."""
    text = (text or "").lower()
    counts = {name: len(re.findall(pattern, text)) for name, pattern in _SUBJECTS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] else "stillness"


def sky_css(name: str) -> str:
    """The small piece of CSS that gives the sky its colours."""
    a, b, c, horizon = SKIES.get(name, SKIES["stillness"])
    return f"<style>.stApp {{ --haze-a: {a}; --haze-b: {b}; --haze-c: {c}; --horizon: {horizon}; }}</style>"


# ---------------- pieces of the page ----------------
def hero(small: bool, tagline: str = "", library: str = "") -> str:
    """The point of light and the title. 'small' is used once there is an answer to show."""
    words = "" if small else (f'<p class="ps-tag">{html.escape(tagline)}</p>'
                              f'<p class="ps-from">{html.escape(library)}</p>')
    return (f'<div class="ps-hero{" ps-hero--small" if small else ""}">'
            f'<div class="ps-light" aria-hidden="true"></div>'
            f'<div class="ps-title" role="heading" aria-level="1">PARAMSHANTI AI</div>{words}</div>')


def page(book: str, chapter: str, paragraphs: list[str], page_number, link: str = "") -> str:
    """One passage shown as a page of its book. The text is shown exactly as given."""
    body = "".join(f'<p class="ps-para">{html.escape(p)}</p>' for p in paragraphs)
    opened = (f'<a href="{html.escape(link)}" target="_blank" rel="noopener">Open the book</a>'
              if link else "<span></span>")
    return (f'<div class="ps-page"><div class="ps-page-head"><span class="ps-book">{html.escape(book)}</span>'
            f'<span class="ps-chapter">{html.escape(chapter)}</span></div>{body}'
            f'<div class="ps-page-foot">{opened}<span class="ps-folio">page {html.escape(str(page_number))}</span></div></div>')


def steps(stages: list[tuple[str, str, float]]) -> str:
    """The stages an answer went through, as (what happened, who did it, seconds)."""
    cells = "".join(
        f'<li>{html.escape(what)}<span class="ps-step-time">{seconds:.1f} s</span>'
        + (f'<span class="ps-step-by">{html.escape(who)}</span>' if who else "") + "</li>"
        for what, who, seconds in stages)
    return f'<ol class="ps-steps" style="--n: {len(stages)}">{cells}</ol>'
