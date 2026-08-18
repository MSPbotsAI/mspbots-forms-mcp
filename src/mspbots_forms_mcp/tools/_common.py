from .._json import error_envelope

NO_TOKEN = error_envelope(
    "not_configured",
    "No Forms API credentials. Send the X-MSP-Token, X-MSP-Host, and X-MSP-Tenant-Id headers.",
    False,
)
