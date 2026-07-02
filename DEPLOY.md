# Deploying the hosted web link (Streamlit Community Cloud)

This puts the app at a URL your workers open in a browser — nothing to install on
the Mac. It's free. You do this once; after that, workers just visit the link and
enter the password.

## What I already set up
- A **password gate** (`app.py`): the app asks for a password when `app_password`
  is set in Streamlit secrets.
- Theme, upload limits, and a `.gitignore` that keeps the real password out of git.
- **The code is already on GitHub (public):**
  <https://github.com/jazim-bot/havn-hangtags>  ← Step 1 is DONE.

## Step 1 — Put the code on GitHub ✅ DONE
Already pushed to `jazim-bot/havn-hangtags` (public). Nothing to do here. Because
it's public, you can deploy from **any** GitHub account you sign into Streamlit
with — the live app is still protected by the password gate.

## Step 2 — Deploy on Streamlit Community Cloud (one time)
1. Go to <https://share.streamlit.io> and **sign in with GitHub** (any account).
2. Click **Create app → Deploy a public app from a repo**.
3. In the **Repository** field, type or paste exactly:  `jazim-bot/havn-hangtags`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   (If it doesn't autocomplete in the dropdown, just type the full path above —
   it works because the repo is public.)
4. Click **Advanced settings → Secrets** and paste:
   ```toml
   app_password = "pick-a-password-for-your-workers"
   ```
5. Click **Deploy**. In ~1–2 minutes you'll get a URL like
   `https://havn-hangtags.streamlit.app`.

## Step 3 — Give it to your workers
Send them the URL + the password. They open it in any browser (on the work Mac or
anywhere), enter the password, upload the weekly CSV, and download the PDFs.

## Changing the password later
Streamlit Cloud → your app → **Settings → Secrets** → edit `app_password` → save.
The app restarts automatically.

## Updating the app later
Any change you push to GitHub (`git push`) redeploys automatically.

---

### Privacy note
The weekly CSV (customer names + meals) is uploaded to Streamlit's servers while
the app runs; the password keeps the link private. If you'd rather the data never
leave the work computer, I can instead give you a **double-click launcher** that
runs the app locally on the Mac — just ask.
