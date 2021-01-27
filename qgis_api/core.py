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

 This script uses QGIS api to check which layers are suitable for upload.
 It also creates GIS Cloud Layer object, defines parent-child relationships
 between layers, does project analysis to detect if update is needed.

"""

import datetime
import json
import os
import os.path
import re

from difflib import SequenceMatcher

from qgis.core import QgsMapLayer, QgsProject, QgsUnitTypes
from qgis.core import QgsLayerTreeGroup, QgsLayerTreeLayer, QgsVectorLayer
from qgis.utils import iface

from .logger import get_gc_publisher_logger
from .utils import GISCloudQgisUtils
from .version import ISQGIS3
from ..gis_cloud_api.layer import GISCloudLayer
from ..gis_cloud_api.layer_style import GISCloudLayerStyle

if not ISQGIS3:
    from qgis.core import QGis

if ISQGIS3:
    from PyQt5.QtCore import Qt, QFileInfo
else:
    from PyQt4.QtCore import Qt, QFileInfo

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudQgisCore(object):
    """Class for handling QGIS api."""

    def __init__(self, path):
        """Initialize layers, map_name, supported datasources."""
        self.tmp_dir = path + '/tmp'
        self.tmp_dir_len = len(self.tmp_dir)
        self.gc_api = None
        self.tree_order = {}
        self.map_name = None
        self.map_name_override = None
        self.project = None
        self.layers_to_upload = None
        self.layers_to_update = {}
        self.use_all_layers = True
        self.last_analysis = {"time": 0}
        self.layer_data_timestamps = {}
        self.layers_to_upload_ids = {}
        self.group_parent = {}
        self.supported_file_source_vector = [
            'shp', 'mif', 'mid', 'gpx', 'sqlite',
            'tab', 'kml', 'json', 'geojson']

        self.supported_file_source_raster = [
            'jpeg', 'tif', 'tiff', 'jpg',
            'gif', 'sid', 'hgt', 'dem', 'ecw',
            'img', 'jp2', 'pdf', 'png']
        self.init_project()

    def init_project(self):
        """Initialize project instance"""
        self.project = QgsProject.instance()

    def get_map_name(self, use_override=False):
        """Return map_name from project instance fileName."""
        if use_override and self.map_name_override:
            return self.map_name_override
        self.map_name = QFileInfo(self.project.fileName()).fileName()
        if not self.map_name:   # define non existent map name as QGIS Untitled
            self.map_name = 'QGIS Untitled'
        else:
            self.map_name = os.path.splitext(self.map_name)[0]

        return self.map_name

    def get_tree_order(self):
        """Retrieving layer/group ordering."""
        self.tree_order = {}
        root = self.project.layerTreeRoot()

        max_order = self.get_tree_order_rec(root, 0)

        for i in self.tree_order:
            self.tree_order[i] = max_order - self.tree_order[i] + 1

    def get_tree_order_rec(self, root, order):
        """Recursive method for retrieving tree order"""
        for child in root.children():
            order = order + 1
            if child and isinstance(child, QgsLayerTreeGroup):
                self.tree_order[child] = order
                order = self.get_tree_order_rec(child, order)

            elif isinstance(child, QgsLayerTreeLayer) and child.layer():
                self.tree_order[child.layer()] = order

        return order

    def get_layers_to_upload(self, for_publish):
        """ Filter all layers that are not supported, not checked as visible or
        not in the list for update.

        This function creates a list of layers which are supported by GIS Cloud
        Unfiltered_layers are all layers that are currently loadeded(interface)
        """
        self.layers_to_upload = []
        self.layers_to_upload_ids = {}

        unfiltered_layers = GISCloudQgisUtils.get_qgis_layers(self.project)

        for layer in unfiltered_layers:
            provider_type = layer.providerType().lower()
            ext = layer.source().split('.')[-1].lower()

            if ISQGIS3:
                is_visible = self.project.layerTreeRoot().findLayer(
                    layer.id()).itemVisibilityChecked()
            else:
                is_visible = self.project.layerTreeRoot().findLayer(
                    layer.id()).isVisible() != Qt.Unchecked

            full_update = self.use_all_layers or not for_publish or is_visible
            if (full_update or layer.id() in self.layers_to_update) and \
                (isinstance(layer, QgsVectorLayer) or
                 ext in self.supported_file_source_raster or
                 provider_type in ("wms", "wfs")):

                self.layers_to_upload_ids[layer.id()] = True

                order = self.tree_order[layer]
                layer_object = GISCloudLayer(self.gc_api)
                layer_object.full_update = full_update
                layer_object.qgis_layer = layer
                layer_object.original_id = layer.id()

                if layer.id() in self.layers_to_update:
                    layer_object.giscloud_layer = \
                        self.layers_to_update[layer.id()]

                layer_object.order = order
                layer_object.name = layer.name().encode('utf-8').decode('utf-8')
                layer_object.mid = \
                    int(self.gc_api.map.map_id) if self.gc_api.map.map_id \
                    else None
                layer_object.qgis_layer = layer
                layer_object.visible = is_visible
                epsg = re.search("EPSG:(.*)", layer.crs().authid())
                if epsg:
                    layer_object.epsg = epsg.group(1)
                try:
                    layer_object.type = \
                        GISCloudQgisUtils.get_layer_geometry(layer)
                    if layer_object.type[0] is None:
                        continue
                except Exception:
                    LOGGER.error('Couldn\'t fetch geometry of the layer',
                                 exc_info=True)

                if layer_object.mid:
                    provider_type = layer.providerType().lower()
                    if provider_type == "wfs":
                        self.create_wfs_layer(layer, layer_object)
                    elif provider_type == "wms":
                        self.create_wms_layer(layer, layer_object)
                    else:
                        self.create_general_layer(layer, layer_object)

                self.layers_to_upload.insert(0, layer_object)

    def get_layers_file_source(self):
        """Get sources of layers."""
        layers_all = []

        for layer_object in self.layers_to_upload:
            layer = layer_object.qgis_layer
            group = GISCloudQgisUtils.get_qgis_layer_parent(layer,
                                                            self.project)
            parent = None
            if group:
                parent = self.gc_api.qgis_groups[group]
            if layer.id() in self.layers_to_update:
                if layer_object.full_update and layer_object.hash() == \
                   self.layers_to_update[layer.id()]["hash"]:
                    continue
                if not layer_object.full_update and \
                   layer_object.order == \
                   self.layers_to_update[layer.id()]["order"] and \
                   parent == self.layers_to_update[layer.id()]["parent"]:
                    continue

            layer_object.parent = parent

            if not layer_object.mid:
                layer_object.mid = int(self.gc_api.map.map_id)
                provider_type = layer.providerType().lower()
                if provider_type == "wfs":
                    self.create_wfs_layer(layer, layer_object)
                elif provider_type == "wms":
                    self.create_wms_layer(layer, layer_object)
                else:
                    self.create_general_layer(layer, layer_object)

            layers_all.append(layer_object)
            LOGGER.info('get_layers_file_source has finished')
        return layers_all

    def get_project_crs(self):
        """Getting project CRS to transfer it to a GIS Cloud map"""
        if ISQGIS3:
            crs = self.project.crs()
        else:
            crs = iface.mapCanvas().mapSettings().destinationCrs()

        proj4 = str(crs.toProj4())

        epsg = re.search("EPSG:(.*)", crs.authid())
        epsg = str(epsg.group(1)) if epsg is not None else None

        units = "meter"
        map_units = crs.mapUnits()
        if ISQGIS3:
            if map_units == QgsUnitTypes.DistanceDegrees:
                units = "degree"
            elif map_units == QgsUnitTypes.DistanceFeet:
                units = "foot"
        else:
            if map_units == QGis.Degrees:
                units = "degree"
            elif map_units == QGis.Feet:
                units = "foot"

        return {'proj4': proj4,
                'epsg': epsg,
                'units': units}

    def create_general_layer(self, layer, layer_object):
        """Processing Raster and Vector layers.
           Vector formats that aren't supported directly by GIS Cloud are
           converted to SQLlite format that GIS Cloud can read.
        """
        if layer.type() not in (QgsMapLayer.RasterLayer,
                                QgsMapLayer.VectorLayer):
            return

        source = layer.source()
        source = source.replace('\\', '/')

        if (layer.type() == QgsMapLayer.VectorLayer and
                (not os.path.isfile(source) or
                 not source.split('.')[-1].lower() in
                 self.supported_file_source_vector)):
            source = u'{0}/{1}.{2}'.format(self.tmp_dir,
                                           layer.id(),
                                           'sqlite')
            layer_object.source_to_convert = u'{0}/{1}'.format(
                self.tmp_dir,
                layer.id())

        GISCloudQgisUtils.find_layer_source(layer, layer_object, source, self.tmp_dir_len)
        layer_object.source = {"type": "file",
                               "src": u'/qgis/map{}/{}'.format(
                                   self.gc_api.map.map_id,
                                   layer_object.gc_source)}

        if layer.type() == QgsMapLayer.RasterLayer:
            layer_object.styles = [{"bordercolor": "255,153,253",
                                    "color": "230,179,229",
                                    "fontcolor": "0,0,0",
                                    "outline": "255,255,255",
                                    "width": 1,
                                    "borderwidth": 0,
                                    "fontsize": 12,
                                    "cap": False,
                                    "scale": True,
                                    "visible": True,
                                    "showlabel": False,
                                    "expression": ""}]
        elif layer.type() == QgsMapLayer.VectorLayer:
            try:
                map_style = GISCloudLayerStyle(layer,
                                               layer_object,
                                               self.gc_api)
                layer_object.styles = map_style.get_style()
                layer_object.alpha = map_style.get_alpha()
                LOGGER.info('Layer object style is {}'.format(
                    layer_object.styles))
            except Exception:
                LOGGER.info('Failed while trying to create styles',
                            exc_info=True)

    def create_wms_layer(self, layer, layer_object):
        """Processing WMS layers."""
        # pylint: disable=R0201
        source = {'type': "wms",
                  'version': "1.1.1"}

        LOGGER.info("wms source url {}".format(layer.source()))
        params = GISCloudQgisUtils.parse_qs(layer.source())

        if "url" in params:
            source["url"] = params["url"]
        if "crs" in params:
            source["srs"] = params["crs"]
            layer_object.epsg = int(source['srs'].split(':')[-1])
        if "styles" in params:
            source["style"] = params["styles"]
        if "layers" in params:
            source["layer"] = params["layers"]

        ext = layer.extent()

        layer_object.source = source
        layer_object.type = ["wms", 998]
        layer_object.styles = [{"showlabel": 'false',
                                "visible": 'true',
                                "expression": ' '}]
        layer_object.x_min = ext.xMinimum()
        layer_object.x_max = ext.xMaximum()
        layer_object.y_min = ext.yMinimum()
        layer_object.y_max = ext.yMaximum()

        LOGGER.info("wms layer obj {}".format(layer_object))

    def create_wfs_layer(self, layer, layer_object):
        """Processing WFS layers."""
        source = {'type': "wfs"}

        LOGGER.info("wfs source url {}".format(layer.source()))
        params = GISCloudQgisUtils.parse_params(layer.source())

        if "url" in params:
            source["url"] = params["url"]
        if "typename" in params:
            source["layer_id"] = params["typename"]
        if "srsname" in params:
            source["srs"] = params["srsname"].split(':')[-1]
            layer_object.epsg = int(source["srs"])

        ext = layer.extent()

        GISCloudQgisUtils.get_layer_id(layer, layer_object, self.tmp_dir_len)
        layer_object.source = source
        map_style = GISCloudLayerStyle(layer, layer_object, self.gc_api)
        layer_object.styles = map_style.get_style()
        layer_object.alpha = map_style.get_alpha()

        wfs_source = {"url": layer_object.source['url'],
                      "version": "1.1.1",
                      "type": "wfs",
                      "layerid": layer_object.source['layer_id'],
                      "geometry_type": layer_object.type[1]}
        layer_object.datasource_object = \
            {"name": layer_object.source['layer_id'],
             "type": 70,
             "x_min": ext.xMinimum(),
             "x_max": ext.xMaximum(),
             "y_min": ext.yMinimum(),
             "y_max": ext.yMaximum(),
             "epsg": layer_object.epsg,
             "params": json.dumps(wfs_source)}

        LOGGER.info("wfs layer obj {}".format(layer_object))

    def get_groups_rec(self, groups, root):
        """Getting all groups in QGIS to recreate them on GIS Cloud"""
        for child in root.children():
            if isinstance(child, QgsLayerTreeGroup):
                self.group_parent[child] = root
                self.get_groups_rec(groups, child)
                groups.insert(0, child)

    def check_layers_for_updates(self, result):
        """Check if layer has to be updated."""
        count = 0

        result["layers_new"] = 0

        for layer_object in self.layers_to_upload:
            layer = layer_object.qgis_layer
            order = self.tree_order[layer]
            group = GISCloudQgisUtils.get_qgis_layer_parent(layer,
                                                            self.project)
            parent = None
            if group:
                parent = self.gc_api.qgis_groups[group]

            layer_object.parent = parent
            layer_object.order = order

            if (layer.id() in self.layers_to_update and
                    layer_object.hash() ==
                    self.layers_to_update[layer.id()]["hash"]):
                continue

            if not layer.id() in self.layers_to_update:
                result["layers_new"] = result["layers_new"] + 1

            count = count + 1
        result["layers_changes"] = count
        return count

    def check_folders_for_updates(self, result):
        """Check if group has to be updated."""
        groups = []
        self.gc_api.qgis_groups = {}
        self.group_parent = {}
        self.get_groups_rec(groups, self.project.layerTreeRoot())

        count = 0

        result["folders_order_changed"] = False

        for group in groups:

            if not self.gc_api.check_group_for_layers(group):
                continue

            parent = None
            if self.group_parent[group] in self.gc_api.qgis_groups:
                parent = self.gc_api.qgis_groups[self.group_parent[group]]

            if group in self.gc_api.giscloud_groups_map:
                gc_group = self.gc_api.giscloud_groups_map[group]
                if (group.name() != gc_group["name"] or
                        parent != gc_group["parent"] or
                        self.tree_order[group] != gc_group["order"]):
                    if parent != gc_group["parent"]:
                        result["folders_order_changed"] = True
                    count = count + 1
                self.gc_api.qgis_groups[group] = gc_group["id"]
            else:
                self.gc_api.qgis_groups[group] = "new"
                count = count + 1
        result["folders_changes"] = count

    def analyze_groups(self):
        """This method analyzes groups to detect which
        groups on GIS Cloud should be updated, created or deleted"""
        for layer in GISCloudQgisUtils.get_qgis_layers(self.project):
            layer_legend = self.project.layerTreeRoot().findLayer(layer.id())
            group = layer_legend.parent()
            if group:
                layer_id = layer.id()
                if layer_id in self.layers_to_update:
                    group_id = self.layers_to_update[layer_id]["parent"]
                    if group_id in self.gc_api.giscloud_groups and \
                       not self.gc_api.giscloud_groups[group_id] in \
                       self.gc_api.giscloud_groups_map.values():
                        self.gc_api.giscloud_groups_map[group] = \
                            self.gc_api.giscloud_groups[group_id]
                        current_group = group
                        while current_group in self.gc_api.giscloud_groups_map:
                            current_group_id = group_id
                            group_id = self.gc_api.giscloud_groups_map[
                                current_group]["parent"]
                            if current_group_id == group_id:
                                break
                            current_group = current_group.parent()
                            if current_group and group_id in \
                               self.gc_api.giscloud_groups and \
                               not self.gc_api.giscloud_groups[group_id] in \
                               self.gc_api.giscloud_groups_map.values():
                                self.gc_api.giscloud_groups_map[
                                    current_group] = \
                                    self.gc_api.giscloud_groups[group_id]

    def analyze_layers(self, force=False, new_map=False, for_publish=False):
        """This method does layer analysis in QGIS by comparing QGIS state
        to the state on GIS Cloud. We are computing differences and then
        applying just changes to sync the state between QGIS and GIS Cloud
        map to minimize number of requests."""
        # pylint: disable=R0914

        result = {"folders_changes": 0,
                  "layers_changes": 0,
                  "layers_to_delete": 0,
                  "layers_new": 0,
                  "folders_order_changed": False,
                  "layers_order_changed": False}

        self.get_tree_order()

        if not self.tree_order:
            self.last_analysis["result"] = result
            return result

        self.gc_api.giscloud_groups_map = {}
        dirname = self.get_map_name(True)

        use_cache = True
        if not new_map:
            current_time = (datetime.datetime.utcnow() -
                            datetime.datetime(1970, 1, 1)).total_seconds()
            if force or current_time - self.last_analysis["time"] > 30 or \
               self.last_analysis["map_id"] != self.gc_api.map.map_id:
                self.last_analysis["time"] = current_time
                self.last_analysis["map_id"] = self.gc_api.map.map_id
                use_cache = False

        result["dirname"] = dirname
        if self.gc_api.map.map_id:
            self.gc_api.get_layers(use_cache)
        if not self.gc_api.map.map_id:
            self.layers_to_update = {}
            self.gc_api.giscloud_groups = {}
            self.gc_api.layers_to_delete = []

        self.analyze_groups()
        self.get_layers_to_upload(for_publish)
        self.check_folders_for_updates(result)
        for layer in self.layers_to_upload:
            group = GISCloudQgisUtils.get_qgis_layer_parent(layer.qgis_layer,
                                                            self.project)
            layer.datasource_timestamp = \
                self.layer_data_timestamps[layer.original_id] \
                if layer.original_id in self.layer_data_timestamps \
                else 0
            layer.should_updata_data = \
                (layer.original_id in self.layers_to_update and
                 self.layers_to_update[layer.original_id][
                     "datasource_timestamp"] != layer.datasource_timestamp)
            layer.parent = self.gc_api.qgis_groups[group] if group else None
        self.check_layers_for_updates(result)
        result["layers_to_delete"] = len(self.gc_api.layers_to_delete)

        list1 = []
        for key in self.layers_to_update:
            list1.append({"id": key,
                          "order": self.layers_to_update[key]["order"]})
        list1.sort(key=lambda x: x["order"])
        list1 = [x["id"] for x in list1]

        list2 = []
        for layer in self.layers_to_upload:
            list2.append({"id": layer.original_id, "order": layer.order})
        list2.sort(key=lambda x: x["order"])
        list2 = [x["id"] for x in list2]

        did_order_changed = []
        for tag, from_1, to_1, from_2, to_2 in SequenceMatcher(
                None, list1, list2).get_opcodes():
            if tag in ('delete', 'replace'):
                did_order_changed.extend(list1[from_1:to_1])
            if tag in ('insert', 'replace'):
                did_order_changed.extend(list2[from_2:to_2])

        # if there are duplicates then it means that order has been changed
        # as item has been removed from their position and moved
        # to another position
        result["layers_order_changed"] = \
            len(did_order_changed) != len(set(did_order_changed))
        LOGGER.info("analyze_layers {}".format(result))

        self.last_analysis["result"] = result
        return result
