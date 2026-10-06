#!/usr/bin/env python3
"""Refresh the public repository index. No GitHub writes or deployment."""
import argparse
import datetime
import html
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'nebelwerfer41'
CATEGORIES = ('Production & PDF', 'Weather', 'Input testing', 'Other projects')

def safe_url(value):
    if not isinstance(value, str):
        return ''
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        return ''
    return value.strip()

def public_records(records):
    if not isinstance(records, list):
        raise ValueError('Invalid GitHub response: expected a list.')
    result = {}
    for item in records:
        if not isinstance(item, dict):
            raise ValueError('Invalid repository entry.')
        if item.get('private') is not False:
            continue
        owner = item.get('owner', {}).get('login', '')
        name = item.get('name', '')
        if owner.lower() != OWNER.lower():
            continue
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise ValueError('Invalid repository name.')
        if name.lower() in {OWNER.lower(), OWNER.lower()+'.github.io'}:
            continue
        license_info = item.get('license') or {}
        result[name] = {
            'name': name, 'owner': {'login': OWNER}, 'private': False,
            'description': item.get('description') or '',
            'language': item.get('language') or '',
            'homepage': safe_url(item.get('homepage')),
            'archived': bool(item.get('archived', False)),
            'fork': bool(item.get('fork', False)),
            'license': {'spdx_id': license_info.get('spdx_id') or ''},
        }
    return sorted(result.values(), key=lambda item: item['name'].lower())

def fetch_repositories(opener=urllib.request.urlopen):
    records = []
    for page in range(1, 101):
        url = f'https://api.github.com/users/{OWNER}/repos?type=owner&per_page=100&page={page}'
        request = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': f'{OWNER}-catalog',
        })
        with opener(request, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError('GitHub did not return a repository list.')
        records.extend(batch)
        if len(batch) < 100:
            return public_records(records)
    raise ValueError('Too many pages: update stopped without saving.')

def escaped(value):
    return html.escape(str(value), quote=True)

def render(records, overrides, date):
    records = public_records(records)
    groups = {name: [] for name in CATEGORIES}
    profile_rows = []
    for repo in records:
        name = repo['name']
        custom = overrides.get(name, {})
        category = custom.get('category', 'Other projects')
        if category not in groups:
            category = 'Other projects'
        title = custom.get('title', name)
        description = custom.get('description') or repo['description'] or 'No description available.'
        url = f'https://github.com/{OWNER}/{name}'
        homepage = safe_url(custom.get('homepage') or repo['homepage'])
        labels = [repo['language'] or 'Resource']
        if repo['archived']:
            labels.append('Archived')
        if repo['fork']:
            labels.append('Fork')
        app_link = f'<a href="{escaped(homepage)}" aria-label="Open {escaped(title)}">Open</a>' if homepage else ''
        card = f'<article class="project"><div class="project-top"><h3><a href="{escaped(url)}">{escaped(title)}</a></h3><span class="type">{escaped(" · ".join(labels))}</span></div><p>{escaped(description)}</p><div class="project-bottom"><code>{escaped(name)}</code><div class="links">{app_link}<a href="{escaped(url)}" aria-label="Repository {escaped(title)}">Code</a></div></div></article>'
        groups[category].append((custom.get('order', 999), name, card))
        clean = lambda text: html.escape(str(text)).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ').replace('[', '&#91;').replace(']', '&#93;')
        profile_rows.append(f'| [{clean(title)}]({url}) | {clean(description)} |')
    sections = []
    for number, (category, cards) in enumerate(groups.items(), 1):
        if cards:
            body = ''.join(card for _, _, card in sorted(cards))
            sections.append(f'<section id="group-{number}" aria-labelledby="heading-{number}"><h2 id="heading-{number}">{escaped(category)} <span>{len(cards)}</span></h2><div class="grid">{body}</div></section>')
    contents = ''.join(sections) or '<p>There are no public repositories in the catalog.</p>'
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>nebelwerfer41 — Public Repository Index</title><meta name="description" content="Public repositories by nebelwerfer41, with descriptions and links to the source code."><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='8' fill='%232c433b'/%3E%3Ctext x='32' y='44' text-anchor='middle' font-family='monospace' font-size='36' fill='white'%3E41%3C/text%3E%3C/svg%3E"><link rel="stylesheet" href="styles.css"></head><body><a class="skip" href="#catalog">Skip to catalog</a><div class="shell"><header><a class="brand" href="https://github.com/{OWNER}">nebelwerfer41</a><a href="https://github.com/{OWNER}?tab=repositories">GitHub profile ↗</a></header><main id="catalog"><div class="intro"><h1>Public Repository Index</h1><p>Film production and PDF tools, weather forecasts, and input testing.</p><p class="meta">{len(records)} repositories · updated on {escaped(date)}</p></div>{contents}</main><footer><p>Features, setup instructions, and limitations are documented in each repository’s README.</p><p>This index includes public repositories. The profile and catalog repositories are excluded.</p></footer></div></body></html>
'''
    profile = f'# nebelwerfer41\n\nPublic repositories: film production, PDFs, weather, and input testing.\n\n[Public Repository Index](https://{OWNER}.github.io/) · [GitHub profile](https://github.com/{OWNER})\n\n| Repository | Purpose |\n| --- | --- |\n'+'\n'.join(profile_rows)+'\n\nFeatures, setup instructions, and limitations are documented in each repository’s README.\n'
    return page, profile

def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def update(root=ROOT, offline=False):
    root = Path(root)
    cache_path = root/'data/repos.json'
    overrides = json.loads((root/'data/overrides.json').read_text(encoding='utf-8'))
    if offline:
        snapshot = json.loads(cache_path.read_text(encoding='utf-8'))
        records = public_records(snapshot['repositories'])
        date = snapshot['updated_at']
    else:
        records = fetch_repositories()
        date = datetime.datetime.now(ZoneInfo('Europe/Rome')).date().isoformat()
    page, profile = render(records, overrides, date)
    atomic_write(root/'index.html', page)
    atomic_write(root/'data/profile-README.md', profile)
    atomic_write(cache_path, json.dumps({'updated_at':date,'repositories':records}, ensure_ascii=False, indent=2)+'\n')
    return len(records)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Rebuild from the local snapshot without contacting GitHub.')
    args = parser.parse_args()
    try:
        count = update(offline=args.offline)
    except Exception as error:
        parser.exit(1, f'Update failed: {error}\n')
    print(f'Local catalog updated: {count} repositories. No push or deployment performed.')
