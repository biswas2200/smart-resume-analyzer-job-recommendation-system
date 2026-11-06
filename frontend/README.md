# Frontend

Static web client for resume upload and the results dashboard: parsed profile, ATS score and
checks, role matches with skill gaps, JD match and feedback. It is built from **HTML, one
hand-written stylesheet and vanilla JavaScript** (native ES modules), with no framework, no
bundler and no build step. The files in `src/` are exactly what the browser runs, so DevTools
shows your own code, line for line.

The look is a calm dashboard: a soft grey canvas, white cards, a sidebar with the account, the
navigation and the resume versions, a monospace face for field labels and numbers, and small
tinted badges. It follows the system light or dark theme. The fonts are Plus Jakarta Sans and
JetBrains Mono from Google Fonts; the icons are drawn for the project (`components/icons.js`).
The layout was inspired by the public Dribbble shot "MyCV – CV Analyzer AI Dashboard" by Sina
Pasha; no assets were copied from it.

Every screen calls the real backend (`backend/`) directly.

## Running it

The pages need to be served over HTTP, because browsers refuse to load ES modules from
`file://`. Any static server works; Python is already part of this repo's toolchain:

```bash
cd frontend
python3 -m http.server 4200 --directory src     # or: npm start (same command)
```

Open `http://localhost:4200/`. The app expects the backend at `http://localhost:8080`, which is
set in `src/js/config.js`. The backend only accepts browser calls from the origins in
`app.cors.allowed-origins` (default `http://localhost:4200`). If you serve the pages from a
different port (VS Code Live Server, for example, uses 5500), add that origin to
`CORS_ALLOWED_ORIGINS`.

In Docker Compose, the `frontend` service is plain nginx serving `src/` on port 4200
(`Dockerfile`, `nginx.conf`).

## Pages

