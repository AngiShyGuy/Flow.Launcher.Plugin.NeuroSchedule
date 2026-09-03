import sys
import os
import json
import webbrowser
import urllib.request
import urllib.parse
import subprocess
from datetime import datetime, timezone, timedelta

# ── Flow Launcher base class ──────────────────────────────────────────────────

class FlowLauncher:
    def __init__(self):
        self.settings = {}
        if len(sys.argv) > 1:
            try:
                data = json.loads(sys.argv[1])
                method = data.get("method", "")
                params = data.get("parameters", [])

                self.settings = data.get("settings") or data.get("Settings") or {}

                handler = getattr(self, method, None)
                if handler:
                    result = handler(*params)
                    if result is not None:
                        print(json.dumps({"result": result}))
                else:
                    print(json.dumps({"result": []}))
            except Exception:
                print(json.dumps({"result": []}))

    def get_bool_setting(self, key, default=True):
        """Helper to parse boolean values safely from settings dict."""
        val = self.settings.get(key, default)
        if isinstance(val, bool):
            return val
        return str(val).lower() == "true"


# ── Plugin config ─────────────────────────────────────────────────────────────

API_URL          = "https://schedule-api.nwero.net/schedule"
TWITCH_URL       = "https://www.twitch.tv/vedal987"
WEB_SCHEDULE_URL = "https://neuro.appstun.net/schedule/"
CORE_STREAMERS   = {"Neuro", "Evil", "Vedal"}

