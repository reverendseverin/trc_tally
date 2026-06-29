#!/usr/bin/env python3
"""TRC Tally — entry point.

Loads (and migrates) configuration, starts the MQTT client and one poller thread
per vMix machine, then serves the web management/monitoring interface. Everything
is controlled from the browser; there is no desktop window.
"""

import logging
import secrets

from tally_core import Core
from web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("trc_tally")


def main():
    core = Core()
    core.pollers.start_all()

    web_cfg = core.config.web
    app = create_app(core, secret_key=secrets.token_hex(16))

    port = int(web_cfg.get("port", 8070))
    log.info("TRC Tally web interface: http://localhost:%s", port)
    if web_cfg.get("password") == "changeme":
        log.warning("Default password in use — change 'web.password' in config.json")

    try:
        app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
    finally:
        log.info("Shutting down…")
        core.shutdown()


if __name__ == "__main__":
    main()
