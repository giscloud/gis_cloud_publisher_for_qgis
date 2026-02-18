# -*- coding: utf-8 -*-
"""
/***************************************************************************
                                 A QGIS plugin
 GIS Cloud Publisher
                              -------------------
        copyright            : (C) 2026 by GIS Cloud Ltd.
        email                : info@giscloud.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *  This program is distributed in the hope that it will be useful,        *
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of         *
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          *
 *  GNU General Public License for more details.                           *
 *                                                                         *
 *  This program is free software; you can redistribute it and/or modify   *
 *  it under the terms of the GNU General Public License as published by   *
 *  the Free Software Foundation; either version 2 of the License, or      *
 *  (at your option) any later version.                                    *
 *                                                                         *
 *  You should have received a copy of the GNU General Public License      *
 *  along with this program.  If not, see <https://www.gnu.org/licenses/>. *
 *                                                                         *
 ***************************************************************************/

 Local HTTP server for handling Google SSO callback.

 The default browser is used for Google authentication. After the user
 completes login, the auth server redirects to a localhost URL served by
 this server, which captures the session id and passes it back to the
 plugin.

"""

import threading

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
except ImportError:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
    from urlparse import urlparse, parse_qs

from .logger import get_gc_publisher_logger

LOGGER = get_gc_publisher_logger(__name__)

_SUCCESS_PAGE = """\
<!DOCTYPE html>
<html><head><title>GIS Cloud Login</title></head>
<body>
<p>Login successful! You can close this tab and return to QGIS.</p>
<script>window.history.replaceState(null, '', '/callback');</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    """HTTP handler for SSO callback requests."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/callback':
            params = parse_qs(parsed.query)
            session = params.get('session', [None])[0]
            if session:
                self.server.sso_session = session
                self._respond(200, _SUCCESS_PAGE)
            else:
                self._respond(400, 'Missing session')
        else:
            self._respond(404, 'Not found')

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def log_message(self, format, *args):
        pass


class SSOCallbackServer(object):
    """Ephemeral HTTP server on localhost that captures an SSO session."""

    def __init__(self):
        self._server = HTTPServer(('127.0.0.1', 0), _Handler)
        self._server.sso_session = None
        self._server.timeout = 1
        self.port = self._server.server_address[1]
        self._thread = None
        self._running = False

    def start(self):
        """Start serving in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._serve)
        self._thread.daemon = True
        self._thread.start()
        LOGGER.info('SSO callback server started on port %s', self.port)

    def _serve(self):
        while self._running and not self._server.sso_session:
            self._server.handle_request()

    def stop(self):
        """Shut down the server."""
        self._running = False
        try:
            self._server.server_close()
        except Exception:
            pass

    @property
    def session(self):
        """Return the captured session id, or None."""
        return self._server.sso_session

