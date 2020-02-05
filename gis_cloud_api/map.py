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

 GIS Cloud Map class that controls maps on GIS Cloud.

"""

from .exception import handle_error
from .network_handler import GISCloudNetworkHandler
from ..qgis_api.logger import get_gc_publisher_logger

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudMap(object):
    """Class for handling GIS Cloud Maps."""

    def __init__(self, gc_api, qgis_api):
        """Initialize host, HTTP headers."""
        self.qgis_api = qgis_api
        self.gc_api = gc_api
        self.map_name = None
        self.map_id = None
        self.is_map_public = False

    def get_unique_map_name(self, query, count=1, maps=None):
        """Find maps by name, used to build a unique map name on GIS Cloud"""
        try:
            if count > 1:
                unique_map_name = "{0} {1}".format(query, count)
            else:
                unique_map_name = query

            if not maps:
                get_url = ("{0}1/maps.json?perpage=50&page=1" +
                           "&order_by=accessed:desc&query_on=name" +
                           "&query={1}&type=private").format(
                               self.gc_api.host, query)
                response = GISCloudNetworkHandler.blocking_request(
                    GISCloudNetworkHandler.GET,
                    get_url,
                    self.gc_api.user.apikey)
                if response["status_code"] == 200:
                    maps = response["response"]["data"]

            for gc_map in maps:
                if gc_map["name"] == unique_map_name:
                    return self.get_unique_map_name(query, count + 1, maps)

            return unique_map_name

        except Exception:
            LOGGER.info('Failed while getting maps', exc_info=True)
            return None

    def detach_map(self):
        """Deatch a map if user wants to publish as a new map"""
        self.map_id = None
        self.qgis_api.project.removeEntry('giscloud_project', 'save_as')

    def update_map(self):
        """Update existing map on GIS Cloud"""
        map_url = '{0}1/maps/{1}.json'.format(self.gc_api.host, self.map_id)
        crs = self.qgis_api.get_project_crs()
        payload = {'name': str(self.map_name),
                   'proj4': crs['proj4'],
                   'units': crs['units']}
        if crs['epsg'] is not None:
            payload['epsg'] = crs['epsg']

        LOGGER.info('Updating map: {}'.format(payload))

        GISCloudNetworkHandler.blocking_request(
            GISCloudNetworkHandler.PUT,
            map_url,
            self.gc_api.user.apikey,
            payload)

    def create_map(self, project_name):
        """Send request to create map on GIS Cloud."""
        post_url = '{}1/maps.json'.format(self.gc_api.host)
        crs = self.qgis_api.get_project_crs()
        payload = {'name': str(project_name),
                   'proj4': crs['proj4'],
                   'units': crs['units']}
        if crs['epsg'] is not None:
            payload['epsg'] = crs['epsg']

        self.qgis_api.layers_to_update = []

        LOGGER.info('Creating new map: {}'.format(payload))

        response = GISCloudNetworkHandler.blocking_request(
            GISCloudNetworkHandler.POST,
            post_url,
            self.gc_api.user.apikey,
            payload)
        if response["status_code"] == 201:
            self.map_id = int(response['location'].split('/')[-1])
        else:
            handle_error(response)

        if self.is_map_public:
            map_url = '{0}1/maps/{1}.json'.format(
                self.gc_api.host, self.map_id)
            response = GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.GET,
                map_url,
                self.gc_api.user.apikey)

            resource_id = response['response']['resource_id']
            payload = {"username": "anonymous", "permission": "READ"}
            post_url = '{0}1/resources/{1}/permission.json'.format(
                self.gc_api.host, resource_id)
            GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.POST,
                post_url,
                self.gc_api.user.apikey,
                payload)

        self.qgis_api.project.writeEntry(
            "giscloud_project",
            "save_as",
            self.map_id)
