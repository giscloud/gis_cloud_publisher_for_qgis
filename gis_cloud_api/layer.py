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

 GIS Cloud Layer class that controls layers on GIS Cloud.

"""

import hashlib
import json
import os
import zipfile

from .exception import handle_error
from .network_handler import GISCloudNetworkHandler
from ..qgis_api.logger import get_gc_publisher_logger
from ..qgis_api.utils import GISCloudQgisUtils

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudLayer(object):
    """Layer stores all atributes that are needed to translate it from
    QGIS to GIS Cloud."""

    def __init__(self, gc_api):
        self.id = None  # pylint: disable=C0103
        self.mid = None
        self.name = None
        self.epsg = None
        self.source = None
        self.type = [None, 100]
        self.styles = []
        self.alpha = None
        self.visible = None
        self.order = None
        self.parent = None
        self.x_min = None
        self.y_min = None
        self.x_max = None
        self.y_max = None
        self.datasource_id = None
        self.datasource_object = {}
        self.datasource_timestamp = 0
        self.should_updata_data = False
        self.source_to_convert = None
        self.files = []
        self.assets = []
        self.source_dir = None
        self.resource_id = None
        self.api = gc_api
        self.giscloud_layer = {}
        self.original_id = None
        self.full_update = True

    def hash(self):
        """We generate state to compare states between QGIS and GIS Cloud"""
        hash_input = json.dumps(self.data()) + \
            "datasource_timestamp:" + \
            str(self.datasource_timestamp)
        return hashlib.md5(hash_input.encode("UTF-8")).hexdigest()

    def data(self):
        """Returns layer data that can be used as payload"""
        data = {"mid": self.mid,
                "order": self.order,
                "parent": self.parent}

        data["name"] = self.name
        data["alpha"] = self.alpha
        data["type"] = self.type[0]
        data["visible"] = "t" if self.visible else "f"
        data["source"] = json.dumps(self.source)
        data['styles'] = json.dumps(self.styles)

        if self.epsg:
            data['epsg'] = self.epsg
        if self.x_min is not None:
            data["x_min"] = self.x_min
        if self.y_min is not None:
            data["y_min"] = self.y_min
        if self.x_max is not None:
            data["x_max"] = self.x_max
        if self.y_max is not None:
            data["y_max"] = self.y_max
        if self.datasource_id is not None:
            data["datasource_id"] = self.datasource_id
        return data

    def create_datasource(self):
        """Creating GIS Cloud datasource if needed"""
        if self.datasource_object:
            ds_type = self.datasource_object["type"]

            if ds_type not in self.api.datasources_cache:
                get_url = "{}1/datasources.json?type={}".format(
                    self.api.host, ds_type)
                response = GISCloudNetworkHandler.blocking_request(
                    GISCloudNetworkHandler.GET, get_url, self.api.user.apikey)
                self.api.datasources_cache[ds_type] = \
                    response['response']['data']

            for datasource in self.api.datasources_cache[ds_type]:
                if GISCloudQgisUtils.deep_obj_compare(self.datasource_object,
                                                      datasource,
                                                      decode_json=["params"]):
                    self.datasource_id = datasource["id"]
                    LOGGER.info("found datasource {}".format(datasource))
                    break

            if not self.datasource_id:
                if "datasource_id" in self.giscloud_layer:
                    if not self.full_update:
                        return
                    request_url = self.api.host + '1/datasources/' + \
                        str(self.giscloud_layer["datasource_id"]) + '.json'
                    response = GISCloudNetworkHandler.blocking_request(
                        GISCloudNetworkHandler.PUT,
                        request_url,
                        self.api.user.apikey,
                        self.datasource_object)
                    self.datasource_id = self.giscloud_layer["datasource_id"]
                else:
                    request_url = self.api.host + '1/datasources.json'
                    response = GISCloudNetworkHandler.blocking_request(
                        GISCloudNetworkHandler.POST,
                        request_url,
                        self.api.user.apikey,
                        self.datasource_object)
                    self.datasource_id = response["location"].split('/')[-1]
                LOGGER.debug(response)

    def upload_files(self, callback):
        """File uploader"""
        zip_to_upload = None
        directory = 'qgis/map' + str(self.api.map.map_id)

        GISCloudQgisUtils.get_layer_source_files(self, self.api)

        try:
            _files_to_zip = [_file for _file in self.files
                             if self.should_updata_data or
                             not _file[1] in self.api.current_gc_files]
            zip_to_upload = self.__zip_files(_files_to_zip)
        except Exception:
            LOGGER.error('Failed to zip file', exc_info=True)
            os.remove(zip_to_upload)
            raise Exception()

        if zip_to_upload:
            self.api.files_to_delete_after_upload.append(zip_to_upload)
            post_url = '{}1/storage/fs/{}'.format(self.api.host, directory)
            response = GISCloudNetworkHandler.upload_file(
                zip_to_upload,
                post_url,
                self.api.user.apikey,
                callback)
            LOGGER.info('File post status code {}'.format(
                response["status_code"]))

    def create_layer(self):
        """Create layer on GISCloud."""
        try:
            LOGGER.info('Layer name: {}'.format(self.name))
            LOGGER.info('Layer type: {}'.format(self.type))
            LOGGER.info('Layer order id: {}'.format(self.order))
        except Exception:
            LOGGER.error('Logger info has failed :', exc_info=True)
        post_url = self.api.host + '1/layers.json'

        if "id" in self.giscloud_layer:
            current_layer_id = self.giscloud_layer["id"]
            LOGGER.debug('Updating layer {}'.format(current_layer_id))
            req_url = self.api.host + '1/layers/{}.json'.format(
                current_layer_id)
            response = GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.PUT,
                req_url,
                self.api.user.apikey,
                self.data())

            if response["status_code"] != 204:
                LOGGER.warning('Layer update {} has failed'.format(self.name),
                               exc_info=True)
                handle_error(response)
            self.resource_id = self.giscloud_layer["resource_id"]
            return

        response = GISCloudNetworkHandler.blocking_request(
            GISCloudNetworkHandler.POST,
            post_url,
            self.api.user.apikey,
            self.data())

        LOGGER.debug('Upload layer status code {}'.format(
            str(response["status_code"])))
        LOGGER.debug('Create layer content {}'.format(response['response']))
        if not response["status_code"] in (200, 201, 204):
            LOGGER.warning('Layer upload {} has failed'.format(self.name),
                           exc_info=True)
            handle_error(response)
        else:
            last_layer_id = response['location'].split('/')[-1]
            req_url = self.api.host + '1/layers/' + last_layer_id + '.json'
            response = GISCloudNetworkHandler.blocking_request(
                GISCloudNetworkHandler.GET,
                req_url,
                self.api.user.apikey)
            if response["status_code"] == 200:
                self.resource_id = response["response"]["resource_id"]
            LOGGER.debug('Upload layer resource id {}'.format(
                str(self.resource_id)))

    def create_option(self):
        """Storing QGIS layer information on GIS Cloud to enable updates"""
        if self.resource_id:
            option_value = {"id": self.original_id,
                            "datasource_timestamp": self.datasource_timestamp,
                            "hash": self.hash()}
            payload = {"option_name": "QGIS_LAYER",
                       "option_value": json.dumps(option_value),
                       "option_type": 5}
            if "option_id" in self.giscloud_layer:
                if not self.full_update:
                    return
                request_type = GISCloudNetworkHandler.PUT
                request_url = "{}1/resources/{}/options/{}.json".format(
                    self.api.host,
                    self.resource_id,
                    self.giscloud_layer["option_id"])
            else:
                request_type = GISCloudNetworkHandler.POST
                request_url = "{}1/resources/{}/options.json".format(
                    self.api.host,
                    self.resource_id)

            response = GISCloudNetworkHandler.blocking_request(
                request_type,
                request_url,
                self.api.user.apikey,
                payload)
            if not response["status_code"] in (201, 204):
                LOGGER.error('Failed to create option, status code {}'.format(
                    response["status_code"]))
                handle_error(response)

    def __zip_files(self, files):
        """Zip given layer data and assets."""
        LOGGER.debug('Function zip_files started')
        LOGGER.debug('[zip] files {}'.format(files))

        if not files:
            return None

        zip_file_name = self.api.qgis_api.tmp_dir + '/' + self.id + '.zip'

        LOGGER.debug('[zip] archive {}'.format(zip_file_name))

        zipfile_handle = zipfile.ZipFile(zip_file_name,
                                         mode='w',
                                         compression=zipfile.ZIP_DEFLATED)
        for _file in files:
            zipfile_handle.write(_file[0], _file[1])
        zipfile_handle.close()
        LOGGER.debug('Function zip_files finished')
        return zip_file_name
