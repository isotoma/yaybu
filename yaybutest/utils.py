import os, signal, shlex, subprocess, tempfile, time, shutil
import testtools
from yaybu.core import error
from yaybu.util import sibpath

def default_distro():
    options = {
        "Ubuntu 9.10": "karmic",
        "Ubuntu 10.04": "lucid",
        "Ubuntu 10.10": "maverick",
        "Ubuntu 11.04": "natty",
        }
    sundayname = open("/etc/issue.net","r").read().strip()
    return options[sundayname[:12]]

def run_commands(commands, base_image, distro=None):
    for command in commands:
        command = command % dict(base_image=base_image, distro=distro)
        p = subprocess.Popen(shlex.split(command))
        if p.wait():
            raise SystemExit("Command failed")


def build_environment(base_image):
    distro = default_distro()
    commands = [
        "fakeroot fakechroot -s debootstrap --variant=fakechroot --include=python-setuptools,python-dateutil,python-magic,ubuntu-keyring,gpgv %(distro)s %(base_image)s",
        "fakeroot fakechroot -s /usr/sbin/chroot %(base_image)s apt-get update",
        ]
    if not os.path.exists(base_image):
        run_commands(commands, base_image, distro)
    refresh_environment(base_image)

def refresh_environment(base_image):
    commands = [
        "rm -rf /usr/local/lib/python2.6/dist-packages/Yaybu*",
        "python setup.py sdist --dist-dir %(base_image)s",
        "fakeroot fakechroot -s /usr/sbin/chroot %(base_image)s sh -c 'easy_install /Yaybu-*.tar.gz'",
        ]
    run_commands(commands, base_image)


class TestCase(testtools.TestCase):

    fakerootkey = None

    test_network = os.environ.get("TEST_NETWORK", "0") == "1"

    def cleanup_session(self):
        if self.faked:
            os.kill(int(self.faked.strip()), signal.SIGTERM)
            self.faked = None

    def get_session(self):
        if self.fakerootkey:
            return self.fakerootkey

        p = subprocess.Popen(['faked-sysv'], stdout=subprocess.PIPE)
        self.addCleanup(self.cleanup_session)

        stdout, stderr = p.communicate()
        self.fakerootkey, self.faked = stdout.split(":")
        return self.fakerootkey

    def write_temporary_file(self, contents):
        f = tempfile.NamedTemporaryFile(dir=os.path.join(self.chroot_path, 'tmp'), delete=False)
        f.write(contents)
        f.close()
        return f.name

    def call(self, command):
        env = os.environ.copy()
        env['FAKEROOTKEY'] = self.get_session()
        env['LD_PRELOAD'] = "/usr/lib/libfakeroot/libfakeroot-sysv.so"

        chroot = ["fakechroot", "-s", "cow-shell", "/usr/sbin/chroot", self.chroot_path]
        retval = subprocess.call(chroot + command, cwd=self.chroot_path, env=env)
        self.wait_for_cowdancer()
        return retval

    def yaybu(self, *args):
        filespath = os.path.join(self.chroot_path, "tmp", "files")
        args = list(args)
        if self.test_network:
            args.insert(0, "localhost")
            args.insert(0, "--host")

        return self.call(["yaybu", "-d", "--ypath", filespath] + list(args))

    def simulate(self, *args):
        """ Run yaybu in simulate mode """
        args = ["--simulate"] + list(args)
        return self.yaybu(*args)

    def apply(self, contents, *args):
        path = self.write_temporary_file(contents)
        return self.yaybu(path, *args)

    def apply_simulate(self, contents):
        path = self.write_temporary_file(contents)
        return self.simulate(path)

    def check_apply(self, contents, *args):
        # Apply the change in simulate mode
        sim_args = list(args) + ["-s"]
        rv = self.apply(contents, *sim_args)
        self.failUnlessEqual(rv, 0, "Simulation failed")

        # Apply the change for real
        rv = self.apply(contents, *args)
        self.failUnlessEqual(rv, 0, "Apply failed")

        # If we apply the change again nothing should be changed
        rv = self.apply(contents, *args)
        self.failUnlessEqual(rv, error.NothingChanged.returncode, "Change still outstanding on 2nd run")

    def check_apply_simulate(self, contents):
        rv = self.apply_simulate(contents)
        if rv != 0:
            raise subprocess.CalledProcessError(rv, "yaybu")

    def wait_for_cowdancer(self):
        # give cowdancer a few seconds to exit (avoids a race where it delets another sessions .ilist)
        for i in range(20):
            if not os.path.exists(os.path.join(self.chroot_path, ".ilist")):
                break
            time.sleep(0.1)

    def setUp(self):
        super(TestCase, self).setUp()
        self.chroot_path = os.path.realpath("tmp")
        subprocess.check_call(["cp", "-al", os.getenv("YAYBU_TESTS_BASE"), self.chroot_path])

        sshsrc = sibpath(__file__, "files/ssh")
        sshdst = os.path.join(self.chroot_path, "usr", "bin", "ssh")
        shutil.copy(sshsrc, sshdst)

        cfgsrc = sibpath(__file__, "files/yaybu.cfg")
        cfgdest = os.path.join(self.chroot_path, "etc", "yaybu")
        shutil.copy(cfgsrc, cfgdest)

    def tearDown(self):
        super(TestCase, self).tearDown()

        subprocess.check_call(["rm", "-rf", self.chroot_path])

    def failUnlessExists(self, path):
        full_path = self.enpathinate(path)
        self.failUnless(os.path.exists(full_path))

    def enpathinate(self, path):
        return os.path.join(self.chroot_path, *path.split(os.path.sep))

    def get_user(self, user):
        users_list = open(self.enpathinate("/etc/passwd")).read().splitlines()
        users = dict(u.split(":", 1) for u in users_list)
        return users[user].split(":")

    def get_group(self, group):
        # Returns a tuple of group info if the group exists, or raises KeyError if it does not
        groups_list = open(self.enpathinate("/etc/group")).read().splitlines()
        groups = dict(g.split(":", 1) for g in groups_list)
        return groups[group].split(":")
