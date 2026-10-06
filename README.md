# Public Repository Index

A static catalog of public repositories by nebelwerfer41. It consists of an HTML page, a CSS stylesheet, and a Python script that refreshes the repository list. The page makes no API requests when opened.

## Update the catalog

From the site folder, using Python 3.9 or later:

```sh
python3 tools/update_catalog.py
```

The script reads every page of GitHub’s public repository list, saves `data/repos.json`, and rebuilds `index.html` and `data/profile-README.md`. It uses no token and does not modify repositories, push commits, or deploy the site. If GitHub is unavailable or rate-limits the request, the update stops and keeps the previous version.

New repositories appear under **Other projects**, using their GitHub name, description, and language. Repositories without a description display “No description available.” The `nebelwerfer41` profile repository and the catalog repository are excluded. Forks and archived repositories are included and labeled. Deleted repositories and repositories that are no longer public disappear from the index after the next refresh. Overrides for repositories absent from the public list are not rendered.

To edit a description, assign a category, or add an application link, update `data/overrides.json`:

```json
{
  "repository-name": {
    "title": "Display name",
    "category": "Other projects",
    "description": "What the project does and which formats it supports.",
    "homepage": "https://example.com/",
    "order": 9
  }
}
```

Available categories: Production & PDF, Weather, Input testing, Other projects. Overrides take precedence over GitHub descriptions. If an override is omitted, the script uses the GitHub description. The initial eight repositories already have English descriptions and verified application links. For a new repository without a homepage, the script does not guess a Pages URL.

GitHub descriptions are used as written. If a new repository has a description in another language, add an English override; the script does not automatically translate it.

Rebuild from the local snapshot without a network request:

```sh
python3 tools/update_catalog.py --offline
```

The profile README is generated at `data/profile-README.md`. Review it before copying it to the GitHub profile repository. The script does not update individual repository READMEs, licenses, or metadata; those drafts are separate from the site.

## Local preview

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

Open http://127.0.0.1:8000.

## Run the script tests

```sh
python3 -m unittest discover -s tools -p 'test_*.py'
```

## License

[MIT](LICENSE). Modifications and derivative works, including commercial uses, are permitted provided copies or substantial portions retain the copyright notice and license. MIT does not require a visible credit in the interface or require derivative works to use the same license.

## Publication

The site is hosted at https://nebelwerfer41.github.io/ using GitHub Pages from the `main` branch root. After running the updater, review and commit the generated changes, then push to `main`. GitHub Pages publishes the committed static files. `.nojekyll` disables Jekyll processing. No scheduled update workflow is configured.

The script can later be run by GitHub Actions manually or on a schedule. No workflow that writes to GitHub or deploys the site has been added.

## Styling

The site uses `Tahoma, Verdana, sans-serif`, without downloading a web font. The browser uses Verdana when Tahoma is unavailable. Cards display the project name, language or resource type, description, and links.