| Page | What it shows |
|---|---|
| `index.html` | Public landing page: what the app does, its features and what every account gets. |
| `login.html`, `register.html` | Sign in and create an account. A new account goes straight to the analyzer. |
| `upload.html` | **Resume analyzer.** Left: the resume as we read it (or the original PDF, for a file chosen in this browser) and the file card for uploading a new version. Right: the parsing result (name, email, phone, skills, experience, education) for the version picked in the version menu. `?resume=<id>` opens a given version. |
| `dashboard.html` | **Dashboard**, in three tabs driven by the hash. `#overview`: ATS score and band, detected field, best match, every ATS check with its points and how to fix it, the suggestions (written by AI when the engine is available) and up to three next steps. `#matches`: ranked roles with the skills you have and the ones to add, a "New" badge for roles not shown before, and helpful/not-helpful feedback; a locked card takes their place when the field needs the AI engine and this analysis could not use it. `#jd`: the job-description match. |
| `jobs.html` | **Jobs for you.** Open jobs in Bengaluru from each company's own careers feed, ranked for the latest resume: match percent and band, why it ranks there, the skills you have and the ones to add, and Apply / View posting links to the company's site. Search (title or company; `jobs.html?q=Groww` opens it already searched, which is where a company card's Apply goes) and a workplace filter. Without a resume the jobs show newest first with an upload prompt. Save keeps a job for tracking. Credits the Bangalore Startup Map for part of the company list. |
| `saved.html` | **Saved jobs**, grouped by where each application stands: Saved, Applied, Interviewing, Offer, Not selected. A status menu moves a job between groups; Remove drops it; a job the company closed stays, marked as closed. |
| `watchlist.html` | **Companies.** Every company in our list (the Bangalore Startup Map's public pages, used with its creator's permission, and Wikidata's Bengaluru companies) as a grid of rectangular cards: initial avatar, name, website, a badge (Hiring now, Careers page only, ...), a **Watch** toggle and an **Apply** button (the company's open jobs on the Jobs page, else its careers page, else its website). Search by name or website, filter All / Hiring now / Watching, Load more (24 at a time). Above the grid, the companies you watch with their open and new job counts; below it, a form to add a company by its website. Up to 25 companies can be watched. |

## Layout

```
src/
  index.html  login.html  register.html  upload.html  dashboard.html  jobs.html  saved.html
  favicon.svg                  the logo mark
  css/app.css                  every style: colour tokens (light and dark), site, auth, app shell, cards
  js/
    config.js                  API_BASE_URL
    core/
      http.js                  every backend call goes through request(): JSON/FormData,
                               Bearer token, 204 → null, errors → ApiError, 401 → back to login
      session.js               JWT + user in localStorage; requireAuth() page guard
      api-error.js             ApiError, extractApiErrorMessage() for user-facing messages
      validation.js            form and file rules (mirror the backend's own checks)
      dom.js                   byId, el, show/hide, setText, cloneTemplate, setBusy, renderChips
      local-store.js           try/catch JSON localStorage for the small per-browser memories
    api/                       one module per backend controller
      auth-api.js  resume-api.js  recommendation-api.js  feedback-api.js  jobs-api.js
    components/
      shell.js                 the sidebar: account, navigation, resume versions, mobile drawer
      icons.js                 the SVG icon sprite and icon()
      signed-in.js             "already signed in" panel on the sign-in pages
    pages/
      landing.js  login.js  register.js  upload.js  dashboard.js  jobs.js  saved.js
                               one script per HTML page
      dashboard-rules.js       lock decisions (pure, unit-tested)
      jobs-rules.js            jobs request, match band, location, workplace, job-type and
                               posted labels, safe links for feed URLs, saved-job grouping
                               (pure, unit-tested)
      insights.js              ATS check wording, fixes and points, score band, next steps,
                               new matches, score change (pure, unit-tested)
tests/                         node --test suites for the pure modules
```

### How a page works

Each HTML file contains all of its markup up front, with the optional sections marked `hidden`.
The page's script (`<script type="module" src="js/pages/<page>.js">`) then:

1. calls `requireAuth()` on protected pages, which sends a signed-out visitor to `login.html`;
2. calls `renderShell(active)` on the app pages to build the sidebar;
3. fetches data through the `api/` modules;
4. fills the markup in and shows or hides sections.

Repeated items, such as role cards and ATS checks, are cloned from `<template>` elements in the
HTML.

**Security rule:** anything that comes from the backend (resume text, skills, the AI
suggestions) is written with `textContent`, never `innerHTML`. A resume that contains
`<script>` is shown as text, not run.

### ATS checks

`insights.js` holds a readable name, the points and a "how to fix" line for each check the ML
service runs (`ml-service/app/services/ats_score.py`). Keep its weights in step with
`BASE_CHECK_WEIGHTS` and `KEYWORD_WEIGHT` there. A check the frontend doesn't know is still
shown, with its name tidied up and no points.

## Debugging

- **Network tab.** Every API call is a `fetch` issued from `core/http.js`. Filter by
  `localhost:8080` to see the request, its `Authorization` header and the backend's JSON
  error body (`{ message, fieldErrors }`).
- **Sources tab.** Open `js/pages/<page>.js` and set a breakpoint. There is no transpilation,
  so you don't need source maps.
- **Session.** Go to Application → Local Storage → `http://localhost:4200`. The keys are
  `resumeAnalyser.auth.token` and `resumeAnalyser.auth.user`. Delete them to sign out. After
  an admin changes an account's role, reload any app page: the sidebar re-reads `GET /auth/me`.
- **Per-browser memories.** `resumeAnalyser.seenRoles.<userId>` (roles already shown, so new
  ones get a "New" badge) and `resumeAnalyser.lastAts.<userId>` (the "Up 7 points since your
  previous version" line). Losing them only loses that polish.
- **Wrong element?** `byId()` throws `No element with id "…"` when the HTML and the script
  disagree on an id, so a typo shows up in the Console straight away.
- **Stale page after an edit?** Hard-reload (Ctrl+Shift+R). `python3 -m http.server` lets the
  browser cache files.

## Tests

The pure logic has unit tests: validation, error messages, the `http.js` request/401 handling,
the dashboard's lock and unlock rules, and the insights (check fixes and points, score band,
next steps, new matches, score change). They run on Node's built-in test runner (Node 21 or
later), with no `npm install` needed:

```bash
cd frontend
npm test            # = node --test "tests/*.test.js"
```

`package.json` only exists to mark the `.js` files as ES modules for Node and to name these two
scripts. It has no dependencies.

DOM rendering is checked by hand in the browser. The flows to walk through are register/login,
upload, the dashboard in its normal and locked states, JD match and feedback, each in light and
dark mode and at phone width.
