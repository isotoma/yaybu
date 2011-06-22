# Copyright 2011 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import logging
import logging.handlers
import subprocess
import getpass

from yaybu.core import resource
from yaybu.core import error
from yaybu.core import runcontext
from yaybu.core import event

logger = logging.getLogger("runner")

class LoaderError(Exception):
    pass


class Runner(object):

    resources = None

    def configure_session_logging(self, opts):
        root = logging.getLogger()
        root.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)

    def configure_audit_logging(self, opts):
        """ configure the audit trail to log to file or to syslog """

        if opts.simulate:
            return

        levels = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL,
            }

        log_level = levels.get(opts.log_level, None)
        if log_level is None:
            raise KeyError("Log level %s not recognised, terminating" % opts.log_level)

        if opts.logfile is not None and opts.logfile != '-':
            logging.basicConfig(filename=opts.logfile,
                                filemode="a",
                                format="%(asctime)s %(levelname)s %(message)s",
                                level=log_level)
        else:
            facility = getattr(logging.handlers.SysLogHandler, "LOG_LOCAL%s" % opts.log_facility)
            handler = logging.handlers.SysLogHandler("/dev/log", facility=facility)
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            handler.setFormatter(formatter)
            logging.getLogger().addHandler(handler)

    def trampoline(self, username):
        command = ["sudo", "-u", username] + sys.argv[0:1]

        if "SSH_AUTH_SOCK" in os.environ:
            command.extend(["--ssh-auth-sock", os.environ["SSH_AUTH_SOCK"]])

        command.extend(sys.argv[1:])

        os.execvp(command[0], command)

    def run(self, opts, args):
        """ Run locally. """
        if opts.user and getpass.getuser() != opts.user:
            self.trampoline(opts.user)
            return 0

        if opts.debug:
            opts.logfile = "-"
            opts.verbose = 2

        self.configure_session_logging(opts)
        self.configure_audit_logging(opts)

        event.EventState.save_file = "/var/run/yaybu/events.saved"

        # This makes me a little sad inside, but the whole
        # context thing needs a little thought before jumping in
        event.state.simulate = opts.simulate

        if not opts.simulate:
            save_parent = os.path.realpath(os.path.join(event.EventState.save_file, os.path.pardir))
            if not os.path.exists(save_parent):
                os.mkdir(save_parent)

        try:
            if not opts.remote:
                ctx = runcontext.RunContext(args[0], opts)
            else:
                ctx = runcontext.RemoteRunContext(args[0], opts)

            if os.path.exists(event.EventState.save_file):
                if opts.resume:
                    event.state.loaded = False
                elif opts.no_resume:
                    if not opts.simulate:
                        os.unlink(event.EventState.save_file)
                    event.state.loaded = True
                else:
                    raise error.SavedEventsAndNoInstruction("There is a saved events file - you need to specify --resume or --no-resume")

            config = ctx.get_config()

            self.resources = resource.ResourceBundle(config.get("resources", []))
            self.resources.bind()
            changed = self.resources.apply(ctx, config)

            if not opts.simulate and os.path.exists(event.EventState.save_file):
                os.unlink(event.EventState.save_file)

            if not changed:
                # nothing changed
                ctx.changelog.info("No changes were required")
                sys.exit(255)

            ctx.changelog.info("All changes were applied successfully")
            sys.exit(0)

        except error.ExecutionError, e:
            # this will have been reported by the context manager, so we wish to terminate
            # but not to raise it further. Other exceptions should be fully reported with
            # tracebacks etc automatically
            print >>sys.stderr, "Terminated due to execution error in processing"
            sys.exit(e.returncode)
        except error.Error, e:
            # If its not an Execution error then it won't have been logged by the
            # Resource.apply() machinery - make sure we log it here.
            ctx.changelog.write(str(e))
            print >>sys.stderr, "Terminated due to execution error in processing"
            sys.exit(e.returncode)

