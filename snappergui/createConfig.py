from snappergui import snapper
import pkg_resources
import subprocess
from gi.repository import Gtk


class createConfig(object):
    """docstring for createConfig"""

    def __init__(self, parent):
        super(createConfig, self).__init__()
        builder = Gtk.Builder()
        builder.add_from_file(pkg_resources.resource_filename("snappergui",
                                                              "glade/createConfig.glade"))
        self.dialog = builder.get_object("createConfig")
        self.dialog.set_transient_for(parent)
        builder.connect_signals(self)
        self.subvolume_combo = builder.get_object("configSubvolume")
        self.subvolume_entry = self.subvolume_combo.get_child()

        self.name = ""
        self.subvolume = ""
        self.fstype = "btrfs"
        self.template = "default"

        builder.get_object("fsTypeCombo").set_active(0)
        self.subvolume_entry.connect("changed", self.on_subvolume_entry_changed)
        self.populate_subvolumes()

    def on_name_changed(self, widget):
        self.name = widget.get_chars(0, -1)

    def on_subvolume_changed(self, widget):
        self.subvolume = widget.get_active_text() or ""
        self.subvolume_entry.set_text(self.subvolume)
        self.subvolume_entry.set_position(-1)

    def on_subvolume_entry_changed(self, widget):
        self.subvolume = widget.get_text()

    def on_fstype_changed(self, widget):
        self.fstype = widget.get_active_text()
        self.populate_subvolumes()

    def on_template_changed(self, widget):
        self.template = widget.get_chars(0, -1)

    def run(self):
        return self.dialog.run()

    def destroy(self):
        self.dialog.destroy()

    def populate_subvolumes(self):
        subvolumes = self._list_subvolumes_for_fstype(self.fstype)
        self.subvolume_combo.remove_all()
        for subvolume in subvolumes:
            self.subvolume_combo.append_text(subvolume)
        if subvolumes:
            self.subvolume_combo.set_active(0)
        else:
            self.subvolume_entry.set_text("")
            self.subvolume = ""

    def _list_subvolumes_for_fstype(self, fstype):
        mountpoints = []
        try:
            output = subprocess.check_output(
                ['findmnt', '-rn', '-t', fstype, '-o', 'TARGET'],
                universal_newlines=True
            )
            mountpoints = [line.strip() for line in output.splitlines() if line.strip()]
        except (subprocess.CalledProcessError, OSError):
            try:
                with open('/proc/self/mounts', 'r') as mounts_file:
                    for line in mounts_file:
                        parts = line.split()
                        if len(parts) >= 3 and parts[2] == fstype:
                            mountpoints.append(parts[1].replace('\\040', ' '))
            except OSError:
                return []

        # Preserve discovery order while removing duplicates.
        deduped = []
        for mountpoint in mountpoints:
            if mountpoint not in deduped:
                deduped.append(mountpoint)
        return deduped
