from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ReadFileRequest(_message.Message):
    __slots__ = ("path", "offset", "length")
    PATH_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LENGTH_FIELD_NUMBER: _ClassVar[int]
    path: str
    offset: int
    length: int
    def __init__(self, path: _Optional[str] = ..., offset: _Optional[int] = ..., length: _Optional[int] = ...) -> None: ...

class ReadFileResponse(_message.Message):
    __slots__ = ("content", "sha256", "total_size", "truncated")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    SHA256_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SIZE_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    content: bytes
    sha256: str
    total_size: int
    truncated: bool
    def __init__(self, content: _Optional[bytes] = ..., sha256: _Optional[str] = ..., total_size: _Optional[int] = ..., truncated: _Optional[bool] = ...) -> None: ...

class WriteFileRequest(_message.Message):
    __slots__ = ("path", "content", "expected_hash")
    PATH_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_HASH_FIELD_NUMBER: _ClassVar[int]
    path: str
    content: bytes
    expected_hash: str
    def __init__(self, path: _Optional[str] = ..., content: _Optional[bytes] = ..., expected_hash: _Optional[str] = ...) -> None: ...

class WriteFileResponse(_message.Message):
    __slots__ = ("sha256", "written")
    SHA256_FIELD_NUMBER: _ClassVar[int]
    WRITTEN_FIELD_NUMBER: _ClassVar[int]
    sha256: str
    written: bool
    def __init__(self, sha256: _Optional[str] = ..., written: _Optional[bool] = ...) -> None: ...

class ExecCommandRequest(_message.Message):
    __slots__ = ("argv", "timeout_seconds")
    ARGV_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    argv: _containers.RepeatedScalarFieldContainer[str]
    timeout_seconds: int
    def __init__(self, argv: _Optional[_Iterable[str]] = ..., timeout_seconds: _Optional[int] = ...) -> None: ...

class ExecCommandResponse(_message.Message):
    __slots__ = ("exit_code", "status", "stdout", "stderr", "duration_ms")
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STDOUT_FIELD_NUMBER: _ClassVar[int]
    STDERR_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    exit_code: int
    status: str
    stdout: bytes
    stderr: bytes
    duration_ms: int
    def __init__(self, exit_code: _Optional[int] = ..., status: _Optional[str] = ..., stdout: _Optional[bytes] = ..., stderr: _Optional[bytes] = ..., duration_ms: _Optional[int] = ...) -> None: ...

class GitCreateBranchRequest(_message.Message):
    __slots__ = ("branch_name", "from_head")
    BRANCH_NAME_FIELD_NUMBER: _ClassVar[int]
    FROM_HEAD_FIELD_NUMBER: _ClassVar[int]
    branch_name: str
    from_head: bool
    def __init__(self, branch_name: _Optional[str] = ..., from_head: _Optional[bool] = ...) -> None: ...

class GitCreateBranchResponse(_message.Message):
    __slots__ = ("branch_name", "created", "message")
    BRANCH_NAME_FIELD_NUMBER: _ClassVar[int]
    CREATED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    branch_name: str
    created: bool
    message: str
    def __init__(self, branch_name: _Optional[str] = ..., created: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class GitStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GitStatusEntry(_message.Message):
    __slots__ = ("path", "status")
    PATH_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    path: str
    status: str
    def __init__(self, path: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class GitStatusResponse(_message.Message):
    __slots__ = ("branch", "clean", "entries")
    BRANCH_FIELD_NUMBER: _ClassVar[int]
    CLEAN_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    branch: str
    clean: bool
    entries: _containers.RepeatedCompositeFieldContainer[GitStatusEntry]
    def __init__(self, branch: _Optional[str] = ..., clean: _Optional[bool] = ..., entries: _Optional[_Iterable[_Union[GitStatusEntry, _Mapping]]] = ...) -> None: ...

class GitCommitRequest(_message.Message):
    __slots__ = ("message", "paths")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PATHS_FIELD_NUMBER: _ClassVar[int]
    message: str
    paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, message: _Optional[str] = ..., paths: _Optional[_Iterable[str]] = ...) -> None: ...

class GitCommitResponse(_message.Message):
    __slots__ = ("commit_hash", "committed", "message")
    COMMIT_HASH_FIELD_NUMBER: _ClassVar[int]
    COMMITTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    commit_hash: str
    committed: bool
    message: str
    def __init__(self, commit_hash: _Optional[str] = ..., committed: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...
