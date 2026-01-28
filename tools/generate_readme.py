#!/usr/bin/env python3
"""
Generate README.md for profile DivineSMG/DivineSMG.

What this does:
- Reads config.yml
- Fetches public repos and languages via GitHub API
- Builds language percentages and simple progress bars
- Creates GitHub stat card and top-langs images (via github-readme-stats)
- Uses countapi + shields.io for a more reliable visitor counter
- Optionally embeds an animated GIF (from repo assets or external URL)
- Fetches recent public push events to show recent commit messages (if any)
- Writes README.md
"""
from __future__ import annotations
import os
import sys
import yaml
import requests
import urllib.parse
from datetime import datetime, timezone
from collections import defaultdict, OrderedDict

ROOT = os.path.dirname(os.path.dirname(__file__)) if os.path.dirname(__file__) else "."
CONFIG_PATH = os.path.join(ROOT, "config.yml")
OUT_PATH = os.path.join(ROOT, "README.md")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print("Missing config.yml. Please create one based on config.yml.example.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def gh_get(url, token=None, params=None):
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"
    r = requests.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_repos(username, token=None):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{username}/repos"
        params = {"per_page": 100, "page": page, "type": "owner", "sort": "pushed"}
        page_data = gh_get(url, token=token, params=params)
        if not page_data:
            break
        repos.extend(page_data)
        if len(page_data) < 100:
            break
        page += 1
    return repos

def fetch_languages_for_repos(repos, token=None):
    totals = defaultdict(int)
    for r in repos:
        # skip forks to better reflect your own code
        if r.get("fork"):
            continue
        lang_url = r.get("languages_url")
        if not lang_url:
            continue
        try:
            data = gh_get(lang_url, token=token)
        except Exception:
            continue
        for lang, bytes_count in data.items():
            totals[lang] += bytes_count
    return totals

def build_language_section(lang_totals):
    total_bytes = sum(lang_totals.values())
    if total_bytes == 0:
        return "No language data available.\n"

    # sort languages by bytes descending
    ordered = OrderedDict(sorted(lang_totals.items(), key=lambda kv: kv[1], reverse=True))
    lines = []
    lines.append("| Language | % | Progress |")
    lines.append("|---:|:---:|:---|")
    for lang, b in ordered.items():
        pct = (b / total_bytes) * 100
        pct_str = f"{pct:.1f}%"
        bar = progress_bar(pct, length=20)
        lines.append(f"| {lang} | {pct_str} | {bar} |")
    return "\n".join(lines) + "\n"

def progress_bar(percent, length=20):
    filled = int(round(percent / 100 * length))
    empty = length - filled
    return "█" * filled + "░" * empty

def fetch_recent_commits(username, token=None, limit=5):
    # Use public events endpoint and extract commits from PushEvent
    url = f"https://api.github.com/users/{username}/events/public"
    try:
        events = gh_get(url, token=token)
    except Exception:
        return []
    commits = []
    for ev in events:
        if ev.get("type") != "PushEvent":
            continue
        repo_name = ev.get("repo", {}).get("name")
        for c in ev.get("payload", {}).get("commits", []):
            sha = c.get("sha")
            msg = c.get("message")
            url = f"https://github.com/{repo_name}/commit/{sha}" if sha and repo_name else ""
            commits.append({"repo": repo_name, "message": msg, "url": url})
            if len(commits) >= limit:
                return commits
    return commits

def make_shield_link(label, color, logo):
    # simple shields.io for generic label (LinkedIn)
    label_enc = label.replace(" ", "%20")
    return f"https://img.shields.io/badge/{label_enc}-{color}?style=for-the-badge&logo={logo}&logoColor=white"

def build_readme(cfg, stats_img_urls, lang_section_md, recent_commits, last_updated):
    display_name = cfg.get("display_name", cfg.get("github_username"))
    bio_code = cfg.get("bio_code", "")
    linkedin = cfg.get("linkedin_url", "").strip()
    visitor_badge = cfg.get("visitor_badge_url")
    gif_url = cfg.get("gif_url")

    lines = []
    # Header
    lines.append(f"# {display_name}\n")
    # animated GIF (centered) if available
    if gif_url:
        lines.append('<p align="center">')
        lines.append(f'  <img src="{gif_url}" alt="Animated coder" width="320"/>')
        lines.append("</p>\n")

    # bio as code (C++ style line)
    if bio_code:
        lines.append("```cpp")
        lines.append(bio_code)
        lines.append("```\n")

    # Badges & cards row
    stats_card = stats_img_urls.get("stats")
    top_langs_card = stats_img_urls.get("top_langs")
    cards = []
    if stats_card:
        cards.append(f"![GitHub stats]({stats_card})")
    if top_langs_card:
        cards.append(f"![Top languages]({top_langs_card})")
    if visitor_badge:
        cards.append(f"[![Visitors]({visitor_badge})](https://github.com/{cfg.get('github_username')})")
    if linkedin:
        # shields.io badge linking to LinkedIn
        lines.append(f"[![LinkedIn]({make_shield_link('LinkedIn', 'blue', 'linkedin')})]({linkedin})  ")
    if cards:
        lines.append("  \n".join(cards) + "\n")

    # Languages section
    lines.append("## Languages\n")
    lines.append(lang_section_md)

    # Recent commits
    lines.append("## Recent activity\n")
    if not recent_commits:
        lines.append("_No public commits found yet — start committing!_\n")
    else:
        for c in recent_commits:
            if c.get("url"):
                lines.append(f"- [{c['message']}]({c['url']}) — _{c['repo']}_")
            else:
                lines.append(f"- {c['message']} — _{c['repo']}_")
        lines.append("")

    # Last updated
    lines.append(f"_Last updated: {last_updated} UTC_\n")

    # Footer / small note
    lines.append("---")
    lines.append("This README is generated automatically. Updates occur daily and whenever this repository receives a push.")
    return "\n".join(lines)

def build_visitor_badge(username):
    """
    Use countapi + shields.io dynamic JSON badge to show a visitor counter.
    This is more reliable than some third-party badge providers.
    """
    # CountAPI endpoint to increment and return the value
    countapi_endpoint = f"https://api.countapi.xyz/hit/{username}/{username}"
    # shields requires the endpoint URL to be url-encoded
    encoded = urllib.parse.quote_plus(countapi_endpoint)
    badge = (
        f"https://img.shields.io/badge/dynamic/json"
        f"?color=blue&label=Visitors&query=value&url={encoded}"
    )
    return badge

def find_gif_url(cfg, username):
    """
    Determine the gif URL to embed:
    - If external_gif_url configured, return it.
    - Else if gif_path configured and file exists in repo locally, return a relative path for local previews.
    - Else return the raw.githubusercontent.com URL (works once the file is committed).
    """
    external = cfg.get("external_gif_url", "").strip()
    gif_path = cfg.get("gif_path", "").strip()
    branch = cfg.get("branch_name", "Main").strip() or "Main"

    if external:
        return external

    if not gif_path:
        return ""

    local_path = os.path.join(ROOT, gif_path)
    if os.path.exists(local_path):
        # For local preview, use the local relative path (many editors will render this)
        return gif_path.replace("\\", "/")

    # Otherwise use the raw.githubusercontent URL (works after you push the file)
    # Repo is expected to be a profile repo named exactly as the username
    raw_url = f"https://raw.githubusercontent.com/{username}/{username}/{branch}/{gif_path}"
    return raw_url

def main():
    cfg = load_config()
    username = cfg.get("github_username") or os.getenv("GITHUB_ACTOR")
    if not username:
        print("No github_username in config.yml and GITHUB_ACTOR not set.", file=sys.stderr)
        sys.exit(1)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not found in environment. Requests will be unauthenticated and rate-limited.", file=sys.stderr)

    # GitHub-readme-stats endpoints (image cards)
    stats_img = f"https://github-readme-stats.vercel.app/api?username={username}&show_icons=true&count_private=false&theme=radical"
    top_langs_img = f"https://github-readme-stats.vercel.app/api/top-langs/?username={username}&layout=compact&langs_count=8&theme=radical"

    repos = fetch_repos(username, token=token)
    lang_totals = fetch_languages_for_repos(repos, token=token)
    lang_section_md = build_language_section(lang_totals)
    recent_commits = fetch_recent_commits(username, token=token, limit=5)
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # visitor badge (countapi + shields)
    visitor_badge = build_visitor_badge(username)

    # determine gif url (external or repo asset)
    gif_url = find_gif_url(cfg, username)

    stats_img_urls = {"stats": stats_img, "top_langs": top_langs_img}

    readme_md = build_readme(
        cfg={
            "github_username": username,
            "display_name": cfg.get("display_name"),
            "bio_code": cfg.get("bio_code"),
            "linkedin_url": cfg.get("linkedin_url"),
            "visitor_badge_url": visitor_badge,
            "gif_url": gif_url
        },
        stats_img_urls=stats_img_urls,
        lang_section_md=lang_section_md,
        recent_commits=recent_commits,
        last_updated=last_updated
    )

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(readme_md)

    print("README.md generated.")

if __name__ == "__main__":
    main()