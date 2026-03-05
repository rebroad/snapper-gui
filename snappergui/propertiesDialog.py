from snappergui import snapper
import pkg_resources, dbus
from gi.repository import Gtk


class PropertiesTab(object):
    """docstring for PropertiesTab"""

    def __init__(self, config):
        builder = Gtk.Builder()
        builder.add_from_file(pkg_resources.resource_filename("snappergui",
                                                              "glade/propertiesDialog.glade"))
        self.configsGrid = builder.get_object("configsGrid")

        self.widgets = {}
        for k, v in config[2].items():
            widget = builder.get_object(k)
            if widget is None:
                # Unknown/new snapper option without a dedicated UI control.
                self.widgets[k] = None
                continue
            # Values are set here depending on their types
            if type(widget) == Gtk.Entry:
                widget.set_text(v)
            elif type(widget) == Gtk.SpinButton:
                adjustment = Gtk.Adjustment(value=int(v),
                                            lower=0, upper=5000,
                                            step_increment=1,
                                            page_increment=10,
                                            page_size=0)
                widget.set_adjustment(adjustment)
            elif type(widget) == Gtk.Switch:
                if v == "yes":
                    widget.set_active(True)
                elif v == "no":
                    widget.set_active(False)
            else:
                print("WARNING: Unsupported widget type for property \"%s\"." % k)
            self.widgets[k] = widget

    def get_current_value(self, setting):
        widget = self.widgets[setting]
        if widget is None:
            return None
        if type(widget) == Gtk.Entry:
            return widget.get_text()
        elif type(widget) == Gtk.Switch:
            if widget.get_active():
                return "yes"
            else:
                return "no"
        elif type(widget) == Gtk.SpinButton:
            return str(int(widget.get_value()))


class propertiesDialog(object):
    """docstring for propertiesDialog"""

    def __init__(self, widget, parent):
        self.parent = parent
        self.config_names = []
        self.permission_denied = False
        self.config_load_error = None

        builder = Gtk.Builder()
        builder.add_from_file(pkg_resources.resource_filename("snappergui",
                                                              "glade/propertiesDialog.glade"))
        self.dialog = builder.get_object("dialogProperties")
        self.notebook = builder.get_object("notebookProperties")
        builder.connect_signals(self)

        self.dialog.set_transient_for(parent)

        self.tabs = {}
        try:
            configs = snapper.ListConfigs()
        except dbus.exceptions.DBusException as error:
            configs = []
            error_str = str(error)
            if "AccessDenied" in error_str or "error.no_permission" in error_str:
                self.permission_denied = True
            else:
                self.config_load_error = error_str

        for config in configs:
            currentTab = PropertiesTab(config)
            config_name = str(config[0])
            self.config_names.append(config_name)
            self.tabs[config_name] = currentTab
            self.notebook.append_page(currentTab.configsGrid, Gtk.Label.new(config_name))

        if len(self.config_names) == 0:
            warning_text = "No snapper configurations are available."
            if self.permission_denied:
                warning_text += "\nPermission denied while reading configurations."
            elif self.config_load_error:
                warning_text += "\nCould not read configurations."
            warning_label = Gtk.Label.new(warning_text)
            warning_label.set_line_wrap(True)
            warning_label.set_margin_left(10)
            warning_label.set_margin_right(10)
            warning_label.set_margin_top(10)
            warning_label.set_margin_bottom(10)
            warning_label.set_xalign(0)
            self.notebook.append_page(warning_label, Gtk.Label.new("Warning"))
            self.dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        self.notebook.show_all()

    def get_changed_settings(self, config):
        changed = {}
        for k, v in snapper.GetConfig(config)[2].items():
            currentValue = self.tabs[config].get_current_value(k)
            if currentValue and v != currentValue:
                changed[k] = currentValue
        return changed

    def on_response(self, widget, response):
        if response == Gtk.ResponseType.OK:
            current_page = self.notebook.get_current_page()
            if current_page < 0 or current_page >= len(self.config_names):
                self.dialog.destroy()
                return
            currentConfig = self.config_names[current_page]
            try:
                snapper.SetConfig(currentConfig, self.get_changed_settings(currentConfig))
            except dbus.exceptions.DBusException as error:
                if str(error).find("error.no_permission") != -1:
                    self.dialog.destroy()
                    dialog = Gtk.MessageDialog(self.parent, 0, Gtk.MessageType.WARNING,
                                               Gtk.ButtonsType.OK,
                                               "You don't have permission to edit configurations")
                    dialog.run()
                    dialog.destroy()
