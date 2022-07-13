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

 GIS Cloud Layer Style class that controls layer styles on GIS Cloud.

"""

import hashlib
import math
import re

from qgis.core import QgsPalLayerSettings, QgsRenderContext, QgsUnitTypes
from qgis.utils import iface

from ..qgis_api.version import ISQGIS3
from ..qgis_api.logger import get_gc_publisher_logger

if ISQGIS3:
    from qgis.core import QgsFillSymbol, QgsRuleBasedRenderer
else:
    from qgis.core import QgsFillSymbolV2, QgsRuleBasedRendererV2

if ISQGIS3:
    from PyQt5.QtCore import QSize
else:
    from PyQt4.QtCore import QSize

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudLayerStyle(object):
    """GIS Cloud layer style definitions"""
    # need to refactor this method
    # pylint: disable=R0914,R0912,R0915

    def __init__(self, qgis_layer, layer, gc_api):
        self.qgis_layer = qgis_layer
        self.layer = layer
        self.gc_api = gc_api
        self.scale_pixels = 1
        self.unit_to_px = {}
        self.supported_fonts = [
            'Arial', 'Arial Black', 'Comic Sans MS', 'Courier New', 'Georgia',
            'Impact', 'Times New Roman', 'Trebuchet MS', 'Verdana']

    def get_style(self):
        """Get map styles. Get Fill color, label font, outline color.

        This function takes layer as input and configures style dictionary
        which is sent as HTTP request in order to adequatly represent
        map style on GIS Cloud.
        """
        LOGGER.debug('Started map_styles function')
        if ISQGIS3:
            self.scale_pixels = \
                iface.mapCanvas().mapSettings().outputDpi() / 72
        else:
            self.scale_pixels = \
                iface.mapCanvas().mapRenderer().outputDpi() / 72

        self.unit_to_px = {"MM": 3.78 * self.scale_pixels,
                           "Point": 1.33 * self.scale_pixels,
                           "Inch": 96 * self.scale_pixels,
                           # these two aren't yet supported by GC rendering,
                           # so defaulting them to value of 1 px
                           "MapUnit": None,
                           "RenderMetersInMapUnits": None}

        layer_fromlevel = 0
        layer_tolevel = 0

        if self.qgis_layer.hasScaleBasedVisibility():
            dpi = iface.mainWindow().physicalDpiX()
            max_scale_per_pixel = 156543.04
            inches_per_meter = 39.37
            factor = dpi * inches_per_meter * max_scale_per_pixel
            if self.qgis_layer.minimumScale() > 0:
                layer_fromlevel = int(round(
                    math.log((factor / self.qgis_layer.minimumScale()), 2),
                    0))
            if self.qgis_layer.maximumScale() > 0:
                layer_tolevel = int(round(
                    math.log((factor / self.qgis_layer.maximumScale()), 2),
                    0))

            if not ISQGIS3:
                # QGis2 has oposite logic with min/max scales
                # so we need to switch them
                (layer_tolevel, layer_fromlevel) = \
                    (layer_fromlevel, layer_tolevel)

        styles = []
        tmp_dir = self.gc_api.qgis_api.tmp_dir

        if ISQGIS3:
            renderer = QgsRuleBasedRenderer.convertFromRenderer(
                self.qgis_layer.renderer())
        else:
            renderer = QgsRuleBasedRendererV2.convertFromRenderer(
                self.qgis_layer.rendererV2())

        for rule in renderer.rootRule().children():
            symbol = rule.symbol()
            sym_size = 0
            if self.layer.type[0] == "point":
                for layer_sym in symbol.symbolLayers():
                    temp_style = layer_sym.properties()
                    self.convert_units_to_px(temp_style)
                    if "size" in temp_style and \
                       float(temp_style["size"]) > sym_size:
                        sym_size = float(temp_style["size"])

            is_first_sym = True

            index = symbol.symbolLayerCount()
            while index > 0:
                index = index - 1
                layer_sym = symbol.symbolLayer(index)
                temp_style = layer_sym.properties()
                self.convert_units_to_px(temp_style)

                val_label = None
                # in case of multiple symbolLayers()
                # labels should be set only once
                if is_first_sym:
                    if ISQGIS3:
                        if self.qgis_layer.labelsEnabled():
                            val_label = self.qgis_layer.labeling().settings()
                    else:
                        val_label = QgsPalLayerSettings()
                        val_label.readFromLayer(self.qgis_layer)
                style = {}
                line_style = "line_style"
                line_width = 0
                if self.layer.type[0] == "point":
                    size = int(round(sym_size)) + 2
                    md5 = hashlib.md5()
                    properties = str(temp_style) + self.dump_symbol_properties(
                        layer_sym.subSymbol())
                    md5.update(properties.encode('utf-8'))
                    symbol_file = "{}_{}.png".format(self.layer.id,
                                                     md5.hexdigest())
                    style['iconsoverlap'] = 2
                    style['url'] = {"full_path": tmp_dir + '/' + symbol_file,
                                    "file": symbol_file,
                                    "symbol": symbol.clone(),
                                    "size": QSize(size, size)}

                elif self.layer.type[0] == "line":
                    LOGGER.info('entered line_type part of function')
                    LOGGER.info(temp_style)
                    try:
                        if u'line_color' in temp_style:
                            style['color'] = ','.join(
                                temp_style[u'line_color']
                                .split(',')[0:3])
                            style['bordercolor'] = style['color']
                        if u'line_width' in temp_style:
                            style['width'] = temp_style[u'line_width']
                        else:
                            style['width'] = '1'
                        line_width = float(style['width'])
                    except Exception:
                        LOGGER.info(
                            'Failed while mapping style for line vector layer',
                            exc_info=True)
                    if ('color' or 'bordercolor') not in style:
                        style['color'] = '0,0,0'
                        style['bordercolor'] = '0,0,0'
                    LOGGER.info('Style is{}'.format(style))
                # VectorPolygonLayer styles -> dashed line
                # and offset possibilities
                elif self.layer.type[0] == "polygon":
                    line_style = "outline_style"
                    has_border = not ("outline_style" in temp_style and
                                      temp_style["outline_style"] == "no")
                    if layer_sym.layerType() == 'SimpleFill':
                        if u'outline_color' in temp_style and has_border:
                            style['bordercolor'] = \
                                ','.join(
                                    temp_style[u'outline_color']
                                    .split(',')[0:3])
                        if u'outline_width' in temp_style and has_border:
                            style['borderwidth'] = temp_style[u'outline_width']
                        if u'color' in temp_style and \
                           "style" in temp_style and \
                           temp_style["style"] == "solid" and \
                           temp_style[u'color'].split(',')[3:4][0] != '0':
                            style['color'] = ','.join(
                                temp_style[u'color']
                                .split(',')[0:3])
                    elif layer_sym.layerType() == 'SimpleLine':
                        if u'line_color' in temp_style:
                            style['bordercolor'] = \
                                ','.join(
                                    temp_style[u'line_color']
                                    .split(',')[0:3])
                        if u'line_width' in temp_style:
                            style['line_width'] = temp_style[u'line_width']
                    elif u'color1' in temp_style:
                        style['color'] = ','.join(
                            temp_style[u'color1']
                            .split(',')[0:3])
                        style['borderwidth'] = '1'
                        if has_border:
                            style['bordercolor'] = '0,0,0'
                    else:
                        style['bordercolor'] = '0,0,0'
                        if has_border:
                            style['borderwidth'] = '1'
                        style['color'] = '0,0,0'

                    if "borderwidth" in style:
                        line_width = float(style['borderwidth'])

                    if (layer_sym.layerType() != "SimpleFill" and
                            layer_sym.layerType() != "SimpleLine") or \
                            ("style" in temp_style and
                             not temp_style["style"] in ["solid", "no"]):
                        if layer_sym.layerType() != "SimpleFill":
                            temp_symbol = symbol.clone()
                            tmp_sym_layer = temp_symbol.symbolLayer(index)
                            while temp_symbol.symbolLayerCount() > 1:
                                if temp_symbol.symbolLayer(0) == tmp_sym_layer:
                                    temp_symbol.deleteSymbolLayer(1)
                                else:
                                    temp_symbol.deleteSymbolLayer(0)
                        else:
                            temp_style_hatch = temp_style.copy()
                            temp_style_hatch["outline_style"] = "no"
                            if ISQGIS3:
                                temp_symbol = QgsFillSymbol.createSimple(
                                    temp_style_hatch)
                            else:
                                temp_symbol = QgsFillSymbolV2.createSimple(
                                    temp_style_hatch)
                        properties = self.dump_symbol_properties(temp_symbol)
                        md5 = hashlib.md5()
                        md5.update(properties.encode('utf-8'))
                        symbol_file = "{}_{}.png"\
                            .format(self.layer.id, md5.hexdigest())
                        style['hatchUrl'] = {
                            "full_path": tmp_dir + '/' + symbol_file,
                            "file": symbol_file,
                            "symbol": temp_symbol,
                            "size": QSize(64, 64)}

                if "use_custom_dash" in temp_style and \
                        temp_style["use_custom_dash"] == '1':
                    style['dashed'] = temp_style[u'customdash'].replace(';',
                                                                        ',')

                if ("dashed" not in style and
                        line_style in temp_style and
                        not temp_style[line_style] in ["solid", "no"]):
                    process_dash_param(temp_style[line_style],
                                       line_width,
                                       style)

                if ISQGIS3:
                    if val_label is not None:
                        label_format = val_label.format()
                        style['fontsize'] = label_format.size()
                        style['labelfield'] = val_label.fieldName.lower()
                        style['fontcolor'] = \
                            rgb_int2tuple(label_format.color().rgb())
                        if label_format.buffer().enabled():
                            style['outline'] = \
                                rgb_int2tuple(
                                    label_format.buffer().color().rgb())
                        if self.qgis_layer.geometryType() == 1:
                            style['labelfield'] = ''
                            style['textfield'] = val_label.fieldName.lower()
                        if str(label_format.font().family()) in \
                           self.supported_fonts:
                            style['fontname'] = label_format.font().family()
                        else:
                            style['fontname'] = 'Arial'
                            LOGGER.info(
                                ("Choosen font is not supported, " +
                                 "so every font style has been changed " +
                                 "to {0}").format(style['fontname']))
                        self.setup_label_offset(val_label, style)
                else:
                    if val_label is not None and val_label.enabled:
                        style['fontsize'] = val_label.textFont.pointSize()
                        style['labelfield'] = val_label.fieldName.lower()
                        style['fontcolor'] = rgb_int2tuple(
                            val_label.textColor.rgb())
                        if val_label.bufferDraw:
                            style['outline'] = rgb_int2tuple(
                                val_label.bufferColor.rgb())
                        if self.qgis_layer.geometryType() == 1:
                            style['labelfield'] = ''
                            style['textfield'] = val_label.fieldName.lower()
                        if str(val_label.textFont.family()) in \
                           self.supported_fonts:
                            style['fontname'] = val_label.textFont.family()
                        else:
                            style['fontname'] = 'Arial'
                            LOGGER.info("Choosen font is not supported, so " +
                                        "every font style has been changed " +
                                        " to {0}".format(style['fontname']))
                        self.setup_label_offset(val_label, style)

                if rule.filterExpression():
                    style['expression'] = rule.filterExpression().replace('"',
                                                                          '')
                    expressionEqualIndex = re.search(' = ', style['expression']).span()
                    columnName = style['expression'][:expressionEqualIndex[0]]
                    layer = iface.activeLayer()

                    for i in layer.attributeTableConfig().columns():
                        if i.name == columnName and layer.fields().field(columnName).typeName() == "String":
                            style['expression'] = style['expression'][:expressionEqualIndex[1]] + "\'" + style['expression'][expressionEqualIndex[1]:] + "\'"

                expression = self.qgis_layer.subsetString().replace('"', '')
                if expression and expression != '':
                    if 'expression' in style and style['expression'] != '':
                        style['expression'] = "(" + \
                                              style['expression'] + \
                                              ") AND (" + expression + ")"
                    else:
                        style['expression'] = expression
                if rule.label():
                    style['label'] = rule.label()
                style['showlabel'] = 't' \
                                     if val_label is not None and \
                                     'labelfield' in style \
                                     else 'f'
                style['visible'] = '1'

                if self.qgis_layer.hasScaleBasedVisibility():
                    factor = dpi * inches_per_meter * max_scale_per_pixel
                    if ISQGIS3 and rule.minimumScale() > 0:
                        style['fromlevel'] = \
                            int(round(
                                math.log((factor / rule.minimumScale()), 2),
                                0))
                    elif layer_fromlevel > 0:
                        style['fromlevel'] = layer_fromlevel

                    if ISQGIS3 and rule.maximumScale() > 0:
                        style['tolevel'] = \
                            int(round(
                                math.log((factor / rule.maximumScale()), 2),
                                0))
                    elif layer_tolevel > 0:
                        style['tolevel'] = layer_tolevel

                if 'borderwidth' in styles and \
                   style['borderwidth'] and \
                   float(style['borderwidth']) < 1:
                    style['borderwidth'] = '1'

                key = "hatchUrl" if "hatchUrl" in style else "url"

                if key in style:
                    asset = style[key]
                    self.layer.assets.append(asset)
                    LOGGER.info(
                        'URL for image upload: {}'.format(asset["file"]))
                    style[key] = '/{}/qgis/map{}/{}'.format(
                        self.gc_api.user.user_md5,
                        self.gc_api.map.map_id,
                        asset["file"])

                styles.append(style)

                is_first_sym = False

                # all point styles are merged into one as we export the symbol
                # so it's not required to iterrate symbolLayers()
                if self.layer.type[0] == "point":
                    break

        LOGGER.info('Styles function output {}'.format(styles))
        LOGGER.debug('Finished map_styles function')
        return styles

    def dump_symbol_properties(self, symbol):
        """This is recursive method that gathers properties from subsymbols"""
        properties = ""
        if symbol:
            for i in range(symbol.symbolLayerCount()):
                sym_layer = symbol.symbolLayer(i)
                properties += str(sym_layer.properties())
                properties += self.dump_symbol_properties(
                    sym_layer.subSymbol())
        return properties

    def get_alpha(self):
        """Get layer opacity, alpha.

        Read from QGIS layer opacity value in range from 0 to 100. Return that
        opacity as alpha in order to properly configure Layer object alpha
        attribute.
        """
        LOGGER.debug('Started map_alpha function')
        alpha = 1.0

        if ISQGIS3:
            symbols = self.qgis_layer.renderer().symbols(QgsRenderContext())
        else:
            symbols = self.qgis_layer.rendererV2().symbols2(QgsRenderContext())

        for symbol in symbols:
            if ISQGIS3:
                alpha = symbol.opacity() * 100
            else:
                alpha = symbol.alpha() * 100
        LOGGER.debug('Finished map_alpha function')
        return alpha

    def convert_render_units_to_px(self, render_unit):
        """Converted of QGIS units to pixels."""
        if render_unit == QgsUnitTypes.RenderMillimeters:
            return self.unit_to_px["MM"]
        if render_unit == QgsUnitTypes.RenderPoints:
            return self.unit_to_px["Point"]
        if render_unit == QgsUnitTypes.RenderInches:
            return self.unit_to_px["Inch"]
        return 1

    def convert_units_to_px(self, temp_style):
        """This method goes into qgis style properties
        and converts all units to px"""
        for i in temp_style:
            unit_param = re.search("(.*)_unit$", i)
            if unit_param:
                param = unit_param.group(1)
                if param in temp_style:
                    if temp_style[i] in self.unit_to_px:
                        delimiter = ";" if ";" in temp_style[param] else ","
                        conversion = self.unit_to_px[temp_style[i]]
                        values = temp_style[param].split(delimiter)
                        values = [str(float(x) * conversion)
                                  if conversion else "1" for x in values]
                        temp_style[param] = delimiter.join(values)

    def setup_label_offset(self, val_label, style):
        """Helper method to translate label offset to GIS Cloud."""
        if ISQGIS3:
            offset_to_px = self.convert_render_units_to_px(
                val_label.offsetUnits)
        else:
            offset_to_px = 1 if val_label.labelOffsetInMapUnits \
                else self.unit_to_px["MM"]
        style['ldx'] = val_label.xOffset * offset_to_px
        style['ldy'] = val_label.yOffset * offset_to_px

        if val_label.quadOffset == QgsPalLayerSettings.QuadrantAboveLeft:
            style['labelplacement'] = 'BR'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantAbove:
            style['labelplacement'] = 'B'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantAboveRight:
            style['labelplacement'] = 'BL'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantLeft:
            style['labelplacement'] = 'R'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantRight:
            style['labelplacement'] = 'L'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantBelowLeft:
            style['labelplacement'] = 'TR'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantBelow:
            style['labelplacement'] = 'T'
        elif val_label.quadOffset == QgsPalLayerSettings.QuadrantBelowRight:
            style['labelplacement'] = 'TL'


def rgb_int2tuple(rgbint):
    """Convert RGB integer to corresponding RGB tuple."""
    return '{},{},{}'.format(rgbint // 256 // 256 % 256,
                             rgbint // 256 % 256,
                             rgbint % 256)


def process_dash_param(param, line_width, style):
    """Processing QGIS dash style."""
    space = str(line_width * 2)
    tokens = {"dash": str(line_width * 4) + "," + space,
              "dot": str(line_width) + "," + space}
    try:
        dash_def = param.split(" ")
        dash_def = [tokens[x] for x in dash_def]
        style["dashed"] = ",".join(dash_def)
    except Exception:
        LOGGER.debug("failed setting dash style {}".format(param))
