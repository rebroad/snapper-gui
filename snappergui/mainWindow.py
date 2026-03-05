from snappergui import snapper
import pkg_resources, subprocess, dbus
from snappergui.createSnapshot import createSnapshot
from snappergui.createConfig import createConfig
from snappergui.deleteDialog import deleteDialog
from snappergui.changesWindow import changesWindow
from snappergui.snapshotsView import snapshotsView
from gi.repository import Gtk
from time import strftime, localtime
from pwd import getpwuid
import os


class SnapperGUI():
    """docstring for SnapperGUI"""

    def __init__(self, app):
        super(SnapperGUI, self).__init__()
        self.builder = Gtk.Builder()
        self.builder.add_from_file(pkg_resources.resource_filename("snappergui",
                                                                   "glade/mainWindow.glade"))
        self.statusbar = self.builder.get_object("statusbar")
        self.snapshotsTreeView = self.builder.get_object("snapstreeview")
        self.configsGroup = self.builder.get_object("configsGroup")
        self.window = self.builder.get_object("applicationwindow1")
        self.stack = self.builder.get_object("stack1")
        self.builder.connect_signals(self)

        self.window.set_application(app)

        self.configView = {}
        self.pending_initial_snapshot_for = set()

        for config in snapper.ListConfigs():
            name = str(config[0])
            self.configView[name] = snapshotsView(name)
            self.stack.add_titled(self.configView[name].scrolledwindow, name, name)
            self.configView[name].selection.connect("changed",
                                                    self.on_snapshots_selection_changed)

        self.init_dbus_signal_handlers()
        self.window.show()

    def snapshot_columns(self, snapshot):
        if snapshot[3] == -1:
            date = "Now"
        else:
            date = strftime("%a %x %R", localtime(snapshot[3]))
        return [snapshot[0],
                snapshot[1],
                snapshot[2],
                date,
                getpwuid(snapshot[4])[0],
                snapshot[5],
                snapshot[6]]

    def get_current_config(self):
        return self.stack.get_visible_child_name()

    def on_stack_visible_child_changed(self, stack, property):
        self.update_controlls_and_userdatatreeview()

    def on_snapshots_selection_changed(self, selection):
        self.update_controlls_and_userdatatreeview()

    def update_controlls_and_userdatatreeview(self):
        config = self.get_current_config()
        userdatatreeview = self.builder.get_object("userdatatreeview")
        if config is not None:
            model, paths = self.configView[config].selection.get_selected_rows()
        if config is None or len(paths) == 0:
            self.builder.get_object("snapshotActions").set_sensitive(False)
            userdatatreeview.set_model(None)
        else:
            self.builder.get_object("snapshotActions").set_sensitive(True)

            if len(paths) == 1 and not model.iter_has_child(model.get_iter(paths[0])):
                self.builder.get_object("view-changes").set_sensitive(False)
            else:
                self.builder.get_object("view-changes").set_sensitive(True)

            try:
                snapshot_data = snapper.GetSnapshot(config, model[model.get_iter(paths[0])][0])
                userdata_liststore = Gtk.ListStore(str, str)
                for key, value in snapshot_data[7].items():
                    userdata_liststore.append([key, value])
                userdatatreeview.set_model(userdata_liststore)
            except dbus.exceptions.DBusException:
                pass

    def on_create_snapshot(self, widget):
        config = self.get_current_config()
        if config is None:
            self.on_create_config(widget)
            return
        dialog = createSnapshot(self.window, config)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            newSnapshot = snapper.CreateSingleSnapshot(dialog.config,
                                                       dialog.description,
                                                       dialog.cleanup,
                                                       dialog.userdata)
        elif response == Gtk.ResponseType.CANCEL:
            pass

    def on_create_config(self, widget):
        if os.geteuid() != 0:
            error_dialog = Gtk.MessageDialog(
                self.window, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                "Creating configurations requires root privileges.\n"
                "Please re-run snapper-gui as root."
            )
            error_dialog.run()
            error_dialog.destroy()
            return

        dialog = createConfig(self.window)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            try:
                self.pending_initial_snapshot_for.add(dialog.name)
                snapper.CreateConfig(dialog.name,
                                     dialog.subvolume,
                                     dialog.fstype,
                                     dialog.template)
            except dbus.exceptions.DBusException as error:
                if dialog.name in self.pending_initial_snapshot_for:
                    self.pending_initial_snapshot_for.remove(dialog.name)
                error_str = str(error)
                if ("error.no_permission" in error_str or
                        "error.no_permissions" in error_str or
                        "AccessDenied" in error_str):
                    message = "You don't have permission to create configurations"
                elif "subvolume already covered" in error_str:
                    message = ("Could not create configuration:\n"
                               "The selected subvolume is already covered by an existing "
                               "snapper configuration.")
                else:
                    message = "Could not create configuration:\n%s" % error_str
                error_dialog = Gtk.MessageDialog(self.window, 0, Gtk.MessageType.WARNING,
                                                 Gtk.ButtonsType.OK, message)
                error_dialog.run()
                error_dialog.destroy()
        elif response == Gtk.ResponseType.CANCEL:
            pass

    def on_delete_snapshot(self, widget):
        config = self.get_current_config()
        if config is None or config not in self.configView:
            return
        selection = self.configView[config].selection
        (model, paths) = selection.get_selected_rows()
        if len(paths) == 0:
            return
        snapshots = []
        for path in paths:
            treeiter = model.get_iter(path)
            # avoid duplicates because post snapshots are always added
            if model[treeiter][0] not in snapshots:
                snapshots.append(model[treeiter][0])
            # if snapshot has post add that to delete
            if model.iter_has_child(treeiter):
                child_treeiter = model.iter_children(treeiter)
                snapshots.append(model[child_treeiter][0])
        dialog = deleteDialog(self.window, config, snapshots)
        response = dialog.run()
        if response == Gtk.ResponseType.YES and len(dialog.to_delete) > 0:
            snapper.DeleteSnapshots(config, dialog.to_delete)

    def on_open_snapshot_folder(self, widget):
        config = self.get_current_config()
        if config is None or config not in self.configView:
            return
        selection = self.configView[config].selection
        model, paths = selection.get_selected_rows()
        if len(paths) == 0:
            return
        for path in paths:
            treeiter = model.get_iter(path)
            mountpoint = snapper.GetMountPoint(config, model[treeiter][0])
            if model[treeiter][6] != '':
                snapper.MountSnapshot(config, model[treeiter][0], 'true')
            subprocess.Popen(['xdg-open', mountpoint])
            self.statusbar.push(True,
                                "The mount point for the snapshot %s from %s is %s" %
                                (model[treeiter][0], config, mountpoint))

    def on_viewchanges_clicked(self, widget):
        config = self.get_current_config()
        if config is None or config not in self.configView:
            return
        selection = self.configView[config].selection
        model, paths = selection.get_selected_rows()
        if len(paths) == 0:
            return
        if len(paths) > 1:
            # open a changes window with the first and the last snapshot selected
            begin = model[paths[0]][0]
            end = model[paths[-1]][0]
            window = changesWindow(config, begin, end)
        elif len(paths) == 1 and model.iter_has_child(model.get_iter(paths[0])):
            # open a changes window with the selected pre snapshot and its corresponding post snapshot
            child_iter = model.iter_children(model.get_iter(paths[0]))
            begin = model[paths[0]][0]
            end = model.get_value(child_iter, 0)
            window = changesWindow(config, begin, end)

    def init_dbus_signal_handlers(self):
        signals = {
            "SnapshotCreated": self.on_dbus_snapshot_created,
            "SnapshotModified": self.on_dbus_snapshot_modified,
            "SnapshotsDeleted": self.on_dbus_snapshots_deleted,
            "ConfigCreated": self.on_dbus_config_created,
            "ConfigModified": self.on_dbus_config_modified,
            "ConfigDeleted": self.on_dbus_config_deleted
        }
        for signal, handler in signals.items():
            snapper.connect_to_signal(signal, handler)

    def on_dbus_snapshot_created(self, config, snapshot):
        if config not in self.configView:
            return
        if config in self.pending_initial_snapshot_for and str(snapshot) == "1":
            self.statusbar.push(True, "Initial snapshot created for new configuration %s" % config)
            self.pending_initial_snapshot_for.remove(config)
        else:
            self.statusbar.push(True, "Snapshot %s created for %s" % (str(snapshot), config))
        self.configView[config].add_snapshot_to_tree(str(snapshot))

    def on_dbus_snapshot_modified(self, config, snapshot):
        print("Snapshot SnapshotModified")

    def on_dbus_snapshots_deleted(self, config, snapshots):
        snaps_str = ""
        for snapshot in snapshots:
            snaps_str += str(snapshot) + " "
        self.statusbar.push(True, "Snapshots deleted from %s: %s" % (config, snaps_str))
        for deleted in snapshots:
            self.configView[config].remove_snapshot_from_tree(deleted)

    def on_dbus_config_created(self, config):
        self.configView[config] = snapshotsView(config)
        self.configView[config].update_view()
        self.stack.add_titled(self.configView[config].scrolledwindow, config, config)
        self.configView[config].selection.connect("changed",
                                                  self.on_snapshots_selection_changed)
        self.statusbar.push(5, "Created new configuration %s" % config)
        self.pending_initial_snapshot_for.add(config)

    def on_dbus_config_modified(self, args):
        print("Config Modified")

    def on_dbus_config_deleted(self, args):
        print("Config Deleted")

    def on_main_destroy(self, args):
        try:
            configs = snapper.ListConfigs()
        except dbus.exceptions.DBusException:
            return

        for config in configs:
            config_name = str(config[0])
            try:
                snapshots = snapper.ListSnapshots(config_name)
            except dbus.exceptions.DBusException:
                # Non-root users may not be allowed to list snapshots for all configs.
                continue
            for snapshot in snapshots:
                if snapshot[6] != '':
                    try:
                        snapper.UmountSnapshot(config_name, snapshot[0], 'true')
                    except dbus.exceptions.DBusException:
                        # Ignore permission failures while shutting down.
                        pass
