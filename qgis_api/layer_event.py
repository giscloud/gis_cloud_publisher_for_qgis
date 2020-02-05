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

 Even handler for QGIS layers, we use it to detect changes and do layer
 analysis to compute the state and decide if updated is needed.

"""

import datetime


class GISCloudQgisLayerEvent(object):
    """Class used to register events on QGIS layers"""
    # pylint: disable=R0903

    def __init__(self, gui, layer):
        self.gui = gui
        self.layer = layer

    def handle_data_change(self):
        """On data change we record a timestamp that we use to compare states
        between QGIS and GIS Cloud"""
        self.gui.qgis_api.layer_data_timestamps[self.layer.id()] = \
            (datetime.datetime.utcnow() -
             datetime.datetime(1970, 1, 1)).total_seconds()
        self.gui.handle_project_update()
