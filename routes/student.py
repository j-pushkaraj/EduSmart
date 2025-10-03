from flask import Blueprint, render_template, request, redirect, flash, url_for
from flask_login import current_user, login_required
from models import db, Class, StudentClass, Test, Question, TestAttempt, StudentAnswer, AssignmentSubmission

from datetime import datetime, timedelta
from flask import jsonify


student_bp = Blueprint("student", __name__, url_prefix="/student")


# ==============================
# DASHBOARD
# ==============================
@student_bp.route("/dashboard")
@login_required
def dashboard():
    enrolled_classes = (
        db.session.query(Class)
        .join(StudentClass, StudentClass.class_id == Class.id)
        .filter(StudentClass.student_id == current_user.id)
        .all()
    )

    class_tests_status = {}
    now = datetime.now()

    for cls in enrolled_classes:
        class_tests_status[cls.id] = []
        for chapter in cls.chapters:
            for test in chapter.tests:
                attempt = TestAttempt.query.filter_by(
                    student_id=current_user.id, test_id=test.id
                ).first()

                # ✅ Safe test status check
                if test.start_time <= now <= (
                    test.end_time or (test.start_time + timedelta(minutes=(test.duration_minutes or 0)))
                ):
                    status = "Active"
                elif attempt:
                    status = "Attempted"
                else:
                    status = "Unattempted"

                # Scores
                if attempt:
                    correct = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
                    wrong = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
                    total_questions = StudentAnswer.query.filter_by(attempt_id=attempt.id).count()
                    score = attempt.score
                else:
                    correct = wrong = total_questions = score = 0

                class_tests_status[cls.id].append(
                    {
                        "test": test,
                        "status": status,
                        "correct": correct,
                        "wrong": wrong,
                        "total": total_questions,
                        "score": score,
                    }
                )

    return render_template(
        "student/dashboard.html",
        classes=enrolled_classes,
        class_tests_status=class_tests_status,
    )


# ==============================
# JOIN CLASS
# ==============================
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

# ==============================
# CLASS DETAIL ROUTE
# ==============================
@student_bp.route("/class/<int:class_id>")
@login_required
def class_detail(class_id):
    class_obj = Class.query.get_or_404(class_id)

    # Check if enrolled
    is_enrolled = StudentClass.query.filter_by(student_id=current_user.id, class_id=class_id).first()
    if not is_enrolled:
        flash("You are not enrolled in this class", "danger")
        return redirect(url_for("student.dashboard"))

    # Prepare test attempts dictionary
    attempts = {}
    for chapter in class_obj.chapters:
        for test in chapter.tests:
            attempt = TestAttempt.query.filter_by(student_id=current_user.id, test_id=test.id).first()
            if attempt:
                attempts[test.id] = attempt

    # Prepare assignment submissions dictionary
    submissions = {}
    for assignment in class_obj.assignments:
        submission = AssignmentSubmission.query.filter_by(student_id=current_user.id, assignment_id=assignment.id).first()
        if submission:
            submissions[assignment.id] = submission

    return render_template(
        "student/class_detail.html",
        class_obj=class_obj,
        chapters=class_obj.chapters,
        assignments=class_obj.assignments,
        current_time=datetime.now(),
        attempts=attempts,
        submissions=submissions
    )



