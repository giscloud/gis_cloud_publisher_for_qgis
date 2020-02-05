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

 This script is used for defining functions that communicate with GIS Cloud.
 There are various methods that send different types of HTTP requests in order
 to recreate QGIS project in GIS Cloud.

"""

import json
import os

from .exception import handle_error
from .map import GISCloudMap
from .network_handler import GISCloudNetworkHandler
from .user import GISCloudUser
from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.utils import GISCloudQgisUtils

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudCore(object):
    """Class for handling QGIS Api."""

    def __init__(self, path, qgis_api, controller):
        """Initialize host, HTTP headers."""
        self.host = 'https://api.giscloud.com/'
        self.editor_host = 'https://editor.giscloud.com/'
        self.path = os.path.join(path, '.gc_api_key')
        self.qgis_api = qgis_api
        self.controller = controller
        self.datasources_cache = {}
        self.qgis_groups = {}
        self.layers_cache_data = None
        self.files_to_delete_after_upload = []
        self.layers_to_delete = []
        self.giscloud_groups = {}
        self.giscloud_groups_map = {}
        self.current_gc_files = []
        self.map = GISCloudMap(self, qgis_api)
        self.user = GISCloudUser(self, qgis_api)

    def get_current_gc_files(self):
        """Get current files on GIS Cloud to avoid unnecessary upload"""
        directory = '/qgis/map' + str(self.map.map_id)

        try:
            get_url = "{}1/storage/fs{}/info.json".format(self.host, directory)
            response = GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.GET,
                get_url,
                self.user.apikey)
            current_gc_files = response['response']['data']
            self.current_gc_files = [f["name"] for f in current_gc_files]
        except Exception:
            self.current_gc_files = []

        LOGGER.debug("current_gc_files {}".format(self.current_gc_files))

    def clean_up_tmp_files(self):
        """Cleaning up all tmp files generated in the publish process"""
        for tmp_file in self.files_to_delete_after_upload:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        self.files_to_delete_after_upload = []

    def get_layers(self, use_cache=False):
        """Get layers that are on GIS Cloud to compare them locally."""
        self.qgis_api.layers_to_update = {}
        self.giscloud_groups = {}
        self.layers_to_delete = []
        LOGGER.info("gc api get_layers")
        if use_cache and self.layers_cache_data:
            data = self.layers_cache_data
            LOGGER.info("using cache")
        else:
            get_url = "{0}1/maps/{1}/layers.json?expand=options".format(
                self.host,
                self.map.map_id)
            response = GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.GET,
                get_url,
                self.user.apikey)

            if response["status_code"] == 200:
                data = response["response"]["data"]
            else:
                if response["status_code"] is not None:
                    self.map.map_id = None
                    self.qgis_api.project.writeEntry("giscloud_project",
                                                     "save_as",
                                                     self.map.map_id)
                return False
            self.layers_cache_data = data
        self.__process_layers(data)
        return True

    def __process_layers(self, data):
        qgis_layers = GISCloudQgisUtils.get_qgis_layers(self.qgis_api.project)
        for i in data:
            layer_id = i['id']
            delete_layer = False
            if i['type'] == "folder":
                source = json.loads(i["source"])
                if source["qgis"] == 1:
                    self.giscloud_groups[layer_id] = {"id": layer_id,
                                                      "name": i['name'],
                                                      "order": int(i['order']),
                                                      "parent": i['parent']}
            if 'options' in i and i['options']:
                for option in i['options']:
                    if option['option_name'] == 'QGIS_LAYER':
                        option_value = json.loads(option['option_value'])
                        if isinstance(option_value, dict):
                            layer_to_update = \
                                {"id": layer_id,
                                 "option_id": option['id'],
                                 "parent": i['parent'],
                                 "order": int(i['order']),
                                 "resource_id": i['resource_id'],
                                 "datasource_id": i['datasource_id']}
                            layer_to_update["datasource_timestamp"] = \
                                option_value["datasource_timestamp"] \
                                if "datasource_timestamp" in option_value \
                                else 0
                            layer_to_update["hash"] = \
                                option_value["hash"] \
                                if "hash" in option_value \
                                else 0

                            delete_layer = True
                            for layer in qgis_layers:
                                if layer.id() == option_value["id"]:
                                    delete_layer = False
                            if delete_layer:
                                if (option_value["id"] in
                                        self.qgis_api.layer_data_timestamps
                                        .keys()):
                                    del self.qgis_api.layer_data_timestamps[
                                        option_value["id"]]
                                    self.qgis_api.project.writeEntry(
                                        'giscloud_layers_data_state',
                                        'state',
                                        json.dumps(
                                            self.qgis_api
                                            .layer_data_timestamps))
                                self.layers_to_delete.append(layer_id)
                            else:
                                self.qgis_api.layers_to_update[
                                    option_value["id"]] = layer_to_update

    def delete_layers(self):
        """Delete layers on GIS Cloud that have been removed in QGIS"""
        for layer_id in self.layers_to_delete:
            layer_url = "{0}/1/layers/{1}.json".format(self.host, layer_id)
            try:
                GISCloudNetworkHandler.blocking_request(
                    GISCloudNetworkHandler.DELETE,
                    layer_url,
                    self.user.apikey)
            except Exception:
                LOGGER.debug('Delete layers failed while deleting\
                             layer/cache', exc_info=True)

    def check_group_for_layers(self, group):
        """Checking which active layers are belonging to a group"""
        for layer_id in group.findLayerIds():
            if (layer_id in self.qgis_api.layers_to_update or
                    layer_id in self.qgis_api.layers_to_upload_ids):
                return True
        return False

    def purge_folders(self):
        """Delete folders(groups) on GIS Cloud"""
        LOGGER.debug('Function purge_folders has started')

        for group_id in self.giscloud_groups:
            if group_id not in self.qgis_groups.values():
                LOGGER.info("deleting group {}".format(group_id))
                group_url = "{0}/1/layers/{1}.json".format(
                    self.host, group_id)
                try:
                    GISCloudNetworkHandler.blocking_request(
                        GISCloudNetworkHandler.DELETE,
                        group_url,
                        self.user.apikey)
                except Exception:
                    LOGGER.debug('Delete group failed', exc_info=True)

    def create_folders(self):
        """Create groups as folders on GIS Cloud."""
        self.qgis_api.group_parent = {}
        self.qgis_groups = {}
        LOGGER.debug('Function create_folder has started')
        groups = []
        self.qgis_api.get_groups_rec(groups,
                                     self.qgis_api.project.layerTreeRoot())

        for group in groups:

            if not self.check_group_for_layers(group):
                continue

            folder_data = {"mid": int(self.map.map_id), "name": group.name(),
                           "order": self.qgis_api.tree_order[group],
                           "type": 'folder', "source": '{"qgis":1}'}

            folder_data["parent"] = None
            if self.qgis_api.group_parent[group] in self.qgis_groups:
                folder_data["parent"] = \
                    self.qgis_groups[self.qgis_api.group_parent[group]]

            try:
                if group in self.giscloud_groups_map:
                    gc_group = self.giscloud_groups_map[group]
                    if (folder_data["name"] != gc_group["name"] or
                            folder_data["parent"] != gc_group["parent"] or
                            folder_data["order"] != gc_group["order"]):

                        LOGGER.debug('updating folder {} {}'.format(
                            gc_group["id"], folder_data))
                        put_url = self.host + '1/layers/' + \
                            gc_group["id"] + '.json'
                        response = GISCloudNetworkHandler.blocking_request(
                            GISCloudNetworkHandler.PUT,
                            put_url,
                            self.user.apikey,
                            folder_data)
                        LOGGER.info('Folder update status code: {}'.format(
                            response["status_code"]))
                    self.qgis_groups[group] = gc_group["id"]
                else:
                    post_url = self.host + '1/layers.json'
                    LOGGER.debug('creating folder {}'.format(folder_data))
                    response = GISCloudNetworkHandler.blocking_request(
                        GISCloudNetworkHandler.POST,
                        post_url,
                        self.user.apikey,
                        folder_data)
                    LOGGER.info('Folder create status code{}'.format(
                        response["status_code"]))
                    if response["status_code"] == 201:
                        folder_id = response['location']
                        folder_id = folder_id.split("/")[-1]
                        self.qgis_groups[group] = folder_id
                    else:
                        handle_error(response)

            except Exception:
                LOGGER.warning('Create folder failed {}'.format(folder_data),
                               exc_info=True)
