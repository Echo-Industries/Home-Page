import os
import requests
from urllib.parse import urlencode
from flask import Flask, render_template, redirect, url_for, session, request
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or "super_secret_tablet_key_change_in_prod"

# Enable ProxyFix so _external=True and cookies correctly detect HTTPS and proxy headers in Codespaces/cloud hosts
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Ensure cookies work properly under HTTPS proxies
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30

ERLC_API_KEY = os.getenv("ERLC_API_KEY", "")
ERLC_API_BASE = "https://api.erlc.gg/v1"

ROBLOX_CLIENT_ID = os.getenv("ROBLOX_CLIENT_ID", "")
ROBLOX_CLIENT_SECRET = os.getenv("ROBLOX_CLIENT_SECRET", "")


def fetch_erlc_player_team(username):
    """
    Queries the ER:LC API using the server API key to find the player's current team.
    Returns: (team_name_or_none, api_error_boolean)
    """
    if not ERLC_API_KEY:
        return None, True
    
    try:
        headers = {
            "server-key": ERLC_API_KEY,
            "Accept": "application/json"
        }
        response = requests.get(f"{ERLC_API_BASE}/server/players", headers=headers, timeout=5)
        
        if response.status_code == 200:
            players_data = response.json()
            for player in players_data:
                player_name = player.get("name") if isinstance(player, dict) else str(player).split(":")[0]
                if player_name and player_name.lower() == username.lower():
                    return player.get("team", "Civilian"), False
            return None, False
        else:
            print(f"ER:LC API Error Status [{response.status_code}]: {response.text}")
            return None, True
            
    except Exception as e:
        print(f"ER:LC API Exception: {e}")
        return None, True


@app.route("/")
def index():
    username = session.get('username')
    team = None
    api_error = False
    
    # Define your in-game time here (or connect it to your bot/webhook/custom calculation source)
    in_game_time = "12:49"

    if username:
        team, api_error = fetch_erlc_player_team(username)
        
    return render_template('index.html', team=team, api_error=api_error, in_game_time=in_game_time)


@app.route("/login")
def login():
    """
    Initiates Roblox OAuth2 authorization flow.
    """
    if not ROBLOX_CLIENT_ID:
        session['username'] = "YaBoi_Napoleon"
        return redirect(url_for('index'))
    
    redirect_uri = os.getenv("ROBLOX_REDIRECT_URI") or url_for('auth_callback', _external=True)
    
    roblox_auth_url = "https://apis.roblox.com/oauth/v1/authorize?" + urlencode({
        "client_id": ROBLOX_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile",
    })
    return redirect(roblox_auth_url)


@app.route("/auth/callback")
def auth_callback():
    """
    Handles callback from Roblox OAuth2, exchanges authorization code for token, and fetches user info.
    """
    code = request.args.get("code")
    if not code:
        print("OAuth Error: No code received in callback query args.")
        return redirect(url_for('index'))
    
    redirect_uri = os.getenv("ROBLOX_REDIRECT_URI") or url_for('auth_callback', _external=True)
    
    try:
        token_res = requests.post("https://apis.roblox.com/oauth/v1/token", data={
            "client_id": ROBLOX_CLIENT_ID,
            "client_secret": ROBLOX_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        })
        
        if token_res.status_code != 200:
            print(f"Roblox Token Exchange Failed [{token_res.status_code}]: {token_res.text}")
            return redirect(url_for('index'))

        token_data = token_res.json()
        access_token = token_data.get("access_token")

        if access_token:
            user_res = requests.get("https://apis.roblox.com/oauth/v1/userinfo", headers={
                "Authorization": f"Bearer {access_token}"
            })
            if user_res.status_code == 200:
                user_data = user_res.json()
                username = user_data.get("preferred_username") or user_data.get("name") or user_data.get("sub", "RobloxUser")
                session.clear()
                session.permanent = True
                session['username'] = username
                print(f"Successfully authenticated Roblox user: {username}")
            else:
                print(f"Failed to fetch userinfo [{user_res.status_code}]: {user_res.text}")
        else:
            print("Token response missing access_token.")
    except Exception as e:
        print(f"OAuth Exception: {e}")

    return redirect(url_for('index'))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)