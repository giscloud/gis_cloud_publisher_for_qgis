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

 This script extracts layer name, source, geometry and boundaries. Also it
 provides file management and other helper methods.

"""

import hashlib
import json
import os
from os.path import basename
import re
from urllib.parse import parse_qsl

from qgis.core import QgsApplication, QgsLayerTreeNode, QgsMapLayer
from qgis.core import QgsVectorFileWriter, QgsVectorLayer
from qgis.utils import iface
from .version import ISQGIS3
from .logger import get_gc_publisher_logger

if ISQGIS3:
    from qgis.core import QgsWkbTypes
else:
    from qgis.core import QGis

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudQgisUtils(object):
    """Utility methods based on QGIS Api."""

    @staticmethod
    def get_layer_source_files(layer_object, gc_api):
        """Getting source and assets files that we need to upload."""

        # converting symbology by exporting images (e.g. points, hatch fills)
        for asset in layer_object.assets:
            asset["symbol"].exportImage(asset["full_path"],
                                        'png',
                                        asset["size"])
            layer_object.files.append([asset["full_path"], asset["file"]])
            gc_api.files_to_delete_after_upload.append(asset["full_path"])

        if not layer_object.source_dir:
            return

        source_dir = layer_object.source_dir
        source_no_ext = layer_object.source_no_ext
        source_no_ext_enum = enumerate(source_no_ext.split('.'))

        if layer_object.source_to_convert:
            layer = layer_object.qgis_layer
            gc_file = re.sub(source_no_ext,
                             layer_object.id,
                             layer.id() + ".sqlite",
                             flags=re.I)
            if layer_object.should_updata_data or gc_file not in gc_api.current_gc_files:
                gc_api.files_to_delete_after_upload.append(
                    layer_object.source_to_convert + ".sqlite")
                if ISQGIS3:
                    QgsVectorFileWriter.writeAsVectorFormat(
                        layer,
                        layer_object.source_to_convert,
                        'utf-8',
                        layer.crs(),
                        'SQLite')
                else:
                    QgsVectorFileWriter.writeAsVectorFormat(
                        layer,
                        layer_object.source_to_convert,
                        'utf-8',
                        None,
                        'SQLite')
        files = os.listdir(source_dir)
        for _file in files:
            filename = _file.lower().split('.')
            filename_len = len(filename)
            matched_file = True
            for i, item in source_no_ext_enum:
                if i >= filename_len or filename[i] != item:
                    matched_file = False
                    break
            if matched_file and \
               (filename_len == 1 or filename[-1] != "zip"):
                gc_file = re.sub(source_no_ext,
                                 layer_object.id,
                                 _file,
                                 flags=re.I)
                if layer_object.should_updata_data or \
                   gc_file not in gc_api.current_gc_files:
                    layer_object.files.append(
                        [source_dir + '/' + _file, gc_file])

    @staticmethod
    def find_layer_source(layer, layer_object, source, tmp_dir_len):
        """Pasing layer source and sanitizing file name."""
        source_dir = source.split('/')
        source_dir.pop()
        source_dir = '/'.join(source_dir)
        LOGGER.debug('Source dir is {}'.format(source_dir))

        source_no_ext = source.split("/")[-1].rsplit('.', 1)[0].lower()
        GISCloudQgisUtils.get_layer_id(layer, layer_object, tmp_dir_len)
        layer_object.source = source
        layer_object.gc_source = re.sub(source_no_ext,
                                        layer_object.id,
                                        basename(source),
                                        flags=re.I)
        layer_object.source_dir = source_dir
        layer_object.source_no_ext = source_no_ext

    @staticmethod
    def get_layer_id(layer, layer_object, tmp_dir_len):
        """get layer id from qgis id"""
        layer_object.id = re.sub(r'[^a-zA-Z0-9\-_\. ]',
                                 '_',
                                 layer.id().encode('ascii',
                                                   errors='backslashreplace')
                                 .decode())

        # some OSes, e.g. Windows have full path name limited to 260 chars
        # so we need to make sure we're below that threshold
        # our filename can be appended with md5 suffix of 32 + 1 chars + extensions
        # which in total can around 240-250 chars, so we layer id to 210
        layer_id_len = len(layer_object.id)
        if layer_id_len + tmp_dir_len > 210:
            layer_id_substring_len = 210 - tmp_dir_len - 1 - 32
            md5 = hashlib.md5()
            md5.update(layer_object.id.encode("utf-8"))
            md5 = md5.hexdigest()
            if layer_id_substring_len > 0:
                layer_object.id = layer_object.id[:layer_id_substring_len] + "_" + md5
            else:
                layer_object.id = md5

    @staticmethod
    def get_layer_geometry(layer):
        """Get layer geometry for vector layers.

        From layer object extract which geometry type it has. Is it point,
        line or polygon.
        """

        if layer.type() == QgsMapLayer.RasterLayer:
            return ['raster', 999]

        if ISQGIS3:
            wkb_type = QgsWkbTypes.flatType(layer.wkbType())
            point_type = QgsWkbTypes.Point
            line_string_type = QgsWkbTypes.LineString
            polygon_type = QgsWkbTypes.Polygon
            multi_point_type = QgsWkbTypes.MultiPoint
            multi_line_string_type = QgsWkbTypes.MultiLineString
            multi_polygon_type = QgsWkbTypes.MultiPolygon
        else:
            wkb_type = QGis.flatType(layer.wkbType())
            point_type = QGis.WKBPoint
            line_string_type = QGis.WKBLineString
            polygon_type = QGis.WKBPolygon
            multi_point_type = QGis.WKBMultiPoint
            multi_line_string_type = QGis.WKBMultiLineString
            multi_polygon_type = QGis.WKBMultiPolygon
        LOGGER.info('type {}', layer.wkbType())

        geometry = [None, 100]

        if wkb_type == point_type:
            geometry = ['point', 1]
        if wkb_type == line_string_type:
            geometry = ['line', 2]
        if wkb_type == polygon_type:
            geometry = ['polygon', 3]
        if wkb_type == multi_point_type:
            geometry = ['point', 4]
        if wkb_type == multi_line_string_type:
            geometry = ['line', 5]
        if wkb_type == multi_polygon_type:
            geometry = ['polygon', 6]
        if wkb_type == 100:
            LOGGER.info('Layer is a data-only layer')
        return geometry

    @staticmethod
    def parse_params(params):
        """Parser for WFS params."""
        params = re.findall(
            r"\s*([^=]*)\s*=\s*(?:'([^\']+)'|\"([^\"]+)\"|([^\s]*))",
            params)
        result = {}
        for param in params:
            result[param[0]] = param[1]
        return result

    @staticmethod
    def parse_qs(params):
        """Parser for WMS params."""
        return dict(parse_qsl(params, keep_blank_values=True))

    @staticmethod
    def deep_obj_compare(obj1, obj2, decode_json=None):
        """We use deep object to compare GIS Cloud datasource objects."""
        for i in obj1:
            if i not in obj2:
                return False

            if decode_json and i in decode_json:
                if not GISCloudQgisUtils.deep_obj_compare(json.loads(obj1[i]),
                                                          json.loads(obj2[i])):
                    return False
            elif str(obj1[i]) != str(obj2[i]):
                return False
        return True

    @staticmethod
    def get_qgis_layers(project):
        """Return list of layers currently loaded."""
        if ISQGIS3:
            return [tree_layer.layer()
                    for tree_layer in
                    project.layerTreeRoot().findLayers()]
        return iface.legendInterface().layers()

    @staticmethod
    def get_qgis_layer_parent(layer, project):
        """Define parent and child relationship for layers.

        When there exists tree structure in project (folders and layers),
        parent and child relationship between folders and layers must
        be defined correctly in order to show them same as in qgis."""
        root = project.layerTreeRoot()
        group = root.findLayer(layer.id()).parent()
        return group if group.name() != '' else None

    @staticmethod
    def copy_to_cliboard(content):
        """Copy content to clipboard"""
        clipboard_handler = QgsApplication.clipboard()
        clipboard_handler.clear(mode=clipboard_handler.Clipboard)
        clipboard_handler.setText(content,
                                  mode=clipboard_handler.Clipboard)

    @staticmethod
    def is_vector_layer(layer):
        """checking if layer is vector type """
        return isinstance(layer, QgsVectorLayer)

    @staticmethod
    def is_layer_tree_node(tree_node):
        """checking if tree node is layer type """
        return tree_node.nodeType() == QgsLayerTreeNode.NodeLayer
