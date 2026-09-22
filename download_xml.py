"""Download open-access PMC full-text XML for articles matching a query.

Only PubMed/MEDLINE-indexed journal articles are kept. Preprints are excluded.
Before downloading, the script counts eligible articles and asks for
confirmation.
"""

import csv
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


# ---------------- user settings ----------------
QUERY = '(PC12) AND (growth)'

# Change this single value to switch between journal filters:
#   'whitelist' -> only journals in the whitelist CSV are downloaded
#   'blacklist' -> only journals NOT in the blacklist CSV are downloaded
MODE = 'whitelist'

WHITELIST_FILE = 'whitelist.csv'
BLACKLIST_FILE = 'blacklist.csv'
OUTPUT_DIR = 'xml_output'

PAGE_SIZE = 1000
MAX_WORKERS = 8
# ----------------------------------------------


HERE = pathlib.Path(__file__).resolve().parent
SEARCH_URL = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
FULLTEXT_URL = 'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'


def normalize_issn(value):
    """Make an ISSN comparable by removing dashes/spaces and lowercasing."""
    return (value or '').replace('-', '').replace(' ', '').lower()


def load_journal_issns(csv_name):
    """Load all ISSN and eISSN values from a journal CSV into a set."""
    path = HERE / csv_name
    issns = set()
    with path.open(newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            for key in ('issn', 'eissn'):
                value = normalize_issn(row.get(key))
                if value:
                    issns.add(value)
    return issns


def build_search_query():
    """Build the Europe PMC query with the required restrictions."""
    return (
        f'({QUERY}) AND (OPEN_ACCESS:Y) '
        'AND (SRC:MED) AND (PUB_TYPE:"Journal Article")'
    )


def is_eligible(item, journal_issns, mode):
    """Return True if the article passes the active journal filter."""
    journal = ((item.get('journalInfo') or {}).get('journal') or {})
    article_issns = {
        normalize_issn(journal.get('issn')),
        normalize_issn(journal.get('essn')),
    }
    article_issns.discard('')

    if mode == 'whitelist':
        return bool(article_issns & journal_issns)
    if mode == 'blacklist':
        return not bool(article_issns & journal_issns)
    raise ValueError(f'Unknown MODE: {mode!r}')


def fetch_eligible(session, query, journal_issns, mode):
    """Return a list of {'pmcid': ...} for eligible articles."""
    eligible = []
    cursor = None
    page = 0

    while True:
        page += 1
        params = {
            'query': query,
            'format': 'json',
            'resultType': 'core',
            'pageSize': PAGE_SIZE,
        }
        if cursor is not None:
            params['cursorMark'] = cursor
        data = None
        for attempt in range(3):
            resp = session.get(
                SEARCH_URL,
                params=params,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            if 'resultList' in data:
                break
            print(f'  page {page} attempt {attempt + 1}: retrying ...', flush=True)
            time.sleep(2)
        else:
            print('Unexpected Europe PMC response:', resp.text[:1000], flush=True)
            raise RuntimeError('Europe PMC response is missing "resultList".')
        results = data['resultList']['result']

        for item in results:
            pmcid = item.get('pmcid')
            if pmcid and is_eligible(item, journal_issns, mode):
                eligible.append({'pmcid': pmcid})

        if page == 1:
            print(
                f'  page 1: hitCount={data.get("hitCount")}, '
                f'{len(eligible)} eligible so far',
                flush=True,
            )
        elif not results:
            print(f'  finished after {page - 1} pages', flush=True)
        else:
            print(f'  page {page}: {len(eligible)} eligible so far', flush=True)

        cursor = data.get('nextCursorMark')
        if not results:
            break

    return eligible


def download_xml(session, pmcid, out_dir):
    """Download one full-text XML file. Return (pmcid, ok, reason)."""
    url = FULLTEXT_URL.format(pmcid=pmcid)
    try:
        resp = session.get(url, timeout=120)
    except requests.RequestException as exc:
        return pmcid, False, str(exc)

    if resp.status_code != 200:
        return pmcid, False, f'HTTP {resp.status_code}'

    target = out_dir / f'{pmcid}.xml'
    target.write_bytes(resp.content)
    return pmcid, True, ''


def main():
    if MODE not in ('whitelist', 'blacklist'):
        sys.exit("MODE must be 'whitelist' or 'blacklist'.")

    if MODE == 'whitelist':
        journal_issns = load_journal_issns(WHITELIST_FILE)
        print(
            f'Using whitelist mode: {len(journal_issns)} ISSNs '
            f'loaded from {WHITELIST_FILE}',
            flush=True,
        )
    else:
        journal_issns = load_journal_issns(BLACKLIST_FILE)
        print(
            f'Using blacklist mode: {len(journal_issns)} ISSNs '
            f'loaded from {BLACKLIST_FILE}',
            flush=True,
        )

    query = build_search_query()
    print('Search query:', query, flush=True)

    session = requests.Session()
    print('Counting eligible articles...', flush=True)
    eligible = fetch_eligible(session, query, journal_issns, MODE)

    if not eligible:
        print('No eligible articles found. Nothing to download.')
        return

    print(f'\nEligible articles: {len(eligible)}', flush=True)
    answer = input('Download them now? (yes/no): ').strip().lower()
    if answer not in ('yes', 'y'):
        print('Aborted by user.')
        return

    out_dir = HERE / OUTPUT_DIR
    out_dir.mkdir(exist_ok=True)
    print(f'Downloading XML to {out_dir} ...', flush=True)

    success = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(download_xml, session, item['pmcid'], out_dir)
            for item in eligible
        ]
        for future in as_completed(futures):
            pmcid, ok, reason = future.result()
            if ok:
                success += 1
            else:
                failed += 1
                print(f'  FAIL {pmcid}: {reason}', flush=True)

    print(f'Done. Success: {success}, Failed: {failed}')


if __name__ == '__main__':
    main()
