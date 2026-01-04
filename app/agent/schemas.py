from pydantic import BaseModel


class Analysis(BaseModel):
    language: str
    tone: str
    task_type: str
