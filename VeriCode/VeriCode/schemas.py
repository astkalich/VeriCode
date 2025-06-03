from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str
    first_name: str
    last_name: str
    role: str = "student"

class UserOut(UserBase):
    id: int
    role: str

    class Config:
        from_attributes = True

# --- Group Schemas ---
class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class GroupCreate(GroupBase):
    pass

class GroupOut(GroupBase):
    id: int
    teacher_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Assignment Schemas ---
class AssignmentBase(BaseModel):
    title: str
    description: Optional[str] = None

class AssignmentCreate(AssignmentBase):
    expected_output: Optional[str] = None
    tests: Optional[str] = None
    deadline: Optional[str] = None
    group_id: int

class AssignmentOut(AssignmentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Solution Schemas ---
class SolutionBase(BaseModel):
    code: str

class SolutionCreate(SolutionBase):
    assignment_id: int

class SolutionOut(SolutionBase):
    id: int
    style: Optional[str]
    errors: Optional[str]
    performance: Optional[int]
    plagiarism: bool
    submitted_at: datetime
    user_id: int
    assignment_id: int
    teacher_grade: Optional[int]
    teacher_comment: Optional[str]
    is_checked: bool
    checked_at: Optional[datetime]

    class Config:
        from_attributes = True

# --- Teacher Evaluation Schema ---
class TeacherEvaluation(BaseModel):
    solution_id: int
    grade: int
    comment: Optional[str] = None