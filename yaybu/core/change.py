
""" Classes that handle logging of changes. """

import abc
import sys
import logging
import types

from yaybu.core import error

logger = logging.getLogger("audit")


class ResourceHeaderHandler(object):

    """ Automatically add a header and footer to log messages about particular
    resources """

    def __init__(self, target):
        self.target = target
        self.resource = None

    def emit(self, record):
        next_resource = getattr(record, "resource", None)

        # Is the logging now about a different resource?
        if self.resource != next_resource:

            # If there was already a resource, let us add a footer
            if self.resource:
                self.render_resource_footer()

            self.resource = next_resource

            # Are we now logging for a new resource?
            if self.resource:
                self.render_resource_header()

        self.target.emit(record)

    def render_resource_header(self):
        rl = len(unicode(self.resource))
        if rl < 80:
            total_minuses = 77 - rl
            minuses = total_minuses/2
            leftover = total_minuses % 2
        else:
            minuses = 4
            leftover = 0

        self.target.emit("/%s %r %s" % ("-"*minuses,
                                 self.resource,
                                 "-"*(minuses + leftover)))

    def render_resource_footer(self):
        self.target.emit("\%s" % ("-" *79,))
        self.target.emit("")


class Change(object):
    """ Base class for changes """

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def apply(self, renderer):
        """ Apply the specified change. The supplied renderer will be
        instantiated as below. """

class AttributeChange(Change):
    """ A change to one attribute of a file's metadata """

class ChangeRendererType(type):

    """ Keeps a registry of available renderers by type. The only types
    supported are text """

    renderers = {}

    def __new__(meta, class_name, bases, new_attrs):
        cls = type.__new__(meta, class_name, bases, new_attrs)
        if cls.renderer_for is not None:
            ChangeRendererType.renderers[(cls.renderer_type, cls.renderer_for)] = cls
        return cls

class ChangeRenderer:

    """ A class that knows how to render a change. """

    __metaclass__ = ChangeRendererType

    renderer_for = None
    renderer_type = None

    def __init__(self, logger, verbose):
        self.logger = logger
        self.verbose = verbose

    def render(self, logger):
        pass

class TextRenderer(ChangeRenderer):
    renderer_type = "text"

class ResourceChange(object):

    """ A context manager that handles logging per resource. This allows us to
    elide unchanged resources, which is the default logging output option. """

    def __init__(self, changelog, resource):
        self.changelog = changelog
        self.resource = resource

        # We wrap the logger so it always has context information
        logger = logging.getLogger("yaybu.changelog")
        self.logger = logging.LoggerAdapter(logger, dict(resource=unicode(resource)))

    def info(self, message, *args):
        self.logger.info(message, *args)

    def notice(self, message, *args):
        self.logger.info(message, *args)

    def __enter__(self):
        self.changelog.current_resource = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exc_type = exc_type
        self.exc_val = exc_val
        self.exc_tb = exc_tb

        if self.exc_val is not None:
            self.notice("Exception: %s" % (self.exc_val,))

        self.changelog.current_resource = None


class ChangeLog:

    """ Orchestrate writing output to a changelog. """

    def __init__(self, context):
        self.current_resource = None
        self.ctx = context
        self.verbose = self.ctx.verbose

        self.logger = logging.getLogger("yaybu.changelog")

    def write(self, line=""):
        #FIXME: Very much needs removing
        self.logger.info("%s", line)

    def resource(self, resource):
        return ResourceChange(self, resource)

    def apply(self, change):
        """ Execute the change, passing it the appropriate renderer to use. """
        renderers = []
        text_class = ChangeRendererType.renderers.get(("text", change.__class__), None)
        return change.apply(text_class(self, self.verbose))

    def info(self, message, *args, **kwargs):
        """ Write a textual information message. This is used for both the
        audit trail and the text console log. """
        if self.current_resource:
            self.current_resource.info(message)
        else:
            self.logger.info("%s", message, *args)

    def notice(self, message, *args, **kwargs):
        """ Write a textual notification message. This is used for both the
        audit trail and the text console log. """
        if self.current_resource:
            self.current_resource.notice(message)
        else:
            self.logger.info("%s", message, *args)


