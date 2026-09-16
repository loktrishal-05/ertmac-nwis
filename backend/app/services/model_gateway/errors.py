"""Model-gateway exception hierarchy.

Every message here is a short, redacted diagnostic. No error message, log line
or exception raised by this package may contain full prompt text."""


class ModelGatewayError(Exception):
    """Base for every model-gateway failure."""


class ModelConfigurationError(ModelGatewayError, ValueError):
    """Bad URL, a host outside the allowlist, a denylisted hosted provider,
    an unknown runtime name, or an empty MODEL_NAME.

    Also inherits ValueError so pydantic's model_validator wraps it into a
    ValidationError uniformly with every other Settings-time failure, whether
    raised here or via a plain ValueError elsewhere in config.py."""


class ModelUnavailableError(ModelGatewayError):
    """Connect refused, DNS failure, the configured model tag is absent, or 404."""


class ModelTimeoutError(ModelGatewayError):
    """Connect or read deadline exceeded."""


class ModelRuntimeError(ModelGatewayError):
    """The runtime returned 5xx, or its response envelope was malformed."""


class StructuredOutputError(ModelGatewayError):
    """Output still failed schema validation after the bounded repair attempt."""

    def __init__(self, message: str, raw_text: str | None = None, validation_errors: str | None = None):
        super().__init__(message)
        self.raw_text = raw_text
        self.validation_errors = validation_errors


class ModelOutputTruncatedError(ModelGatewayError):
    """done_reason == 'length' where the caller forbade truncation."""


class ToolCallProtocolError(ModelGatewayError):
    """A tool call named something outside the supplied tool specs, or its
    arguments could not be parsed."""
