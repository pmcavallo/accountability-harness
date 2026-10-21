# Deploying the Demo App

How to put `app/streamlit_app.py` on Streamlit Community Cloud from the public GitHub repository. These steps are for Paulo. Nothing here was run: the repository has no remote yet, and the app has not been deployed.

**The app needs no secrets.** It calls no AI model, reads no API key or environment variable, and makes no network calls. Leave the Secrets box empty. If a deploy screen ever asks for a key, something is wrong: stop and check what changed. A test (`tests/test_app.py`) fails if the app imports a model SDK or reads a key.

## Settings

| Setting | Value |
|---|---|
| Repository | `pmcavallo/accountability-harness` |
| Branch | `main` |
| Main file path | `app/streamlit_app.py` |
| Python version | 3.12 (anything from 3.11 works; the harness needs `tomllib`) |
| Requirements file | `app/requirements.txt` (Community Cloud looks next to the main file first) |
| Secrets | none |

The harness itself has no dependencies, and the app loads it from `src/` directly, so the package does not need to be installed on the server. `app/requirements.txt` holds only `streamlit`; `pandas` comes with it.

## Steps

1. Before deploying, run the tests locally and check that they pass: `python -m pytest`.
2. Push the repository to GitHub as a public repository (with the usual pre-push checks).
3. Sign in at https://share.streamlit.io with the GitHub account that owns the repository, and allow Streamlit to read it when asked.
4. Choose **Create app**, then deploy a public app from a GitHub repository.
5. Enter the repository, the branch and the main file path `app/streamlit_app.py`.
6. Open **Advanced settings**, set the Python version to 3.12, and leave Secrets empty.
7. Optionally choose a custom subdomain, then **Deploy**. The first build installs Streamlit and takes a few minutes.
8. Open the app and click through all six pages. Each shows the header "Synthetic demo. No real email is sent. No AI model runs in this app." On "Observe vs enforce", observe shows 1 email sent and enforce shows 0.

## After deploying

- Replace the placeholder line in the README's "Demo app" section with the app's URL.
- `REPO_BLOB_URL` near the top of `app/streamlit_app.py` is already set to `https://github.com/pmcavallo/accountability-harness/blob/main`, so the Findings page links to `experiments/RESULTS.md` and `docs/WHAT-THIS-DOES-NOT-PROVE.md`. Check that both links open once the repository is public.
- Commit the change; Community Cloud redeploys on every push to the deployed branch.

## Notes

- The Community Cloud screens may differ in wording from the steps above; the settings in the table are what matters. They were written from memory of the service, not checked against its current pages.
- The app writes each run's audit log to a temporary folder and deletes it at the end of the run. Nothing persists between visits.
- Governance checks in the app use the fixed demo date, 2026-10-21, shown in the sidebar, so the demo scopes do not start reporting an overdue review after 2027-04-15.
