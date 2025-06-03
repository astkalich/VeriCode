from sqlalchemy.orm import Session
from sqlalchemy.sql import func
import models, schemas
from passlib.hash import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return bcrypt.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    return bcrypt.hash(password)

# --------- Пользователи ---------
def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = bcrypt.hash(user.password)
    # Учителя создаются неодобренными, остальные - одобренными
    is_approved = user.role != "teacher"
    db_user = models.User(
        username=user.username,
        password=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        is_approved=is_approved
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user or not bcrypt.verify(password, user.password):
        return None
    return user

# --------- Группы ---------
def create_group(db: Session, group: schemas.GroupCreate, teacher_id: int):
    db_group = models.Group(
        name=group.name,
        description=group.description,
        teacher_id=teacher_id
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group

def get_teacher_groups(db: Session, teacher_id: int):
    try:
        groups = db.query(models.Group).filter(models.Group.teacher_id == teacher_id).all()
        print(f"Найдено {len(groups)} групп для учителя {teacher_id}")
        return groups
    except Exception as e:
        print(f"Ошибка получения групп для учителя {teacher_id}: {str(e)}")
        return []

def get_user_groups(db: Session, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user.groups if user else []

def get_all_groups(db: Session):
    return db.query(models.Group).all()

def add_user_to_group(db: Session, user_id: int, group_id: int, teacher_id: int):
    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == group_id,
        models.Group.teacher_id == teacher_id
    ).first()
    if not group:
        return False

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or user.role != "student":
        return False

    if group not in user.groups:
        user.groups.append(group)
        db.commit()
    return True

def remove_user_from_group(db: Session, user_id: int, group_id: int, teacher_id: int):
    group = db.query(models.Group).filter(
        models.Group.id == group_id,
        models.Group.teacher_id == teacher_id
    ).first()

    if not group:
        return False

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return False

    if group in user.groups:
        user.groups.remove(group)
        db.commit()
    return True

def remove_user_from_group_student(db: Session, user_id: int, group_id: int):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        return False

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return False

    if group in user.groups:
        user.groups.remove(group)
        db.commit()
    return True

def get_students_not_in_group(db: Session, group_id: int):
    # Получаем всех студентов, которые не в данной группе
    return db.query(models.User).filter(
        models.User.role == "student",
        models.User.is_approved == True,
        ~models.User.groups.any(models.Group.id == group_id)
    ).all()

# --------- Задания ---------
def get_assignments(db: Session, teacher_id: int = None, user_id: int = None):
    if teacher_id:
        # Учителя видят только свои задания
        return db.query(models.Assignment).filter(models.Assignment.teacher_id == teacher_id).all()
    elif user_id:
        # Студенты видят только задания из групп, в которых они состоят
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or user.role != "student":
            return []

        group_ids = [group.id for group in user.groups]
        if not group_ids:
            return []

        return db.query(models.Assignment).filter(models.Assignment.group_id.in_(group_ids)).all()

    # Админы видят все задания
    return db.query(models.Assignment).all()

def create_assignment(db: Session, assignment: schemas.AssignmentCreate, teacher_id: int):
    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == assignment.group_id,
        models.Group.teacher_id == teacher_id
    ).first()
    if not group:
        return None

    deadline = None
    if assignment.deadline:
        from datetime import datetime
        try:
            deadline = datetime.fromisoformat(assignment.deadline.replace('Z', '+00:00'))
        except:
            pass

    assignment_data = assignment.dict()
    assignment_data['teacher_id'] = teacher_id
    db_assignment = models.Assignment(
        title=assignment.title,
        description=assignment.description,
        expected_output=assignment.expected_output,
        tests=assignment.tests,
        deadline=deadline,
        teacher_id=teacher_id,
        group_id=assignment.group_id
    )
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return db_assignment

def update_assignment(db: Session, assignment_id: int, assignment_data: schemas.AssignmentCreate, teacher_id: int):
    assignment = db.query(models.Assignment).filter(
        models.Assignment.id == assignment_id,
        models.Assignment.teacher_id == teacher_id
    ).first()
    if not assignment:
        return None

    # Проверяем, что новая группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == assignment_data.group_id,
        models.Group.teacher_id == teacher_id
    ).first()
    if not group:
        return None

    deadline = None
    if assignment_data.deadline:
        from datetime import datetime
        try:
            deadline = datetime.fromisoformat(assignment_data.deadline.replace('Z', '+00:00'))
        except:
            pass

    assignment.title = assignment_data.title
    assignment.description = assignment_data.description
    assignment.expected_output = assignment_data.expected_output
    assignment.tests = assignment_data.tests
    assignment.deadline = deadline
    assignment.group_id = assignment_data.group_id
    assignment.updated_at = func.now()

    db.commit()
    db.refresh(assignment)
    return assignment

