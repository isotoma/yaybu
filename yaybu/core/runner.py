
import optparse

import yay

from yaybu.core import shell
from yaybu.core.resource import MetaResource


class LoaderError(Exception):
    pass


class Runner(object):

    def __init__(self, registry=None):
        self.resources = []
        self.registry = registry or MetaResource.resources

    def create_resource(self, typename, instance):
        kls = self.registry[typename](**instance)
        self.resources.append(kls)

    def create_resources_of_type(self, typename, instances):
        # Create a Resource object for each item
        for instance in instances:
            self.create_resource(typename, instance)

    def create_resources(self, resources):
        for resource in resources:
            if len(resource.keys()) > 1:
                raise LoaderError("Too many keys in list item")

            typename, instances = resource.items()[0]

            if not isinstance(instances, list):
                instances = [instances]

            self.create_resources_of_type(typename, instances)

    def run(self):
        parser = optparse.OptionParser()
        parser.add_option("-s", "--simulate", default=False, action="store_true")
        opts, args = parser.parse_args()

        config = yay.load_uri(args[0])

        self.create_resources(config.get("resources", []))

        shell = shell.Shell(simulate=opts.simulate)

        for resource in self.resources:
            provider = resource.select_provider(None)
            provider.action_create(shell)

        return 0


def main():
    return Runner().run()

