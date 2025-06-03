from fastapi import FastAPI, HTTPException, Depends, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uvicorn
from typing import List, Optional
from utils import analyze_code, detect_plagiarism
import models, schemas, crud
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

def create_default_admin():
    db = SessionLocal()
    try:
        admin_user = crud.get_user_by_username(db, "admin")
        if not admin_user:
            admin_data = schemas.UserCreate(
                username="admin", 
                password="admin", 
                first_name="Администратор", 
                last_name="Системы", 
                role="admin"
            )
            crud.create_user(db, admin_data)
            print("Создан администратор по умолчанию: логин=admin, пароль=admin")
    finally:
        db.close()

create_default_admin()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="vericode-secret-key")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()

def require_auth(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user

def require_teacher(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступ только для учителей")
    return user

def require_admin(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return user
@app.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    with open("frontend/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    with open("frontend/register.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    if user.role == "admin":
        with open("frontend/admin_dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    elif user.role == "teacher":
        with open("frontend/teacher_dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    else:
        with open("frontend/student_dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
@app.post("/api/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=400, detail="Неверные учетные данные")

    # Проверяем, одобрен ли аккаунт учителя
    if user.role == "teacher" and not user.is_approved:
        raise HTTPException(status_code=403, detail="Ваш аккаунт еще не одобрен администратором")

    request.session["user_id"] = user.id
    return {"success": True, "role": user.role}

@app.post("/api/register")
async def register(
    username: str = Form(...), 
    password: str = Form(...), 
    first_name: str = Form(...),
    last_name: str = Form(...),
    role: str = Form(...), 
    teacherCode: str = Form(None),
    db: Session = Depends(get_db)
):
    existing_user = crud.get_user_by_username(db, username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")

    # Проверка кода учителя
    if role == "teacher":
        if not teacherCode:
            raise HTTPException(status_code=400, detail="Для регистрации учителя требуется проверочный код")

        # Получаем текущий код из БД или используем дефолтный
        teacher_code = crud.get_teacher_code(db)
        if not teacher_code:
            teacher_code = "TEACHER2024"  # Код по умолчанию

        if teacherCode != teacher_code:
            raise HTTPException(status_code=400, detail="Неверный проверочный код учителя")

    user_data = schemas.UserCreate(
        username=username, 
        password=password, 
        first_name=first_name,
        last_name=last_name,
        role=role
    )
    crud.create_user(db, user_data)

    if role == "teacher":
        return {"success": True, "message": "Регистрация отправлена на модерацию. Ожидайте одобрения администратора."}
    else:
        return {"success": True}

@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"success": True}

@app.get("/api/current-user")
async def current_user(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return {
        "id": user.id, 
        "username": user.username, 
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role
    }
@app.get("/api/assignments")
def get_assignments(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)

    if user.role == "teacher":
        # Учителя видят только свои задания
        assignments = crud.get_assignments(db, teacher_id=user.id)
    elif user.role == "student":
        # Студенты видят только задания из групп, в которых они состоят
        assignments = crud.get_assignments(db, user_id=user.id)
    else:
        # Админы видят все задания
        assignments = crud.get_assignments(db)

    return {"assignments": [
        {
            "id": a.id, 
            "title": a.title, 
            "description": a.description,
            "tests": a.tests,
            "deadline": a.deadline.isoformat() if a.deadline else None,
            "group_id": a.group_id,
            "group_name": a.group.name
        } for a in assignments
    ]}
class CodeSubmission(BaseModel):
    assignment_id: int
    code: str

@app.post("/api/submit")
def submit_code(submission: CodeSubmission, request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Только студенты могут отправлять решения")

    try:
        print(f"Получено решение от пользователя {user.username} для задания {submission.assignment_id}")

        # Получаем задание для проверки ожидаемого вывода и тестов
        assignment = db.query(models.Assignment).filter(models.Assignment.id == submission.assignment_id).first()
        if not assignment:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        # Проверяем дедлайн
        if assignment.deadline:
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc)
            # Убираем информацию о часовом поясе для корректного сравнения
            current_time_naive = current_time.replace(tzinfo=None)
            if current_time_naive > assignment.deadline:
                raise HTTPException(status_code=403, detail="Дедлайн для этого задания истек")

        expected_output = assignment.expected_output
        tests = assignment.tests

        print(f"Начинаем анализ кода...")
        result = analyze_code(submission.code, expected_output, tests)
        print(f"Анализ кода завершен: {result}")

        print(f"Проверяем плагиат...")
        plagiarism_data = detect_plagiarism(db, submission.code, submission.assignment_id, user.id)
        print(f"Проверка плагиата завершена: {plagiarism_data}")

        print(f"Сохраняем решение...")
        crud.save_solution(db, user.username, submission.assignment_id, submission.code, result, plagiarism_data)
        print(f"Решение сохранено")

        return {
            "style": result["style"],
            "errors": result["errors"],
            "performance": result["performance"],
            "output_check": result["output_check"],
            "tests_passed": result.get("tests_passed", 0),
            "total_tests": result.get("total_tests", 0),
            "plagiarism": plagiarism_data["similar_users"] if plagiarism_data["is_plagiarized"] else "Плагиат не обнаружен"
        }
    except Exception as e:
        print(f"Ошибка при обработке решения: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
class AssignmentCreateAPI(BaseModel):
    title: str
    description: str
    expected_output: Optional[str] = None
    tests: Optional[str] = None
    deadline: Optional[str] = None
    group_id: int

@app.post("/api/assignments")
def create_assignment(assignment: AssignmentCreateAPI, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    assignment_data = schemas.AssignmentCreate(
        title=assignment.title, 
        description=assignment.description,
        expected_output=assignment.expected_output,
        tests=assignment.tests,
        deadline=assignment.deadline,
        group_id=assignment.group_id
    )
    new_assignment = crud.create_assignment(db, assignment_data, teacher_id=user.id)
    if not new_assignment:
        raise HTTPException(status_code=400, detail="Группа не найдена или не принадлежит вам")

    return {
        "id": new_assignment.id, 
        "title": new_assignment.title, 
        "description": new_assignment.description,
        "expected_output": new_assignment.expected_output,
        "tests": new_assignment.tests,
        "deadline": new_assignment.deadline.isoformat() if new_assignment.deadline else None,
        "group_id": new_assignment.group_id
    }
@app.put("/api/assignments/{assignment_id}")
def update_assignment(assignment_id: int, assignment: AssignmentCreateAPI, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    assignment_data = schemas.AssignmentCreate(
        title=assignment.title,
        description=assignment.description,
        expected_output=assignment.expected_output,
        tests=assignment.tests,
        deadline=assignment.deadline,
        group_id=assignment.group_id
    )
    updated_assignment = crud.update_assignment(db, assignment_id, assignment_data, teacher_id=user.id)
    if not updated_assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено или у вас нет прав на его редактирование")
    return {
        "id": updated_assignment.id,
        "title": updated_assignment.title,
        "description": updated_assignment.description,
        "expected_output": updated_assignment.expected_output,
        "tests": updated_assignment.tests,
        "deadline": updated_assignment.deadline.isoformat() if updated_assignment.deadline else None,
        "group_id": updated_assignment.group_id
    }
@app.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    success = crud.delete_assignment(db, assignment_id, teacher_id=user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Задание не найдено или у вас нет прав на его удаление")
    return {"success": True, "message": "Задание удалено успешно"}
@app.get("/api/solutions/{assignment_id}")
def get_solutions(assignment_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user = require_teacher(request, db)
        print(f"Загрузка решений для задания {assignment_id} учителем {user.username}")

        # Проверяем, что задание принадлежит этому учителю
        assignment = db.query(models.Assignment).filter(
            models.Assignment.id == assignment_id,
            models.Assignment.teacher_id == user.id
        ).first()

        if not assignment:
            print(f"Задание {assignment_id} не найдено для учителя {user.id}")
            raise HTTPException(status_code=404, detail="Задание не найдено или у вас нет прав на просмотр решений")

        print(f"Получение решений из БД для задания {assignment_id}")
        solutions = crud.get_solutions_for_assignment(db, assignment_id)
        print(f"Найдено {len(solutions)} решений")

        solutions_data = []
        for i, s in enumerate(solutions):
            try:
                print(f"Обработка решения {i+1}/{len(solutions)} (ID: {s.id})")
                
                # Безопасное получение данных пользователя
                username = "Неизвестный пользователь"
                full_name = "Неизвестный пользователь"
                try:
                    if s.user:
                        username = s.user.username
                        full_name = f"{s.user.last_name} {s.user.first_name}"
                except Exception as user_error:
                    print(f"Ошибка получения данных пользователя для решения {s.id}: {user_error}")

                solution_data = {
                    "id": s.id,
                    "code": str(s.code) if s.code else "",
                    "style": str(s.style) if s.style else "",
                    "errors": str(s.errors) if s.errors else "",
                    "performance": int(s.performance) if s.performance else 0,
                    "plagiarism": str(s.plagiarism) if s.plagiarism else "Плагиат не обнаружен",
                    "submitted_at": s.submitted_at.isoformat() if s.submitted_at else "",
                    "username": username,
                    "full_name": full_name,
                    "teacher_grade": int(s.teacher_grade) if s.teacher_grade else None,
                    "teacher_comment": str(s.teacher_comment) if s.teacher_comment else "",
                    "is_checked": bool(s.is_checked) if s.is_checked else False,
                    "checked_at": s.checked_at.isoformat() if s.checked_at else None,
                    "tests_passed": int(s.tests_passed) if s.tests_passed else 0,
                    "total_tests": int(s.total_tests) if s.total_tests else 0,
                    "test_results": str(s.test_results) if s.test_results else "[]"
                }
                solutions_data.append(solution_data)
                
            except Exception as solution_error:
                print(f"Ошибка обработки решения {s.id}: {str(solution_error)}")
                # Добавляем базовую информацию даже при ошибке
                try:
                    solutions_data.append({
                        "id": s.id,
                        "code": "Ошибка загрузки кода",
                        "style": "Ошибка анализа",
                        "errors": "Ошибка загрузки",
                        "performance": 0,
                        "plagiarism": "Ошибка проверки",
                        "submitted_at": "",
                        "username": "Ошибка загрузки",
                        "full_name": "Ошибка загрузки",
                        "teacher_grade": None,
                        "teacher_comment": "",
                        "is_checked": False,
                        "checked_at": None,
                        "tests_passed": 0,
                        "total_tests": 0,
                        "test_results": "[]"
                    })
                except:
                    pass  # Пропускаем проблемное решение
                continue

        print(f"Успешно обработано {len(solutions_data)} решений")
        return {"solutions": solutions_data}

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Критическая ошибка получения решений для задания {assignment_id}: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        # Возвращаем более информативную ошибку
        raise HTTPException(status_code=500, detail="Ошибка загрузки решений. Попробуйте обновить страницу.")
@app.get("/api/my-solutions")
def get_my_solutions(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Только студенты могут просматривать свои решения")

    solutions = crud.get_user_solutions(db, user.id)
    return {
        "solutions": [
            {
                "id": s.id,
                "assignment_id": s.assignment_id,
                "assignment_title": s.assignment.title,
                "code": s.code,
                "submitted_at": s.submitted_at.isoformat(),
                "teacher_grade": s.teacher_grade,
                "teacher_comment": s.teacher_comment,
                "is_checked": s.is_checked,
                "checked_at": s.checked_at.isoformat() if s.checked_at else None,
                "tests_passed": s.tests_passed,
                "total_tests": s.total_tests,
                "test_results": s.test_results,
                "last_modified": s.last_modified.isoformat() if s.last_modified else None
            }
            for s in solutions
        ]
    }
@app.post("/api/evaluate-solution")
def evaluate_solution(evaluation: schemas.TeacherEvaluation, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)

    solution = crud.update_solution_grade(db, evaluation.solution_id, evaluation.grade, evaluation.comment)
    if not solution:
        raise HTTPException(status_code=404, detail="Решение не найдено")

    return {
        "success": True,
        "message": "Оценка выставлена успешно"
    }
@app.get("/api/solution-history/{solution_id}")
def get_solution_history(solution_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)

    history = crud.get_solution_history(db, solution_id)
    return {
        "history": [
            {
                "id": h.id,
                "code": h.code,
                "style": h.style,
                "errors": h.errors,
                "performance": h.performance,
                "plagiarism": h.plagiarism,
                "submitted_at": h.submitted_at.isoformat()
            }
            for h in history
        ]
    }
class GroupCreateAPI(BaseModel):
    name: str
    description: Optional[str] = None

@app.get("/api/groups")
def get_teacher_groups(request: Request, db: Session = Depends(get_db)):
    try:
        user = require_teacher(request, db)
        print(f"Загружаем группы для учителя {user.username} (ID: {user.id})")
        
        groups = crud.get_teacher_groups(db, user.id)
        print(f"Получено {len(groups)} групп")
        
        groups_data = []
        for g in groups:
            try:
                group_data = {
                    "id": g.id,
                    "name": g.name,
                    "description": g.description or "",
                    "member_count": len(g.members) if g.members else 0,
                    "created_at": g.created_at.isoformat() if g.created_at else ""
                }
                groups_data.append(group_data)
            except Exception as e:
                print(f"Ошибка обработки группы {g.id}: {str(e)}")
                continue
        
        return {"groups": groups_data}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Критическая ошибка загрузки групп: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Ошибка загрузки групп")

@app.get("/api/student-groups")
def get_student_groups(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Доступ только для студентов")

    groups = crud.get_user_groups(db, user.id)
    return {"groups": [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "teacher_name": f"{g.teacher.last_name} {g.teacher.first_name}",
            "member_count": len(g.members),
            "created_at": g.created_at.isoformat()
        } for g in groups
    ]}

@app.get("/api/all-groups")
def get_all_groups(request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Доступ только для студентов")

    groups = crud.get_all_groups(db)
    user_group_ids = [group.id for group in user.groups]

    return {"groups": [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "teacher_name": f"{g.teacher.last_name} {g.teacher.first_name}",
            "member_count": len(g.members),
            "is_member": g.id in user_group_ids,
            "created_at": g.created_at.isoformat()
        } for g in groups
    ]}

@app.post("/api/groups")
def create_group(group: GroupCreateAPI, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    group_data = schemas.GroupCreate(name=group.name, description=group.description)
    new_group = crud.create_group(db, group_data, teacher_id=user.id)
    return {
        "id": new_group.id,
        "name": new_group.name,
        "description": new_group.description,
        "member_count": 0
    }

@app.get("/api/groups/{group_id}/members")
def get_group_members(group_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)

    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == group_id,
        models.Group.teacher_id == user.id
    ).first()

    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    return {
        "group": {
            "id": group.id,
            "name": group.name,
            "description": group.description
        },
        "members": [
            {
                "id": member.id,
                "username": member.username,
                "full_name": f"{member.last_name} {member.first_name}"
            } for member in group.members
        ]
    }

@app.get("/api/groups/{group_id}/available-students")
def get_available_students(group_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)

    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == group_id,
        models.Group.teacher_id == user.id
    ).first()

    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    available_students = crud.get_students_not_in_group(db, group_id)
    return {
        "students": [
            {
                "id": student.id,
                "username": student.username
            } for student in available_students
        ]
    }

@app.post("/api/groups/{group_id}/members/{user_id}")
def add_user_to_group(group_id: int, user_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    success = crud.add_user_to_group(db, user_id, group_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось добавить пользователя в группу")
    return {"success": True, "message": "Пользователь добавлен в группу"}

@app.delete("/api/groups/{group_id}/members/{user_id}")
def remove_user_from_group(group_id: int, user_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_auth(request, db)

    # Если это учитель, проверяем, что группа принадлежит ему
    if current_user.role == "teacher":
        success = crud.remove_user_from_group(db, user_id, group_id, current_user.id)
        if not success:
            raise HTTPException(status_code=400, detail="Не удалось удалить пользователя из группы")
        return {"success": True, "message": "Пользователь удален из группы"}

    # Если это студент, проверяем, что он удаляет себя
    elif current_user.role == "student" and current_user.id == user_id:
        success = crud.remove_user_from_group_student(db, user_id, group_id)
        if not success:
            raise HTTPException(status_code=400, detail="Не удалось выйти из группы")
        return {"success": True, "message": "Вы вышли из группы"}

    else:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

@app.post("/api/groups/{group_id}/request-join")
def request_join_group(group_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Только студенты могут подавать заявки на вступление")

    success = crud.create_group_join_request(db, user.id, group_id)
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось создать заявку")
    return {"success": True, "message": "Заявка на вступление отправлена"}

@app.get("/api/groups/{group_id}/join-requests")
def get_group_join_requests(group_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)

    # Проверяем, что группа принадлежит учителю
    group = db.query(models.Group).filter(
        models.Group.id == group_id,
        models.Group.teacher_id == user.id
    ).first()

    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    requests = crud.get_group_join_requests(db, group_id)
    return {
        "requests": [
            {
                "id": req.id,
                "user_id": req.user_id,
                "username": req.user.username,
                "full_name": f"{req.user.last_name} {req.user.first_name}",
                "created_at": req.created_at.isoformat()
            } for req in requests
        ]
    }

@app.post("/api/group-requests/{request_id}/approve")
def approve_group_request(request_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    success = crud.approve_group_join_request(db, request_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось одобрить заявку")
    return {"success": True, "message": "Заявка одобрена"}

@app.delete("/api/group-requests/{request_id}")
def reject_group_request(request_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    success = crud.reject_group_join_request(db, request_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось отклонить заявку")
    return {"success": True, "message": "Заявка отклонена"}

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_teacher(request, db)
    success = crud.delete_group(db, group_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось удалить группу или у вас нет прав")
    return {"success": True, "message": "Группа удалена успешно"}
@app.get("/api/teacher-code")
def get_teacher_code(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    code = crud.get_teacher_code(db)
    return {"teacher_code": code or "TEACHER2024"}

@app.post("/api/teacher-code")
def update_teacher_code(new_code: str = Form(...), request: Request = Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    crud.set_teacher_code(db, new_code)
    return {"success": True, "message": "Код учителя обновлен"}

@app.get("/api/all-users")
def get_all_users(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    users = crud.get_all_users(db)
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "full_name": f"{u.last_name} {u.first_name}",
                "role": u.role
            }
            for u in users if u.role != "admin"  # Не показываем админов
        ]
    }

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    success = crud.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"success": True, "message": "Пользователь удален успешно"}

@app.get("/api/pending-teachers")
def get_pending_teachers(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    pending_teachers = crud.get_pending_teachers(db)
    return {
        "teachers": [
            {
                "id": t.id,
                "username": t.username,
                "full_name": f"{t.last_name} {t.first_name}",
                "created_at": t.created_at.isoformat()
            }
            for t in pending_teachers
        ]
    }

@app.post("/api/approve-teacher/{teacher_id}")
def approve_teacher(teacher_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    success = crud.approve_teacher(db, teacher_id)
    if not success:
        raise HTTPException(status_code=404, detail="Учитель не найден")
    return {"success": True, "message": "Учитель одобрен"}

@app.post("/api/reject-teacher/{teacher_id}")
def reject_teacher(teacher_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    success = crud.reject_teacher(db, teacher_id)
    if not success:
        raise HTTPException(status_code=404, detail="Учитель не найден")
    return {"success": True, "message": "Регистрация учителя отклонена"}
class UserUpdateProfile(BaseModel):
    first_name: str
    last_name: str
    current_password: str
    new_password: Optional[str] = None

@app.post("/api/update-profile")
def update_profile(profile: UserUpdateProfile, request: Request, db: Session = Depends(get_db)):
    user = require_auth(request, db)

    # Проверяем текущий пароль
    if not crud.verify_password(profile.current_password, user.password):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    # Обновляем данные
    user.first_name = profile.first_name
    user.last_name = profile.last_name

    if profile.new_password:
        user.password = crud.get_password_hash(profile.new_password)

    db.commit()
    db.refresh(user)

    return {"success": True, "message": "Профиль обновлен успешно"}

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)