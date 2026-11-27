#!/usr/bin/env python3
"""Build one combined SideStore/AltStore source (source.json) from apps.json.

Each entry in apps.json is one of:

  {"type": "source", "url": "<upstream source.json>", "bundleIdentifier": "..."}
      Copies that app straight from an existing AltStore/SideStore source.

  {"type": "releases", "repo": "owner/name", "assetPattern": "<regex>", ...}
      Builds the app from a GitHub repo's releases. Bundle ID, version and minimum iOS
      are read from each IPA's Info.plist with HTTP Range requests (a few hundred KB per
      IPA, cached in cache.json). IPAs are linked, never re-hosted.

If an upstream can't be reached, the app's previous entry in source.json is kept.
"""
import io
import json
import os
import plistlib
import re
import sys
import traceback
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remotezip import RemoteFile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "apps.json"
CACHE_PATH = ROOT / "cache.json"
SOURCE_PATH = ROOT / "source.json"

OWN_REPO = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
RAW_BASE = f"https://raw.githubusercontent.com/{OWN_REPO}/main"
UA = {"User-Agent": "sidestore-source-generator"}


def fetch_json(url, github_api=False):
    headers = dict(UA)
    if github_api:
        headers["Accept"] = "application/vnd.github+json"
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return json.load(r)


def rel_url(value):
    """Turn a repo-relative path like icons/x.png into a raw URL; leave full URLs alone."""
    if value and not re.match(r"https?://", value):
        return f"{RAW_BASE}/{value}"
    return value


# ---------------------------------------------------------------- type: source

def normalize_versions(app):
    """Convert legacy single-version apps (version/downloadURL at top level) to versions[]."""
    if app.get("versions"):
        return app
    if app.get("downloadURL"):
        app["versions"] = [{
            k2: app[k1] for k1, k2 in [
                ("version", "version"), ("versionDate", "date"), ("downloadURL", "downloadURL"),
                ("versionDescription", "localizedDescription"), ("size", "size"),
                ("minOSVersion", "minOSVersion"), ("maxOSVersion", "maxOSVersion"),
            ] if k1 in app
        }]
    return app


def app_from_source(entry):
    data = fetch_json(entry["url"])
    want = entry.get("bundleIdentifier")
    matches = [a for a in data["apps"] if not want or a.get("bundleIdentifier") == want]
    if not matches:
        raise RuntimeError(f"{want} not found in {entry['url']}")
    app = normalize_versions(dict(matches[0]))
    if entry.get("maxVersions"):
        app["versions"] = app["versions"][: entry["maxVersions"]]
    app.update(entry.get("overrides", {}))
    return app


# -------------------------------------------------------------- type: releases

def read_ipa_metadata(url):
    z = zipfile.ZipFile(io.BufferedReader(RemoteFile(url), 1 << 16))
    info_name = next(n for n in z.namelist() if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n))
    p = plistlib.loads(z.read(info_name))
    return {
        "bundleIdentifier": p["CFBundleIdentifier"],
        "version": p["CFBundleShortVersionString"],
        "buildVersion": str(p.get("CFBundleVersion", p["CFBundleShortVersionString"])),
        "minOSVersion": p.get("MinimumOSVersion", "14.0"),
        "privacy": {k: v for k, v in p.items() if k.startswith("NS") and k.endswith("UsageDescription")},
    }


def major(v):
    return int(v.split(".")[0])


