# PMC-journal-filter-downloader
Batch download PubMed/MEDLINE open-access articles from PMC as XML or PDF, with JCR-based journal whitelist/blacklist filtering and preprint exclusion.

This folder downloads open-access PMC articles for a PubMed-style query and
optionally filters them by a journal whitelist or blacklist.

## Files

- `download_xml.py` downloads full-text JATS XML.
- `download_pdf.py` downloads PDF files.
- `whitelist.csv` is the journal whitelist.
- `blacklist.csv` is the journal blacklist.
- `readme.md` is this file.

## What is downloaded

Both scripts keep only articles that are:

- open access,
- indexed in PubMed/MEDLINE,
- tagged as journal articles,
- not preprints.

The search query is sent to Europe PMC. XML files are downloaded from
Europe PMC, and PDF files are downloaded from the PMC AWS Open Data bucket.

## Before running

Install the only dependency:

```bash
pip install requests
```

The CSV files must stay in the same folder as the scripts. Each CSV uses these
columns:

```text
journal_name,issn,eissn
```

Both `issn` and `eissn` are used for matching.

## Settings

Open either script and edit the values near the top:

```python
QUERY = '(PC12) AND (growth)'
MODE = 'whitelist'
```

Change `MODE` to one of:

- `whitelist`: only journals present in `whitelist.csv` are downloaded.
- `blacklist`: journals present in `blacklist.csv` are excluded; all other
  journals are downloaded.

You can also change `MAX_WORKERS` to control parallel download speed.

## Run

```bash
python download_xml.py
python download_pdf.py
```

Each script first counts eligible articles and prints the number. It then asks:

```text
Download them now? (yes/no):
```

Type `yes` to download, or `no` to stop.

## Notes

- The first counting step pages through all matching records, so a very broad
  query can take a few minutes before the confirmation prompt appears.
- Downloads run in parallel. Increase `MAX_WORKERS` for more speed, but keep it
  reasonable to avoid being rate-limited.