def delete_assignment(db: Session, assignment_id: int, teacher_id: int):
    assignment = db.query(models.Assignment).filter(
        models.Assignment.id == assignment_id,
        models.Assignment.teacher_id == teacher_id
    ).first()
    if not assignment:
        return False

    # Удаляем все связанные решения и их историю
    solutions = db.query(models.Solution).filter(models.Solution.assignment_id == assignment_id).all()
    for solution in solutions:
        # Удаляем историю решений
        db.query(models.SolutionHistory).filter(models.SolutionHistory.solution_id == solution.id).delete()
        # Удаляем само решение
        db.delete(solution)

    # Удаляем задание
    db.delete(assignment)
    db.commit()
    return True

# --------- Решения ---------
def save_solution(db: Session, username: str, assignment_id: int, code: str, result: dict, plagiarism_data: dict):
    user = get_user_by_username(db, username)

    # Проверяем, есть ли уже решение для этого задания от этого пользователя
    existing_solution = db.query(models.Solution).filter(
        models.Solution.user_id == user.id,
        models.Solution.assignment_id == assignment_id
    ).first()

    plagiarism_text = ""
    if plagiarism_data["is_plagiarized"]:
        plagiarism_text = f"Плагиат обнаружен. Похоже на работы: {', '.join(plagiarism_data['similar_users'])}"
    else:
        plagiarism_text = "Плагиат не обнаружен"

    if existing_solution:
        # Сохраняем старое решение в историю
        history_entry = models.SolutionHistory(
            code=existing_solution.code,
            style=existing_solution.style,
            errors=existing_solution.errors,
            performance=existing_solution.performance,
            plagiarism=existing_solution.plagiarism,
            submitted_at=existing_solution.submitted_at,
            solution_id=existing_solution.id
        )
        db.add(history_entry)

        # Обновляем существующее решение
        existing_solution.code = code
        existing_solution.style = result.get("style")
        existing_solution.errors = result.get("errors")
        existing_solution.performance = result.get("performance")
        existing_solution.plagiarism = plagiarism_text
        existing_solution.output_check = result.get("output_check")
        existing_solution.actual_output = result.get("actual_output")
        existing_solution.tests_passed = result.get("tests_passed", 0)
        existing_solution.total_tests = result.get("total_tests", 0)
        existing_solution.test_results = result.get("test_results", "[]")
        existing_solution.last_modified = func.now()
        # Сбрасываем оценку учителя при новой отправке
        existing_solution.teacher_grade = None
        existing_solution.teacher_comment = None
        existing_solution.is_checked = False
        existing_solution.checked_at = None

        db.commit()
        db.refresh(existing_solution)
        return existing_solution
    else:
        # Создаем новое решение
        db_solution = models.Solution(
            code=code,
            style=result.get("style"),
            errors=result.get("errors"),
            performance=result.get("performance"),
            plagiarism=plagiarism_text,
            output_check=result.get("output_check"),
            actual_output=result.get("actual_output"),
            tests_passed=result.get("tests_passed", 0),
            total_tests=result.get("total_tests", 0),
            test_results=result.get("test_results", "[]"),
            user_id=user.id,
            assignment_id=assignment_id
        )
        db.add(db_solution)
        db.commit()
        db.refresh(db_solution)
        return db_solution

