# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import tempfile
import subprocess
import logging
import StringIO
import yaml

from . import error

from yaybu.compute.util import SubRunner, SubRunnerException

logger = logging.getLogger("cloudinit")

genisoimage = SubRunner(
    command_name="genisoimage",
    args=["-output", "{seedfile}",
          "-volid", "cidata",
          "-joliet", "-rock"],
    log_execution=True,
)

vmware_tools_install = [
    ['mkdir', '/vmware'],
    ['mount', '/dev/sr1', '/vmware'],
    ['bash', '-c', '"tar -zxf /vmware/VMwareTools-*.tar.gz"'],
    #['umount', '/dev/sr1'],
    ['vmware-tools-distrib/vmware-install.pl', '--d'],
    #['rm', '-rf', 'vmware-tools-distrib'],
]

# there is probably a neater way of doing this
open_tools_install = [
    ['sed', '-i', "'/^# deb.*multiverse/ s/^# //'", '/etc/apt/sources.list'],
    ['apt-get', 'update'],
    ['apt-get', 'install', '-y', 'open-vm-tools'],
]

default_config = {
        "password": "password",
        "chpasswd": {
            "expire": False,
        },
        "ssh_pwauth": True,
        "apt_upgrade": False,
        "runcmd": vmware_tools_install,
}

        #print >> f, "password: password"
        #print >> f, "chpasswd: { expire: False }"
        #print >> f, "ssh_pwauth: True"
        #print >> f, "apt_upgrade: true"
        #print >> f, "runcmd:"
        #if tools == "open":
            #print >> f, "  - [ sed, -i, '/^# deb.*multiverse/ s/^# //', /etc/apt/sources.list ]"
            #print >> f, "  - [ apt-get, update ]"
            #print >> f, "  - [ apt-get, install, -y, open-vm-tools ]"
        #elif tools == "vmware":
            #print >> f, "  - [ mkdir, /vmware ]"
            #print >> f, "  - [ mount, /dev/sr1, /vmware ]"
            #print >> f, '  - [ bash, -c, "tar -zxf /vmware/VMwareTools-*.tar.gz" ]'
            #print >> f, "  - [ umount, /dev/sr1 ]"
            #print >> f, "  - [ vmware-tools-distrib/vmware-install.pl, --d]"
            #print >> f, "  - [ rm, -rf, vmware-tools-distrib ]"

class CloudConfig:

    filename = "user-data"

    def __init__(self, config=None):
        self.config = config
        if self.config is None:
            self.config = default_config

    def as_dict(self):
        return self.config

    def open(self):
        f = StringIO.StringIO()
        print >> f, "#cloud-config"
        print >> f, yaml.dump(self.config)
        return StringIO.StringIO(f.getvalue())

class MetaData:

    filename = "meta-data"

    def __init__(self, instance_id, localhost="localhost"):
        self.instance_id = instance_id
        self.localhost = localhost

    def as_dict(self):
        return {
            "local-hostname": self.localhost,
            "instance-id": self.instance_id,
        }

    def open(self):
        return StringIO.StringIO(yaml.dump(self.as_dict()))

class Seed:

    def __init__(self, seedfile, config_files):
        self.seedfile = seedfile
        self.files = config_files
        self.tmpdir = tempfile.mkdtemp()

    @property
    def filenames(self):
        for f in self.files:
            yield f.filename

    def _save(self):
        """ Overwrite the seed ISO file. Will clobber it potentially."""
        genisoimage(*self.filenames, seedfile=self.seedfile, cwd=self.tmpdir)

    def open(self, filename):
        path = os.path.join(self.tmpdir, filename)
        return open(path, "w")

    def _output(self, cloudfile):
        fout = self.open(cloudfile.filename)
        fin = cloudfile.open()
        fout.write(fin.read())

    def create(self):
        for f in self.files:
            self._output(f)
        self._save()
        self._cleanup()

    def _cleanup(self):
        for f in self.filenames:
            os.unlink(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)