def app_from_releases(entry, cache):
    repo = entry["repo"]
    pattern = re.compile(entry.get("assetPattern", r"\.ipa$"))
    releases = fetch_json(
        f"https://api.github.com/repos/{repo}/releases?per_page={entry.get('maxReleases', 10)}",
        github_api=True,
    )
    releases = [r for r in releases if not r["draft"] and (entry.get("prereleases") or not r["prerelease"])]

    versions, seen, privacy, bundle_id = [], set(), {}, entry.get("bundleIdentifier")
    for rel in releases:  # newest first
        tag = rel["tag_name"]
        ipas = []
        for a in rel["assets"]:
            if not a["name"].endswith(".ipa") or not pattern.search(a["name"]):
                continue
            url = a["browser_download_url"]
            if url not in cache:
                print(f"  reading {a['name']}", file=sys.stderr)
                cache[url] = read_ipa_metadata(url)
            ipas.append((a, cache[url]))

        # When a release has several IPAs for different iOS versions (e.g. an iOS 16 build),
        # list the highest-minimum one first and cap the others just below it.
        ipas.sort(key=lambda x: major(x[1]["minOSVersion"]), reverse=True)
        ceiling = None
        for a, meta in ipas:
            bundle_id = bundle_id or meta["bundleIdentifier"]
            if meta["bundleIdentifier"] != bundle_id:
                continue
            privacy.update(meta["privacy"])
            # SideStore requires the source version to equal the IPA's own version, so
            # builds that reuse a version only appear once (from the newest release).
            key = (meta["version"], meta["buildVersion"], meta["minOSVersion"])
            if key not in seen:
                seen.add(key)
                v = {
                    "version": meta["version"],
                    "buildVersion": meta["buildVersion"],
                    "date": rel["published_at"],
                    "localizedDescription": f"{tag} ({a['name']})\n\n{rel.get('body') or ''}".strip(),
                    "downloadURL": a["browser_download_url"],
                    "size": a["size"],
                    "minOSVersion": meta["minOSVersion"],
                }
                if ceiling:
                    v["maxOSVersion"] = f"{ceiling - 1}.99"
                versions.append(v)
            ceiling = major(meta["minOSVersion"])

    if not versions:
        raise RuntimeError(f"no matching IPAs in {repo} releases")

    app = {
        "name": entry.get("name", repo.split("/")[1]),
        "bundleIdentifier": bundle_id,
        "developerName": entry.get("developerName", repo.split("/")[0]),
        "subtitle": entry.get("subtitle", ""),
        "localizedDescription": entry.get("localizedDescription", "")
        + f"\n\nBuilt automatically from https://github.com/{repo}/releases.",
        "iconURL": rel_url(entry.get("iconURL", "icon.png")),
        "tintColor": entry.get("tintColor", "#3478F6"),
        "category": entry.get("category", "other"),
        "versions": versions,
        "appPermissions": {"entitlements": [], "privacy": privacy},
    }
    return app


# ------------------------------------------------------------------------ main

def main():
    config = json.loads(CONFIG_PATH.read_text())
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    previous = json.loads(SOURCE_PATH.read_text()) if SOURCE_PATH.exists() else {"apps": []}
    prev_by_key = {a.get("_key"): a for a in previous["apps"]}

    apps, failures = [], 0
    for entry in config["apps"]:
        key = entry.get("url") or entry.get("repo")
        print(f"{entry['type']}: {key}", file=sys.stderr)
        try:
            app = app_from_source(entry) if entry["type"] == "source" else app_from_releases(entry, cache)
            app["_key"] = key
        except Exception:
            failures += 1
            traceback.print_exc()
            app = prev_by_key.get(key) or next(
                (a for a in previous["apps"] if a.get("bundleIdentifier") == entry.get("bundleIdentifier")), None
            )
            if not app:
                continue
            print("  keeping previous entry", file=sys.stderr)
        apps.append(app)

    s = config["source"]
    source = {
        "name": s["name"],
        "identifier": s.get("identifier", f"io.github.{OWN_REPO.replace('/', '.').lower()}"),
        "subtitle": s.get("subtitle", ""),
        "description": s.get("description", ""),
        "sourceURL": f"{RAW_BASE}/source.json",
        "iconURL": rel_url(s.get("iconURL", "icon.png")),
        "tintColor": s.get("tintColor", "#3478F6"),
        "website": f"https://github.com/{OWN_REPO}",
        "featuredApps": [a["bundleIdentifier"] for a in apps],
        "apps": apps,
        "news": [],
    }

    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    SOURCE_PATH.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n")
    for a in apps:
        print(f"  {a['name']}: {len(a['versions'])} versions, latest {a['versions'][0]['version']}", file=sys.stderr)
    # Fail the run (so you get an email) only if every app failed.
    sys.exit(1 if failures and failures == len(config["apps"]) else 0)


if __name__ == "__main__":
    main()
