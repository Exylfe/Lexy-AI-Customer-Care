"""
Lexy — System Tray Launcher for Windows.
Starts the web dashboard in background and shows a tray icon.
"""

import os
import sys
import threading
import webbrowser
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lexy_tray")

# ─── Configuration ─────────────────────────────────────────────

DASHBOARD_PORT = 5050
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(APP_DIR, "lexy.ico")


def start_dashboard():
    """Start the Flask web dashboard in a background thread."""
    sys.path.insert(0, APP_DIR)
    from frontends.web_dashboard import app
    logger.info("Starting Lexy dashboard on %s", DASHBOARD_URL)
    app.run(host="127.0.0.1", port=DASHBOARD_PORT, debug=False, use_reloader=False)


def open_dashboard():
    """Open the dashboard in the default browser."""
    webbrowser.open(DASHBOARD_URL)


def main():
    # Start dashboard in background
    t = threading.Thread(target=start_dashboard, daemon=True)
    t.start()

    # Open browser on startup
    threading.Timer(2.0, open_dashboard).start()

    # Try to use pystray for system tray icon
    try:
        import pystray
        from PIL import Image

        # Create a simple icon or load from file
        if os.path.exists(ICON_PATH):
            icon_image = Image.open(ICON_PATH)
        else:
            # Fallback: create a simple colored square
            icon_image = Image.new("RGB", (64, 64), color=(108, 99, 255))

        def on_open(icon, item):
            open_dashboard()

        def on_exit(icon, item):
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("📊 Open Dashboard", on_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🚪 Exit", on_exit),
        )

        icon = pystray.Icon("lexy", icon_image, "Lexy AI Assistant", menu)
        icon.run()

    except ImportError:
        logger.warning("pystray not installed — running in console mode.")
        logger.info("Install with: pip install pystray pillow")
        logger.info("Dashboard running at %s", DASHBOARD_URL)
        # Keep the thread alive
        t.join()


if __name__ == "__main__":
    main()
