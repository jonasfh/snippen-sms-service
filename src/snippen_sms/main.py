"""Main entry point for Snippen SMS Service."""


def get_status() -> dict[str, str]:
    """Return status of the SMS service."""
    return {"status": "ok", "service": "snippen-sms-service", "version": "0.1.0"}


if __name__ == "__main__":
    print(get_status())
