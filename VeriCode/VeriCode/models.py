from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# Таблица связи многие-ко-многим между пользователями и группами
user_group_association = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    role = Column(String, default="student")  # student, teacher, admin
    is_approved = Column(Boolean, default=True)  # False для учителей до одобрения админом
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    solutions = relationship("Solution", back_populates="user")
    groups = relationship("Group", secondary=user_group_association, back_populates="members")

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Учитель, создавший группу
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    teacher = relationship("User", foreign_keys=[teacher_id])
    members = relationship("User", secondary=user_group_association, back_populates="groups")
    assignments = relationship("Assignment", back_populates="group")

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    expected_output = Column(String)
    tests = Column(Text)  # JSON строка с тестами
    deadline = Column(DateTime(timezone=True), nullable=True)  # Дедлайн для выполнения
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Привязка к учителю
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)  # Привязка к группе
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    teacher = relationship("User", foreign_keys=[teacher_id])
    group = relationship("Group", back_populates="assignments")
    solutions = relationship("Solution", back_populates="assignment")

class Solution(Base):
    __tablename__ = "solutions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(Text, nullable=False)
    style = Column(String)
    errors = Column(String)
    performance = Column(Integer)
    plagiarism = Column(String, default="Плагиат не обнаружен")
    output_check = Column(String)
    actual_output = Column(String)
    tests_passed = Column(Integer, default=0)  # Количество пройденных тестов
    total_tests = Column(Integer, default=0)   # Общее количество тестов
    test_results = Column(Text)  # JSON с результатами каждого теста
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    last_modified = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Новые поля для оценки учителя
    teacher_grade = Column(Integer)  # Оценка от учителя
    teacher_comment = Column(Text)   # Комментарий учителя
    is_checked = Column(Boolean, default=False)  # Статус проверки
    checked_at = Column(DateTime(timezone=True))  # Время проверки

    user_id = Column(Integer, ForeignKey("users.id"))
    assignment_id = Column(Integer, ForeignKey("assignments.id"))

    user = relationship("User", back_populates="solutions")
    assignment = relationship("Assignment", back_populates="solutions")
    history = relationship("SolutionHistory", back_populates="solution")

class SolutionHistory(Base):
    __tablename__ = "solution_history"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(Text, nullable=False)
    style = Column(String)
    errors = Column(String)
    performance = Column(Integer)
    plagiarism = Column(String, default="Плагиат не обнаружен")
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    solution_id = Column(Integer, ForeignKey("solutions.id"))
    solution = relationship("Solution", back_populates="history")

class GroupJoinRequest(Base):
    __tablename__ = "group_join_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    group = relationship("Group")

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())