@student_bp.route("/start_test/<int:test_id>/<int:question_index>", methods=["GET", "POST"])
@login_required
def start_test(test_id, question_index=0):
    test = Test.query.get_or_404(test_id)

    # Check enrollment
    class_id = test.chapter.class_id
    enrolled = StudentClass.query.filter_by(student_id=current_user.id, class_id=class_id).first()
    if not enrolled:
        flash("You are not enrolled in this class", "danger")
        return redirect(url_for("student.dashboard"))

    now = datetime.now()

    # Ensure test is active
    if test.start_time and now < test.start_time:
        flash("⏰ Test has not started yet!", "warning")
        return redirect(url_for("student.dashboard"))
    if test.end_time and now > test.end_time:
        flash("⏰ Test is already over!", "danger")
        return redirect(url_for("student.dashboard"))

    # Retrieve or create attempt
    attempt = TestAttempt.query.filter_by(student_id=current_user.id, test_id=test.id).first()
    if not attempt:
        attempt = TestAttempt(student_id=current_user.id, test_id=test.id, attempted_at=now)
        db.session.add(attempt)
        db.session.commit()

    # Dynamic end_time
    if not attempt.end_time:
        if test.end_time:
            calculated_end = attempt.attempted_at + timedelta(minutes=test.duration_minutes)
            attempt.end_time = min(test.end_time, calculated_end)
        else:
            attempt.end_time = attempt.attempted_at + timedelta(minutes=test.duration_minutes)
        db.session.commit()

    remaining_seconds = int((attempt.end_time - now).total_seconds())
    if remaining_seconds <= 0:
        # Auto-submit
        attempt.correct_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
        attempt.wrong_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
        attempt.total_questions = len(test.questions)
        attempt.score = attempt.correct_answers
        db.session.commit()
        flash("⏰ Time over! Test submitted automatically.", "danger")
        return redirect(url_for("student.dashboard"))

    # Load questions
    questions = test.questions
    total_questions = len(questions)
    if total_questions == 0:
        flash("No questions available for this test!", "info")
        return redirect(url_for("student.class_detail", class_id=class_id))
    if question_index < 0 or question_index >= total_questions:
        return redirect(url_for("student.start_test", test_id=test_id, question_index=0))

    current_question = questions[question_index]

    student_answer = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=current_question.id).first()

    options = {
        "A": current_question.option_a,
        "B": current_question.option_b,
        "C": current_question.option_c,
        "D": current_question.option_d
    }

    # Handle POST
    if request.method == "POST":
        selected_option = request.form.get("selected_option")
        mark_review = "mark" in request.form

        if not student_answer:
            student_answer = StudentAnswer(
                attempt_id=attempt.id,
                question_id=current_question.id,
                selected_option=selected_option if selected_option else None,
                is_correct=(selected_option == current_question.correct_option if selected_option else False),
                marked_for_review=mark_review
            )
            db.session.add(student_answer)
        else:
            if selected_option:
                student_answer.selected_option = selected_option
                student_answer.is_correct = selected_option == current_question.correct_option
            student_answer.marked_for_review = mark_review

        db.session.commit()

        # Navigation
        if "next" in request.form and question_index + 1 < total_questions:
            return redirect(url_for("student.start_test", test_id=test.id, question_index=question_index + 1))
        elif "prev" in request.form and question_index > 0:
            return redirect(url_for("student.start_test", test_id=test.id, question_index=question_index - 1))
        elif "submit" in request.form:
            attempt.correct_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
            attempt.wrong_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
            attempt.total_questions = total_questions
            attempt.score = attempt.correct_answers
            db.session.commit()
            flash("🎉 Test submitted successfully!", "success")
            return redirect(url_for("student.dashboard"))

    # Sidebar question states
    q_states = {}
    for idx, q in enumerate(questions):
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
        if ans and ans.marked_for_review:
            q_states[idx] = "review"
        elif ans and ans.selected_option:
            q_states[idx] = "answered"
        elif ans or idx == question_index:
            q_states[idx] = "visited"
        else:
            q_states[idx] = "not_visited"

    return render_template(
        "student/start_test.html",
        test=test,
        current_question=current_question,
        current_index=question_index,
        total_questions=total_questions,
        student_answer=student_answer,
        q_states=q_states,
        remaining_seconds=remaining_seconds,
        options=options
    )


@student_bp.route("/ajax_save_answer/<int:test_id>/<int:question_index>", methods=["POST"])
@login_required
def ajax_save_answer(test_id, question_index):
    data = request.get_json()
    action = data.get("action")
    selected_option = data.get("selected_option")
    
    test = Test.query.get_or_404(test_id)
    attempt = TestAttempt.query.filter_by(student_id=current_user.id, test_id=test.id).first()
    if not attempt:
        return jsonify({"error": "Attempt not found"}), 404

    questions = test.questions
    if question_index < 0 or question_index >= len(questions):
        return jsonify({"error": "Invalid question index"}), 400

    current_question = questions[question_index]
    
    student_answer = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=current_question.id).first()
    if not student_answer:
        student_answer = StudentAnswer(attempt_id=attempt.id, question_id=current_question.id)
        db.session.add(student_answer)

    # Handle actions
    if action == "mark":
        student_answer.marked_for_review = True
    elif action == "clear":
        student_answer.selected_option = None
        student_answer.is_correct = False
        student_answer.marked_for_review = False
    else:
        if selected_option:
            student_answer.selected_option = selected_option
            student_answer.is_correct = (selected_option == current_question.correct_option)
        if action == "submit":
            # Finalize attempt
            attempt.correct_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
            attempt.wrong_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
            attempt.total_questions = len(questions)
            attempt.score = attempt.correct_answers
            db.session.commit()
            return jsonify({"submit": True})

    db.session.commit()

    # Update q_states
    q_states = {}
    for idx, q in enumerate(questions):
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
        if ans and ans.marked_for_review:
            q_states[idx] = "review"
        elif ans and ans.selected_option:
            q_states[idx] = "answered"
        elif ans or idx == question_index:
            q_states[idx] = "visited"
        else:
            q_states[idx] = "not_visited"

    counts = {
        "answered": list(q_states.values()).count("answered"),
        "review": list(q_states.values()).count("review"),
        "visited": list(q_states.values()).count("visited"),
        "not_visited": list(q_states.values()).count("not_visited")
    }

    # Determine next index
    new_index = question_index
    if action == "next" and question_index + 1 < len(questions):
        new_index += 1
    elif action == "prev" and question_index > 0:
        new_index -= 1

    return jsonify({
        "q_states": q_states,
        "counts": counts,
        "new_index": new_index
    })


# ==============================
# REVIEW TEST (After Attempt)
# ==============================
@student_bp.route("/review_test/<int:attempt_id>")
@login_required
def review_test(attempt_id):
    attempt = TestAttempt.query.filter_by(
        id=attempt_id, student_id=current_user.id
    ).first_or_404()

    test = attempt.test
    answers = (
        StudentAnswer.query.filter_by(attempt_id=attempt.id)
        .join(Question, Question.id == StudentAnswer.question_id)
        .add_entity(Question)
        .all()
    )

    return render_template(
        "student/review_test.html",
        attempt=attempt,
        test=test,
        answers=answers
    )
