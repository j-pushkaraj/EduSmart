# routes/teacher.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Class, Chapter, Test, Question, TestAttempt, StudentAnswer, User, StudentClass
from datetime import datetime

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


# ================================
# ✅ TEACHER DASHBOARD
# ================================
@teacher_bp.route("/dashboard")
@login_required
def dashboard():
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    return render_template("teacher/dashboard.html", classes=classes)


# ================================
# ✅ CREATE CLASSROOM
# ================================
@teacher_bp.route("/class/create", methods=["GET", "POST"])
@login_required
def create_class():
    if request.method == "POST":
        class_name = request.form.get("name", "").strip()
        join_code = request.form.get("join_code", "").strip()

        if not class_name or not join_code:
            flash("Class name and join code are required!", "danger")
            return redirect(url_for("teacher.create_class"))

        if Class.query.filter_by(join_code=join_code).first():
            flash("❌ Join code already exists. Please use a different one.", "danger")
            return redirect(url_for("teacher.create_class"))

        new_class = Class(name=class_name, join_code=join_code, teacher_id=current_user.id)
        db.session.add(new_class)
        db.session.commit()

        flash("✅ Classroom created successfully!", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template("teacher/create_class.html")


# ================================
# ✅ VIEW CLASS DETAILS
# ================================
@teacher_bp.route("/class/<int:class_id>")
@login_required
def view_class(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    enrolled_students = [sc.student for sc in class_obj.students]

    for chapter in class_obj.chapters:
        chapter_analytics = get_chapter_analytics(chapter.id)
        chapter.avg_score = chapter_analytics["avg"]
        chapter.lowest_test_name = chapter_analytics["lowest_test"]
        for test in chapter.tests:
            t_analytics = get_test_analytics(test.id)
            test.avg_score = t_analytics["avg"]
            test.highest_score = t_analytics["highest"]
            test.lowest_score = t_analytics["lowest"]

    return render_template(
        "teacher/view_class.html",
        class_obj=class_obj,
        enrolled_students=enrolled_students
    )


# ================================
# ✅ CREATE CHAPTER
# ================================
@teacher_bp.route("/class/<int:class_id>/create_chapter", methods=["GET", "POST"])
@login_required
def create_chapter(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    if request.method == "POST":
        chapter_name = request.form.get("name", "").strip()
        if not chapter_name:
            flash("Chapter name cannot be empty!", "danger")
            return redirect(url_for("teacher.create_chapter", class_id=class_id))

        new_chapter = Chapter(name=chapter_name, class_id=class_id)
        db.session.add(new_chapter)
        db.session.commit()
        flash("✅ Chapter created!", "success")
        return redirect(url_for("teacher.view_class", class_id=class_id))

    return render_template("teacher/create_chapter.html", class_obj=class_obj)


# ================================
# ✅ CREATE TEST
# ================================
@teacher_bp.route("/chapter/<int:chapter_id>/create_test", methods=["GET", "POST"])
@login_required
def create_test(chapter_id):
    chapter_obj = Chapter.query.get_or_404(chapter_id)
    class_obj = Class.query.get(chapter_obj.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    if request.method == "POST":
        test_name = request.form.get("name", "").strip()
        max_score = int(request.form.get("max_score") or 100)
        start_time_str = request.form.get("start_time", "").strip()
        end_time_str = request.form.get("end_time", "").strip()
        duration_minutes = int(request.form.get("duration_minutes") or 30)  # ✅ Dynamic duration

        if not test_name:
            flash("Test name cannot be empty!", "danger")
            return redirect(url_for("teacher.create_test", chapter_id=chapter_id))

        start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
        end_time = datetime.fromisoformat(end_time_str) if end_time_str else None

        new_test = Test(
            name=test_name,
            chapter_id=chapter_id,
            max_score=max_score,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes  # ✅ Save dynamic duration
        )
        db.session.add(new_test)
        db.session.commit()
        flash("✅ Test created! Now add questions.", "success")
        return redirect(url_for("teacher.manage_test", test_id=new_test.id))

    return render_template("teacher/create_test.html", chapter_obj=chapter_obj)

# ================================
# ✅ MANAGE TEST
# ================================
@teacher_bp.route("/test/<int:test_id>/manage", methods=["GET", "POST"])
@login_required
def manage_test(test_id):
    test_obj = Test.query.get_or_404(test_id)
    class_obj = Class.query.get(test_obj.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    questions = Question.query.filter_by(test_id=test_id).all()
    current_total_marks = sum(q.marks for q in questions if q.marks)

    if request.method == "POST":
        q_text = request.form.get("question_text", "").strip()
        opt_a = request.form.get("option_a", "").strip()
        opt_b = request.form.get("option_b", "").strip()
        opt_c = request.form.get("option_c", "").strip()
        opt_d = request.form.get("option_d", "").strip()
        correct_opt = request.form.get("correct_option", "").strip()
        marks = int(request.form.get("marks") or 1)

        if not q_text or not correct_opt:
            flash("Question text and correct option are required!", "danger")
            return redirect(url_for("teacher.manage_test", test_id=test_id))

        if test_obj.max_score and current_total_marks + marks > test_obj.max_score:
            flash(f"❌ Cannot add question! Total marks would exceed max score ({test_obj.max_score}).", "danger")
            return redirect(url_for("teacher.manage_test", test_id=test_id))

        new_q = Question(
            test_id=test_id,
            text=q_text,
            option_a=opt_a,
            option_b=opt_b,
            option_c=opt_c,
            option_d=opt_d,
            correct_option=correct_opt,
            marks=marks
        )
        db.session.add(new_q)
        db.session.commit()
        flash("✅ Question added successfully!", "success")
        return redirect(url_for("teacher.manage_test", test_id=test_id))

    return render_template(
        "teacher/manage_test.html",
        test_obj=test_obj,
        questions=questions,
        current_total_marks=current_total_marks
    )


# ================================
# ✅ DELETE & EDIT QUESTIONS & TESTS
# ================================
@teacher_bp.route("/question/<int:question_id>/delete", methods=["POST"])
@login_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    class_obj = Class.query.get(question.test.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("teacher.dashboard"))

    test_id = question.test_id
    db.session.delete(question)
    db.session.commit()
    flash("❌ Question deleted!", "danger")
    return redirect(url_for("teacher.manage_test", test_id=test_id))


@teacher_bp.route("/question/<int:question_id>/edit", methods=["POST"])
@login_required
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    class_obj = Class.query.get(question.test.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("teacher.dashboard"))

    question.text = request.form.get("edit_text", "").strip()
    question.option_a = request.form.get("edit_option_a", "").strip()
    question.option_b = request.form.get("edit_option_b", "").strip()
    question.option_c = request.form.get("edit_option_c", "").strip()
    question.option_d = request.form.get("edit_option_d", "").strip()
    question.correct_option = request.form.get("edit_correct_option", "").strip()
    question.marks = int(request.form.get("edit_marks") or question.marks)

    db.session.commit()
    flash("✅ Question updated!", "success")
    return redirect(url_for("teacher.manage_test", test_id=question.test_id))


@teacher_bp.route("/test/<int:test_id>/delete", methods=["POST"])
@login_required
def delete_test(test_id):
    test = Test.query.get_or_404(test_id)
    class_obj = Class.query.get(test.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("teacher.dashboard"))

    class_id = test.chapter.class_id
    db.session.delete(test)
    db.session.commit()
    flash("✅ Test deleted successfully!", "success")
    return redirect(url_for("teacher.view_class", class_id=class_id))


# ================================
# ✅ STUDENT ANALYTICS
# ================================
@teacher_bp.route("/class/<int:class_id>/students")
@login_required
def class_students(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    students = (
        db.session.query(User)
        .join(StudentClass)
        .filter(StudentClass.class_id == class_id, User.role == "student")
        .all()
    )

    student_analytics = []
    for student in students:
        attempts = (
            db.session.query(TestAttempt)
            .join(Test)
            .join(Chapter)
            .filter(TestAttempt.student_id == student.id, Chapter.class_id == class_id)
            .all()
        )

        total_attempts = len(attempts)
        total_score = sum(a.score for a in attempts if a.score is not None)
        avg_score = round(total_score / total_attempts, 2) if total_attempts else 0

        weak_topics = []
        strong_topics = []

        for attempt in attempts:
            for ans in attempt.answers:
                if ans.question.topic:
                    if ans.is_correct:
                        strong_topics.append(ans.question.topic)
                    else:
                        weak_topics.append(ans.question.topic)

        student_analytics.append({
            "student": student,
            "total_attempts": total_attempts,
            "avg_score": avg_score,
            "weak_topics": list(set(weak_topics)),
            "strong_topics": list(set(strong_topics))
        })

    return render_template(
        "teacher/class_students.html",
        class_obj=class_obj,
        student_analytics=student_analytics
    )


# ================================
# ✅ ANALYTICS HELPERS
# ================================
def get_test_analytics(test_id):
    attempts = TestAttempt.query.filter_by(test_id=test_id).all()
    if not attempts:
        return {"avg": 0, "highest": 0, "lowest": 0, "count": 0}

    scores = [a.score for a in attempts if a.score is not None]
    if not scores:
        return {"avg": 0, "highest": 0, "lowest": 0, "count": len(attempts)}

    avg_score = round(sum(scores) / len(scores), 2)
    return {
        "avg": avg_score,
        "highest": max(scores),
        "lowest": min(scores),
        "count": len(scores)
    }


def get_chapter_analytics(chapter_id):
    tests = Test.query.filter_by(chapter_id=chapter_id).all()
    if not tests:
        return {"avg": 0, "lowest_test": None, "total_tests": 0}

    all_scores = []
    test_scores = {}
    for test in tests:
        t_analytics = get_test_analytics(test.id)
        if t_analytics["count"] > 0 and t_analytics["avg"] > 0:
            all_scores.append(t_analytics["avg"])
            test_scores[test.name] = t_analytics["avg"]

    if not all_scores:
        return {"avg": 0, "lowest_test": None, "total_tests": len(tests)}

    avg_score = round(sum(all_scores) / len(all_scores), 2)
    lowest_test = min(test_scores, key=test_scores.get) if test_scores else None

    return {"avg": avg_score, "lowest_test": lowest_test, "total_tests": len(tests)}