FILTER_MAP = {
    "neuro": "Neuro",
    "evil":  "Evil",
    "vedal": "Vedal",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_schedule():
    """Fetch the JSON schedule from the API with a tight timeout for startup reliability."""
    try:
        req = urllib.request.Request(
            API_URL,
            headers={"Accept": "application/json", "User-Agent": "NeuroScheduleFL/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return []


def parse_timestamp(timestamp_str):
    """Parse ISO timestamp into a timezone-aware datetime object."""
    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        return None


def format_time(dt, use_12h=False):
    """Convert datetime → human-readable string in local time."""
    if not dt:
        return ""
    dt_local = dt.astimezone()
    if use_12h:
        return dt_local.strftime("%a %d %b · %I:%M %p")
    return dt_local.strftime("%a %d %b · %H:%M")


def get_stream_icon(streamers):
    """Determine icon path based on streamers present."""
    streamers_set = set(streamers) if streamers else set()

    if "Neuro" in streamers_set and "Evil" in streamers_set:
        return "assets/twins.png"
    elif "Neuro" in streamers_set:
        return "assets/neuro.png"
    elif "Evil" in streamers_set:
        return "assets/evil.png"
    elif "Vedal" in streamers_set:
        return "assets/vedal.png"

    return "icon.png"


def make_gcal_url(title, streamers, dt, duration_hours=2.5):
    """Generate a pre-filled Google Calendar event creation URL in local time."""
    if not dt:
        return TWITCH_URL

    dt_local = dt.astimezone()
    dt_end   = dt_local + timedelta(hours=duration_hours)

    start_str = dt_local.strftime("%Y%m%dT%H%M%S")
    end_str   = dt_end.strftime("%Y%m%dT%H%M%S")

    who = " & ".join(streamers) if streamers else "Neuro / Evil"

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_str}/{end_str}",
        "details": f"Streamer(s): {who}\nWatch live at {TWITCH_URL}",
        "location": TWITCH_URL,
    }

    if dt_local.tzinfo and hasattr(dt_local.tzinfo, "key") and dt_local.tzinfo.key:
        params["ctz"] = dt_local.tzinfo.key

    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def make_result(title, subtitle, icon="icon.png", context_data=None, url=TWITCH_URL, score=0):
    """Shorthand for building a result dict with strict position scoring."""
    result = {
        "Title":    title,
        "SubTitle": subtitle,
        "IcoPath":  icon,
        "Score":    score,
        "JsonRPCAction": {
            "method":     "open_url",
            "parameters": [url],
        },
    }
    if context_data:
        result["ContextData"] = context_data
    return result


# ── Plugin class ──────────────────────────────────────────────────────────────

class NeuroSchedule(FlowLauncher):

    def query(self, search=""):
        tokens = search.strip().lower().split()

        # General settings
        time_setting       = str(self.settings.get("time_format", ""))
        use_12h            = "12-Hour" in time_setting
        hide_past_default  = self.get_bool_setting("hide_past_by_default", False)
        
        action_setting     = str(self.settings.get("default_action", ""))
        primary_url        = WEB_SCHEDULE_URL if "Web" in action_setting else TWITCH_URL

        # Stream visibility settings
        show_neuro         = self.get_bool_setting("show_neuro", True)
        show_evil          = self.get_bool_setting("show_evil", True)
        show_twins         = self.get_bool_setting("show_twins", True)
        show_vedal         = self.get_bool_setting("show_vedal", True)
        show_collab        = self.get_bool_setting("show_collab", True)

        # Keyword blacklist filter
        excluded_raw       = str(self.settings.get("excluded_keywords", "")).strip()
        excluded_keywords  = [kw.strip().lower() for kw in excluded_raw.split(",") if kw.strip()]

        # Search tokens
        only_today    = "today" in tokens
        only_tomorrow = "tomorrow" in tokens
        only_next     = ("next" in tokens) or hide_past_default
        only_collab   = "collab" in tokens
        target_streamers = [FILTER_MAP[t] for t in tokens if t in FILTER_MAP]

        schedule = fetch_schedule()

        if not schedule:
            return [make_result(
                "Couldn't reach the schedule API",
                "Check your internet connection — press Enter to open schedule site",
                icon="icon.png",
                url=WEB_SCHEDULE_URL,
                score=1000
            )]

        now_utc   = datetime.now(timezone.utc)
        now_local = datetime.now().astimezone()
        today_date    = now_local.date()
        tomorrow_date = today_date + timedelta(days=1)

        filtered_entries = []

        for entry in schedule:
            if not entry.get("live", False):
                continue

            streamers     = entry.get("streamers", [])
            streamers_set = set(streamers) if streamers else set()
            title         = entry.get("title", "Stream")
            timestamp     = entry.get("timestamp", "")
            dt            = parse_timestamp(timestamp)

            # Categorize stream
            is_twins  = ("Neuro" in streamers_set) and ("Evil" in streamers_set)
            is_neuro  = ("Neuro" in streamers_set) and not is_twins
            is_evil   = ("Evil" in streamers_set) and not is_twins
            is_vedal  = ("Vedal" in streamers_set)
            is_collab = any(s for s in streamers_set if s not in CORE_STREAMERS)

            # Filter out based on settings checkboxes
            if is_twins and not show_twins:
                continue
            if is_neuro and not show_neuro:
                continue
            if is_evil and not show_evil:
                continue
            if is_vedal and not show_vedal:
                continue
            if is_collab and not show_collab:
                continue

            # Filter out based on excluded title keywords
            title_lower = title.lower()
            if any(kw in title_lower for kw in excluded_keywords):
                continue

            # Query token filters
            if dt:
                dt_local = dt.astimezone()

                if only_today and dt_local.date() != today_date:
                    continue

                if only_tomorrow and dt_local.date() != tomorrow_date:
                    continue

                if only_next and dt < now_utc:
                    continue

            if only_collab and not is_collab:
                continue

            if target_streamers and not any(ts in streamers_set for ts in target_streamers):
                continue

            filtered_entries.append((dt, streamers, title, timestamp))

        # Explicitly sort chronologically by datetime
        filtered_entries.sort(key=lambda x: (x[0] is None, x[0]))

        results = []

        for idx, (dt, streamers, title, timestamp) in enumerate(filtered_entries):
            who  = " & ".join(streamers) if streamers else "Neuro / Evil"
            when = format_time(dt, use_12h=use_12h) if dt else timestamp
            icon = get_stream_icon(streamers)

            context_data = {
                "title":     title,
                "streamers": streamers,
                "who":       who,
                "when":      when,
                "timestamp": timestamp,
                "icon":      icon,
            }

            results.append(make_result(
                title,
                f"{who}  ·  {when}",
                icon=icon,
                context_data=context_data,
                url=primary_url,
                score=10000 - (idx * 100),
            ))

        if not results:
            valid_dts = [
                dt for e in schedule if e.get("live", False)
                and (dt := parse_timestamp(e.get("timestamp", "")))
            ]
            all_past = len(valid_dts) > 0 and all(dt < now_utc for dt in valid_dts)

            if all_past and only_next:
                results.append(make_result(
                    "No upcoming streams (New schedule pending)",
                    "Current schedule has ended. New schedule usually drops on Tuesday!",
                    icon="icon.png",
                    url=primary_url,
                    score=1000
                ))
            elif only_today:
                results.append(make_result(
                    "No streams scheduled for today",
                    "Try 'ns tomorrow' or clear search to view the full week.",
                    icon="icon.png",
                    url=primary_url,
                    score=1000
                ))
            elif only_tomorrow:
                results.append(make_result(
                    "No streams scheduled for tomorrow",
                    "Clear search to view all scheduled streams.",
                    icon="icon.png",
                    url=primary_url,
                    score=1000
                ))
            elif tokens or excluded_keywords:
                results.append(make_result(
                    "No streams match active filters",
                    "Try clearing search terms or check plugin settings/blacklist.",
                    icon="icon.png",
                    url=primary_url,
                    score=1000
                ))
            else:
                results.append(make_result(
                    "No streams found",
                    "Check back later for schedule updates!",
                    icon="icon.png",
                    url=primary_url,
                    score=1000
                ))

        return results

    def context_menu(self, data):
        """Triggered when pressing Shift+Enter on an entry."""
        if not isinstance(data, dict):
            return []

        title     = data.get("title", "Stream")
        streamers = data.get("streamers", [])
        who       = data.get("who", "")
        when      = data.get("when", "")
        timestamp = data.get("timestamp", "")
        icon      = data.get("icon", "icon.png")

        dt        = parse_timestamp(timestamp)
        
        duration_raw = str(self.settings.get("stream_duration", "2.5"))
        try:
            duration = float(duration_raw.split()[0])
        except Exception:
            duration = 2.5

        gcal_url  = make_gcal_url(title, streamers, dt, duration_hours=duration) if dt else TWITCH_URL
        info_text = f"{title} ({who}) - {when}"

        if dt:
            epoch = int(dt.timestamp())
            discord_text = f"<t:{epoch}:F> - <t:{epoch}:R> - {title}"
        else:
            discord_text = f"{title} ({when})"

        return [
            {
                "Title":    "Open Twitch Channel",
                "SubTitle": TWITCH_URL,
                "IcoPath":  icon,
                "JsonRPCAction": {
                    "method":     "open_url",
                    "parameters": [TWITCH_URL],
                },
            },
            {
                "Title":    "Open Web Schedule",
                "SubTitle": WEB_SCHEDULE_URL,
                "IcoPath":  "icon.png",
                "JsonRPCAction": {
                    "method":     "open_url",
                    "parameters": [WEB_SCHEDULE_URL],
                },
            },
            {
                "Title":    "Add to Google Calendar",
                "SubTitle": f"Create event ({duration}h) with automatic notifications",
                "IcoPath":  "icon.png",
                "JsonRPCAction": {
                    "method":     "open_url",
                    "parameters": [gcal_url],
                },
            },
            {
                "Title":    "Copy Discord Format",
                "SubTitle": discord_text,
                "IcoPath":  "icon.png",
                "JsonRPCAction": {
                    "method":     "copy_to_clipboard",
                    "parameters": [discord_text],
                },
            },
            {
                "Title":    "Copy Stream Details",
                "SubTitle": info_text,
                "IcoPath":  "icon.png",
                "JsonRPCAction": {
                    "method":     "copy_to_clipboard",
                    "parameters": [info_text],
                },
            },
        ]

    def open_url(self, url):
        """Open a URL in the default browser."""
        webbrowser.open(url)

    def copy_to_clipboard(self, text):
        """Copy text to Windows clipboard cleanly without spawning a CMD window."""
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.run(
                "clip",
                input=text.encode("utf-16"),
                check=True,
                creationflags=creation_flags
            )
        except Exception:
            pass


if __name__ == "__main__":
    sys.path.append(os.path.dirname(__file__))
    try:
        NeuroSchedule()
    except Exception:
        pass