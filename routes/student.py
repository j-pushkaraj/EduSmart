# routes/student.py

from flask import Blueprint, render_template, request, redirect, flash, url_for
from flask_login import current_user, login_required
from models import db, Class, StudentClass, Test, Question, TestAttempt
from datetime import datetime
import json

student_bp = Blueprint("student", __name__, url_prefix="/student")


# ================================
# ✅ STUDENT DASHBOARD
# ================================
@student_bp.route("/dashboard")
@login_required
def dashboard():
    enrolled_classes = (
        db.session.query(Class)
        .join(StudentClass, StudentClass.class_id == Class.id)
        .filter(StudentClass.student_id == current_user.id)
        .all()
    )
    return render_template("student/dashboard.html", classes=enrolled_classes)


# ================================
# ✅ JOIN CLASS BY CODE
# ================================
@student_bp.route("/join_class", methods=["POST"])
@login_required
def join_class():
    join_code = request.form.get("join_code", "").strip()
    class_obj = Class.query.filter_by(join_code=join_code).first()

    if not class_obj:
        flash("Invalid join code", "danger")
        return redirect(url_for("student.dashboard"))

    already_joined = StudentClass.query.filter_by(
        student_id=current_user.id, class_id=class_obj.id
    ).first()

    if already_joined:
        flash(f"You are already enrolled in {class_obj.name}", "info")
    else:
        new_enrollment = StudentClass(student_id=current_user.id, class_id=class_obj.id)
        db.session.add(new_enrollment)
        db.session.commit()
        flash(f"Successfully joined {class_obj.name}", "success")

    return redirect(url_for("student.dashboard"))


# ================================
# ✅ CLASS DETAILS VIEW
# ================================
@student_bp.route("/class/<int:class_id>")
@login_required
def class_detail(class_id):
    class_obj = Class.query.get_or_404(class_id)

    is_enrolled = StudentClass.query.filter_by(
        student_id=current_user.id, class_id=class_id
    ).first()
    if not is_enrolled:
        flash("You are not enrolled in this class", "danger")
        return redirect(url_for("student.dashboard"))

    return render_template(
        "student/class_detail.html",
        class_obj=class_obj,
        chapters=class_obj.chapters,
        assignments=class_obj.assignments,
    )


# ================================
# ✅ START TEST FLOW
# ================================
@student_bp.route("/start_test/<int:test_id>/<int:question_index>", methods=["GET", "POST"])
@login_required
def start_test(test_id, question_index=0):
    test = Test.query.get_or_404(test_id)

    # ✅ Time validation
    now = datetime.now()  # Use same timezone as DB
    if test.start_time and now < test.start_time:
        flash("This test has not started yet!", "warning")
        return redirect(url_for("student.class_detail", class_id=test.chapter.class_id))
    if test.end_time and now > test.end_time:
        flash("This test is already closed!", "danger")
        return redirect(url_for("student.class_detail", class_id=test.chapter.class_id))

    questions = test.questions
    total_questions = len(questions)

    if total_questions == 0:
        flash("No questions available for this test!", "info")
        return redirect(url_for("student.class_detail", class_id=test.chapter.class_id))

    # ✅ Ensure index is valid
    if question_index < 0 or question_index >= total_questions:
        flash("Invalid question index", "danger")
        return redirect(url_for("student.start_test", test_id=test_id, question_index=0))

    current_question = questions[question_index]

    # ✅ Build options dynamically
    options_list = []
    for opt in ["option_a", "option_b", "option_c", "option_d"]:
        if hasattr(current_question, opt) and getattr(current_question, opt):
            options_list.append(getattr(current_question, opt))

    # ✅ Handle answer submission
    if request.method == "POST":
        selected_option = request.form.get("selected_option")

        if selected_option:
            # Save or update answer in TestAttempt
            attempt = TestAttempt.query.filter_by(
                student_id=current_user.id, test_id=test_id
            ).first()
            if not attempt:
                attempt = TestAttempt(
                    student_id=current_user.id,
                    test_id=test_id,
                    answers={str(question_index): selected_option},
                    started_at=datetime.now()
                )
                db.session.add(attempt)
            else:
                answers = attempt.answers or {}
                answers[str(question_index)] = selected_option
                attempt.answers = answers

            db.session.commit()

        # Next question
        if question_index + 1 < total_questions:
            return redirect(url_for("student.start_test", test_id=test_id, question_index=question_index + 1))
        else:
            flash("🎉 You finished the test! Submitting your responses...", "success")
            return redirect(url_for("student.dashboard"))

    return render_template(
        "student/start_test.html",
        test=test,
        current_question=current_question,
        current_index=question_index,
        total_questions=total_questions,
        options_list=options_list
    )
