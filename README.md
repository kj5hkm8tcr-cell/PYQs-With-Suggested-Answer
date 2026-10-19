# CA PYQs with Suggested Answers: chapter-wise

Past year question papers (PYQs) from the last 10 attempts, with suggested answers,
arranged **Level → Subject → Chapter**, ready to upload to Google Drive.

The **`Google Drive Upload/`** folder in this repo is the finished product:

```
Google Drive Upload/
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
- **Chapter folders**: start the name with a two-digit number (`Chapter 01 - ...`) so they sort correctly.
- You don't need to track which attempts are the "last 10". Keep adding new attempts and
  older ones drop out of the chapter PDF on their own. To change 10, set a repository
  variable `MAX_ATTEMPTS` (Settings → Secrets and variables → Actions → Variables).
- **Already have a merged chapter PDF?** Put it directly in the subject folder
  (`source/CA Foundation/Paper 1 - Accounting/Chapter 03 - Something.pdf`) and it's copied as-is.

Upload from the GitHub website (open a folder → **Add file → Upload files**) or with git.
A GitHub Action then rebuilds the chapter PDFs and commits them to `Google Drive Upload/`
within a minute or two (see the **Actions** tab).

> GitHub rejects single files over 100 MB. Compress large scanned papers first.

## Uploading to Google Drive

1. On GitHub, click **Code → Download ZIP** and unzip it.
2. In Google Drive, drag the three level folders from `Google Drive Upload/`
   (`CA Foundation`, `CA Intermediate`, `CA Final`) into your Drive folder.
3. Share the Drive folder: **Share → General access → Anyone with the link → Viewer**.

When new attempts are added later, download again and upload the changed chapter PDFs.
To keep existing student links working, replace a file in Drive with
**right-click → File information → Manage versions → Upload new version** instead of deleting and re-uploading.

## Building on your own computer (optional)

```bash
pip install -r requirements.txt
python scripts/build_chapters.py
```
