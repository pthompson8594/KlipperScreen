#!/usr/bin/python

import gi
import time
import threading

import json
import requests
import websocket

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from KlippyWebsocket import KlippyWebsocket
from KlippyGtk import KlippyGtk
from panels import IdleStatusPanel

config = "/opt/printer/KlipperScreen/KlipperScreen.config"

class KlipperScreen(Gtk.Window):
    """ Class for creating a screen for Klipper via HDMI """
    currentPanel = None
    bed_temp_label = None
    number_tools = 1

    panels = {}
    _cur_panels = []

    def __init__(self):
        self.read_config()
        self.init_style()
        Gtk.Window.__init__(self)

        self.set_default_size(Gdk.Screen.get_width(Gdk.Screen.get_default()), Gdk.Screen.get_height(Gdk.Screen.get_default()))

        r = requests.get("http://127.0.0.1:7125/printer/info") #, headers={"x-api-key":api_key})
        if r.status_code != 200:
            self.printer_initializing()
            self.create_websocket()
            return

        data = json.loads(r.content)

        if data['result']['is_ready'] != True:
            self.printer_initializing()
            self.create_websocket()
            return

        self.create_websocket()
        self.main_panel()


    def read_config (self):
        with open(config) as config_file:
            self._config = json.load(config_file)


    def init_style(self):
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path("/opt/printer/KlipperScreen/style.css")

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def splash_screen(self):
        if "splash_screen" not in self.panels:
            image = Gtk.Image()
            #TODO: update file reference
            image.set_from_file("/opt/printer/OctoScreen/styles/z-bolt/images/logo.png")

            label = Gtk.Label()
            label.set_text("Initializing printer...")
            #label = Gtk.Button(label="Initializing printer...")
            #label.connect("clicked", self.printer_initialize)

            main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
            main.pack_start(image, True, True, 10)
            main.pack_end(label, True, True, 10)

            box = Gtk.VBox()
            box.add(main)
            self.panels['splash_screen'] = box

        self.add(self.panels['splash_screen'])
        self.show_all()
        self._cur_panels = ['splash_screen']

    def create_websocket(self):
        self._ws = KlippyWebsocket(self._websocket_callback)
        self._ws.connect()
        self._curr = 0

    def main_panel (self):
        if "main_panel" not in self.panels:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

            grid = Gtk.Grid()
            grid.set_row_homogeneous(True)
            grid.set_column_homogeneous(True)

            self.panels['idle_status'] = IdleStatusPanel(self)


            grid.attach(self.panels['idle_status'].initialize(), 0, 0, 1, 1)
            #grid.attach(box2, 1, 0, 1, 1)


            grid.attach(self.arrangeMenuItems(self._config,2), 1, 0, 1, 1)

            self.panels['main_screen'] = grid

        print ("### Adding main panel")
        self.add(self.panels['main_screen'])
        self.show_all()
        self._cur_panels.append("main_screen")

    def _go_to_submenu(self, widget, menu):
        print "#### Go to submenu " + str(menu)
        self._remove_current_panel(False)

        # Find current menu item
        panels = list(self._cur_panels)
        cur_item = self._find_current_menu_item(menu, self._config, panels.pop(0))
        menu = cur_item['items']

        grid = self.arrangeMenuItems(menu, 4)

        b = KlippyGtk.ButtonImage('back', 'Back')
        b.connect("clicked", self._menu_go_back)
        grid.attach(b, 4, 2, 1, 1)

        self._cur_panels.append(cur_item['name']) #str(cur_item['name']))
        self.panels[cur_item['name']] = grid
        self.add(self.panels[cur_item['name']])
        self.show_all()



    def _find_current_menu_item(self, menu, items, names):
        # TODO: Make recursive
        return items[menu]


    def _remove_all_panels(self):
        while len(self._cur_panels) > 0:
            self._remove_current_panel()

    def _remove_current_panel(self, pop=True):
        print "1 " + str(self._cur_panels)
        print self.panels.keys()
        if len(self._cur_panels) > 0:
            self.remove(
                self.panels[
                    self._cur_panels[-1]
                ]
            )
            if pop == True:
                print "Popping _cur_panels"
                self._cur_panels.pop()
                if len(self._cur_panels) > 0:
                    self.add(self.panels[self._cur_panels[-1]])
                    self.show_all()

    def _menu_go_back (self, widget):
        print "#### Menu go back"
        self._remove_current_panel()

    def _websocket_callback(self, action, data):
        if action == "notify_klippy_state_changed":
            if data == "ready":
                print "### Going to ready state"
                self.printer_ready()
            elif data == "disconnect" or data == "shutdown":
                print "### Going to disconnected state"
                self.printer_initializing()

        elif action == "notify_status_update":
            #print data
            if "idle_status" in self.panels:
                if "heater_bed" in data:
                    self.panels['idle_status'].update_temp(
                        "bed",
                        round(data['heater_bed']['temperature'],1),
                        round(data['heater_bed']['target'],1)
                    )
                if "extruder" in data and data['extruder'] != "extruder":
                    self.panels['idle_status'].update_temp(
                        "tool0",
                        round(data['extruder']['temperature'],1),
                        round(data['extruder']['target'],1)
                    )


    def set_bed_temp (self, num, target):
        print str(num) + "C / " + str(target) + "C"
        if self.bed_temp_label == None:
            return
        self.bed_temp_label.set_text(str(num) + "C / " + str(target) + "C")

    def arrangeMenuItems (self, items, columns):
        grid = Gtk.Grid()
        grid.set_row_homogeneous(True)
        grid.set_column_homogeneous(True)

        l = len(items)
        i = 0
        print items
        for i in range(l):
            col = i % columns
            row = round(i/columns, 0)
            width = 1
            #if i+1 == l and l%2 == 1:
            #    width = 2
            b = KlippyGtk.ButtonImage(
                items[i]['icon'], items[i]['name'], "color"+str((i%4)+1)
            )
            if "items" in items[i]:
                b.connect("clicked", self._go_to_submenu, i)
            elif "method" in items[i]:
                params = items[i]['params'] if "params" in items[i] else {}
                b.connect("clicked", self._send_action, items[i]['method'], params)


            grid.attach(b, col, row, 1, width)

            i += 1

        return grid

    def _send_action(self, widget, method, params):
        self._ws.send_method(method, params)

    def printer_initializing(self):
        self._remove_all_panels()
        self.splash_screen()

    def printer_ready(self):
        self._remove_all_panels()
        self.main_panel()

    def on_button1_clicked(self, widget):
        print("Hello")

    def on_button2_clicked(self, widget):
        print("Goodbye")


win = KlipperScreen()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

#win = KlipperScreen()
#win.connect("destroy", Gtk.main_quit)
#win.show_all()
#Gtk.main()
