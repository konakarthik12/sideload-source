# Sideload Apps: one auto-updating SideStore / AltStore source

Add this URL in SideStore → **Sources** → **+**:

```
https://raw.githubusercontent.com/konakarthik12/ytkace-source/main/source.json
```

| App | Comes from |
| --- | --- |
| YTKACE | [itzzace/ytkace](https://github.com/itzzace/ytkace) releases |
| Reynard Browser | [minh-ton/reynard-browser](https://github.com/minh-ton/reynard-browser)'s own source |
| Nuvio Enhanced | [luqmanfadlli/NuvioMobile-Enhanced](https://github.com/luqmanfadlli/NuvioMobile-Enhanced)'s own source (stable) |

Not affiliated with any of these projects. Nothing is re-hosted: every download links to the developer's own release.

## Adding an app

Edit [`apps.json`](apps.json) and push. The Action regenerates `source.json` right away, and every 3 hours after that.

**App that already has a source:**

```json
{ "type": "source", "url": "https://example.com/source.json", "bundleIdentifier": "com.example.app" }
```

Optional: `"maxVersions": 10` to keep only the newest versions, `"overrides": { "name": "..." }` to change fields.

**App that only has GitHub releases:**

```json
{
  "type": "releases",
  "repo": "owner/name",
  "assetPattern": "\\.ipa$",
  "name": "App Name",
  "subtitle": "One line",
  "localizedDescription": "Longer description",
  "iconURL": "icons/app.png",
  "category": "utilities"
}
```

Optional: `"prereleases": true`, `"maxReleases": 10`, `"bundleIdentifier"` (otherwise read from the IPA).
Bundle ID, version and minimum iOS are read from each IPA's `Info.plist` with HTTP Range requests (a few
hundred KB per IPA, cached in `cache.json`). If one release has IPAs for different iOS versions, each gets
`minOSVersion` / `maxOSVersion` so SideStore offers the right one.

To check for updates immediately:

```bash
gh workflow run update-source.yml -R konakarthik12/ytkace-source
```

If an upstream is down, that app's previous entry is kept.

## Limitation for `releases` apps

SideStore requires the source's version to match the IPA's own version. YTKACE IPAs carry YouTube's version
(e.g. `21.47.6`), so a YTKACE update only shows when the bundled YouTube version changes. Its iOS 16 build has
stayed on YouTube `21.33.6`, so newer YTKACE releases for iOS 16 won't show as updates.
