# -*- coding: utf-8 -*-
"""
/***************************************************************************
                                 A QGIS plugin
 GIS Cloud Publisher
                              -------------------
        copyright            : (C) 2019 by GIS Cloud Ltd.
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

 GIS Cloud User class that controls users on GIS Cloud.

"""

import os
import hashlib
import datetime

from .network_handler import GISCloudNetworkHandler
from ..qgis_api.version import QGIS_VERSION, GIS_CLOUD_PUBLISHER_VERSION
from ..qgis_api.logger import get_gc_publisher_logger

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudUser(object):
    """Class for handling QGIS Api."""

    def __init__(self, gc_api, qgis_api):
        """Initialize host, HTTP headers."""
        self.qgis_api = qgis_api
        self.gc_api = gc_api
        self.username = None
        self.session = None
        self.apikey = None
        self.is_user_premium = False
        self.user_md5 = None

    def is_auth_api(self):
        """Check if there exists apikey."""
        self.__get_api_key()
        return self.apikey is not None

    def auth_api_key(self, username, password, callback):
        """Authentification for apikey.


        Use HTTP request with username/password or session (for SSO)
        in order to obtain apikey. If login was succesful save apikey
        """
        if self.session:
            req = GISCloudNetworkHandler.auth_with_session(
                self.session)
            self.session = None
        elif username and password:
            req = GISCloudNetworkHandler.auth_with_login(username,
                                                         password)
        else:
            callback(False)
            return

        post_url = self.gc_api.host + '1/keys.json'

        data = {"key_desc": "QGIS Publisher v{}; QGIS/{}".format(
            GIS_CLOUD_PUBLISHER_VERSION, QGIS_VERSION), "scope": "qgis"}

        handler = GISCloudNetworkHandler.request(
            GISCloudNetworkHandler.POST,
            post_url,
            None,
            data,
            self.__auth_api_key_handle_reply,
            self.gc_api.controller.notify_user_login,
            req)

        handler.callback = callback

    def remove_api_key(self):
        """Remove api_key from plugin directory."""
        self.username = None
        self.session = None
        if os.path.exists(self.gc_api.path):
            os.remove(self.gc_api.path)

    def get_username(self, callback=None):
        """Get username"""
        try:
            self.is_user_premium = False
            get_url = "{0}1/users/current.json".format(self.gc_api.host)
            handler = GISCloudNetworkHandler.request(
                GISCloudNetworkHandler.GET,
                get_url,
                self.apikey,
                None,
                self.__get_username_reply_handler)
            handler.callback = callback
        except Exception:
            LOGGER.info('Failed while getting username', exc_info=True)
            callback()

    def api_key_check_validity(self):
        """Check if api_key exists."""

        get_url = "{0}1/users/current.json".format(self.gc_api.host)
        try:
            response = GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.GET,
                get_url,
                self.apikey)
            LOGGER.info('Request {}'.format(response))
            return response
        except Exception:
            LOGGER.debug("api_key_check_validity exception")
            raise

    def __get_username_reply_handler(self, status_code, data, handler):
        if status_code == (200 or 201):
            md5 = hashlib.md5()
            md5.update(data['id'].encode('utf-8'))
            self.user_md5 = md5.hexdigest()
            self.username = data['username']
            get_url = "{}1/users/current/subscriptions.json".format(
                self.gc_api.host)

            sub_handler = GISCloudNetworkHandler.request(
                GISCloudNetworkHandler.GET,
                get_url,
                self.apikey,
                None,
                self.__get_subscriptions_reply)
            sub_handler.callback = handler.callback
        else:
            handler.callback()

    def __get_subscriptions_reply(self, status_code, data, handler):
        """Get user subscription information"""

        if status_code == 200:
            current_time = (datetime.datetime.utcnow() -
                            datetime.datetime(1970, 1, 1)).total_seconds()

            for subscription in data['data']:
                if (subscription['app_instance_id'] == '100004' and
                        int(subscription['type']) >= 20 and
                        subscription['active'] == "t" and
                        (not subscription['ends'] or
                         subscription['ends'] > current_time)):
                    self.is_user_premium = True
                    break

        if handler.callback:
            handler.callback()

    def __auth_api_key_handle_reply(self, status_code, data, handler):
        # pylint: disable=W0613
        if status_code in (200, 201):
            self.apikey = data["value"]
            with open(self.gc_api.path, 'w+') as the_file:
                the_file.write(self.apikey)
                the_file.close()
                handler.callback(True)
        else:
            self.apikey = None
            handler.callback(False)

    def __get_api_key(self):
        """Read apikey.
        If login process has finished succesfully, then apikey is saved.
        """
        if os.path.exists(self.gc_api.path):
            api_key_file = open(self.gc_api.path, 'r')
            if api_key_file:
                self.apikey = api_key_file.readline()
                api_key_file.close()
        else:
            self.apikey = None
