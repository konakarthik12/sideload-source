#!/usr/bin/env python3
"""Build a SideStore/AltStore source (source.json) from itzzace/ytkace GitHub releases.

The IPAs are not re-hosted: each version links straight to the upstream release asset.
Bundle ID, version and minimum iOS are read from each IPA's Info.plist with HTTP Range
requests, so only a few hundred KB are fetched per IPA. Results are cached in cache.json.
"""
import io
import json
import os
import plistlib
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remotezip import RemoteFile  # noqa: E402

UPSTREAM = "itzzace/ytkace"
ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "cache.json"
SOURCE_PATH = ROOT / "source.json"
MAX_RELEASES = 10

# e.g. konakarthik12/ytkace-source, set automatically in GitHub Actions
OWN_REPO = os.environ.get("GITHUB_REPOSITORY", "OWNER/ytkace-source")
RAW_BASE = f"https://raw.githubusercontent.com/{OWN_REPO}/main"


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ytkace-source"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def read_ipa_metadata(url):
    z = zipfile.ZipFile(io.BufferedReader(RemoteFile(url), 1 << 16))
    info_name = next(
        n for n in z.namelist() if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", n)
    )
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


def main():
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    releases = [r for r in api(f"repos/{UPSTREAM}/releases?per_page={MAX_RELEASES}") if not r["draft"]]

    versions, seen, privacy, bundle_id = [], set(), {}, None
    for rel in releases:  # newest first
        tag = rel["tag_name"]
        ipas = []
        for a in rel["assets"]:
            if not a["name"].endswith(".ipa"):
                continue
            url = a["browser_download_url"]
            if url not in cache:
                print(f"reading {a['name']}", file=sys.stderr)
                cache[url] = read_ipa_metadata(url)
            ipas.append((a, cache[url]))

        # Highest minimum iOS first; each lower build gets a maxOSVersion just below the next one.
        ipas.sort(key=lambda x: major(x[1]["minOSVersion"]), reverse=True)
        ceiling = None
        for a, meta in ipas:
            bundle_id = bundle_id or meta["bundleIdentifier"]
            if meta["bundleIdentifier"] != bundle_id:
                continue
            privacy.update(meta["privacy"])
            # SideStore checks that the IPA's version matches the source, so we must use
            # YouTube's version. Builds that reuse a YouTube version (e.g. the iOS 16 IPA)
            # only appear once, from the newest YTKACE release.
            key = (meta["version"], meta["buildVersion"], meta["minOSVersion"])
            if key not in seen:
                seen.add(key)
                v = {
                    "version": meta["version"],
                    "buildVersion": meta["buildVersion"],
                    "date": rel["published_at"],
                    "localizedDescription": f"YTKACE {tag.lstrip('v')} ({a['name']})\n\n{rel.get('body') or ''}".strip(),
                    "downloadURL": a["browser_download_url"],
                    "size": a["size"],
                    "minOSVersion": meta["minOSVersion"],
                }
                if ceiling:
                    v["maxOSVersion"] = f"{ceiling - 1}.99"
                versions.append(v)
            ceiling = major(meta["minOSVersion"])

    source = {
        "name": "YTKACE (unofficial)",
        "identifier": f"io.github.{OWN_REPO.split('/')[0].lower()}.ytkace-source",
        "subtitle": f"Auto-generated from github.com/{UPSTREAM} releases",
        "sourceURL": f"{RAW_BASE}/source.json",
        "iconURL": f"{RAW_BASE}/icon.png",
        "website": f"https://github.com/{UPSTREAM}",
        "apps": [
            {
                "name": "YTKACE",
                "bundleIdentifier": bundle_id,
                "developerName": "itzzace",
                "subtitle": "YouTube with SponsorBlock, downloads and more",
                "localizedDescription": "YTKACE is a free, open-source YouTube enhancer and downloader for iOS "
                "with SponsorBlock, background playback, player controls, and interface customization.\n\n"
                f"This source is generated automatically from https://github.com/{UPSTREAM}/releases.",
                "iconURL": f"{RAW_BASE}/icon.png",
                "tintColor": "#E62117",
                "category": "entertainment",
                "versions": versions,
                "appPermissions": {"entitlements": [], "privacy": privacy},
            }
        ],
        "news": [],
    }

    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    SOURCE_PATH.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(versions)} versions to {SOURCE_PATH.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
