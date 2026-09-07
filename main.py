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


def parse_timestamp(raw):
    """
    Parse a timestamp value from the API into a timezone-aware datetime, or None.
    """
    if raw is None:
        return None, False

    timestamp_str = str(raw).strip()

    if timestamp_str.lower() in ("", "none", "null", "n/a", "tbd", "unknown"):
        return None, False

    if "T" not in timestamp_str and ":" not in timestamp_str:
        try:
            d = datetime.strptime(timestamp_str[:10], "%Y-%m-%d")
            return d.replace(tzinfo=timezone.utc), True
        except ValueError:
            pass

    iso_str = timestamp_str[:-1] + "+00:00" if timestamp_str.endswith(("Z", "z")) else timestamp_str
    try:
        return datetime.fromisoformat(iso_str), False
    except ValueError:
        pass

    return None, False


def get_relative_time_str(dt, now_utc):
    """Calculate human-readable relative time (e.g., 'In 2 hours' or '1 day ago')."""
    if not dt or not now_utc:
        return ""

    diff_seconds = (dt - now_utc).total_seconds()

    if diff_seconds >= 0:
        if diff_seconds < 3600:
            mins = int(diff_seconds // 60)
            if mins < 1:
                return "In < 1 min"
            return f"In {mins} min" if mins == 1 else f"In {mins} mins"
        elif diff_seconds < 86400:
            hours = int(diff_seconds // 3600)
            return f"In {hours} hour" if hours == 1 else f"In {hours} hours"
        else:
            days = int(diff_seconds // 86400)
            return f"In {days} day" if days == 1 else f"In {days} days"
    else:
        past_sec = abs(diff_seconds)
        if past_sec < 3600:
            mins = int(past_sec // 60)
            if mins < 1:
                return "< 1 min ago"
            return f"{mins} min ago" if mins == 1 else f"{mins} mins ago"
        elif past_sec < 86400:
            hours = int(past_sec // 86400)
            return f"{hours} hour ago" if hours == 1 else f"{hours} hours ago"
        else:
            days = int(past_sec // 86400)
            return f"{days} day ago" if days == 1 else f"{days} days ago"


def format_time(dt, use_12h=False, date_only=False, now_utc=None):
    """
    Convert a datetime → human-readable string in local time with relative time attached.
    """
    if not dt:
        return "Time TBD"
    dt_local = dt.astimezone()
    if date_only:
        return dt_local.strftime("%a %d %b · Time TBD")

    base_time = dt_local.strftime("%a %d %b · %I:%M %p") if use_12h else dt_local.strftime("%a %d %b · %H:%M")

    if now_utc is not None:
        rel_str = get_relative_time_str(dt, now_utc)
        if rel_str:
            return f"{base_time} ({rel_str})"

    return base_time


def get_stream_icon(streamers_set):
    """Determine icon path directly using the streamers set."""
    if "Vedal" in streamers_set:
        return "assets/vedal.png"
    elif "Neuro" in streamers_set and "Evil" in streamers_set:
        return "assets/twins.png"
    elif "Neuro" in streamers_set:
        return "assets/neuro.png"
    elif "Evil" in streamers_set:
        return "assets/evil.png"

    return "icon.png"


def make_gcal_url(title, streamers, dt, date_only=False, duration_hours=2.5):
    """Generate a Google Calendar creation URL with support for both timed and All-Day events."""
    if not dt:
        return TWITCH_URL

    dt_local = dt.astimezone()
    clean_streamers = [str(s).strip() for s in streamers if s and str(s).strip()] if streamers else []
    who = " & ".join(clean_streamers) if clean_streamers else "Neuro / Evil"

    if date_only:
        start_str = dt_local.strftime("%Y%m%d")
        end_str   = (dt_local + timedelta(days=1)).strftime("%Y%m%d")
        dates_param = f"{start_str}/{end_str}"
    else:
        dt_end    = dt_local + timedelta(hours=duration_hours)
        start_str = dt_local.strftime("%Y%m%dT%H%M%S")
        end_str   = dt_end.strftime("%Y%m%dT%H%M%S")
        dates_param = f"{start_str}/{end_str}"

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": f"Streamer(s): {who}\nWatch live at {TWITCH_URL}",
        "location": TWITCH_URL,
    }

    if not date_only and dt_local.tzinfo and hasattr(dt_local.tzinfo, "key") and dt_local.tzinfo.key:
        params["ctz"] = dt_local.tzinfo.key

    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def create_ics_content(title, streamers, dt, date_only=False, duration_hours=2.5):
    """Construct a standard RFC 5545 iCalendar string."""
    clean_streamers = [str(s).strip() for s in streamers if s and str(s).strip()] if streamers else []
    who = " & ".join(clean_streamers) if clean_streamers else "Neuro / Evil"
    now_utc_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NeuroSchedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:neuro-stream-{int(dt.timestamp())}@neuro.appstun.net",
        f"DTSTAMP:{now_utc_str}",
        f"SUMMARY:{title}",
        f"DESCRIPTION:Streamer(s): {who}\\nWatch live at {TWITCH_URL}",
        f"LOCATION:{TWITCH_URL}",
    ]

    if date_only:
        start_str = dt.strftime("%Y%m%d")
        end_str = (dt + timedelta(days=1)).strftime("%Y%m%d")
        ics_lines.append(f"DTSTART;VALUE=DATE:{start_str}")
        ics_lines.append(f"DTEND;VALUE=DATE:{end_str}")
    else:
        dt_utc = dt.astimezone(timezone.utc)
        end_utc = dt_utc + timedelta(hours=duration_hours)
        ics_lines.append(f"DTSTART:{dt_utc.strftime('%Y%m%dT%H%M%SZ')}")
        ics_lines.append(f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}")

    ics_lines.append("END:VEVENT")
    ics_lines.append("END:VCALENDAR")

    return "\r\n".join(ics_lines)


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
        only_today       = "today" in tokens
        only_tomorrow    = "tomorrow" in tokens
        only_next        = ("next" in tokens) or hide_past_default
        only_collab      = "collab" in tokens
        target_streamers = {FILTER_MAP[t] for t in tokens if t in FILTER_MAP}

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
        all_valid_dts = []

        for entry in schedule:
            if not entry.get("live", False):
                continue

            timestamp     = entry.get("timestamp", "")
            dt, date_only = parse_timestamp(timestamp)
            
            if dt is not None:
                all_valid_dts.append(dt)

            raw_streamers = entry.get("streamers", [])
            streamers     = [str(s).strip() for s in raw_streamers if s and str(s).strip()] if isinstance(raw_streamers, list) else []
            streamers_set = set(streamers)
            title         = entry.get("title", "Stream")

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
            if excluded_keywords and any(kw in title.lower() for kw in excluded_keywords):
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

            if target_streamers and not (target_streamers & streamers_set):
                continue

            filtered_entries.append((dt, date_only, streamers, streamers_set, title, timestamp))

        # Sort chronologically; entries with no parseable time go to the bottom
        filtered_entries.sort(key=lambda x: (x[0] is None, x[0]))

        results = []

        for idx, (dt, date_only, streamers, streamers_set, title, timestamp) in enumerate(filtered_entries):
            who  = " & ".join(streamers) if streamers else ""
            when = format_time(dt, use_12h=use_12h, date_only=date_only, now_utc=now_utc)
            icon = get_stream_icon(streamers_set)

            subtitle = "  ·  ".join(p for p in (who, when) if p)

            context_data = {
                "title":     title,
                "streamers": streamers,
                "who":       who,
                "when":      when,
                "timestamp": timestamp,
                "date_only": date_only,
                "icon":      icon,
            }

            results.append(make_result(
                title,
                subtitle,
                icon=icon,
                context_data=context_data,
                url=primary_url,
                score=10000 - (idx * 100),
            ))

        if not results:
            all_past = len(all_valid_dts) > 0 and all(dt < now_utc for dt in all_valid_dts)

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
        who       = data.get("who", "").strip()
        when      = data.get("when", "").strip()
        timestamp = data.get("timestamp", "")
        icon      = data.get("icon", "icon.png")

        dt, date_only = parse_timestamp(timestamp)

        duration_raw = str(self.settings.get("stream_duration", "2.5"))
        try:
            duration = float(duration_raw.split()[0])
        except Exception:
            duration = 2.5

        if dt is not None:
            gcal_url     = make_gcal_url(title, streamers, dt, date_only=date_only, duration_hours=duration)
            gcal_sub     = "Open Google Calendar event form (All-Day Event)" if date_only else f"Open Google Calendar event form ({duration}h)"
            ical_sub     = "Save .ics file to Downloads (All-Day Event)" if date_only else f"Save .ics file to Downloads ({duration}h)"
            gcal_action  = {"method": "open_url", "parameters": [gcal_url]}
            ical_action  = {"method": "export_ical", "parameters": [title, streamers, timestamp]}
        else:
            gcal_sub    = "Time TBD — cannot create calendar event"
            ical_sub    = "Time TBD — cannot create calendar event"
            gcal_action = {"method": "open_url", "parameters": [WEB_SCHEDULE_URL]}
            ical_action = {"method": "open_url", "parameters": [WEB_SCHEDULE_URL]}

        header = f"{title} ({who})" if who else title
        info_text = f"{header} - {when}" if when else header

        if dt and not date_only:
            epoch = int(dt.timestamp())
            discord_text = f"<t:{epoch}:F> - <t:{epoch}:R> - {title}"
        elif dt and date_only:
            epoch = int(dt.timestamp())
            discord_text = f"<t:{epoch}:D> - {title} (time TBD)"
        else:
            discord_text = f"{title} - {when}" if when else title

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
                "SubTitle": gcal_sub,
                "IcoPath":  "icon.png",
                "JsonRPCAction": gcal_action,
            },
            {
                "Title":    "Export iCal File (.ics)",
                "SubTitle": ical_sub,
                "IcoPath":  "icon.png",
                "JsonRPCAction": ical_action,
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

    def export_ical(self, title, streamers, timestamp):
        """Dynamically build and save an .ics file to Downloads when selected."""
        dt, date_only = parse_timestamp(timestamp)
        if not dt:
            return

        duration_raw = str(self.settings.get("stream_duration", "2.5"))
        try:
            duration = float(duration_raw.split()[0])
        except Exception:
            duration = 2.5

        ics_content = create_ics_content(title, streamers, dt, date_only=date_only, duration_hours=duration)

        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
        filename = f"{safe_title}.ics" if safe_title else "stream.ics"

        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        file_path = os.path.join(downloads_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(ics_content)

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