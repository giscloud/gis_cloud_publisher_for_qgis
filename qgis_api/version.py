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

 Detecing QGIS version for QGIS 2/3 compatibility

"""

try:
    from qgis.core import Qgis
except ImportError:  # QGIS 2
    from qgis.core import QGis as Qgis

GIS_CLOUD_PUBLISHER_VERSION = "1.0.11"
QGIS_VERSION = Qgis.QGIS_VERSION
QGIS_VERSION_INT = Qgis.QGIS_VERSION_INT

# Exactly one of these is True
ISQGIS2 = QGIS_VERSION_INT < 30000
ISQGIS3 = 30000 <= QGIS_VERSION_INT < 40000
ISQGIS4 = QGIS_VERSION_INT >= 40000
