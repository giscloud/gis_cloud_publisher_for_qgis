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

 Main script which handles GUI.

"""

import json
import os
import os.path

from qgis.gui import QgsDockWidget

from .gis_cloud_api.core import GISCloudCore
from .gis_cloud_api.network_handler import GISCloudNetworkHandler
from .qgis_api.core import GISCloudQgisCore
from .qgis_api.layer_event import GISCloudQgisLayerEvent
from .qgis_api.logger import gc_publisher_loggers_unload
from .qgis_api.logger import get_gc_publisher_logger
from .qgis_api.utils import GISCloudQgisUtils
from .qgis_api.version import ISQGIS3
from .ui.login import GISCloudUiLogin
from .ui.publish import GISCloudUiPublish
from .ui.update import GISCloudUiUpdate
from .workers.check_connection import GISCloudWorkerCheckConnection
from .workers.map_analysis import GISCloudWorkerMapAnalysis

if ISQGIS3:
    from .ui import resources5  # noqa:F401 pylint:disable=unused-import
else:
    from .ui import resources4  # noqa:F401 pylint:disable=unused-import

if ISQGIS3:
    from PyQt5.QtCore import Qt, QEvent, QObject, QSize, QTimer
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QAction, QMessageBox
else:
    from PyQt4.QtCore import Qt, QEvent, QObject, QSize, QTimer
    from PyQt4.QtGui import QAction, QIcon, QMessageBox

LOGGER = get_gc_publisher_logger(__name__)


class GISCloudPublisher(QObject):
    """This class controls all plugin-related GUI elements."""

    def __init__(self, iface):
        QObject.__init__(self)
        self.iface = iface
        self.path = os.path.dirname(os.path.abspath(__file__))
        self.check = None
        self.read_project = iface.projectRead
        self.new_project = iface.newProjectCreated
        self.main_widget = None
        self.main_widget_opened = False
        self.current_dock_widget = None
        self.previous_dock_widget = None
        self.objects_with_connected_signals = []
        self.is_initialized = False
        self.qgis_api = None
        self.api = None
        self.message_box = None
        self.login_control = None
        self.publish_control = None
        self.update_control = None
        self.check_task = None
        self.map_analysis_task = None
        self.analysis_timer = None
        self.action = None
        self.gui_initialized = False

        self.default_input_style_dark = 'QLineEdit\
                                         {border:0px;\
                                         border-radius:2px;\
                                         padding:0px 8px 0px 8px;\
                                         color:white;}'
        self.default_input_style_dark_error = 'QLineEdit\
                                               {border:1px solid red;\
                                               border-radius: 2px;\
                                               padding:0px 8px 0px 8px;\
                                               color:white;}'
        self.default_input_style_lite = 'QLineEdit\
                                         {border:0px;\
                                         border-radius:2px;\
                                         padding:0px 8px 0px 8px;\
                                         color:#222222} '
        self.default_input_style_lite_error = 'QLineEdit\
                                               {border:1px solid red;\
                                               border-radius: 2px;\
                                               padding:0px 8px 0px 8px;\
                                               color:#222222}'

        self.layer_hooks = ["styleChanged", "blendModeChanged",
                            "configChanged", "crsChanged",
                            "legendChanged", "metadataChanged",
                            "nameChanged", "statusChanged",
                            "rendererChanged", "repaintRequested",
                            "flagsChanged"]

    def initGui(self):
        """initialize the gui"""
        # pylint: disable=C0103
        self.gui_initialized = True
        self.qgis_api = GISCloudQgisCore(self.path)
        self.api = GISCloudCore(self.path, self.qgis_api, self)
        self.qgis_api.gc_api = self.api

        self.message_box = QMessageBox()

        self.login_control = GISCloudUiLogin(self)
        self.publish_control = GISCloudUiPublish(self)
        self.update_control = GISCloudUiUpdate(self)

        self.adjust_theme(self.login_control.login_dock.username, True)
        self.adjust_theme(self.login_control.login_dock.password, True)
        self.adjust_theme(self.publish_control.publish_details_dock.map_name,
                          True)

        if ISQGIS3:
            components = (self.login_control.login_dock.username,
                          self.login_control.login_dock.password,
                          self.publish_control.publish_details_dock.map_name)
            for component in components:
                component.installEventFilter(self)

        self.check_task = GISCloudWorkerCheckConnection(self.api,
                                                        self.qgis_api)
        self.check_task.alertSignal.connect(self.__notify_user_publish)
        self.check_task.wrongApiSignal.connect(self.__wrong_api_notify)

        self.map_analysis_task = GISCloudWorkerMapAnalysis(self.qgis_api)
        if ISQGIS3:
            self.map_analysis_task.result.connect(
                self.__handle_project_update_test)

        self.analysis_timer = QTimer()
        self.analysis_timer.timeout.connect(self.__run_analysis)

        self.main_widget = QgsDockWidget("Publisher")
        self.main_widget.setFixedSize(QSize(360, 310))
        self.main_widget.setObjectName("GISCloudPublisherMainDockWidget")

        self.login_control.is_auth = self.api.user.is_auth_api()
        if self.login_control.is_auth:
            self.set_dock_widget(self.publish_control.publish_dock)
        else:
            self.set_dock_widget(self.login_control.login_dock)
            if ISQGIS3:
                self.login_control.login_dock.username.setFocus()

        self.action = QAction(
            QIcon(":/plugins/gis_cloud_publisher/ui/img/icon.png"),
            "GIS Cloud Publisher",
            self.iface.mainWindow())
        self.action.triggered.connect(self.__toggle_dock)
        self.iface.addPluginToWebMenu("&GIS Cloud Publisher", self.action)

        self.main_widget.opened.connect(self.__dock_widget_opened)
        self.main_widget.closed.connect(self.__dock_widget_closed)
        self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.main_widget)

    def eventFilter(self, obj, event):
        """This is needed to filter events and hook on palette change,
        to detect lite/dark mode switches"""
        # pylint: disable=C0103
        if event.type() == QEvent.PaletteChange:
            self.adjust_theme(obj)
            return True

        return QObject.eventFilter(self, obj, event)

    def adjust_theme(self, obj, force=False):
        """We adjust theme for input field when dark/lite theme is selected."""
        color = self.iface.mainWindow().palette().window().color()
        color_condition = color.red() <= 50 and \
            color.green() <= 50 and \
            color.blue() <= 50

        if color_condition and (force or not obj.darkMode):
            obj.darkMode = True
            obj.default_input_style = self.default_input_style_dark
            obj.default_input_style_error = self.default_input_style_dark_error
            obj.setStyleSheet(self.default_input_style_dark)
        elif not color_condition and (force or obj.darkMode):
            obj.darkMode = False
            obj.default_input_style = self.default_input_style_lite
            obj.default_input_style_error = self.default_input_style_lite_error
            obj.setStyleSheet(self.default_input_style_lite)

    def logged_in(self):
        """Login control calls this method once it has logged in"""
        self.set_dock_widget(self.publish_control.publish_dock)
        self.set_login_info(self.publish_control.publish_dock.user)
        LOGGER.info("Login has been succesful")
        self.__project_check()

    def notify_user_login(self, handler):
        """Notify user if somethhing goes wrong during login."""
        # pylint: disable=W0613
        self.login_control.animation.stop()
        self.__no_internet_message()
        self.restore_previous_dock_widget()

    def set_login_info(self, label):
        """Set login information in a widgets"""
        label.setWordWrap(True)
        label.setText("You are logged in as <b>" +
                      str(self.api.user.username) + "</b>")

    def published(self):
        """Publish control will call this method
        once publish has been completed"""
        self.check = True
        self.update_control.get_map_link()

        self.__project_check()

        # if project is modified or newly created, prompt user to save it
        if (self.qgis_api.project.isDirty() or
                not self.qgis_api.project.fileName() and
                GISCloudQgisUtils.get_qgis_layers(self.qgis_api.project)):
            save = self.message_box.information(
                self.iface.mainWindow(),
                'Information',
                'To be able to update this QGIS project later and ' +
                'sync it with published GIS Cloud map, please save it now.',
                self.message_box.Save, self.message_box.Cancel)
            if save == self.message_box.Save:
                # have to save project like this,
                # otherwise qgis doesn't detect that
                # project has been saved
                self.iface.mainWindow().findChild(
                    QAction,
                    'mActionSaveProject').trigger()

    def deleted_map_message(self):
        """If user has deleted map on GIS Cloud
        update should fail and warn about this."""
        self.message_box.warning(self.iface.mainWindow(), 'Warning',
                                 "The published version of this map " +
                                 "was deleted from GIS Cloud, " +
                                 "so it can't be updated. " +
                                 "You can publish your map again.",
                                 self.message_box.Ok,
                                 self.message_box.Ok)
        self.__project_check()

    def publishing_cancel(self):
        """Cancel publish process and return to Publish or Update Dock."""
        self.publish_control.sync_task.quit()
        self.publish_control.publish_write_state()
        if self.check:
            self.set_dock_widget(self.update_control.update_done_dock)
        else:
            self.set_dock_widget(self.publish_control.publish_dock)
        self.__project_check()

    def set_dock_widget(self, widget):
        """Helper method that makes it easy to switch widgets."""
        if self.current_dock_widget == widget or not self.gui_initialized:
            return

        self.previous_dock_widget = self.current_dock_widget
        self.current_dock_widget = widget
        self.main_widget.setWidget(widget)
        self.main_widget.show()

    def restore_previous_dock_widget(self):
        """Helper method that makes it easy to go back to a previous widget."""
        if self.previous_dock_widget:
            self.set_dock_widget(self.previous_dock_widget)

    def inform_fail(self, layer, error_details):
        """Inform user that upload of certain layer has failed."""
        if error_details == "Storage limit exceeded":
            message = "Project wasn't published because you exceeded " + \
                "your GIS Cloud storage limit.\n\n" + \
                "Go to Store in the GIS Cloud Manager " + \
                "and buy morestorage to continue. " + \
                "If the issue persists, contact sales@giscloud.com."
        else:
            error_details = ': ' + error_details if error_details else \
                ', we are sorry for the incovenience'
            if layer:
                message = (
                    'Project layer \"{0}\" couldn\'t be uploaded ' +
                    'correctly{1}.\n\nPlease set the layer \"{0}\" to ' +
                    '\'not visible\' in your layer list and try again.\n\n') \
                    .format(layer.name, error_details)
            else:
                message = 'Project couldn\'t be uploaded correctly{0}.\n\n' \
                    .format(error_details)
            message += 'If the issue persists, contact support@giscloud.com.'

        failed = self.message_box.critical(self.iface.mainWindow(),
                                           'Error', message,
                                           self.message_box.Ok)
        if failed == self.message_box.Ok:
            self.publish_control.sync_task.quit()
            self.__project_check()

    def handle_project_update(self):
        """Starting the analysis with a 50msec throttle"""
        if self.login_control.is_auth:
            self.analysis_timer.start(50)

    def __dock_widget_opened(self):
        """Handling widget open"""
        if self.main_widget_opened:
            return
        self.main_widget_opened = True

        self.read_project.connect(self.__load_project)
        self.new_project.connect(self.__load_project)

        if self.login_control.is_auth and not self.api.user.username:
            self.api.user.get_username(self.__ui_init)
        else:
            self.__ui_init()

        self.__load_project(True)

    def __dock_widget_closed(self):
        """Handling widget close"""
        if not self.main_widget_opened:
            return
        self.main_widget_opened = False

        self.read_project.disconnect(self.__load_project)
        self.new_project.disconnect(self.__load_project)
        self.__unhook_all_events()

    def unload(self):
        """Unload the plugin."""
        self.gui_initialized = False
        GISCloudNetworkHandler.cancel()
        gc_publisher_loggers_unload()
        self.__dock_widget_closed()
        self.main_widget.opened.disconnect(self.__dock_widget_opened)
        self.main_widget.closed.disconnect(self.__dock_widget_closed)
        self.iface.removeDockWidget(self.main_widget)
        self.current_dock_widget = None
        self.iface.removePluginWebMenu("GIS Cloud Publisher", self.action)

    def __ui_init(self):
        """Final stage of UI initialization."""
        self.is_initialized = True
        if not self.login_control.is_auth or not self.api.user.username:
            self.login_control.is_auth = None
            self.set_dock_widget(self.login_control.login_dock)
            if ISQGIS3:
                self.login_control.login_dock.username.setFocus()
        else:
            self.set_dock_widget(self.publish_control.publish_dock)
            self.set_login_info(self.publish_control.publish_dock.user)
            self.__project_check()

    def __handle_added_child(self, group):
        if GISCloudQgisUtils.is_layer_tree_node(group):
            return
        for node in group.children():
            if GISCloudQgisUtils.is_layer_tree_node(node):
                self.__hook_on_layer_events([node.layer()])

    def __hook_on_layer_legend(self):
        root = self.qgis_api.project.layerTreeRoot()
        if root in self.objects_with_connected_signals:
            return

        self.objects_with_connected_signals.append(root)

        if not ISQGIS3:
            root.addedChildren.connect(self.__handle_added_child)
            return

        if root.layerOrderChanged:
            root.layerOrderChanged.connect(self.handle_project_update)
        if root.visibilityChanged:
            root.visibilityChanged.connect(self.handle_project_update)
        if root.nameChanged:
            root.nameChanged.connect(self.handle_project_update)

    def __unhook_on_layer_legend(self):

        root = self.qgis_api.project.layerTreeRoot()
        if root not in self.objects_with_connected_signals:
            return

        if not ISQGIS3:
            root.addedChildren.disconnect(self.__handle_added_child)
            return

        if root.layerOrderChanged:
            root.layerOrderChanged.disconnect(self.handle_project_update)
        if root.visibilityChanged:
            root.visibilityChanged.disconnect(self.handle_project_update)
        if root.nameChanged:
            root.nameChanged.disconnect(self.handle_project_update)

    def __hook_on_layer_events(self, layers):
        for layer in layers:
            if layer is None or layer in self.objects_with_connected_signals:
                continue

            self.objects_with_connected_signals.append(layer)

            event_handler = GISCloudQgisLayerEvent(self, layer)
            layer.giscloud_event_handler = event_handler

            layer.dataChanged.connect(event_handler.handle_data_change)
            layer.dataProvider().dataChanged.connect(
                event_handler.handle_data_change)
            if GISCloudQgisUtils.is_vector_layer(layer):
                layer.editingStopped.connect(event_handler.handle_data_change)

            if not ISQGIS3:
                continue

            if hasattr(layer, "dataSourceChanged"):
                layer.dataSourceChanged.connect(event_handler.handle_data_change)

            for hook in self.layer_hooks:
                if hasattr(layer, hook):
                    signal = getattr(layer, hook)
                    signal.connect(self.handle_project_update)

    def __unhook_on_layer_events(self, layers):
        for layer in layers:
            if layer not in self.objects_with_connected_signals:
                continue

            event_handler = layer.giscloud_event_handler

            layer.dataChanged.disconnect(event_handler.handle_data_change)
            layer.dataProvider().dataChanged.disconnect(
                event_handler.handle_data_change)
            if GISCloudQgisUtils.is_vector_layer(layer):
                layer.editingStopped.disconnect(
                    event_handler.handle_data_change)

            if not ISQGIS3:
                continue

            if hasattr(layer, "dataSourceChanged"):
                layer.dataSourceChanged.disconnect(event_handler.handle_data_change)

            for hook in self.layer_hooks:
                if hasattr(layer, hook):
                    signal = getattr(layer, hook)
                    signal.disconnect(self.handle_project_update)

    def __unhook_all_events(self, unhook_layer_events=True):
        if unhook_layer_events or ISQGIS3:
            self.__unhook_on_layer_events(
                GISCloudQgisUtils.get_qgis_layers(self.qgis_api.project))
            self.__unhook_on_layer_legend()
        self.objects_with_connected_signals = []

    def __load_project(self, unhook_layer_events=False):
        self.qgis_api.init_project()
        self.__unhook_all_events(unhook_layer_events)
        self.__hook_on_layer_legend()
        self.__hook_on_layer_events(
            GISCloudQgisUtils.get_qgis_layers(self.qgis_api.project))
        if ISQGIS3:
            self.qgis_api.project.legendLayersAdded.connect(
                self.__hook_on_layer_events)
        if self.is_initialized:
            self.__project_check()

    def __project_check(self):
        """Check if loaded project is already synced with GIS Cloud."""
        self.qgis_api.map_name_override = None

        self.api.map.map_name = self.qgis_api.get_map_name(True)
        if self.qgis_api.project.readEntry(
                "giscloud_project", "save_as")[0] != '':
            map_id = int(self.qgis_api.project.readEntry("giscloud_project",
                                                         "save_as")[0])
            self.api.map.map_id = map_id
        else:
            self.api.map.map_id = None

        if not self.publish_control.sync_task.isRunning():
            if self.login_control.is_auth:
                if self.api.map.map_id:
                    self.check = True
                    map_name = self.qgis_api.project.readEntry(
                        'giscloud_map_name',
                        'name')[0]
                    self.qgis_api.map_name_override = map_name
                    self.api.map.map_name = map_name
                    layer_data_timestamps = self.qgis_api.project.readEntry(
                        'giscloud_layers_data_state',
                        'state')[0]
                    self.qgis_api.layer_data_timestamps = json.loads(
                        layer_data_timestamps) if layer_data_timestamps else {}
                    if not ISQGIS3:
                        self.set_dock_widget(
                            self.update_control.update_dock)
                        self.set_login_info(
                            self.update_control.update_dock.user)
                    else:
                        self.set_dock_widget(
                            self.update_control.update_done_dock)
                        self.set_login_info(
                            self.update_control.update_done_dock.user)
                    self.update_control.get_map_link()
                else:
                    self.set_dock_widget(self.publish_control.publish_dock)
                    self.check = False

        LOGGER.info("Map name: {}".format(self.api.map.map_name))
        LOGGER.info("Map id: {}".format(self.api.map.map_id))

        self.handle_project_update()

    def __notify_user_publish(self):
        """Notify user if internet connection is bad."""
        self.publishing_cancel()
        self.check_task.terminate()
        self.__no_internet_message()

    def __no_internet_message(self):
        """Warn user that his
        internet connection is too slow or non existent."""

        notify = self.message_box.warning(
            self.iface.mainWindow(),
            'Warning',
            'No internet connection. ' +
            'It looks like you are not connected to the internet. ' +
            'Please check your internet connection and try again.',
            self.message_box.Ok)
        if notify == self.message_box.Ok:
            self.message_box.close()

    def __wrong_api_notify(self):
        """Notifiy user if api key has been deleted."""
        wrong_api = True
        self.check_task.terminate()
        wrong_api = self.message_box.warning(
            self.iface.mainWindow(),
            'Warning',
            'It seems that you have deleted your api key. ' +
            'Please log out in order to refresh api key.',
            self.message_box.Ok)
        if wrong_api == self.message_box.Ok:
            self.message_box.close()

    def __toggle_dock(self):
        if self.main_widget.isUserVisible():
            self.main_widget.close()
        else:
            self.main_widget.show()

    def __handle_project_update_test(self, result):
        invalidated = result["layers_changes"] > 0 or \
            result["folders_changes"] > 0 or \
            result["layers_to_delete"] > 0

        if invalidated and \
                self.current_dock_widget == \
                self.update_control.update_done_dock:
            self.set_dock_widget(self.update_control.update_dock)
            self.set_login_info(self.update_control.update_dock.user)
        if not invalidated and \
                self.current_dock_widget == \
                self.update_control.update_dock:
            self.set_dock_widget(self.update_control.update_done_dock)
            self.set_login_info(self.update_control.update_done_dock.user)

    def __run_analysis(self):
        """Running layer analysis with a throttle."""
        self.analysis_timer.stop()
        self.map_analysis_task.start()
