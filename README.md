# CA PYQs with Suggested Answers: chapter-wise

Past year question papers (PYQs) from the last 10 attempts, with suggested answers,
arranged **Level → Subject → Chapter** and published automatically to Google Drive.

When a student opens the Drive folder they see:

```
CA Foundation/
  Paper 1 - Accounting/
    Chapter 01 - Theoretical Framework.pdf   ← last 10 attempts, newest first
    Chapter 02 - ....pdf
  Paper 2 - Business Laws/
  ...
CA Intermediate/
CA Final/
```

Each chapter PDF has a divider page and a clickable bookmark for every attempt
(May 2026, January 2026, September 2025, ...).

## How it works

1. You add PDFs to the `source/` folder in this repo (one PDF per attempt per chapter).
2. On every push to `main`, a GitHub Action:
   - merges each chapter's attempt PDFs into one chapter PDF, keeping only the **latest 10 attempts**,
   - uploads the result to your Google Drive folder, creating missing folders,
     updating changed files in place (shared links keep working) and skipping unchanged ones.

## Adding papers

Put each attempt's questions plus suggested answers for one chapter in a separate PDF:

```
source/<Level>/<Subject>/<Chapter folder>/<Attempt>.pdf
```

Example:

```
source/CA Foundation/Paper 1 - Accounting/Chapter 01 - Theoretical Framework/May 2026.pdf
source/CA Foundation/Paper 1 - Accounting/Chapter 01 - Theoretical Framework/Jan 2026.pdf
source/CA Foundation/Paper 1 - Accounting/Chapter 01 - Theoretical Framework/Sept 2025.pdf
```

- **Attempt file names** must contain the month and year. These all work: `May 2026`, `Jan-26`,
  `Sept 2025`, `2026-05`. Files without a date are skipped with a warning.
- **Chapter folders**: start the name with a two-digit number (`Chapter 01 - ...`) so they sort correctly in Drive.
- You don't need to track which attempts are the "last 10". Keep adding new attempts and
  older ones drop out of the chapter PDF on their own. This handles Final (fewer attempts a year)
  and Foundation/Inter (three a year) the same way. To change 10, set a repository
  variable `MAX_ATTEMPTS` (Settings → Secrets and variables → Actions → Variables).
- **Already have a merged chapter PDF?** Put it directly in the subject folder
  (`source/CA Foundation/Paper 1 - Accounting/Chapter 03 - Something.pdf`) and it's uploaded as-is.
- Subject folders for all three levels are already created (empty, with `.gitkeep`). Rename them if you prefer different names.

You can upload from the GitHub website (open a folder → **Add file → Upload files**;
drag in a whole folder) or with git.

> GitHub rejects single files over 100 MB, and a repo over ~1–2 GB gets slow. If the papers are
> large scans, compress them first or enable [Git LFS](https://git-lfs.com) (`git lfs track "*.pdf"`).
> The workflow already checks out LFS files.

## One-time Google Drive setup

### 1. Create the Drive folder
Create a folder (for example `CA PYQs - Last 10 Attempts`) in Google Drive. Open it and copy the ID from the URL:
`https://drive.google.com/drive/folders/`**`1AbCdEfGh...`** ← this part.

To let students view it: **Share → General access → Anyone with the link → Viewer**.
Everything the workflow uploads inside this folder inherits that permission.

### 2. Create Google API credentials
1. Go to <https://console.cloud.google.com/>, create a project, then **APIs & Services → Library → Google Drive API → Enable**.
2. **APIs & Services → OAuth consent screen**: choose *External*, fill in the app name and your email,
   add yourself as a **Test user**, then **Publish app** (in *Testing* mode, refresh tokens expire after 7 days).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON.
4. On your own computer:
   ```bash
   pip install google-auth-oauthlib
   python scripts/get_refresh_token.py ~/Downloads/client_secret_XXXX.json
   ```
   Sign in with the Google account that owns the Drive folder. The script prints three values.

### 3. Add GitHub secrets
In this repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
| --- | --- |
| `GDRIVE_ROOT_FOLDER_ID` | folder ID from step 1 |
| `GDRIVE_CLIENT_ID` | from step 2.4 |
| `GDRIVE_CLIENT_SECRET` | from step 2.4 |
| `GDRIVE_REFRESH_TOKEN` | from step 2.4 |

*Alternative:* if the folder is in a **Shared Drive** (Google Workspace), you can use a service account instead:
add it as a member of the Shared Drive and store its JSON key as `GDRIVE_SERVICE_ACCOUNT_JSON`
(skip the three OAuth secrets). Service accounts can't upload into a normal "My Drive" folder.

### 4. Run it
Push to `main`, or go to **Actions → Sync PYQs to Google Drive → Run workflow**. Tick *dry run* to preview the changes first.

The workflow runs with `--prune`, so a PDF you delete from `source/` is moved to the Drive trash too.
Don't add files by hand inside the synced folder; they'll be trashed on the next run. Keep extra material in a separate Drive folder.

## Running locally

```bash
pip install -r requirements.txt
python scripts/build_chapters.py            # builds dist/
export GDRIVE_ROOT_FOLDER_ID=... GDRIVE_CLIENT_ID=... GDRIVE_CLIENT_SECRET=... GDRIVE_REFRESH_TOKEN=...
python scripts/sync_to_drive.py --dry-run   # preview
python scripts/sync_to_drive.py --prune     # upload
```
