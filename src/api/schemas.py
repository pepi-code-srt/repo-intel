from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    repo_url: str

class AnalyzeResponse(BaseModel):
    job_id: str
    message: str

class ReportResponse(BaseModel):
    job_id: str
    report: str
    status: str
