from datetime import datetime
from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session

WORKER_URL = "https://topgames.butternut.cloud"

class top_games(BasePlugin):

    def generate_settings_template(self):
        params = super().generate_settings_template()
        params["style_settings"] = True
        return params

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

        # --- TIMEZONE FIX ---
        tz = device_config.get_config("timezone")
        if tz:
            params["tz"] = tz
        # --------------------

        # --- SECURITY FIX ---
        app_key = device_config.load_env_key("app_key")
        if app_key:
            params["app_key"] = app_key
        # --------------------

        try:
            session = get_http_session()
            response = session.get(WORKER_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch top games: {e}")

        raw_games = data.get("games", [])

        # Process games and determine home/away team positioning
        formatted_games = []
        for g in raw_games:
            game_copy = dict(g)
            game_copy["formatted_date"] = self._format_game_date(g.get("date"))

            venue_status = g.get("venue_status", "Neutral")
            higher = g.get("higher_team", {})
            lower = g.get("lower_team", {})

            # Order teams: Home team first, or higher ranked team if neutral
            if venue_status == "Away":
                game_copy["team1"] = lower
                game_copy["team2"] = higher
            else:
                game_copy["team1"] = higher
                game_copy["team2"] = lower

            formatted_games.append(game_copy)

        # Sort strictly by the rank of the higher ranked team (1 to 10)
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
