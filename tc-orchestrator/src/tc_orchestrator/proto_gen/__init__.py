"""Generated gRPC stubs for the Workspace Daemon.

These files are produced from ``daemon.proto`` and ``health.proto`` (copied
from ``backend-rust/proto/``) using ``grpcio-tools``. They are committed so
that the orchestrator does not require ``protoc`` at install time.

Regenerate with::

    python -m grpc_tools.protoc -I. \\
        --python_out=. --grpc_python_out=. --pyi_out=. \\
        daemon.proto health.proto

Then patch the top-level ``import <name>_pb2`` lines in the ``*_pb2_grpc.py``
files to relative imports (``from . import <name>_pb2``) so they work inside
this package.
"""
