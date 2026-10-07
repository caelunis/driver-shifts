class DomainValidationError(Exception):
    """A business rule rejected a value; reported as a 422 error on that field."""

    def __init__(self, field: str, type_: str, msg: str, **ctx):
        super().__init__(msg)
        self.field, self.type, self.msg, self.ctx = field, type_, msg, ctx

    def as_detail(self) -> dict:
        # Same shape as FastAPI's own validation errors, so clients handle both alike
        return {"type": self.type, "loc": ["body", self.field], "msg": self.msg, "ctx": self.ctx}


class EmailTaken(Exception):
    pass


class TripConflict(Exception):
    """A trip with this id already exists, but with different data."""

    def __init__(self, existing):
        self.existing = existing


class NotFound(Exception):
    pass


class Conflict(Exception):
    """The request clashes with the current state (409), e.g. a shift is already open."""

    def __init__(self, code: str, message: str, **ctx):
        super().__init__(message)
        self.code, self.message, self.ctx = code, message, ctx
