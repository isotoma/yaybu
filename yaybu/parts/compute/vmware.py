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

# This driver presents a libcloud interface around vmrun - the command line API
# for controlling VMWare VM's.

# Base image notes:
#1. Install vmware tools from packages.vmware.com/tools - the latest esx ones work with vmware fusion
#2. Don't forget to delete the persistent net rules
#3. There needs to be a user with a password/key that can get to root without sudo requiring a passphrase.

#============================================================================================
# libcloud/common/proces.py

import os
import shlex
import subprocess
from pipes import quote

from libcloud.common.types import LibcloudError


class Response(object):

    def __init__(self, status, body, error):
        self.status = status
        self.body = body
        self.error = error

        if not self.success():
            raise LibcloudError(self.parse_error())

        self.object = self.parse_body()

    def parse_body(self):
        return self.body

    def parse_error(self):
        return self.error

    def success(self):
        return self.status == 0


class Connection(object):

    responseCls = Response
    log = None

    def  __init__(self, secure=True, host=None, port=None, url=None,
                  timeout=None):
        pass

    def connect(self):
        pass

    def request(self, command, data='', capture_output=True):
        if not isinstance(command, list):
            command = shlex.split(command)

        if self.log:
            self.log.write(' '.join(quote(c) for c in command) + '\n')

        if not capture_output:
            stdout, stderr = '', ''
            returncode = self._silent_request(command, data)
        else:
            returncode, stdout, stderr = self._request(command, data)

        if self.log:
            self.log.write("# returncode is %d\n" % returncode)
            self.log.write("# -------- begin stdout ----------\n")
            self.log.write(stdout)
            self.log.write("# -------- begin stderr ----------\n")
            self.log.write(stderr)
            self.log.write("# -------- end ----------\n")

        return self.responseCls(returncode, stdout, stderr)

    def _request(self, command, data):
        stdin = subprocess.PIPE if data else None
        p = subprocess.Popen(command, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate(data)
        return p.returncode, stdout, stderr

    def _silent_request(self, command, data):
        stdin = subprocess.PIPE if data else None
        with open(os.devnull, "w") as null:
            p = subprocess.Popen(command, stdin=stdin, stdout=null, stderr=null)
            if data:
                p.stdin.write(data)
                p.stdin.close()
            return p.wait()

#=========================================================================================================

import os
import glob
import logging
import shutil
import uuid

from libcloud.common.types import LibcloudError
from libcloud.compute.base import NodeDriver, Node, NodeSize, NodeImage
from libcloud.compute.base import NodeState
from libcloud.compute.types import Provider

# FIXME:
Provider.VMWARE = 99

class VMXFile(object):

    def __init__(self, path):
        self.path = path
        self.settings = {}
        self.load()

    def load(self):
        self.settings = {}
        with open(self.path, "r") as fp:
            for line in fp.readlines():
                if not line.strip():
                    continue
                if line.sartswith('#'):
                    continue
                k, v = line.split("=", 1)
                self.settings[k.strip().lower()] = v.strip()

    def save(self):
        with open(self.path, "w") as fp:
            for key in sorted(self.settings.keys()):
                fp.write("%s = %s\n" % (key, self.settings[key]))

    def __getitem__(self, key):
        return self.settings[key]

    def __setitem__(self, key, value):
        self.settings[key] = value
        self.save()


class VMWareDriver(NodeDriver):

    type = Provider.VMWARE
    name = "vmware"
    website = "http://www.vmware.com/products/fusion/"
    connectionCls = Connection

    def __init__(self, vm_library="~/.libcloud/vmware/library", vm_instances="~/.libcloud/vmware/instances", vmrun=None, hosttype=None):
        super(VMWareDriver, self).__init__(None)
        self.vm_library = os.path.expanduser(vm_library)
        self.vm_instances = os.path.expanduser(vm_instances)
        self.vmrun = vmrun or self._find_vmrun()
        self.hosttype = hosttype or self._find_hosttype()

    def _find_vmrun(self):
        known_locations = [
            "/Applications/VMWare Fusion.app/Contents/Library",
            "/usr/bin",
            ]
        for dir in known_locations:
            path = os.path.join(dir, "vmrun")
            if os.path.exists(path):
                return path
        raise LibcloudError('VMWareDriver requires \'vmrun\' executable to be present on system')

    def _find_hosttype(self):
        default_hosttypes = [
            'ws',
            'fusion',
            'player',
            ]
        for hosttype in default_hosttypes:
            command = [self.vmrun, "-T", hosttype, "list"]
            try:
                resp = self.connection.request(command)
            except LibcloudError:
                continue
            else:
                return hosttype
        raise LibcloudError('VMWareDriver is unable to find a default host type. Please specify the hosttype argument')

    def _action(self, *params, **kwargs):
        capture_output = kwargs.get('capture_output', True)
        command = [self.vmrun, "-T", self.hosttype] + list(params)
        return self.connection.request(command, capture_output=capture_output).body

    def list_images(self, location=None):
        if not location:
            location = self.vm_library
        locs = []
        for match in glob.glob(os.path.join(location, "*", "*.vmx")):
            locs.append(NodeImage(id=match, name="VMWare Image", driver=self))
        return locs

    def list_sizes(self, location=None):
        return [
            NodeSize("small", "small", 1024, 0, 0, 0, self),
            NodeSize("medium", "medium", 4096, 0, 0, 0, self),
            NodeSize("large", "large", 8192, 0, 0, 0, self),
            ]

    def list_locations(self):
        return []

    def list_nodes(self):
        nodes = []
        lines = iter(self._action("list").strip().splitlines())
        lines.next() # Skip the summary line
        for line in lines:
            if not line.strip():
                continue
            n = Node(line.strip(), line.strip(), NodeState.UNKNOWN, None, None, self)
            n.name = self._action("readVariable", n.id, "runtimeConfig", "displayName")
            ip = self._action("readVariable", n.id, "guestVar", "ip").strip()
            if ip:
                n.public_ips = [ip]
                n.state = NodeState.RUNNING
            nodes.append(n)
        return nodes

    def create_node(self, name, size, image):
        source = image.id
        if not os.path.exists(source):
            raise LibcloudError("Base image is not valid")

        target_dir = os.path.join(self.vm_instances, str(uuid.uuid4()))
        target = os.path.join(target_dir, "vm.vmx")

        target_parent = os.path.dirname(target_dir)
        if not os.path.exists(target_parent):
            os.makedirs(target_parent)

        # First try to clone the VM with the VMWare commands. We do this in
        # the hope that they know what the fastest and most efficient way to
        # clone an image is. But if that fails we can just copy the entire
        # image directory.
        try:
            self._action("clone", source, target)
        except LibcloudError:
            src_path = os.path.dirname(source)
            shutil.copytree(src_path, target_dir)
            os.rename(os.path.join(target_dir, os.path.basename(source)), target)

        node = Node(target, name, NodeState.PENDING, None, None, self)

        # If a NodeSize is provided then we can control the amount of RAM the
        # VM has. Number of CPU's would be easy to scale too, but this isn't
        # exposed on a NodeSize

        # if size:
        #     if size.ram:
        #        self.ex_set_runtime_variable(node, "displayName", name, str(size.ram))
        #        self._action("writeVariable", target, "runtimeConfig", "memsize", str(size.ram))

        self._action("start", target, "nogui", capture_output=False)
        self.ex_set_runtime_variable(node, "displayName", name)
        return Node(target, name, NodeState.PENDING, None, None, self)

    def reboot_node(self, node):
        self._action("reset", node.id, "hard")
        node.state = NodeState.REBOOTING

    def destroy_node(self, node):
        self._action("stop", node.id, "hard")
        self._action("deleteVM", node.id)
        shutil.rmtree(os.path.dirname(node.id))

    def ex_get_runtime_variable(self, node, variable):
        return self._action("readVariable", node.id, "runtimeConfig", variable)

    def ex_set_runtime_variable(self, node, variable, value):
        self._action("writeVariable", node.id, "runtimeConfig", variable, value)

