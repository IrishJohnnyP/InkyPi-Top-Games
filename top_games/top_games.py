import base64
import logging
import os
import re
from datetime import datetime
from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session

logger = logging.getLogger(__name__)

WORKER_URL = "https://topgames.butternut.cloud"

class top_games(BasePlugin):

    def generate_settings_template(self):
        params = super().generate_settings_template()
        params["style_settings"] = True
        return params

    def _find_logo_dir(self):
        """Locate static/logos directory across system service paths."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_dirs = [
            "/home/john/InkyPi/src/static/logos",
            "/home/john/InkyPi/static/logos",
            os.path.abspath(os.path.join(current_dir, "../../static/logos")),
            "/usr/local/inkypi/src/static/logos",
        ]
        for d in candidate_dirs:
            if os.path.isdir(d):
                return d
        return candidate_dirs[0]

    def _get_local_logo_b64(self, school_name, logo_dir):
        if not school_name:
            return None

        safe_name = school_name.lower().replace('&', 'and')
        safe_name = re.sub(r'[^a-z0-9]', '_', safe_name)
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')

        for ext in ["png", "jpg", "svg"]:
            full_path = os.path.join(logo_dir, f"{safe_name}.{ext}")
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as img_f:
                        encoded = base64.b64encode(img_f.read()).decode("utf-8")
                        mime = "svg+xml" if ext == "svg" else "png"
                        return f"data:image/{mime};base64,{encoded}"
                except Exception as img_err:
                    logger.warning(f"[{self.name}] Error reading logo {full_path}: {img_err}")
        return None

    def _format_game_date(self, date_str):
        if not date_str or date_str == "TBD":
            return "TBD"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%m/%d")
        except Exception:
            return date_str

    def generate_image(self, settings, device_config):
        season = settings.get("season")
        week = settings.get("week")

        params = {}
        if season:
            params["season"] = season
        if week:
            params["week"] = week

        tz = device_config.get_config("timezone")
        if tz:
            params["tz"] = tz

        app_key = device_config.load_env_key("app_key")
        if app_key:
            params["app_key"] = app_key

        try:
            session = get_http_session()
            response = session.get(WORKER_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"[{self.name}] Failed to fetch top games: {e}")
            return None

        raw_games = data.get("games", [])
        logo_dir = self._find_logo_dir()

        # Process games, order home/away, and inject local Base64 logos
        formatted_games = []
        for g in raw_games:
            game_copy = dict(g)
            game_copy["formatted_date"] = self._format_game_date(g.get("date"))

            venue_status = g.get("venue_status", "Neutral")
            higher = dict(g.get("higher_team", {}))
            lower = dict(g.get("lower_team", {}))

            # Inject Base64 logos
            higher["logo"] = self._get_local_logo_b64(higher.get("name"), logo_dir)
            lower["logo"] = self._get_local_logo_b64(lower.get("name"), logo_dir)

            # Order teams: Home team first, or higher ranked team if neutral
            if venue_status == "Away":
                game_copy["team1"] = lower
                game_copy["team2"] = higher
            else:
                game_copy["team1"] = higher
                game_copy["team2"] = lower

            formatted_games.append(game_copy)

        formatted_games.sort(key=lambda x: x.get("higher_team", {}).get("rank") or 99)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        now_str = datetime.now().strftime("%b %d, %Y %I:%M %p")

        template_params = {
            "poll_name": data.get("poll", "AP TOP 25").upper(),
            "season": data.get("season", ""),
            "week": data.get("week", ""),
            "all_games": formatted_games,
            "last_updated": now_str,
            "plugin_settings": settings,
        }

        return self.render_image(
            dimensions=dimensions,
            html_file="top_games.html",
            css_file="top_games.css",
            template_params=template_params,
        )
