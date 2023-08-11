from pydantic import BaseModel
from typing import List, Dict, Union, Optional


class PartialExecBody(BaseModel):
    session: Union[str, None] = None
    code: str


class ExecOutput(BaseModel):
    session_id: str
    start_time: str
    end_time: Optional[str]
    msg_type: Optional[str]
    content: List[Dict[str, str]] = []
    last_update_time: Optional[str] = None
    execution_count: int = 0
    completed: bool = False


class KernelInfo(BaseModel):
    kernel_id: Optional[str] = None
    room: str
    board: str
    name: str
    alias: str
    is_private: bool
    owner: str