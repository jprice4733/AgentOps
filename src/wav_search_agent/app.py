"""Compatibility entry point for the S3-backed application."""


def create_app():
    from main import create_app as factory
    return factory()
