class HarnessError(ValueError):
    """A user-actionable contract, package, or filesystem error."""


class ValidationError(HarnessError):
    pass


class PackageError(HarnessError):
    pass


class InstallError(HarnessError):
    pass


class RecordError(HarnessError):
    pass


class EvaluationError(HarnessError):
    pass
