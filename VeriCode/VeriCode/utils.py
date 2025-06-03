import time
import ast
import tempfile
import os
import json
import subprocess
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
import models

def analyze_code(code: str, expected_output: str = None, tests: str = None):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode='w') as temp:
        temp.write(code)
        temp_path = temp.name

    try:
        result = subprocess.run(["flake8", temp_path], capture_output=True, text=True)
        style_issues = result.stdout.strip()
    except Exception as e:
        style_issues = f"Ошибка flake8: {e}"

    runtime_error = "Нет"
    actual_output = ""
    output_check = "Не проверялся"
    tests_passed = 0
    total_tests = 0
    test_results_json = "[]"

    try:
        start = time.time()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name

        try:
            result = subprocess.run(
                ["python3", temp_file_path],
                capture_output=True,
                text=True,
                timeout=5,
                input=""
            )

            if result.returncode != 0:
                runtime_error = result.stderr.strip()
            else:
                actual_output = result.stdout.strip()

            try:
                os.remove(temp_file_path)
            except:
                pass

        except subprocess.TimeoutExpired:
            runtime_error = "Превышено время выполнения (5 секунд)"
        except Exception as e:
            runtime_error = str(e)
        finally:
            performance = int((time.time() - start) * 1000)

        if tests:
            test_results = run_tests(code, tests)
            tests_passed = test_results["tests_passed"]
            total_tests = test_results["total_tests"]
            test_results_json = test_results["test_results"]

    except Exception as e:
        runtime_error = str(e)
        performance = 0

    try:
        os.remove(temp_path)
    except:
        pass

    return {
        "style": style_issues if style_issues else "Замечаний нет",
        "errors": runtime_error,
        "performance": performance,
        "output": actual_output,
        "output_check": output_check,
        "tests_passed": tests_passed,
        "total_tests": total_tests,
        "test_results": test_results_json
    }

def run_tests(code, tests):
    test_lines = [line.strip() for line in tests.split('\n') if line.strip()]
    test_results = []
    tests_passed = 0

    for i, test_line in enumerate(test_lines):
        test_name = f"Тест {i + 1}"

        try:
            if " -> " in test_line:
                input_part, expected_output = test_line.split(" -> ", 1)
                input_data = input_part.strip()
                expected_output = expected_output.strip()

                if input_data.lower() == "пусто":
                    input_data = ""
            else:
                expected_output = ""
                input_data = test_line.strip()

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name

            try:
                result = subprocess.run(
                    ["python3", temp_file_path],
                    input=input_data.replace(" ", "\n") if input_data else "",
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.returncode == 0:
                    actual_output = result.stdout.strip()

                    if actual_output == expected_output:
                        test_results.append({
                            "name": test_name,
                            "passed": True,
                            "test": test_line,
                            "input": input_data if input_data else "(без ввода)",
                            "expected": expected_output,
                            "actual": actual_output,
                            "result": "✓ Правильно"
                        })
                        tests_passed += 1
                    else:
                        test_results.append({
                            "name": test_name,
                            "passed": False,
                            "test": test_line,
                            "input": input_data if input_data else "(без ввода)",
                            "expected": expected_output,
                            "actual": actual_output,
                            "result": f"✗ Неверно (ожидалось: {expected_output}, получено: {actual_output})"
                        })
                else:
                    test_results.append({
                        "name": test_name,
                        "passed": False,
                        "test": test_line,
                        "input": input_data if input_data else "(без ввода)",
                        "expected": expected_output,
                        "actual": "",
                        "result": f"✗ Ошибка выполнения: {result.stderr.strip()}"
                    })

                try:
                    os.remove(temp_file_path)
                except:
                    pass

            except subprocess.TimeoutExpired:
                test_results.append({
                    "name": test_name,
                    "passed": False,
                    "test": test_line,
                    "input": input_data if input_data else "(без ввода)",
                    "expected": expected_output,
                    "actual": "",
                    "result": "✗ Превышено время выполнения"
                })

        except Exception as e:
            test_results.append({
                "name": test_name,
                "passed": False,
                "test": test_line,
                "input": input_data if input_data else "(без ввода)",
                "expected": expected_output,
                "actual": "",
                "result": f"Ошибка обработки теста: {str(e)}"
            })

    return {
        "tests_passed": tests_passed,
        "total_tests": len(test_lines),
        "test_results": json.dumps(test_results, ensure_ascii=False)
    }

def normalize_ast(code):
    try:
        tree = ast.parse(code)
        return ast.dump(tree)
    except:
        return ""

def detect_plagiarism(db: Session, new_code: str, assignment_id: int, current_user_id: int):
    solutions = db.query(models.Solution).filter(
        models.Solution.assignment_id == assignment_id,
        models.Solution.user_id != current_user_id
    ).all()

    if not solutions:
        return {"is_plagiarism": False, "similarity": 0, "similar_users": []}

    new_ast = normalize_ast(new_code)
    max_similarity = 0
    similar_users = []

    for solution in solutions:
        existing_ast = normalize_ast(solution.code)

        if new_ast and existing_ast:
            similarity = SequenceMatcher(None, new_ast, existing_ast).ratio()

            if similarity > 0.8:
                max_similarity = max(max_similarity, similarity)
                similar_users.append({
                    "username": solution.user.username,
                    "similarity": round(similarity * 100, 1)
                })

    return {
        "is_plagiarism": max_similarity > 0.8,
        "similarity": round(max_similarity * 100, 1),
        "similar_users": similar_users
    }