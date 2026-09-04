# Neuro Schedule — Flow Launcher Plugin

A [Flow Launcher](https://www.flowlauncher.com/) plugin that lets you check Neuro-sama's upcoming stream schedule without leaving your keyboard.

> Schedule data is sourced from [Cloudburst's Unofficial Neuro-sama Schedule API](https://github.com/cloudburstwan/neuro-schedule-api).

![Neuro Schedule Plugin](https://i.imgur.com/zFAcwth.png)
## Usage

Type `neuro` (the default keyword) in Flow Launcher to pull up the week's stream schedule. Results are sorted chronologically and show the stream title, who's streaming, and the time in your local timezone.

### Search keywords

You can narrow results by typing extra words after the keyword:

| Query | What it shows |
|---|---|
| `neuro` | All scheduled streams |
| `neuro today` | Only today's streams |
| `neuro tomorrow` | Only tomorrow's streams |
| `neuro next` | Only upcoming streams (hides past ones) |
| `neuro collab` | Only collab streams |
| `neuro neuro` | Only Neuro streams |
| `neuro evil` | Only Evil streams |
| `neuro vedal` | Only Vedal streams |

Keywords can be combined — e.g. `neuro neuro today` shows only Neuro's streams today.

### Actions

- **Enter** — Opens the Twitch channel (default) or web schedule (configurable in settings)
- **Shift+Enter** — Opens a context menu with additional actions:
  - Open Twitch Channel (Opens [www.twitch.tv/vedal987](https://www.twitch.tv/vedal987))
  - Open Web Schedule (Opens [neuro.appstun.net/schedule](https://neuro.appstun.net/schedule/))
  - Add to Google Calendar (pre-filled event with configurable duration)
  - Export iCal File (Saves `.ics` file to Downloads)
  - Copy Discord Format (uses the same format as the official Discord schedule)
  - Copy Stream Details (plain text)

## Settings

Open plugin settings in Flow Launcher to configure:

| Setting | Description |
|---|---|
| **Time Format** | Display times in 24-hour (`20:00`) or 12-hour AM/PM (`8:00 PM`) |
| **Hide past streams by default** | Automatically filter out streams that have already started |
| **Primary Action (Enter)** | Choose whether Enter opens the Twitch channel or the web schedule |
| **Calendar Event Duration** | Default event length for calendar events (2h, 2.5h, or 3h) |
| **Show Neuro / Evil / Twins / Vedal / Collab Streams** | Toggle visibility for each streamer category |
| **Exclude Streams by Title Keywords** | Comma-separated list of words — any stream with a matching title is hidden (e.g. `Karaoke, Minecraft`) |

## Credits

Schedule API by [Cloudburst](https://github.com/cloudburstwan/) · Web schedule by [Äppi](https://neuro.appstun.net/)