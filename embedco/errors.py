"""Exception hierarchy.

``BlockError`` is raised by the code generator for bad block graphs.
``ServiceError`` subclasses carry the HTTP status the web layer should answer
with, so services never need to know about HTTP details beyond that number.
"""


class BlockError(ValueError):
    """A block graph cannot be turned into code."""


class ServiceError(Exception):
    """Base class for expected, user-facing service failures."""

    status = 400

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status


class ValidationError(ServiceError):
    status = 400


class ForbiddenError(ServiceError):
    status = 403


class NotFoundError(ServiceError):
    status = 404


class ConflictError(ServiceError):
    status = 409


class PayloadTooLargeError(ServiceError):
    status = 413


class DefinitionError(ValueError):
    """A block / board / plugin definition file is malformed."""
