# Our Roots

A genealogy website for an extended family. It keeps a record of every relative, draws an interactive family tree, and works out how any two people are related.

It started in 2020 as a single static page with a gallery and a hand-built tree of the nuclear family. It is now a Django application backed by a database.

## Features

- **Interactive family tree.** Built with Cytoscape.js and a dagre layout. People appear as cards with a photo or initials, couples meet at a rings symbol, and faint bands mark each generation. Type a name to follow anyone's line of ancestors and descendants, or click them on the tree. Switch between the whole family and a focused view N generations up or down from one person. Colour by gender, family branch or clan, and export the tree as a PNG.
- **Relationship finder.** Names the relationship between any two people: parents, grandparents, *great-great-uncle*, *second cousin twice removed*, half-siblings, spouses, in-laws and step-relatives. It also shows the line through the closest common ancestors.
- **Profiles.** Biography, life-event timeline, tagged photos, parents, partners (children grouped under each couple), siblings (half-siblings flagged) and a small tree of close family.
- **Editing in the site.** Add a new parent, partner or child directly from a profile. Link two people who are already recorded, or remove a link. Validation blocks impossible data, such as a person becoming their own ancestor or having a third biological parent.
- **Photo gallery.** Upload photos, tag people, filter by person, and view them in a lightbox.
- **Accounts and privacy.** Anyone can browse. Sign-ups wait for an administrator to approve them. Approved users join the **Family Editors** group, which can add and edit but cannot delete people. Visitors who are not signed in cannot see birth dates of living relatives.
- **Django admin.** The full data model is available in the admin, with inline editing of relationships and a one-click action to approve accounts.

## Data model

| Model | Purpose |
|---|---|
| `Person` | Names (including maiden name and nickname), gender, birth and death dates and places, clan or lineage, biography, photo, and a "needs review" flag |
| `Union` | A couple: marriage, customary marriage or partnership, with start and end dates. People can have several unions |
| `ParentChild` | A parent → child link (biological, adopted, step or foster), optionally tied to the union the child belongs to |
| `LifeEvent` | Timeline entries such as education, career, migration and achievements |
| `gallery.Photo` | An image, caption and date, with the people in it |
| `ContactMessage` | Messages from the contact form and account requests |

The graph algorithms (ancestry search, kinship naming, tree layout data) are in `genealogy/services/relations.py`. They load every relationship into memory once, so page cost does not grow with the depth of the family.

## Getting started

Requires Python 3.12+.

```powershell
git clone https://github.com/ngigijohn/githinjis-family.git
cd githinjis-family
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # optional; every setting has a development default
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_family      # optional: the family and photos from the original site
python manage.py runserver
```

Open http://127.0.0.1:8000. The admin is at `/admin/`.

> **Working inside Google Drive or OneDrive?** Sync clients add `desktop.ini` files and lock files, which breaks git and SQLite. Keep the virtual environment, `SQLITE_PATH` and `MEDIA_ROOT` outside the synced folder. For git, clone with `git clone --separate-git-dir=<folder outside Drive> …`.

### Seed data

`seed_family` loads the 12 people from the original concept page and the 16 original photos, resized. Every seeded person is flagged **needs review**. The original table was not fully consistent (for example, "John Ngigi" appears as both the grandfather and "self"), so confirm names and relationships and add dates. Use `--reset` to wipe people and photos first, and `--no-photos` to skip the images.

## Running the tests

```powershell
python manage.py test
```

The tests cover the kinship calculator (cousins, "removed", half-siblings, in-laws and step-relatives), relationship validation, the tree and search APIs, privacy rules, permissions, and the add/link/unlink flows.

## Configuration

Settings come from environment variables or `.env`:

| Variable | Default | Notes |
|---|---|---|
| `DEBUG` | `True` | Set to `False` in production |
| `SECRET_KEY` | development key | **Must** be set in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `CSRF_TRUSTED_ORIGINS` | – | e.g. `https://family.example.com` |
| `DATABASE_URL` | – | e.g. `postgres://user:pass@host:5432/our_roots`. SQLite is used when unset |
| `SQLITE_PATH` | `./db.sqlite3` | |
| `MEDIA_ROOT` | `./media` | Uploaded photos |
| `SERVE_MEDIA` | `False` | Let Django serve uploads on a small single-server deployment |
| `SITE_NAME` | `Our Roots` | The name shown in the header, titles and exports |

## Deploying

1. `pip install -r requirements-prod.txt` (adds PostgreSQL support and gunicorn).
2. Set `DEBUG=False`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `DATABASE_URL`.
3. `python manage.py migrate && python manage.py collectstatic --noinput`
4. Run `gunicorn config.wsgi`. WhiteNoise serves static files. Serve `MEDIA_ROOT` from your web server or object storage, or set `SERVE_MEDIA=True` on a small deployment.

The frontend loads Tailwind through its Play CDN so the project needs no Node build step. For a faster production site, generate a static stylesheet with the [Tailwind standalone CLI](https://tailwindcss.com/blog/standalone-cli) and replace the CDN script in `templates/base.html`.

## Project layout

```
config/       settings, URLs, WSGI/ASGI
genealogy/    people, unions, parent–child links, life events, tree/relationship views and JSON API
  services/relations.py   graph algorithms
  static/genealogy/js/    tree.js (Cytoscape explorer), picker.js (person search)
gallery/      photos and tagging
accounts/     sign-up with approval, login, Family Editors group
templates/    base layout and shared components
static/       design tokens (css/site.css) and images
```
