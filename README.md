# YTKACE source for SideStore / AltStore (unofficial)

An auto-updating SideStore/AltStore source for [itzzace/ytkace](https://github.com/itzzace/ytkace).

Add this URL in SideStore → **Sources** → **+**:

```
https://raw.githubusercontent.com/konakarthik12/ytkace-source/main/source.json
```

## How it works

- A GitHub Action runs every 3 hours (and on demand) and reads YTKACE's latest releases.
- For each `.ipa` it reads `Info.plist` with HTTP Range requests (only a few hundred KB), to get the
  bundle ID, version and minimum iOS. Results are cached in `cache.json`.
- `source.json` links straight to the upstream release files; nothing is re-hosted.
- The iOS 17+ and iOS 16 builds are listed as separate versions with `minOSVersion` / `maxOSVersion`,
  so SideStore offers the one that fits your device.

## Limitation

SideStore checks that the IPA's version matches the source, and YTKACE IPAs carry YouTube's version
(e.g. `21.47.6`), not YTKACE's. So an update only shows when the bundled YouTube version changes. The
iOS 16 build has stayed on YouTube `21.33.6`, so its newer YTKACE releases won't show as updates.

Not affiliated with YTKACE.
