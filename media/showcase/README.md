# CleanArr production showcase

[English](README.md) · [Русский](README_RU.md)

The root READMEs use these screenshots and a **33-second** walkthrough recorded
from a running **CleanArr v2.0.3** installation on **September 5, 2026**.

The deployed image was verified as the published `2.0.3` image with digest
`sha256:0e174f17d163ba46edbe82b5875a07a94b0df330c30e0fb2ee3bec7e45ae8864`.
The interface and data were rendered by the running application, without mocked
API responses or changes to the page source. These captures illustrate this
installation; they are not compatibility or accessibility certification.

## Watch

[Play or download the full MP4](cleanarr-demo.mp4) ·
[English captions](cleanarr-demo.en.vtt) ·
[Russian captions](cleanarr-demo.ru.vtt)

| Time | What happens |
| --- | --- |
| 00:00–00:04 | Review free space and connected service health. |
| 00:04–00:10 | Open the library, sorted by size. |
| 00:10–00:17 | Search for a movie. |
| 00:17–00:27 | Open the deletion preview and review affected services. |
| 00:27–00:33 | Cancel the confirmation and return to the library. |

**No deletion was confirmed or submitted for this recording.** The installation
was already in real-deletion mode; that setting was not changed. New CleanArr
installations default to dry-run. Displayed plans and service status describe
only the moment captured and do not grant permission for a later operation.

## Assets

- `library-dark.jpg` and `library-light.jpg`: library screenshots for the README's
  theme-aware hero.
- `dashboard-dark.jpg` and `dashboard-light.jpg`: storage and service overview.
- `preflight-dark.jpg`: mutation-free deletion preview with technical details
  closed.
- `cleanarr-demo.mp4`: actual browser frames sampled at approximately 8 fps,
  presented at 24 fps in a 1920 × 1080 H.264 video. Editorial headings and short
  opening/closing fades were added; pauses between recording segments were cut.
  There is no audio.
- `demo-preview.gif`: a short excerpt that plays once inline in the README.
- `demo-poster.jpg`: a still from the video, also used for reduced-motion readers.
- `cleanarr-demo.en.vtt` and `cleanarr-demo.ru.vtt`: synchronized caption files.

All gallery images are native browser captures stored in their returned JPEG
format. The navigation is collapsed to omit the account name; avatar initials
and aggregate counters remain visible. Service details,
credentials, private URLs, filesystem paths, account menus, playback history,
and individual activity records are excluded. Catalogue titles and artwork are part of
the intentionally captured library view; the UI is English and the configured
media metadata is Russian.

The inline GitHub player uses the [published video attachment](https://github.com/user-attachments/assets/6b831064-6d5e-4d4b-8154-d315432779b8)
from [Issue #36](https://github.com/mambastick/Cleanarr/issues/36). The committed
MP4 is the durable full-video fallback, and the expandable animated preview
remains available when the player cannot load. Both root READMEs share this
same asset set.
