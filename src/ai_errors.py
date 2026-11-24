class AIError(Exception):
    """An AI provider error with a message that is safe to show to the user."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def provider_status(status_code: int) -> int:
    """Maps a provider's HTTP status to ours. 4xx (no credits, unknown model, rate limit)
    pass through; a bad server-side key (401) or a provider outage becomes 502."""
    if status_code == 401 or not 400 <= status_code < 500:
        return 502
    return status_code