def get_solutions_for_assignment(db: Session, assignment_id: int):
    try:
        # Используем joinedload для оптимизации загрузки связанных данных
        from sqlalchemy.orm import joinedload
        
        solutions = db.query(models.Solution).options(
            joinedload(models.Solution.user)
        ).filter(
            models.Solution.assignment_id == assignment_id
        ).order_by(
            models.Solution.submitted_at.desc()
        ).all()
        
        print(f"Загружено {len(solutions)} решений для задания {assignment_id}")
        return solutions
        
    except Exception as e:
        print(f"Ошибка получения решений из БД для задания {assignment_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def get_user_solutions(db: Session, user_id: int):
    return db.query(models.Solution).filter(models.Solution.user_id == user_id).all()

def update_solution_grade(db: Session, solution_id: int, grade: int, comment: str = None):
    solution = db.query(models.Solution).filter(models.Solution.id == solution_id).first()
    if solution:
        solution.teacher_grade = grade
        solution.teacher_comment = comment
        solution.is_checked = True
        solution.checked_at = func.now()
        db.commit()
        db.refresh(solution)
    return solution

def get_solution_history(db: Session, solution_id: int):
    return db.query(models.SolutionHistory).filter(models.SolutionHistory.solution_id == solution_id).order_by(models.SolutionHistory.submitted_at.desc()).all()

# --------- Настройки системы ---------
def get_teacher_code(db: Session):
    setting = db.query(models.Settings).filter(models.Settings.key == "teacher_code").first()
    return setting.value if setting else None

def set_teacher_code(db: Session, code: str):
    setting = db.query(models.Settings).filter(models.Settings.key == "teacher_code").first()
    if setting:
        setting.value = code
        setting.updated_at = func.now()
    else:
        setting = models.Settings(key="teacher_code", value=code)
        db.add(setting)
    db.commit()

def get_all_users(db: Session):
    return db.query(models.User).all()

def delete_user(db: Session, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or user.role == "admin":
        return False

    # Удаляем все решения пользователя и их историю
    solutions = db.query(models.Solution).filter(models.Solution.user_id == user_id).all()
    for solution in solutions:
        # Удаляем историю решений
        db.query(models.SolutionHistory).filter(models.SolutionHistory.solution_id == solution.id).delete()
        # Удаляем само решение
        db.delete(solution)

    # Удаляем пользователя
    db.delete(user)
    db.commit()
    return True

def get_pending_teachers(db: Session):
    return db.query(models.User).filter(
        models.User.role == "teacher", 
        models.User.is_approved == False
    ).all()

def approve_teacher(db: Session, teacher_id: int):
    teacher = db.query(models.User).filter(
        models.User.id == teacher_id,
        models.User.role == "teacher",
        models.User.is_approved == False
    ).first()

    if not teacher:
        return False

    teacher.is_approved = True
    db.commit()
    return True

def reject_teacher(db: Session, teacher_id: int):
    teacher = db.query(models.User).filter(
        models.User.id == teacher_id,
        models.User.role == "teacher",
        models.User.is_approved == False
    ).first()

    if not teacher:
        return False

    # Удаляем пользователя (отклоняем регистрацию)
    db.delete(teacher)
    db.commit()
    return True

# --------- Заявки на вступление в группы ---------
def create_group_join_request(db: Session, user_id: int, group_id: int):
    # Проверяем, что пользователь не в группе и нет активной заявки
    user = db.query(models.User).filter(models.User.id == user_id).first()
    group = db.query(models.Group).filter(models.Group.id == group_id).first()

    if not user or not group or user.role != "student":
        return False

    # Проверяем, что пользователь уже не в группе
    if group in user.groups:
        return False

    # Проверяем, что нет активной заявки
    existing_request = db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.user_id == user_id,
        models.GroupJoinRequest.group_id == group_id
    ).first()

    if existing_request:
        return False

    # Создаем заявку
    join_request = models.GroupJoinRequest(
        user_id=user_id,
        group_id=group_id
    )
    db.add(join_request)
    db.commit()
    return True

def get_group_join_requests(db: Session, group_id: int):
    return db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.group_id == group_id
    ).all()

def approve_group_join_request(db: Session, request_id: int, teacher_id: int):
    join_request = db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.id == request_id
    ).first()

    if not join_request:
        return False

    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == join_request.group_id,
        models.Group.teacher_id == teacher_id
    ).first()

    if not group:
        return False

    # Добавляем пользователя в группу
    user = db.query(models.User).filter(models.User.id == join_request.user_id).first()
    if user and group not in user.groups:
        user.groups.append(group)

    # Удаляем заявку
    db.delete(join_request)
    db.commit()
    return True

def reject_group_join_request(db: Session, request_id: int, teacher_id: int):
    join_request = db.query(models.GroupJoinRequest).filter(
        models.GroupJoinRequest.id == request_id
    ).first()

    if not join_request:
        return False

    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == join_request.group_id,
        models.Group.teacher_id == teacher_id
    ).first()

    if not group:
        return False

    # Удаляем заявку
    db.delete(join_request)
    db.commit()
    return True

def delete_group(db: Session, group_id: int, teacher_id: int):
    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == group_id,
        models.Group.teacher_id == teacher_id
    ).first()

    if not group:
        return False

    # Удаляем все задания группы и связанные с ними решения
    assignments = db.query(models.Assignment).filter(models.Assignment.group_id == group_id).all()
    for assignment in assignments:
        # Удаляем все решения задания и их историю
        solutions = db.query(models.Solution).filter(models.Solution.assignment_id == assignment.id).all()
        for solution in solutions:
            # Удаляем историю решений
            db.query(models.SolutionHistory).filter(models.SolutionHistory.solution_id == solution.id).delete()
            # Удаляем само решение
            db.delete(solution)
        # Удаляем задание
        db.delete(assignment)

    # Удаляем все заявки на вступление в группу
    db.query(models.GroupJoinRequest).filter(models.GroupJoinRequest.group_id == group_id).delete()

    # Удаляем группу (связи с пользователями удалятся автоматически)
    db.delete(group)
    db.commit()
    return True